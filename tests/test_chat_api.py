from typing import cast

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.chat.service import (
    ChatService,
    DocumentNotReadyError,
    PreparedChat,
)
from app.documents.models import DocumentNotFoundError
from app.documents.service import DocumentService
from app.rag.retriever import SearchFilters, TrustedContext
from app.rag.service import Citation, RAGOutcome, RAGResult


class FakeChatService:
    """返回预设准备结果、异常或RAG终态，并记录API调用。"""

    def __init__(
        self,
        *,
        prepared: PreparedChat | None = None,
        prepare_error: Exception | None = None,
        outcome: RAGOutcome | None = None,
    ) -> None:
        """保存预设行为并初始化prepare和answer调用记录。

        输入：可选PreparedChat、准备阶段异常和RAG领域终态。
        输出：可注入create_app的测试聊天服务。
        失败边界：未配置当前阶段所需结果时抛出AssertionError。
        """
        self._prepared = prepared
        self._prepare_error = prepare_error
        self._outcome = outcome
        self.prepare_calls: list[tuple[str, str]] = []
        self.answer_calls: list[PreparedChat] = []

    async def prepare(
        self,
        *,
        document_id: str,
        query: str,
    ) -> PreparedChat:
        """记录浏览器请求，并返回预设输入或抛出前置异常。"""
        self.prepare_calls.append((document_id, query))

        if self._prepare_error is not None:
            raise self._prepare_error
        if self._prepared is None:
            raise AssertionError("当前测试没有配置PreparedChat")

        return self._prepared

    async def answer(
        self,
        prepared: PreparedChat,
    ) -> RAGOutcome:
        """记录流内问答调用，并返回预设领域终态。"""
        self.answer_calls.append(prepared)

        if self._outcome is None:
            raise AssertionError("HTTP前置失败后不得调用answer")

        return self._outcome


def create_chat_test_client(
    chat_service: FakeChatService,
) -> TestClient:
    """创建只调用聊天路由的测试客户端。

    输入：当前测试所需的FakeChatService。
    输出：注入聊天服务的FastAPI TestClient。
    失败边界：document_service仅为满足应用工厂参数，聊天测试不得调用文档路由。
    """
    unused_document_service = cast(
        DocumentService,
        object(),
    )
    injected_chat_service = cast(
        ChatService,
        chat_service,
    )

    return TestClient(
        create_app(
            unused_document_service,
            chat_service=injected_chat_service,
        )
    )


def test_chat_returns_404_before_stream_when_document_is_missing() -> None:
    """证明不存在文档在建流前返回HTTP 404且不执行answer。"""
    chat_service = FakeChatService(
        prepare_error=DocumentNotFoundError("missing-doc"),
    )

    with create_chat_test_client(chat_service) as client:
        response = client.post(
            "/chat",
            json={
                "document_id": "missing-doc",
                "query": "营业收入是多少？",
            },
        )

        assert response.status_code == 404
        assert response.json() == {
            "detail": "文档不存在",
        }
        assert chat_service.prepare_calls == [
            (
                "missing-doc",
                "营业收入是多少？",
            )
        ]
        assert chat_service.answer_calls == []

        calls_before_invalid_request = len(chat_service.prepare_calls)
        invalid_response = client.post(
            "/chat",
            json={
                "document_id": "missing-doc",
                "query": "营业收入是多少？",
                "workspace_id": "attacker-workspace",
            },
        )

        assert invalid_response.status_code == 422
        assert len(chat_service.prepare_calls) == (calls_before_invalid_request)


def test_chat_returns_409_before_stream_when_document_is_not_ready() -> None:
    """证明未ready文档在建流前返回HTTP 409且不执行answer。"""
    chat_service = FakeChatService(
        prepare_error=DocumentNotReadyError("文档状态不是ready"),
    )

    with create_chat_test_client(chat_service) as client:
        response = client.post(
            "/chat",
            json={
                "document_id": "indexing-doc",
                "query": "营业收入是多少？",
            },
        )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "只有处理成功的文档可以聊天",
    }
    assert chat_service.prepare_calls == [
        (
            "indexing-doc",
            "营业收入是多少？",
        )
    ]
    assert chat_service.answer_calls == []


def test_chat_success_stream_starts_with_status_and_ends_once() -> None:
    """证明ready聊天返回SSE并保持成功事件顺序和唯一done。"""
    prepared = PreparedChat(
        query="营业收入是否增长？",
        context=TrustedContext(workspace_id="WS-A"),
        filters=SearchFilters(document_id="doc-1"),
    )
    outcome = RAGResult(
        content="营业收入增长。[1]",
        citations=(
            Citation(
                number=1,
                source_file="report.pdf",
                page=10,
                chunk_id="chunk-1",
            ),
        ),
    )
    chat_service = FakeChatService(
        prepared=prepared,
        outcome=outcome,
    )

    with create_chat_test_client(chat_service) as client:
        response = client.post(
            "/chat",
            json={
                "document_id": "doc-1",
                "query": "营业收入是否增长？",
            },
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    body = response.text
    status_position = body.index("event: status\n")
    answer_position = body.index("event: final_answer\n")
    citation_position = body.index("event: citation\n")
    done_position = body.index("event: done\n")

    assert status_position < answer_position < citation_position < done_position
    assert body.count("event: done\n") == 1
    assert '"content":"营业收入增长。[1]"' in body
    assert '"number":1' in body
    assert '"source_file":"report.pdf"' in body
    assert '"page":10' in body
    assert '"chunk_id":"chunk-1"' in body

    assert chat_service.prepare_calls == [
        (
            "doc-1",
            "营业收入是否增长？",
        )
    ]
    assert chat_service.answer_calls == [prepared]
