"""对既有隔离 ready 文档进行本地收入核对/确认或重开计算，无 LLM。

confirm 必须在交互终端展示全部快照，再输入 CONFIRM <快照摘要>。
没有 --yes、默认确认或测试模拟开关。calculate 不确认，只重新查证并读库。
"""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from app.agent.revenue_confirmation import (
    RevenueConfirmationError,
    RevenueConfirmationService,
    RevenueSourceReader,
)
from app.agent.revenue_extraction import RevenueCandidateService
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


class _NoProcessingDispatcher:
    """CLI 仅使用文档服务的归属查询，不派发上传或重处理任务。"""

    def dispatch(self, document_id: str) -> bool:
        raise RuntimeError("本地事实核对入口不派发文档任务")


def _write_report(output: Path | None, payload: dict[str, Any]) -> None:
    """打印结果并可选保存新报告；拒绝覆盖旧证据。"""
    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")


async def run(args: argparse.Namespace) -> None:
    """显式隔离根组装真实检索，再执行只预览、人工确认或只读计算中的一项。"""
    root: Path = args.runtime_root
    if (
        not root.is_absolute()
        or root.resolve() == DEFAULT_RUNTIME_ROOT.resolve()
        or not (root / "documents.db").is_file()
        # 当前 Milvus Lite 版本将此路径作为目录，不能按扩展名假定它是文件。
        or not (root / "milvus.db").exists()
        or not (root / "objects").is_dir()
    ):
        raise RevenueConfirmationError("isolated_ready_runtime_required")
    if args.output is not None and args.output.exists():
        raise RevenueConfirmationError("output_already_exists")
    if args.action == "confirm" and not sys.stdin.isatty():
        raise RevenueConfirmationError("interactive_confirmation_required")
    await asyncio.to_thread(_warm_runtime_bge_before_milvus)
    documents_repository = SQLiteDocumentRepository(root / "documents.db")
    objects = LocalObjectStore(root / "objects")
    documents = DocumentService(
        repository=documents_repository,
        object_store=objects,
        dispatcher=_NoProcessingDispatcher(),
        workspace_id=DEMO_WORKSPACE_ID,
    )
    client = get_client(str(root / "milvus.db"))
    try:
        client.load_collection(collection_name=RUNTIME_COLLECTION_NAME)
        candidates = RevenueCandidateService(
            preparer=DocumentTaskPreparer(document_service=documents),
            retriever=Retriever(
                _runtime_bge_embed,
                MilvusSearchStore(client, RUNTIME_COLLECTION_NAME, include_scope_metadata=True),
            ),
        )
        service = RevenueConfirmationService(
            source_reader=RevenueSourceReader(
                documents=documents, objects=objects, candidates=candidates
            ),
            repository=SQLiteRevenueConfirmationRepository(root / "documents.db"),
        )
        if args.action in ("preview", "confirm"):
            review = await service.preview(document_id=args.document_id)
            preview = {
                "status": "awaiting_confirmation",
                "snapshot_id": review.snapshot_id,
                "review": review.to_payload(),
                "result": None,
            }
            if args.action == "preview":
                _write_report(args.output, preview)
                return
            print(json.dumps(preview, ensure_ascii=False, indent=2), flush=True)
            expected = f"CONFIRM {review.snapshot_id}"
            print("请核对期间、规范金额/单位及每处原文证据。", flush=True)
            action = input(f"明确接受整组候选请输入：{expected}\n> ")
            if action.strip() != expected:
                raise RevenueConfirmationError("confirmation_required")
            try:
                confirmation = await service.confirm(
                    document_id=args.document_id,
                    reviewed_snapshot_id=review.snapshot_id,
                    accepted=True,
                    confirmation_kind="local_operator",
                )
            except RevenueConfirmationError as exc:
                if exc.code == "review_changed":
                    # 旧动作不能接受新内容：展示新快照后退出，下一次需重新主动确认。
                    changed = await service.preview(document_id=args.document_id)
                    print(
                        json.dumps(
                            {
                                "status": "review_changed",
                                "snapshot_id": changed.snapshot_id,
                                "review": changed.to_payload(),
                                "result": None,
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        flush=True,
                    )
                    print(
                        "本次确认未保存；请重新运行确认入口，核对新快照后再明确接受。", flush=True
                    )
                raise
            _write_report(
                args.output,
                {
                    "status": "confirmed",
                    "confirmation_id": confirmation.confirmation_id,
                    "confirmed_at": confirmation.confirmed_at.isoformat(),
                    "confirmation_kind": confirmation.confirmation_kind,
                    "snapshot_id": confirmation.review.snapshot_id,
                    "review": confirmation.review.to_payload(),
                    "result": None,
                    "paid_llm_called": False,
                },
            )
        else:
            calculation = await service.calculate(
                document_id=args.document_id, confirmation_id=args.confirmation_id
            )
            source_files = (
                "app/agent/revenue_confirmation.py",
                "app/agent/sqlite_financial_facts.py",
                "app/agent/research_workflow.py",
                "app/agent/finance_tools.py",
                "app/agent/revenue_extraction.py",
                "scripts/revenue_review.py",
            )
            project_root = Path(__file__).resolve().parents[1]
            _write_report(
                args.output,
                {
                    "status": "completed",
                    "result": calculation.to_payload(),
                    "path": "real-ready-source-explicit-confirmation-sqlite-reopen-calculation",
                    "read_mode": "new-cli-process",
                    "paid_llm_called": False,
                    "source_sha256": {
                        name: hashlib.sha256((project_root / name).read_bytes()).hexdigest()
                        for name in source_files
                    },
                    "limitations": [
                        "synthetic PDF and fixed annual revenue line syntax",
                        "single local operator; no authentication or approval workflow",
                        "not registered in production Agent runtime",
                        "source checks at operation boundaries; no concurrent external-file lock",
                    ],
                },
            )
    finally:
        client.close()


def main() -> None:
    """要求显式动作与数据根；没有非交互确认或自动使用旧结果的路径。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preview", "confirm", "calculate"))
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--confirmation-id")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.action == "calculate" and not args.confirmation_id:
        parser.error("calculate 必须指定 --confirmation-id")
    try:
        asyncio.run(run(args))
    except (Exception, KeyboardInterrupt) as exc:
        code = exc.code if isinstance(exc, RevenueConfirmationError) else "local_operation_failed"
        print(json.dumps({"status": "rejected", "code": code, "result": None}), flush=True)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
