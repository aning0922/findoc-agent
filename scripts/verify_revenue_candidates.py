"""在全新数据根中验证真实上传→解析/BGE/Milvus→Retriever→候选。

复用现有文档 API 和处理组件，不配置/调用 LLM，不读写旧验证库。
报告明确标注 ASGI 进程内 HTTP 边界，不作为浏览器或通用抽取验收。
"""

import argparse
import asyncio
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import httpx

from app.agent.revenue_extraction import RevenueCandidateService
from app.api.app import create_app
from app.api.runtime_factory import (
    RUNTIME_COLLECTION_NAME,
    RUNTIME_DATA_VERSION,
    _build_runtime_indexer,
    _runtime_bge_embed,
    _warm_runtime_bge_before_milvus,
)
from app.documents.fast_pdf_parser import parse_fast_pdf_bytes
from app.documents.in_process_dispatcher import InProcessTaskDispatcher
from app.documents.local_object_store import LocalObjectStore
from app.documents.preparation import DocumentTaskPreparer
from app.documents.processor import DocumentProcessor
from app.documents.service import DocumentService
from app.documents.sqlite_repository import SQLiteDocumentRepository
from app.rag.retriever import Retriever
from app.rag.store import MilvusSearchStore, get_client


async def verify(pdf: Path, root: Path, output: Path) -> None:
    """只接受尚不存在的数据目录和报告，实际上传后保存完整候选证据。"""
    if root.exists() or output.exists():
        raise ValueError("数据目录和报告必须是新路径，保留以前证据")
    content = pdf.read_bytes()
    root.mkdir(parents=True)
    # BGE 首次初始化必须先于 Milvus/gRPC，沿用真实 runtime 的启动顺序。
    await asyncio.to_thread(_warm_runtime_bge_before_milvus)
    repository = SQLiteDocumentRepository(root / "documents.db")
    processor = DocumentProcessor(
        repository=repository,
        object_store=LocalObjectStore(root / "objects"),
        parser=parse_fast_pdf_bytes,
        embedder=_runtime_bge_embed,
        index_document=_build_runtime_indexer(root / "milvus.db", RUNTIME_COLLECTION_NAME),
        data_version=RUNTIME_DATA_VERSION,
    )
    dispatcher = InProcessTaskDispatcher(processor.process)
    documents = DocumentService(
        repository=repository,
        object_store=LocalObjectStore(root / "objects"),
        dispatcher=dispatcher,
        workspace_id="demo",
    )
    app = create_app(documents)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://local-verification",
    ) as http:
        response = await http.post(
            "/documents",
            files={"file": (pdf.name, content, "application/pdf")},
        )
        response.raise_for_status()
        uploaded = response.json()
        print("actual ASGI upload:", response.status_code, uploaded["document_id"], flush=True)
        await asyncio.wait_for(dispatcher.wait_for_idle(), timeout=180)
        document_response = await http.get(f"/documents/{uploaded['document_id']}")
        document_response.raise_for_status()
        document = document_response.json()
        if document["status"] != "ready":
            raise RuntimeError(f"真实上传未 ready: {document}")
        print("document ready; retrieving actual BGE/Milvus hits", flush=True)

    client = get_client(str(root / "milvus.db"))
    try:
        client.load_collection(collection_name=RUNTIME_COLLECTION_NAME)
        retriever = Retriever(
            _runtime_bge_embed,
            MilvusSearchStore(client, RUNTIME_COLLECTION_NAME, include_scope_metadata=True),
        )
        service = RevenueCandidateService(
            preparer=DocumentTaskPreparer(document_service=documents),
            retriever=retriever,
        )
        collected = await service.collect(document_id=uploaded["document_id"])
    finally:
        client.close()

    report = {
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "path": "actual-asgi-upload-real-parser-bge-milvus-retriever-candidates",
        "input_kind": "explicitly-synthetic-pdf",
        "pdf_sha256": hashlib.sha256(content).hexdigest(),
        "upload_status": response.status_code,
        "upload": uploaded,
        "document": document,
        "collection": asdict(collected),
        "paid_llm_called": False,
        "confirmed_or_calculated": False,
        "limitations": [
            "ASGI in-process HTTP; no browser/TCP deployment verification",
            "fixed annual revenue line syntax; no general financial/table extraction",
            "isolated local candidate service; not exposed by Agent runtime tools",
            "no persistent confirmation, invalidation or calculation integration",
        ],
        "source_sha256": {
            name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
            for name in (
                "app/agent/research_workflow.py",
                "app/agent/revenue_extraction.py",
                "scripts/verify_revenue_candidates.py",
                "app/rag/retriever.py",
                "app/rag/store.py",
                "app/api/runtime_factory.py",
            )
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, default=_json_default)
        stream.write("\n")
    print("candidate stage:", collected.state.stage.value, flush=True)
    for candidate in collected.state.candidates:
        print(
            candidate.period,
            str(candidate.value),
            candidate.unit,
            len(candidate.evidence),
            flush=True,
        )
    print("report:", output, flush=True)


def _json_default(value: object) -> str:
    """Decimal 保存十进制字符串，不经 float；其他未知类型拒绝悄悄序列化。"""
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"不支持的报告字段类型: {type(value).__name__}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(verify(args.pdf, args.runtime_root, args.output))


if __name__ == "__main__":
    main()
