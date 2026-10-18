from collections.abc import (
    AsyncIterator,
    Awaitable,
    Callable,
)
from typing import Literal, Mapping, Protocol
import json

from app.chat.service import PreparedChat
from app.rag.service import RAGOutcome, RAGResult, RefusalResult, SystemErrorResult

SSEEventName = Literal[
    "status",
    "final_answer",
    "citation",
    "usage",
    "error",
    "done",
]

_ALLOWED_SSE_EVENTS = frozenset(
    {
        "status",
        "final_answer",
        "citation",
        "usage",
        "error",
        "done",
    }
)


class PreparedChatAnswerer(Protocol):
    """定义SSE流生成器依赖的最小异步聊天执行能力。"""

    async def answer(
        self,
        prepared: PreparedChat,
    ) -> RAGOutcome:
        """执行已完成可信准备的聊天请求并返回领域终态。"""
        ...


DisconnectProbe = Callable[[], Awaitable[bool]]


def encode_sse_event(
    event: SSEEventName,
    data: Mapping[str, object],
) -> str:
    """把允许的事件名和 JSON 对象编码为完整 SSE 帧。

    输入：冻结的事件名，以及可被标准 JSON 编码的键值数据。
    输出：包含 event、单行 data 和结尾空行的 SSE 文本。
    失败：非法事件名抛出 ValueError；数据无法编码时保留 JSON 编码异常。
    边界：只负责 framing，不决定哪些 RAG 字段可以对外发布。
    """
    if event not in _ALLOWED_SSE_EVENTS:
        raise ValueError(f"sse event 名字必须是 {_ALLOWED_SSE_EVENTS} 中的一个")
    json_data = json.dumps(dict(data), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return f"event: {event}\ndata: {json_data}\n\n"


def map_rag_outcome_to_sse(outcome: RAGOutcome) -> tuple[str, ...]:
    """把可信RAG领域终态映射成冻结的SSE终态帧。

    输入：RAGResult、RefusalResult或SystemErrorResult之一。
    输出：按合同排序且以唯一done结束的不可变SSE帧序列。
    失败：收到RAGOutcome之外的运行时对象时抛出TypeError。
    边界：不执行RAG逻辑、不发送初始answering状态、不处理断开或usage。
    """
    frames: list[str] = []
    if isinstance(outcome, RAGResult):
        frames.append(
            encode_sse_event(
                "final_answer",
                {"content": outcome.content},
            )
        )
        for citation in outcome.citations:
            frames.append(
                encode_sse_event(
                    "citation",
                    {
                        "number": citation.number,
                        "source_file": citation.source_file,
                        "page": citation.page,
                        "chunk_id": citation.chunk_id,
                    },
                )
            )
        frames.append(encode_sse_event("done", {"outcome": "success"}))
        return tuple(frames)
    elif isinstance(outcome, RefusalResult):
        frames.append(
            encode_sse_event("status", {"phase": "refused", "reason": outcome.reason.value})
        )
        frames.append(encode_sse_event("done", {"outcome": "refusal"}))
        return tuple(frames)
    elif isinstance(outcome, SystemErrorResult):
        frames.append(
            encode_sse_event(
                "error", {"code": outcome.error_type.value, "message": outcome.message}
            )
        )
        frames.append(encode_sse_event("done", {"outcome": "error"}))
        return tuple(frames)
    raise TypeError("outcome 必须是受支持的 RAGOutcome")


async def stream_chat_sse(
    answerer: PreparedChatAnswerer, prepared: PreparedChat, is_disconnected: DisconnectProbe
) -> AsyncIterator[str]:
    """在连接仍可用时按顺序产生一次可信聊天的SSE帧。

    输入：异步聊天执行器、服务端PreparedChat和异步断开探针。
    输出：以answering状态开始，并逐帧产生领域终态映射结果。
    失败：answerer意外抛出的异常原样传播，不伪装成正常拒答。
    边界：每帧发送前检查断开；断开不取消已进入工作线程的同步RAG。
    """
    if await is_disconnected():
        return
    yield encode_sse_event("status", {"phase": "answering"})
    outcome = await answerer.answer(prepared)
    frames = map_rag_outcome_to_sse(outcome)
    for frame in frames:
        if await is_disconnected():
            return
        yield frame
