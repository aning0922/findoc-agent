"""在显式 disposable 数据副本上验证真实检索/SQLite 与收入图，无新确认或 LLM。

成功对照后在副本内追加实际 PDF 字节，验证拒绝，再恢复副本文件。
必须传入 --disposable-copy；调用方负责创建副本，不能指向日常 runtime。
"""

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
from pathlib import Path
from typing import cast

from app.agent.revenue_confirmation import RevenueConfirmationService, RevenueSourceReader
from app.agent.revenue_extraction import RevenueCandidateService
from app.agent.revenue_graph import RevenueGraphState, build_revenue_graph
from app.agent.sqlite_financial_facts import SQLiteRevenueConfirmationRepository
from app.api.runtime_factory import (
    DEMO_WORKSPACE_ID,
    RUNTIME_COLLECTION_NAME,
    _runtime_bge_embed,
    _warm_runtime_bge_before_milvus,
)
from app.api.runtime_paths import DEFAULT_RUNTIME_ROOT
from app.documents.local_object_store import LocalObjectStore
from app.documents.preparation import DocumentTaskPreparer
from app.documents.service import DocumentService
from app.documents.sqlite_repository import SQLiteDocumentRepository
from app.rag.retriever import Retriever
from app.rag.store import MilvusSearchStore, get_client


class _NoDispatch:
    """只读研究入口，不派发上传或重处理。"""

    def dispatch(self, document_id: str) -> bool:
        raise RuntimeError("验证不派发文档任务")


def outcome(state: RevenueGraphState) -> dict[str, object]:
    """从图终态抽取安全出口；失败不含旧成功结果。"""
    result = state["result"]
    return {
        "status": state["status"],
        "error_code": state["error_code"],
        "error_kind": state["error_kind"],
        "result": result.to_payload() if result is not None else None,
    }


async def run(args: argparse.Namespace) -> None:
    """组装真实服务，实际 compile/ainvoke，对照成功和必要失败出口后保存新报告。"""
    root: Path = args.runtime_root
    if (
        not args.disposable_copy
        or not root.is_absolute()
        or root.resolve() == DEFAULT_RUNTIME_ROOT.resolve()
        or not (root / "documents.db").is_file()
        or not (root / "milvus.db").exists()
        or not (root / "objects").is_dir()
    ):
        raise ValueError("必须提供已建立的显式 disposable ready 数据副本")
    if args.output.exists():
        raise ValueError("验证报告不得覆盖")
    await asyncio.to_thread(_warm_runtime_bge_before_milvus)
    documents_repository = SQLiteDocumentRepository(root / "documents.db")
    objects = LocalObjectStore(root / "objects")
    documents = DocumentService(
        repository=documents_repository,
        object_store=objects,
        dispatcher=_NoDispatch(),
        workspace_id=DEMO_WORKSPACE_ID,
    )
    client = get_client(str(root / "milvus.db"))
    try:
        client.load_collection(collection_name=RUNTIME_COLLECTION_NAME)
        service = RevenueConfirmationService(
            source_reader=RevenueSourceReader(
                documents=documents,
                objects=objects,
                candidates=RevenueCandidateService(
                    preparer=DocumentTaskPreparer(document_service=documents),
                    retriever=Retriever(
                        _runtime_bge_embed,
                        MilvusSearchStore(client, RUNTIME_COLLECTION_NAME, include_scope_metadata=True),
                    ),
                ),
            ),
            repository=SQLiteRevenueConfirmationRepository(root / "documents.db"),
        )
        direct = await service.calculate(
            document_id=args.document_id, confirmation_id=args.confirmation_id
        )
        graph = build_revenue_graph(service=service)
        success = cast(
            RevenueGraphState,
            await graph.ainvoke(
                {"document_id": args.document_id, "confirmation_id": args.confirmation_id}
            ),
        )
        assert success["status"] == "completed" and success["result"] is not None
        assert success["result"].to_payload() == direct.to_payload()
        missing = cast(
            RevenueGraphState, await graph.ainvoke({"document_id": args.document_id})
        )
        assert missing["status"] == "needs_confirmation" and missing["result"] is None
        unknown = cast(
            RevenueGraphState,
            await graph.ainvoke(
                {"document_id": args.document_id, "confirmation_id": "not-a-confirmation"}
            ),
        )
        assert unknown["status"] == "needs_confirmation" and unknown["result"] is None
        document = await documents.get_document(args.document_id)
        original_bytes = objects.read_bytes(document.object_key)
        try:
            # 仅 disposable 副本的实际文件故障；保留数据库原摘要，不替换业务来源。
            objects.put_bytes(document.object_key, original_bytes + b"\n% graph-source-fault\n")
            changed = cast(
                RevenueGraphState,
                await graph.ainvoke(
                    {"document_id": args.document_id, "confirmation_id": args.confirmation_id}
                ),
            )
            assert changed["status"] == "refused" and changed["error_code"] == "source_changed"
            assert changed["result"] is None
        finally:
            objects.put_bytes(document.object_key, original_bytes)
        assert objects.read_bytes(document.object_key) == original_bytes
        project = Path(__file__).resolve().parents[1]
        source_files = (
            "app/agent/revenue_graph.py",
            "app/agent/revenue_confirmation.py",
            "app/agent/sqlite_financial_facts.py",
            "app/agent/research_workflow.py",
            "app/agent/revenue_extraction.py",
            "app/agent/finance_tools.py",
            "scripts/verify_revenue_graph.py",
        )
        report = {
            "path": "actual-langgraph-real-retriever-existing-confirmation-sqlite",
            "input_kind": "existing explicitly synthetic PDF in disposable copy",
            "versions": {
                name: importlib.metadata.version(name) for name in ("langgraph", "langchain-core")
            },
            "compiled_nodes": list(graph.get_graph().nodes),
            "execution": "actual compile and async ainvoke; no checkpointer/retry/cache",
            "direct_and_graph_full_payload_equal": True,
            "success": outcome(success),
            "missing_confirmation_id": outcome(missing),
            "unknown_confirmation_id": outcome(unknown),
            "actual_source_checksum_fault": outcome(changed),
            "copy_source_restored": True,
            "confirmation_created": False,
            "paid_llm_called": False,
            "source_sha256": {
                name: hashlib.sha256((project / name).read_bytes()).hexdigest() for name in source_files
            },
            "limitations": [
                "fixed 2024/2025 annual revenue syntax and one synthetic document",
                "single local operator; no authentication or approval workflow",
                "not connected to UI or production Agent runtime",
                "no checkpoint, interrupt, recovery, parallel nodes or LLM",
                "source checks at operation boundaries; no concurrent external-file lock",
            ],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        print(json.dumps({"verified": True, "value": direct.to_payload()["value"]}), flush=True)
    finally:
        client.close()


def main() -> None:
    """显式接收副本根、两 ID 和新报告路径；没有 confirm 动作。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--disposable-copy", action="store_true", required=True)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--confirmation-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
