"""运行受控 Agent HTTP 装配；真实业务与 SQLite，重依赖使用确定性替身。"""

from collections.abc import Mapping
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

from fastapi import FastAPI

from app.agent.run_service import AgentRunService
from app.agent.runtime import AgentRuntimeService, RUNTIME_AGENT_CONFIG_VERSION
from app.agent.run_models import RunEvent
from app.agent.sqlite_run_repository import SQLiteAgentRunRepository
from app.agent.tool_loop import Message
from app.api.app import create_app
from app.api.runtime_paths import DEFAULT_RUNTIME_ROOT
from app.documents.local_object_store import LocalObjectStore
from app.documents.models import DocumentRecord, DocumentStatus
from app.documents.preparation import DocumentTaskPreparer
from app.documents.service import DocumentService
from app.documents.sqlite_repository import SQLiteDocumentRepository
from app.rag.openai_compatible_llm import ModelCompletion, ProviderCallError
from app.rag.retriever import Retriever


CONTROLLED_RUNTIME_ROOT_ENV = "FINDOC_CONTROLLED_RUNTIME_ROOT"
CONTROLLED_EVENTS_FAIL_ENV = "FINDOC_CONTROLLED_EVENTS_FAIL"
CONTROLLED_WORKSPACE_ID = "demo"
CONTROLLED_DOCUMENT_ID = "controlled-synthetic-document"
CONTROLLED_SOURCE_FILE = "controlled-synthetic-finance.pdf"


class _RejectingDispatcher:
    """拒绝受控入口中的新上传派发；预置 ready 文档不经过此端口。"""

    def dispatch(self, document_id: str) -> bool:
        """输入任意文档 ID 均返回 False，不创建后台任务或假装完成摄取。"""
        del document_id
        return False


def _controlled_embed(texts: list[str]) -> list[list[float]]:
    """把检索问题映射为最小确定性向量；不加载模型或访问网络。"""
    return [[1.0 if "营业收入" in text else 2.0] for text in texts]


class _ControlledSearchStore:
    """按确定性向量返回一条收入证据或空结果，保留真实 Retriever 校验。"""

    def search(
        self,
        query_vector: list[float],
        *,
        top_k: int,
        filter_expression: str,
    ) -> list[Mapping[str, Any]]:
        """收入向量返回第1页事实；其他向量返回空命中。

        输入仍经过真实 Retriever 构造可信范围表达式。
        输出是待 Retriever 和 Agent 证据会话校验的原始 store 命中。
        边界：本方法不是 Milvus，也不证明 embedding 或检索质量。
        """
        del top_k
        expected_scope = (
            f'workspace_id == "{CONTROLLED_WORKSPACE_ID}" '
            f'and document_id == "{CONTROLLED_DOCUMENT_ID}"'
        )
        if filter_expression != expected_scope:
            raise ValueError("受控检索未收到预期的服务端文档范围")
        if query_vector != [1.0]:
            return []
        return [
            {
                "score": 0.95,
                "chunk_id": "controlled-page-1-revenue",
                "text": "2025年度营业收入：120万元。金额单位：万元。",
                "page": 1,
                "source_file": CONTROLLED_SOURCE_FILE,
                "type": "paragraph",
                "section": "经营摘要：年度营业收入",
                "table_md": None,
                "workspace_id": CONTROLLED_WORKSPACE_ID,
                "document_id": CONTROLLED_DOCUMENT_ID,
            }
        ]


def _tool_call(query: str) -> ModelCompletion:
    """构造一次仍需真实 loop 校验和执行的搜索工具申请。"""
    return ModelCompletion(
        message={
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "controlled-search-1",
                    "type": "function",
                    "function": {
                        "name": "search_finance_docs",
                        "arguments": json.dumps(
                            {"query": query, "top_k": 2}, ensure_ascii=False
                        ),
                    },
                }
            ],
        },
        finish_reason="tool_calls",
    )


class _ControlledModel:
    """按业务任务返回固定候选；不跳过真实工具 loop、验证或结果提交。"""

    def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, object]],
    ) -> ModelCompletion:
        """收入先搜索后回答，年龄先空搜后拒答，净利润触发供应商错误。

        输入是 runtime 维护的完整消息和真实 registry 投影。
        输出仍由真实 loop、SearchEvidenceSession 和持久化合同验证。
        边界：这是无网络 fake provider，只证明受控跨层流程。
        """
        if not tools or tools[0]["function"]["name"] != "search_finance_docs":  # type: ignore[index]
            raise ValueError("受控模型只接受正式搜索工具")
        user_query = next(
            message["content"]
            for message in messages
            if message.get("role") == "user"
        )
        if not isinstance(user_query, str):
            raise ValueError("受控模型未收到字符串任务")
        if "净利润" in user_query:
            raise ProviderCallError(retryable=False)

        has_tool_result = any(message.get("role") == "tool" for message in messages)
        if not has_tool_result:
            metric = "营业收入" if "营业收入" in user_query else "员工平均年龄"
            return _tool_call(metric)
        if "营业收入" in user_query:
            return ModelCompletion(
                message={
                    "role": "assistant",
                    "content": (
                        '{"decision":"answer","content":'
                        '"2025年度营业收入为120万元。[1]"}'
                    ),
                },
                finish_reason="stop",
            )
        return ModelCompletion(
            message={"role": "assistant", "content": '{"decision":"refuse"}'},
            finish_reason="stop",
        )


class _ControlledRunRepository(SQLiteAgentRunRepository):
    """保留真实 SQLite 行为，并可只在 Events 读取处注入一个受控故障。"""

    def __init__(self, database_path: Path, *, fail_events: bool) -> None:
        """保存窄范围故障开关；所有写入和结果 GET 委托真实仓储。"""
        super().__init__(database_path)
        self._fail_events = fail_events

    def list_events(self, *, workspace_id: str, run_id: str) -> list[RunEvent]:
        """开关关闭时真实读库；开启时仅让 Events 形成安全存储错误。"""
        if self._fail_events:
            raise sqlite3.OperationalError("controlled events read failure")
        return super().list_events(workspace_id=workspace_id, run_id=run_id)


def _seed_ready_document(repository: SQLiteDocumentRepository) -> None:
    """向独立 documents.db 幂等写入一条预置 ready 查找记录。"""
    observed_at = datetime(2026, 9, 14, tzinfo=UTC)
    repository.create_or_get(
        DocumentRecord(
            document_id=CONTROLLED_DOCUMENT_ID,
            workspace_id=CONTROLLED_WORKSPACE_ID,
            source_file=CONTROLLED_SOURCE_FILE,
            object_key="documents/controlled-synthetic-finance.pdf",
            content_sha256="c" * 64,
            status=DocumentStatus.READY,
            failed_stage=None,
            error_code=None,
            safe_error_message=None,
            created_at=observed_at,
            updated_at=observed_at,
            attempt=1,
        )
    )


def create_controlled_agent_app(
    runtime_root: Path,
    *,
    fail_events: bool = False,
) -> FastAPI:
    """在显式独立根目录组装受控 HTTP／业务／SQLite 验收应用。

    输入：绝对 runtime 根目录，以及只影响 Events GET 的可选故障开关。
    输出：包含真实文档查询、Agent runtime、结果仓储和 API 的 FastAPI 应用。
    失败：拒绝相对路径和项目默认 runtime，避免误写用户数据。
    边界：embedding、检索 store 和 provider 是确定性替身；不支持真实上传摄取。
    """
    if not runtime_root.is_absolute():
        raise ValueError("受控 runtime 根目录必须是绝对路径")
    resolved_root = runtime_root.resolve()
    if resolved_root == DEFAULT_RUNTIME_ROOT.resolve():
        raise ValueError("受控入口拒绝使用项目默认 runtime")
    resolved_root.mkdir(parents=True, exist_ok=True)

    document_repository = SQLiteDocumentRepository(resolved_root / "documents.db")
    _seed_ready_document(document_repository)
    object_store = LocalObjectStore(resolved_root / "objects")
    # 受控检索不打开 Milvus；保留同名空标记只用于核对隔离目录布局。
    (resolved_root / "milvus.db").touch(exist_ok=True)

    document_service = DocumentService(
        repository=document_repository,
        object_store=object_store,
        dispatcher=_RejectingDispatcher(),
        workspace_id=CONTROLLED_WORKSPACE_ID,
    )
    retriever = Retriever(_controlled_embed, _ControlledSearchStore())
    run_repository = _ControlledRunRepository(
        resolved_root / "agent-runs.db", fail_events=fail_events
    )
    agent_service = AgentRuntimeService(
        document_preparer=DocumentTaskPreparer(document_service=document_service),
        retriever=retriever,
        model=_ControlledModel(),
        run_service=AgentRunService(
            repository=run_repository,
            execution_config_version=RUNTIME_AGENT_CONFIG_VERSION,
        ),
    )
    return create_app(
        document_service,
        agent_service=agent_service,
        agent_workspace_id=CONTROLLED_WORKSPACE_ID,
    )


def create_controlled_agent_app_from_env() -> FastAPI:
    """从必填环境变量读取隔离根目录，供 uvicorn ``--factory`` 启动。

    输入：FINDOC_CONTROLLED_RUNTIME_ROOT 必须是非空绝对路径。
    输出：与直接 factory 相同的受控应用。
    边界：没有默认目录；Events 故障仅在显式值 ``1`` 时开启。
    """
    raw_root = os.environ.get(CONTROLLED_RUNTIME_ROOT_ENV, "").strip()
    if not raw_root:
        raise RuntimeError(f"必须设置 {CONTROLLED_RUNTIME_ROOT_ENV}")
    return create_controlled_agent_app(
        Path(raw_root),
        fail_events=os.environ.get(CONTROLLED_EVENTS_FAIL_ENV) == "1",
    )
