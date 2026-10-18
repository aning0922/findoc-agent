from collections.abc import Iterator
from dataclasses import dataclass
import hashlib
from pathlib import Path
import time
from typing import Any

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.documents.fast_pdf_parser import parse_fast_pdf_bytes
from app.documents.in_process_dispatcher import InProcessTaskDispatcher
from app.documents.local_object_store import LocalObjectStore
from app.documents.models import (
    DocumentRecord,
    DocumentStatus,
    FailureStage,
)
from app.documents.processor import DocumentProcessor
from app.documents.service import DocumentService
from app.documents.sqlite_repository import SQLiteDocumentRepository
from app.rag.ingest import ReplaceResult
from app.rag.parse.models import DocChunk


class _RecordingSQLiteRepository(SQLiteDocumentRepository):
    """使用真实临时SQLite，并记录成功发生的状态迁移。"""

    def __init__(self, database_path: Path) -> None:
        """初始化临时数据库和状态迁移历史。"""
        self.transitions: list[tuple[DocumentStatus, DocumentStatus]] = []
        super().__init__(database_path)

    def transition_status(
        self,
        document_id: str,
        *,
        expected_status: DocumentStatus,
        new_status: DocumentStatus,
        failed_stage: FailureStage | None = None,
        error_code: str | None = None,
        safe_error_message: str | None = None,
    ) -> DocumentRecord:
        """执行真实条件迁移，并只记录实际成功的转换。"""
        record = super().transition_status(
            document_id,
            expected_status=expected_status,
            new_status=new_status,
            failed_stage=failed_stage,
            error_code=error_code,
            safe_error_message=safe_error_message,
        )
        self.transitions.append((expected_status, new_status))
        return record


class _ControllableParser:
    """提供真实PDF smoke以及可控制的解析失败。"""

    def __init__(self) -> None:
        """默认使用确定性假解析，且不主动失败。"""
        self.calls = 0
        self.failures_remaining = 0
        self.use_real_parser = False

    def __call__(
        self,
        content: bytes,
        source_file: str,
    ) -> list[DocChunk]:
        """按测试配置失败、真实解析，或返回一个确定性文本块。"""
        self.calls += 1

        if self.failures_remaining > 0:
            self.failures_remaining -= 1
            raise RuntimeError("/private/internal/parser traceback")

        if self.use_real_parser:
            return parse_fast_pdf_bytes(
                content,
                source_file,
            )

        return [
            DocChunk(
                text="测试文档包含足够长的可索引文本内容。",
                page=1,
                type="paragraph",
                source_file=source_file,
            )
        ]


class _MemoryIndexer:
    """在内存中模拟document级replace并记录调用次数。"""

    def __init__(self) -> None:
        """初始化空的document索引。"""
        self.calls = 0
        self.rows_by_document: dict[
            str,
            list[dict[str, Any]],
        ] = {}

    def __call__(
        self,
        document_id: str,
        rows: list[dict[str, Any]],
    ) -> ReplaceResult:
        """完整替换一个document的rows并返回最终chunk ID。"""
        self.calls += 1
        stored_rows = [dict(row) for row in rows]
        self.rows_by_document[document_id] = stored_rows

        final_ids = frozenset(str(row["chunk_id"]) for row in stored_rows)
        return ReplaceResult(
            inserted=len(stored_rows),
            updated=0,
            skipped=0,
            final_ids=final_ids,
        )


def _fake_embed(
    texts: list[str],
) -> list[list[float]]:
    """返回与输入数量对齐的确定性小向量，不加载真实模型。"""
    return [[1.0, float(index), 0.0] for index, _text in enumerate(texts)]


def _stable_test_chunker(
    blocks: list[DocChunk],
) -> list[DocChunk]:
    """为解析块生成确定性ID，同时保留逻辑source_file。"""
    chunks: list[DocChunk] = []

    for index, block in enumerate(blocks):
        chunk = block.model_copy(deep=True)
        identity = f"{chunk.source_file}\0{chunk.page}\0{chunk.type}\0{chunk.text}\0{index}"
        chunk.chunk_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        chunks.append(chunk)

    return chunks


def _make_text_pdf() -> bytes:
    """自动生成只有一页且带文本层的小型PDF。"""
    document = pymupdf.open()
    try:
        page = document.new_page()
        page.insert_text(
            (72, 100),
            "FinDoc runtime text layer smoke document.",
        )
        return document.tobytes()
    finally:
        document.close()


@dataclass
class _DocumentHarness:
    """保存一次API测试使用的客户端和可观察依赖。"""

    client: TestClient
    repository: _RecordingSQLiteRepository
    parser: _ControllableParser
    indexer: _MemoryIndexer
    dispatcher: InProcessTaskDispatcher
    object_root: Path


@pytest.fixture
def document_harness(
    tmp_path: Path,
) -> Iterator[_DocumentHarness]:
    """在tmp_path中组装真实SQLite、ObjectStore和单进程API。"""
    repository = _RecordingSQLiteRepository(
        tmp_path / "documents.db",
    )
    object_root = tmp_path / "objects"
    object_store = LocalObjectStore(object_root)
    parser = _ControllableParser()
    indexer = _MemoryIndexer()

    processor = DocumentProcessor(
        repository=repository,
        object_store=object_store,
        parser=parser,
        embedder=_fake_embed,
        index_document=indexer,
        chunker=_stable_test_chunker,
        data_version="test-runtime-v1",
    )
    dispatcher = InProcessTaskDispatcher(
        processor.process,
    )
    service = DocumentService(
        repository=repository,
        object_store=object_store,
        dispatcher=dispatcher,
        workspace_id="demo",
    )

    with TestClient(create_app(service)) as client:
        yield _DocumentHarness(
            client=client,
            repository=repository,
            parser=parser,
            indexer=indexer,
            dispatcher=dispatcher,
            object_root=object_root,
        )


def _wait_for_status(
    client: TestClient,
    document_id: str,
    expected_status: DocumentStatus,
    *,
    timeout: float = 3,
) -> dict[str, Any]:
    """轮询文档状态直到命中预期值，超时则报告最后响应。"""
    deadline = time.monotonic() + timeout
    last_payload: dict[str, Any] = {}

    while time.monotonic() < deadline:
        response = client.get(f"/documents/{document_id}")
        assert response.status_code == 200
        last_payload = response.json()

        if last_payload["status"] == expected_status.value:
            return last_payload

        time.sleep(0.01)

    raise AssertionError(
        f"文档状态未在期限内收敛：expected={expected_status.value}, last={last_payload}"
    )


def _wait_for_dispatcher_idle(
    dispatcher: InProcessTaskDispatcher,
    *,
    timeout: float = 3,
) -> None:
    """等待dispatcher释放活动任务引用，超时表示任务没有正确收口。"""
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if dispatcher.active_count == 0:
            return
        time.sleep(0.01)

    raise AssertionError(
        f"dispatcher未在期限内释放活动任务：active_count={dispatcher.active_count}"
    )


def test_text_pdf_reaches_ready_and_exposes_logical_source(
    document_harness: _DocumentHarness,
) -> None:
    """上传带文本层的小PDF后应完成三阶段处理且不暴露物理定位。

    如果失败，说明上传、真实fast parser、状态链、索引最终ID核验、
    list/status可见性或source_file边界至少有一项被破坏。
    """
    document_harness.parser.use_real_parser = True
    pdf_content = _make_text_pdf()

    upload_response = document_harness.client.post(
        "/documents",
        files={
            "file": (
                "report.pdf",
                pdf_content,
                "application/pdf",
            )
        },
    )

    assert upload_response.status_code == 202
    upload_payload = upload_response.json()
    assert upload_payload["status"] == "queued"
    assert upload_payload["duplicate"] is False

    document_id = upload_payload["document_id"]
    ready_payload = _wait_for_status(
        document_harness.client,
        document_id,
        DocumentStatus.READY,
    )

    assert ready_payload["source_file"] == "report.pdf"
    assert "object_key" not in ready_payload
    assert "workspace_id" not in ready_payload
    assert "content_sha256" not in ready_payload

    list_response = document_harness.client.get("/documents")
    assert list_response.status_code == 200
    assert list_response.json() == [ready_payload]

    assert document_harness.repository.transitions == [
        (DocumentStatus.QUEUED, DocumentStatus.PARSING),
        (DocumentStatus.PARSING, DocumentStatus.INDEXING),
        (DocumentStatus.INDEXING, DocumentStatus.READY),
    ]

    indexed_rows = document_harness.indexer.rows_by_document[document_id]
    assert indexed_rows
    assert all(row["source_file"] == "report.pdf" for row in indexed_rows)
    assert all(not Path(str(row["source_file"])).is_absolute() for row in indexed_rows)
    assert all("object_key" not in row for row in indexed_rows)

    object_files = [path for path in document_harness.object_root.rglob("*") if path.is_file()]
    assert len(object_files) == 1


def test_invalid_file_is_rejected_before_queue(
    document_harness: _DocumentHarness,
) -> None:
    """缺少PDF magic的内容应在建档、写对象和派发前返回415。

    如果失败，说明非法输入可能留下SQLite记录、对象文件、后台任务
    或索引污染。
    """
    response = document_harness.client.post(
        "/documents",
        files={
            "file": (
                "broken.pdf",
                b"this is not a pdf",
                "application/pdf",
            )
        },
    )

    assert response.status_code == 415
    assert response.json() == {"detail": "文件缺少合法的 PDF 标识"}

    list_response = document_harness.client.get("/documents")
    assert list_response.status_code == 200
    assert list_response.json() == []

    assert document_harness.repository.list_by_workspace("demo") == []
    assert document_harness.repository.transitions == []
    assert document_harness.parser.calls == 0
    assert document_harness.indexer.calls == 0
    assert document_harness.dispatcher.active_count == 0

    object_files = [path for path in document_harness.object_root.rglob("*") if path.is_file()]
    assert object_files == []


def test_duplicate_upload_reuses_document_without_reindexing(
    document_harness: _DocumentHarness,
) -> None:
    """相同workspace和bytes重复上传应复用原记录且只处理一次。

    如果失败，说明判重可能创建第二条记录、第二个对象、第二次任务
    或重复索引行。
    """
    pdf_content = b"%PDF-1.7\ncontrolled duplicate upload content"

    first_response = document_harness.client.post(
        "/documents",
        files={
            "file": (
                "first.pdf",
                pdf_content,
                "application/pdf",
            )
        },
    )
    assert first_response.status_code == 202
    first_payload = first_response.json()
    assert first_payload["duplicate"] is False

    document_id = first_payload["document_id"]
    _wait_for_status(
        document_harness.client,
        document_id,
        DocumentStatus.READY,
    )
    _wait_for_dispatcher_idle(document_harness.dispatcher)

    second_response = document_harness.client.post(
        "/documents",
        files={
            "file": (
                "renamed.pdf",
                pdf_content,
                "application/pdf",
            )
        },
    )

    assert second_response.status_code == 202
    second_payload = second_response.json()
    assert second_payload["duplicate"] is True
    assert second_payload["document_id"] == document_id

    # 内容身份命中后返回已有逻辑文档，不偷偷改名或建立版本。
    assert second_payload["source_file"] == "first.pdf"
    assert second_payload["status"] == "ready"

    records = document_harness.repository.list_by_workspace("demo")
    assert len(records) == 1
    assert records[0].document_id == document_id

    assert document_harness.parser.calls == 1
    assert document_harness.indexer.calls == 1
    assert document_harness.dispatcher.active_count == 0
    assert len(document_harness.indexer.rows_by_document[document_id]) == 1

    object_files = [path for path in document_harness.object_root.rglob("*") if path.is_file()]
    assert len(object_files) == 1


def test_parse_failure_can_be_retried_only_once(
    document_harness: _DocumentHarness,
) -> None:
    """首次解析失败应安全可见；快速双击retry只能派发一次。

    如果失败，说明failed错误合同、failed→queued条件迁移、重复retry
    防护或完整重跑收敛合同被破坏。
    """
    document_harness.parser.failures_remaining = 1
    pdf_content = b"%PDF-1.7\ncontrolled parser retry content"

    upload_response = document_harness.client.post(
        "/documents",
        files={
            "file": (
                "retry.pdf",
                pdf_content,
                "application/pdf",
            )
        },
    )
    assert upload_response.status_code == 202
    document_id = upload_response.json()["document_id"]

    failed_payload = _wait_for_status(
        document_harness.client,
        document_id,
        DocumentStatus.FAILED,
    )

    assert failed_payload["failed_stage"] == "parsing"
    assert failed_payload["error_code"] == "PDF_PARSE_FAILED"
    assert failed_payload["safe_error_message"] == "无法解析该PDF的文本内容"
    assert "/private/" not in str(failed_payload)
    assert "traceback" not in str(failed_payload)
    assert document_harness.indexer.calls == 0

    # failed写入SQLite与旧Task完成清理之间可能有极短窗口。
    # 先确认旧尝试已经收口，再模拟用户快速双击retry。
    _wait_for_dispatcher_idle(document_harness.dispatcher)

    first_retry = document_harness.client.post(f"/documents/{document_id}/retry")
    second_retry = document_harness.client.post(f"/documents/{document_id}/retry")

    assert first_retry.status_code == 202
    assert first_retry.json()["status"] == "queued"
    assert second_retry.status_code == 409
    assert second_retry.json() == {"detail": "只有处理失败的文档可以重试"}

    ready_payload = _wait_for_status(
        document_harness.client,
        document_id,
        DocumentStatus.READY,
    )
    _wait_for_dispatcher_idle(document_harness.dispatcher)

    assert ready_payload["failed_stage"] is None
    assert ready_payload["error_code"] is None
    assert ready_payload["safe_error_message"] is None

    stored_record = document_harness.repository.get(document_id)
    assert stored_record is not None
    assert stored_record.status is DocumentStatus.READY
    assert stored_record.attempt == 2

    # 两次parser调用分别是首次失败和唯一一次重试；
    # 第二次快速retry没有创建第三次处理。
    assert document_harness.parser.calls == 2
    assert document_harness.indexer.calls == 1
    assert document_harness.dispatcher.active_count == 0

    assert document_harness.repository.transitions == [
        (DocumentStatus.QUEUED, DocumentStatus.PARSING),
        (DocumentStatus.PARSING, DocumentStatus.FAILED),
        (DocumentStatus.FAILED, DocumentStatus.QUEUED),
        (DocumentStatus.QUEUED, DocumentStatus.PARSING),
        (DocumentStatus.PARSING, DocumentStatus.INDEXING),
        (DocumentStatus.INDEXING, DocumentStatus.READY),
    ]
