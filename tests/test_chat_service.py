import asyncio
from datetime import datetime, UTC
import threading

import pytest

from app.chat.service import ChatService, DocumentNotReadyError, PreparedChat
from app.documents.models import DocumentNotFoundError, DocumentRecord, DocumentStatus
from app.documents.preparation import DocumentTaskPreparer
from app.rag.retriever import SearchFilters, TrustedContext
from app.rag.service import RAGOutcome, RefusalReason, RefusalResult


class MissingDocumentService:
    """模拟服务端无法找到指定文档的最小文档查询依赖。"""

    async def get_document(self, document_id: str) -> DocumentRecord:
        """接收待查询文档ID，并固定抛出文档不存在异常。"""
        assert document_id == "missing-doc"
        raise DocumentNotFoundError("文档不存在")


class MustNotCallRAG:
    """拒绝任何RAG调用，用于保护建流前的请求检查边界。"""

    def answer(
        self, query: str, *, context: TrustedContext, filters: SearchFilters | None = None
    ) -> RAGOutcome:
        """若prepare阶段错误进入RAG，则立即让测试失败。"""
        raise AssertionError("prepare阶段绝不能进入RAG answerer")


class StaticDocumentService:
    """返回预先注入的服务端文档记录，并保存收到的查找键。"""

    def __init__(
        self,
        record: DocumentRecord,
    ) -> None:
        """保存待返回记录；不访问SQLite或其他外部基础设施。"""
        self._record = record
        self.requested_document_ids: list[str] = []

    async def get_document(
        self,
        document_id: str,
    ) -> DocumentRecord:
        """记录浏览器查找键，并返回服务端保存的DocumentRecord。"""
        self.requested_document_ids.append(document_id)
        return self._record


def make_document_record(status: DocumentStatus) -> DocumentRecord:
    now = datetime(2026, 8, 24, tzinfo=UTC)
    return DocumentRecord(
        document_id="doc-1",
        workspace_id="WS-A",
        source_file="test.pdf",
        object_key="test.pdf",
        content_sha256="a" * 64,
        status=status,
        failed_stage=None,
        error_code=None,
        safe_error_message=None,
        created_at=now,
        updated_at=now,
        attempt=1,
    )


class SpyRAG:
    """返回固定领域终态，并记录同步answer收到的参数和执行线程。"""

    def __init__(self, outcome: RAGOutcome) -> None:
        """保存待返回终态，并初始化调用参数和线程记录。"""
        self._outcome = outcome
        self.calls: list[tuple[str, TrustedContext, SearchFilters | None]] = []
        self.thread_ids: list[int] = []

    def answer(
        self, query: str, *, context: TrustedContext, filters: SearchFilters | None = None
    ) -> RAGOutcome:
        """记录同步RAG输入和当前线程，并返回预设终态。

        输入：问题、可信workspace上下文和服务端过滤条件。
        输出：构造fake时注入的同一个RAGOutcome。
        失败边界：不执行embedding、检索、LLM或SSE映射。
        """
        self.calls.append((query, context, filters))
        self.thread_ids.append(threading.get_ident())
        return self._outcome


def test_prepare_preserves_document_not_found_without_calling_rag() -> None:
    """证明不存在的文档在开始问答前失败且不会调用RAG。

    输入：DocumentService对指定document_id抛出DocumentNotFoundError。
    输出：ChatService保留同一类异常，供API层映射为HTTP 404。
    失败边界：不得构造PreparedChat，也不得调用RAG answerer。
    """

    async def scenario() -> None:
        chat_service = ChatService(
            document_preparer=DocumentTaskPreparer(document_service=MissingDocumentService()),
            rag_service=MustNotCallRAG(),
        )
        with pytest.raises(DocumentNotFoundError):
            await chat_service.prepare(document_id="missing-doc", query="test query")

    asyncio.run(scenario())


def test_prepare_rejects_non_ready_document_without_calling_rag() -> None:
    """证明未ready文档在开始问答前被拒绝且不会调用RAG。

    输入：服务端返回状态为indexing的DocumentRecord。
    输出：ChatService抛出DocumentNotReadyError。
    失败边界：不得进入RAG，也不得把该情况转换成SSE系统错误。
    """

    async def scenario() -> None:
        record = make_document_record(DocumentStatus.INDEXING)
        document_service = StaticDocumentService(record=record)
        chat_service = ChatService(
            document_preparer=DocumentTaskPreparer(document_service=document_service),
            rag_service=MustNotCallRAG(),
        )
        with pytest.raises(DocumentNotReadyError):
            await chat_service.prepare(document_id="server-doc", query="test query")
        assert document_service.requested_document_ids == ["server-doc"]

    asyncio.run(scenario())


def test_prepare_builds_trusted_inputs_from_server_record() -> None:
    """证明可信workspace和文档过滤条件只来自服务端记录。

    输入：ready的服务端记录，以及浏览器提交的查找键和问题。
    输出：PreparedChat使用记录中的workspace_id和document_id。
    失败边界：不得使用浏览器查找键构造过滤器，也不得加入source_file。
    """

    async def scenario() -> None:
        record = make_document_record(DocumentStatus.READY)
        document_service = StaticDocumentService(record)
        chat_service = ChatService(
            document_preparer=DocumentTaskPreparer(document_service=document_service),
            rag_service=MustNotCallRAG(),
        )
        prepared = await chat_service.prepare(
            document_id="browser-lookup",
            query="营业收入是多少？",
        )
        assert prepared.query == "营业收入是多少？"
        assert prepared.context.workspace_id == "WS-A"
        assert prepared.filters is not None
        assert prepared.filters.document_id == "doc-1"
        assert prepared.filters.source_file is None
        assert document_service.requested_document_ids == ["browser-lookup"]

    asyncio.run(scenario())


def test_answer_forwards_prepared_input_and_returns_rag_outcome() -> None:
    """证明answer把已准备输入原样交给RAG并返回领域终态。

    输入：包含query、TrustedContext和SearchFilters的PreparedChat。
    输出：fake RAG收到完全相同的参数，ChatService返回同一个RAGOutcome。
    失败边界：不得修改query、workspace或document_id，也不得映射SSE事件。
    """

    async def scenario() -> None:
        """调用异步answer，并核对同步RAG收到的完整参数。"""
        expected_outcome = RefusalResult(
            reason=RefusalReason.EMPTY_RETRIEVAL,
        )
        rag_service = SpyRAG(expected_outcome)
        chat_service = ChatService(
            document_preparer=DocumentTaskPreparer(
                document_service=StaticDocumentService(make_document_record(DocumentStatus.READY))
            ),
            rag_service=rag_service,
        )
        prepared = PreparedChat(
            query="营业收入是多少？",
            context=TrustedContext(workspace_id="WS-A"),
            filters=SearchFilters(document_id="doc-1"),
        )

        actual = await chat_service.answer(prepared)

        assert actual is expected_outcome
        assert rag_service.calls == [
            (
                "营业收入是多少？",
                TrustedContext(workspace_id="WS-A"),
                SearchFilters(document_id="doc-1"),
            )
        ]

    asyncio.run(scenario())


def test_answer_runs_synchronous_rag_in_worker_thread() -> None:
    """证明同步RAG调用通过工作线程离开事件循环。

    输入：能够记录当前线程身份的fake同步RAG answerer。
    输出：fake RAG执行线程与异步测试所在事件循环线程不同。
    失败边界：若RAG直接在事件循环线程执行，测试失败并暴露阻塞风险。
    """

    async def scenario() -> None:
        """比较事件循环线程和同步RAG实际执行线程。"""
        expected_outcome = RefusalResult(
            reason=RefusalReason.EMPTY_RETRIEVAL,
        )
        rag_service = SpyRAG(expected_outcome)
        chat_service = ChatService(
            document_preparer=DocumentTaskPreparer(
                document_service=StaticDocumentService(make_document_record(DocumentStatus.READY))
            ),
            rag_service=rag_service,
        )
        prepared = PreparedChat(
            query="营业收入是多少？",
            context=TrustedContext(workspace_id="WS-A"),
            filters=SearchFilters(document_id="doc-1"),
        )
        event_loop_thread_id = threading.get_ident()

        actual = await chat_service.answer(prepared)

        assert actual is expected_outcome
        assert len(rag_service.thread_ids) == 1
        assert rag_service.thread_ids[0] != event_loop_thread_id

    asyncio.run(scenario())
