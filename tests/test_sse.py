import asyncio
import json
from types import MappingProxyType

import pytest

from app.api.sse import SSEEventName, encode_sse_event, map_rag_outcome_to_sse, stream_chat_sse
from app.chat.service import PreparedChat
from app.rag.retriever import SearchFilters, TrustedContext
from app.rag.service import (
    Citation,
    RAGOutcome,
    RAGResult,
    RefusalReason,
    RefusalResult,
    SystemErrorResult,
    SystemErrorType,
)


def test_encode_status_event_as_json_frame() -> None:
    """测试 encode_sse_event 函数是否能正确编码 status 事件"""
    result = encode_sse_event(
        "status",
        {"phase": "answering"},
    )

    assert result == ('event: status\ndata: {"phase":"answering"}\n\n')


@pytest.mark.parametrize(
    "event",
    [
        "status",
        "final_answer",
        "citation",
        "usage",
        "error",
        "done",
    ],
)
def test_encode_all_allowed_sse_event_names(
    event: SSEEventName,
) -> None:
    """证明六种冻结事件名都能编码为正确结束的SSE帧。

    输入：参数化提供的合法事件名。
    输出：事件名进入event行，且完整帧以双换行结束。
    失败边界：任一合法事件被拒绝或产生不完整帧时测试失败。
    """
    result = encode_sse_event(
        event,
        {"message": "test"},
    )

    assert result == f'event: {event}\ndata: {{"message":"test"}}\n\n'


def test_encode_mapping_preserves_chinese_and_escaped_newline() -> None:
    """证明只读Mapping中的中文和字符串换行能安全完成JSON往返。

    输入：包含中文和换行字符的只读Mapping。
    输出：data行保持单行，JSON解码后恢复原始数据。
    失败边界：Mapping无法编码、中文改变或换行破坏SSE framing时测试失败。
    """
    data = MappingProxyType({"message": "你好\n世界"})
    result = encode_sse_event(
        "status",
        data,
    )

    assert result == 'event: status\ndata: {"message":"你好\\n世界"}\n\n'

    decoded = json.loads(result.split("data: ")[1].strip())
    assert decoded == data


def test_reject_event_name_with_line_break() -> None:
    """证明事件名中的换行不能注入额外SSE字段。

    输入：包含换行和伪造data行的非法事件名。
    输出：无SSE帧产生。
    失败边界：必须抛出ValueError，否则事件注入防线失效。
    """
    with pytest.raises(ValueError):
        encode_sse_event(
            'status\ndata: {"injected":true}',  # type: ignore[arg-type]
            {"message": "test"},
        )


def test_reject_non_json_serializable_data() -> None:
    """证明不可JSON序列化的对象不会被静默转换成字符串。

    输入：值为普通object实例的事件数据。
    输出：无SSE帧产生。
    失败边界：必须保留json.dumps抛出的TypeError。
    """
    with pytest.raises(TypeError):
        encode_sse_event(
            "status",
            {"message": object()},
        )


def test_reject_non_finite_number() -> None:
    """证明非标准JSON数值NaN不能进入SSE数据。

    输入：包含NaN的事件数据。
    输出：无SSE帧产生。
    失败边界：必须因严格JSON编码抛出ValueError。
    """
    with pytest.raises(ValueError):
        encode_sse_event(
            "status",
            {"message": float("nan")},
        )


def test_map_rag_result_to_answer_citations_and_done() -> None:
    """证明可信成功按答案、引用和唯一done顺序发布。"""
    outcome = RAGResult(
        content="营业收入增长。[1] 净利润改善。[2]",
        citations=(
            Citation(
                number=1,
                source_file="report.pdf",
                page=10,
                chunk_id="chunk-1",
            ),
            Citation(
                number=2,
                source_file="report.pdf",
                page=12,
                chunk_id="chunk-2",
            ),
        ),
    )
    frames = map_rag_outcome_to_sse(outcome)
    assert frames == (
        'event: final_answer\ndata: {"content":"营业收入增长。[1] 净利润改善。[2]"}\n\n',
        'event: citation\ndata: {"number":1,"source_file":"report.pdf","page":10,"chunk_id":"chunk-1"}\n\n',
        'event: citation\ndata: {"number":2,"source_file":"report.pdf","page":12,"chunk_id":"chunk-2"}\n\n',
        'event: done\ndata: {"outcome":"success"}\n\n',
    )


def test_map_refusal_to_status_and_done_without_answer() -> None:
    """证明正常拒答只发布拒答状态和done。"""
    outcome = RefusalResult(
        reason=RefusalReason.EMPTY_RETRIEVAL,
    )
    frames = map_rag_outcome_to_sse(outcome)
    assert frames == (
        'event: status\ndata: {"phase":"refused","reason":"empty_retrieval"}\n\n',
        'event: done\ndata: {"outcome":"refusal"}\n\n',
    )


def test_map_system_error_omits_raw_error() -> None:
    """证明系统失败只发布安全错误字段且不泄露raw_error。"""
    outcome = SystemErrorResult(
        error_type=SystemErrorType.CITATION_VALIDATION_ERROR,
        message="服务器内部错误",
        raw_error="provider-secret-token",
    )
    frames = map_rag_outcome_to_sse(outcome)
    assert frames == (
        'event: error\ndata: {"code":"citation_validation_error","message":"服务器内部错误"}\n\n',
        'event: done\ndata: {"outcome":"error"}\n\n',
    )
    assert "provider-secret-token" not in "".join(frames)


class StaticPreparedChatAnswerer:
    """异步返回固定RAG终态，并记录收到的PreparedChat。"""

    def __init__(
        self,
        outcome: RAGOutcome,
    ) -> None:
        """保存待返回终态，并初始化聊天调用记录。"""
        self._outcome = outcome
        self.calls: list[PreparedChat] = []

    async def answer(
        self,
        prepared: PreparedChat,
    ) -> RAGOutcome:
        """记录服务端准备输入，并返回预设领域终态。"""
        self.calls.append(prepared)
        return self._outcome


class SequenceDisconnectProbe:
    """按预设顺序返回连接状态，用于复现特定断开时机。"""

    def __init__(
        self,
        results: list[bool],
    ) -> None:
        """复制断开结果序列，并初始化探针调用次数。"""
        self._remaining_results = list(results)
        self.call_count = 0

    async def __call__(self) -> bool:
        """返回下一次断开状态；结果耗尽时让测试明确失败。

        输入：无，由流生成器在每次发送前调用。
        输出：True表示客户端已断开，False表示仍连接。
        失败边界：预设结果耗尽时抛出AssertionError，暴露额外探测。
        """
        if not self._remaining_results:
            raise AssertionError("断开探针调用次数超过测试预期")

        self.call_count += 1
        return self._remaining_results.pop(0)


def test_stream_starts_with_status_and_preserves_success_order() -> None:
    """证明连接正常时按status、答案、引用和唯一done发布。

    输入：固定可信成功终态和始终连接的断开探针。
    输出：完整SSE帧严格遵守冻结的成功顺序。
    失败边界：缺失、乱序或重复done时测试失败。
    """

    async def scenario() -> None:
        """收集异步生成器产生的全部成功帧并精确核对。"""
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
        answerer = StaticPreparedChatAnswerer(outcome)
        prepared = PreparedChat(
            query="营业收入是否增长？",
            context=TrustedContext(workspace_id="WS-A"),
            filters=SearchFilters(document_id="doc-1"),
        )

        # 探测顺序：开始前、final_answer前、citation前、done前。
        disconnect_probe = SequenceDisconnectProbe([False, False, False, False])

        frames = [
            frame
            async for frame in stream_chat_sse(
                answerer,
                prepared,
                disconnect_probe,
            )
        ]

        assert frames == [
            'event: status\ndata: {"phase":"answering"}\n\n',
            'event: final_answer\ndata: {"content":"营业收入增长。[1]"}\n\n',
            (
                "event: citation\n"
                'data: {"number":1,"source_file":"report.pdf",'
                '"page":10,"chunk_id":"chunk-1"}\n'
                "\n"
            ),
            'event: done\ndata: {"outcome":"success"}\n\n',
        ]
        assert answerer.calls == [prepared]
        assert sum(frame.startswith("event: done\n") for frame in frames) == 1
        assert disconnect_probe.call_count == 4

    asyncio.run(scenario())


def test_stream_disconnect_before_done_does_not_claim_completion() -> None:
    """证明客户端在done前断开时不会被记录为正常完成。

    输入：固定正常拒答终态，以及在done前变为断开的探针。
    输出：只产生answering和refused状态，不产生done。
    失败边界：断开后仍发布done就代表服务端虚构了完成交付。
    """

    async def scenario() -> None:
        """按预设探针顺序收集断开前实际能够发布的事件。"""
        outcome = RefusalResult(
            reason=RefusalReason.EMPTY_RETRIEVAL,
        )
        answerer = StaticPreparedChatAnswerer(outcome)
        prepared = PreparedChat(
            query="无法回答的问题",
            context=TrustedContext(workspace_id="WS-A"),
            filters=SearchFilters(document_id="doc-1"),
        )

        # 开始前仍连接；refused前仍连接；done前已经断开。
        disconnect_probe = SequenceDisconnectProbe([False, False, True])

        frames = [
            frame
            async for frame in stream_chat_sse(
                answerer,
                prepared,
                disconnect_probe,
            )
        ]

        assert frames == [
            'event: status\ndata: {"phase":"answering"}\n\n',
            ('event: status\ndata: {"phase":"refused","reason":"empty_retrieval"}\n\n'),
        ]
        assert answerer.calls == [prepared]
        assert not any(frame.startswith("event: done\n") for frame in frames)
        assert disconnect_probe.call_count == 3

    asyncio.run(scenario())
