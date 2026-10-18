import asyncio
from unittest.mock import Mock

import pytest

from app.documents.models import DocumentStateConflictError, DocumentStatus
from app.documents.ports import DocumentRepository, ObjectStore, TaskDispatcher
from app.documents.service import DocumentService


def test_retry_does_not_dispatch_when_state_transition_is_rejected() -> None:
    """给定 failed→queued 条件迁移失败，retry 应报告冲突且不派发任务。
    如果测试失败，说明重复 retry 可能在未取得状态迁移资格时创建额外后台任务。
    """
    repository = Mock(spec=DocumentRepository)
    repository.get.return_value = Mock(workspace_id="demo")
    object_store = Mock(spec=ObjectStore)
    dispatcher = Mock(spec=TaskDispatcher)

    repository.transition_status.side_effect = DocumentStateConflictError("文档当前状态不是 failed")

    service = DocumentService(
        repository=repository, object_store=object_store, dispatcher=dispatcher, workspace_id="demo"
    )

    with pytest.raises(DocumentStateConflictError):
        asyncio.run(service.retry_document("doc-1"))

    repository.transition_status.assert_called_once_with(
        "doc-1",
        expected_status=DocumentStatus.FAILED,
        new_status=DocumentStatus.QUEUED,
    )
    dispatcher.dispatch.assert_not_called()
