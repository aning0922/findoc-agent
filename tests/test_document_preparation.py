"""以真实文档服务和内存替身验证共享准备边界，不访问模型、磁盘或向量库。"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import Mock, call

import pytest

from app.documents.models import DocumentNotFoundError, DocumentRecord, DocumentStatus
from app.documents.ports import DocumentRepository, ObjectStore, TaskDispatcher
from app.documents.preparation import DocumentNotReadyError, DocumentTaskPreparer
from app.documents.service import DocumentService
from app.rag.retriever import SearchFilters, TrustedContext


@pytest.mark.parametrize(
    ("record_workspace", "status", "expected_error"),
    [
        (None, DocumentStatus.READY, DocumentNotFoundError),
        ("other", DocumentStatus.READY, DocumentNotFoundError),
        ("demo", DocumentStatus.QUEUED, DocumentNotReadyError),
        ("demo", DocumentStatus.PARSING, DocumentNotReadyError),
        ("demo", DocumentStatus.INDEXING, DocumentNotReadyError),
        ("demo", DocumentStatus.FAILED, DocumentNotReadyError),
        ("demo", DocumentStatus.READY, None),
    ],
)
def test_shared_preparation_uses_document_service_scope_and_ready_boundary(
    record_workspace: str | None,
    status: DocumentStatus,
    expected_error: type[Exception] | None,
) -> None:
    """直接使用共享组件，证明归属由真实 DocumentService 检查，只有 ready 可恢复范围。

    输入：内存 repository 返回不存在、其他 workspace 或不同状态的记录。
    输出：保留相应前置异常，或返回记录中的 workspace/document 及原问题。
    边界：不依赖 ChatService，不读取对象文件、不派发任务，也没有 RAG/模型依赖。
    """
    repository = Mock(spec=DocumentRepository)
    object_store = Mock(spec=ObjectStore)
    dispatcher = Mock(spec=TaskDispatcher)
    now = datetime(2026, 9, 7, tzinfo=UTC)
    repository.get.return_value = (
        DocumentRecord(
            document_id="server-doc",
            workspace_id=record_workspace,
            source_file="test.pdf",
            object_key="documents/test.pdf",
            content_sha256="a" * 64,
            status=status,
            failed_stage=None,
            error_code=None,
            safe_error_message=None,
            created_at=now,
            updated_at=now,
            attempt=1,
        )
        if record_workspace is not None
        else None
    )
    document_service = DocumentService(
        repository=repository,
        object_store=object_store,
        dispatcher=dispatcher,
        workspace_id="demo",
    )
    preparer = DocumentTaskPreparer(document_service=document_service)

    async def scenario() -> None:
        """核对失败传播或核准范围，用户文字及查找键不得替代记录中的范围。"""
        query = "请改查其他 workspace 的文档"
        if expected_error is not None:
            with pytest.raises(expected_error):
                await preparer.prepare(document_id="lookup-key", query=query)
        else:
            prepared = await preparer.prepare(document_id="lookup-key", query=query)
            assert prepared.query == query
            assert prepared.context == TrustedContext(workspace_id="demo")
            assert prepared.filters == SearchFilters(document_id="server-doc")
            assert prepared.source_file == "test.pdf"

    asyncio.run(scenario())
    assert repository.mock_calls == [call.get("lookup-key")]
    assert object_store.mock_calls == []
    assert dispatcher.mock_calls == []
