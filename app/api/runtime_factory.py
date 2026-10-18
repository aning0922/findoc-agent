"""无导入副作用地组装真实 runtime 应用；调用者必须决定数据根目录。"""

from collections.abc import Callable
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pymilvus import MilvusClient

from app.agent.run_service import AgentRunService
from app.agent.revenue_confirmation import RevenueConfirmationService, RevenueSourceReader
from app.agent.revenue_extraction import RevenueCandidateService
from app.agent.sqlite_financial_facts import SQLiteRevenueConfirmationRepository
from app.agent.runtime import AgentRuntimeService, RUNTIME_AGENT_CONFIG_VERSION
from app.agent.sqlite_run_repository import SQLiteAgentRunRepository
from app.api.app import create_app
from app.research.templates import TemplateService
from app.research.task_repository import TaskRepository
from app.agent.operating_research_graph import PersistentTemplateService
from app.api.research_tasks import create_task_router
from app.api.report_drafts import create_report_router
from app.reports.service import ReportService
from app.api.research_templates import create_template_router
from app.api.research_runs import create_research_runs_router
from app.research.repository import ResearchOwner, ResearchRepository
from app.api.research_qa import create_research_qa_router
from app.api.runtime_paths import DEFAULT_RUNTIME_ROOT
from app.chat.service import ChatService
from app.companies.service import CompanyService
from app.companies.sqlite_repository import SQLiteCompanyRepository
from app.documents.fast_pdf_parser import parse_fast_pdf_bytes
from app.documents.in_process_dispatcher import InProcessTaskDispatcher
from app.documents.local_object_store import LocalObjectStore
from app.documents.preparation import DocumentTaskPreparer
from app.documents.processor import DocumentProcessor
from app.documents.source_repository import SQLiteSourceRepository, revision_id
from app.documents.source_service import DocumentSourceService, PARSER_VERSION
from app.documents.service import DocumentService
from app.documents.sqlite_repository import SQLiteDocumentRepository
from app.rag.evidence_gate import ConservativeScoreEvidenceGate
from app.rag.ingest import ReplaceResult
from app.rag.publications import IndexPublications
from app.rag.openai_compatible_llm import OpenAICompatibleLLMClient
from app.rag.retriever import Retriever
from app.rag.selected_scope import SelectedScopeSearch
from app.rag.service import RAGService
from app.rag.store import MilvusSearchStore, ensure_document_collection, get_client


RUNTIME_COLLECTION_NAME = "findoc_runtime_documents_v1"
DEMO_WORKSPACE_ID = "demo"
RUNTIME_DATA_VERSION = "runtime-v1"

RUNTIME_MIN_TOP_SCORE = 0.55
RUNTIME_MAX_EVIDENCE_CHARS = 4000
ISOLATED_RUNTIME_ROOT_ENV = "FINDOC_RUNTIME_ROOT"


@dataclass(frozen=True)
class RuntimeRAGResources:
    """保存 runtime 可信 RAG、共享 Retriever 及其长生命周期 Milvus 连接。

    输入：已完成依赖组装的RAGService和仍处于打开状态的MilvusClient。
    输出：供应用注入聊天服务，并在应用关闭时释放Milvus连接。
    失败边界：本对象不负责自动关闭；create_runtime_app必须注册关闭处理。
    """

    rag_service: RAGService
    """现有聊天使用的可信 RAG 服务。"""
    retriever: Retriever
    """与 RAG 使用同一实例的检索器，供 Agent 与收入候选复用。"""
    milvus_client: MilvusClient
    """由应用关闭处理释放的同一个检索连接。"""


def _runtime_bge_embed(texts: list[str]) -> list[list[float]]:
    """使用runtime共享的真实BGE模型生成1024维稠密向量。

    输入：待编码文本列表。
    输出：与输入顺序和数量一致的1024维向量列表。
    失败：模型加载或向量计算异常原样传播，由调用层转换安全终态。
    边界：模型模块在首次调用时加载，后续上传和查询在同一进程复用。
    """
    from app.rag.embed import embed

    return embed(texts)


def _warm_runtime_bge_before_milvus() -> None:
    """在创建任何Milvus/gRPC客户端之前完成BGE首次初始化。

    输入：无，使用不进入任何索引的固定短文本。
    输出：无，只验证真实模型能够生成一次向量。
    失败：模型加载或编码失败时阻止应用启动，避免运行时半初始化。
    边界：预热向量不会写入runtime或冻结collection。
    """
    _runtime_bge_embed(["runtime embedding startup check"])


def _build_runtime_indexer(
    database_path: Path,
    collection_name: str,
) -> Callable[[str, list[dict[str, Any]]], ReplaceResult]:
    """建立只写入runtime Milvus数据库和collection的索引函数。

    Args:
        database_path: 独立于冻结数据的runtime Milvus Lite路径。
        collection_name: runtime上传文档专用collection名称。

    Returns:
        可注入DocumentProcessor的document级replace函数。
    """

    def index_document(
        document_id: str,
        rows: list[dict[str, Any]],
    ) -> ReplaceResult:
        """按document_id替换runtime索引，并返回最终ID核验结果。"""
        client = get_client(str(database_path))
        try:
            publications = IndexPublications(
                SQLiteCompanyRepository(database_path.parent / "documents.db"), client
            )
            result = publications.publish(document_id, rows)
            publications.cleanup()
            return result
        finally:
            client.close()

    return index_document


def _build_runtime_rag_resources(
    database_path: Path,
    collection_name: str,
    llm_client: OpenAICompatibleLLMClient,
) -> RuntimeRAGResources:
    """组装只查询runtime collection的可信RAG及Milvus资源。

    输入：runtime Milvus Lite路径、上传文档专用collection名称和已验证的LLM客户端。
    输出：包含RAGService和打开状态MilvusClient的资源对象。
    失败：Milvus连接或RAG依赖构造失败时关闭client并原样抛出。
    边界：启动时只确保并加载runtime collection，不写入文档数据，
    也不访问冻结collection。
    """
    client = get_client(str(database_path))
    try:
        ensure_document_collection(client, collection_name)
        client.load_collection(collection_name=collection_name)

        publications = IndexPublications(
            SQLiteCompanyRepository(database_path.parent / "documents.db"), client
        )
        publications.recover()
        store = MilvusSearchStore(client, collection_name, include_scope_metadata=True,
                                  publications=publications)
        retriever = Retriever(_runtime_bge_embed, store)
        evidence_gate = ConservativeScoreEvidenceGate(min_top_score=RUNTIME_MIN_TOP_SCORE)
        rag_service = RAGService(
            retriever=retriever,
            llm_client=llm_client,
            evidence_gate=evidence_gate,
            max_evidence_chars=RUNTIME_MAX_EVIDENCE_CHARS,
        )
    except Exception:
        client.close()
        raise

    return RuntimeRAGResources(
        rag_service=rag_service,
        retriever=retriever,
        milvus_client=client,
    )


def create_runtime_app(
    runtime_root: Path = DEFAULT_RUNTIME_ROOT, *, max_selected_documents: int = 4,
) -> FastAPI:
    """组装文档/RAG、Agent 和收入确认服务，复用同一 runtime 检索资源。

    Args:
        runtime_root: SQLite、对象文件和runtime Milvus的内部根目录。

    Returns:
        已绑定固定demo workspace和单进程dispatcher的FastAPI应用。

    Notes:
        SQLite记录可跨重启保存，但dispatcher任务只存在于当前进程内；
        D16索引启动复验；D17遗留研究running收口为interrupted，不续跑。
        导入本模块不会调用本函数，
        隔离运行应显式传入已经核验的独立目录。
    """
    # 必需LLM配置是启动前置条件：配置不完整时不得触碰模型、磁盘或Milvus。
    llm_client = OpenAICompatibleLLMClient.from_env()
    # BGE可能在首次加载时触发子进程初始化，必须先于Milvus/gRPC客户端。
    _warm_runtime_bge_before_milvus()
    repository = SQLiteDocumentRepository(
        runtime_root / "documents.db",
    )
    research_owner = ResearchOwner(repository._database_path.parent)
    try:
        object_store = LocalObjectStore(
            runtime_root / "objects",
        )
        index_document = _build_runtime_indexer(
            runtime_root / "milvus.db",
            RUNTIME_COLLECTION_NAME,
        )

        processor = DocumentProcessor(
            repository=repository,
            object_store=object_store,
            parser=parse_fast_pdf_bytes,
            embedder=_runtime_bge_embed,
            index_document=index_document,
            data_version=RUNTIME_DATA_VERSION,
            source_identity=lambda record: dict(
                source_revision=revision_id(record, PARSER_VERSION),
                content_sha256=record.content_sha256, attempt=record.attempt,
                parser_version=PARSER_VERSION,
            ),
            source_recorder=lambda record, content, blocks: source_service.capture(
                record, content, blocks
            ),
        )
        dispatcher = InProcessTaskDispatcher(
            processor.process,
        )
        document_service = DocumentService(
            repository=repository,
            object_store=object_store,
            dispatcher=dispatcher,
            workspace_id=DEMO_WORKSPACE_ID,
        )
        rag_resources = _build_runtime_rag_resources(
            runtime_root / "milvus.db", RUNTIME_COLLECTION_NAME, llm_client
        )
        try:
            document_preparer = DocumentTaskPreparer(document_service=document_service)
            chat_service = ChatService(
                document_preparer=document_preparer,
                rag_service=rag_resources.rag_service,
            )
            agent_repository = SQLiteAgentRunRepository(runtime_root / "agent-runs.db")
            agent_service = AgentRuntimeService(
                document_preparer=document_preparer,
                retriever=rag_resources.retriever,
                model=llm_client,
                run_service=AgentRunService(
                    repository=agent_repository,
                    execution_config_version=RUNTIME_AGENT_CONFIG_VERSION,
                ),
            )
            revenue_repository = SQLiteRevenueConfirmationRepository(runtime_root / "documents.db")
            registry = SQLiteCompanyRepository(runtime_root / "documents.db")
            company_service = CompanyService(
                registry,
                workspace_id=DEMO_WORKSPACE_ID,
            )
            source_service = DocumentSourceService(
                documents=document_service,
                objects=object_store,
                companies=company_service,
                repository=SQLiteSourceRepository(registry),
            )
            selection_preparer = DocumentTaskPreparer(
                document_service=document_service, sources=source_service,
                workspace_id=DEMO_WORKSPACE_ID, max_selected_documents=max_selected_documents,
            )
            selected_scope_search = SelectedScopeSearch(selection_preparer, rag_resources.retriever)
            candidate_service = RevenueCandidateService(
                preparer=document_preparer,
                retriever=rag_resources.retriever,
                sources=source_service,
            )
            # Dynamic and legacy revenue adapters share one candidate instance and confirmation path.
            revenue_service = RevenueConfirmationService(
                source_reader=RevenueSourceReader(
                    documents=document_service,
                    objects=object_store,
                    candidates=candidate_service,
                    sources=source_service,
                ),
                repository=revenue_repository,
            )
            app = create_app(
                document_service,
                company_service=company_service,
                source_service=source_service,
                max_selected_documents=max_selected_documents,
                candidate_service=candidate_service,
                chat_service=chat_service,
                agent_service=agent_service,
                agent_workspace_id=DEMO_WORKSPACE_ID,
                revenue_service=revenue_service,
                revenue_workspace_id=DEMO_WORKSPACE_ID,
            )
            template_service = TemplateService(
                preparer=selection_preparer, facts=revenue_service, workspace_id=DEMO_WORKSPACE_ID,
                scope=selected_scope_search,
                model=llm_client.for_operating_research(),
            )
            app.include_router(create_template_router(template_service))
            app.state.template_service = template_service
            app.include_router(create_research_qa_router(
                selection_preparer, selected_scope_search, rag_resources.rag_service,
                generate_once=llm_client.generate_once,
            ))
            try:
                research_repository = ResearchRepository(registry, DEMO_WORKSPACE_ID)
                research_repository.recover_interrupted()
                task_repository = TaskRepository(registry, DEMO_WORKSPACE_ID)
                task_repository.recover_interrupted()
                app.include_router(create_task_router(task_repository, PersistentTemplateService(template_service, task_repository)))
                app.state.task_repository = task_repository
                app.include_router(create_report_router(ReportService(task_repository, source_service)))
                app.include_router(create_research_runs_router(
                    research_repository, selection_preparer, selected_scope_search, rag_resources.rag_service,
                    generate_once=llm_client.generate_once,
                    execution_config={"mode": "verified_excerpts", "model": llm_client.model,
                                      "max_retries": 0, "top_k": 12, "evidence_budget": 16000},
                ))
            except Exception:
                research_owner.close()
                raise
            app.add_event_handler("shutdown", research_owner.close)
            app.state.research_repository = research_repository
            app.state.selected_scope_search = selected_scope_search
            app.state.selection_preparer = selection_preparer
            app.state.runtime_rag_resources = rag_resources
            # 内部入口与 HTTP 复用同一运行服务、检索依赖和 Run 仓储。
            app.state.company_service = company_service
            app.state.source_service = source_service
            app.state.candidate_service = candidate_service
            app.state.agent_service = agent_service
            app.state.revenue_service = revenue_service
            app.add_event_handler("shutdown", rag_resources.milvus_client.close)
        except Exception:
            rag_resources.milvus_client.close()
            raise
        return app
    except Exception:
        research_owner.close()
        raise


def create_isolated_runtime_app_from_env() -> FastAPI:
    """从必填环境变量读取独立根目录，供 Uvicorn ``--factory`` 启动。

    输入：FINDOC_RUNTIME_ROOT 必须是非空绝对路径，且不能是项目默认 runtime。
    输出：调用真实 create_runtime_app 得到的 FastAPI 应用。
    失败：目录缺失、为相对路径或指向默认库时在装配前拒绝。
    边界：本入口只选择存储根目录，不修改模型、重试、workspace 或启动顺序。
    """
    raw_root = os.environ.get(ISOLATED_RUNTIME_ROOT_ENV, "").strip()
    if not raw_root:
        raise RuntimeError(f"必须设置 {ISOLATED_RUNTIME_ROOT_ENV}")
    runtime_root = Path(raw_root)
    if not runtime_root.is_absolute():
        raise ValueError("隔离 runtime 根目录必须是绝对路径")
    if runtime_root.resolve() == DEFAULT_RUNTIME_ROOT.resolve():
        raise ValueError("隔离入口拒绝使用项目默认 runtime")
    return create_runtime_app(runtime_root.resolve())
