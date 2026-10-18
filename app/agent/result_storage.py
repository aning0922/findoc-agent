"""用户结果的受限存储格式；不恢复工具证据，也不调用模型或检索。"""

from dataclasses import dataclass
import json
import re

from app.agent.user_result import (
    AgentAnswer,
    AgentRefusal,
    AgentRefusalReason,
    AgentResultError,
    AgentSystemError,
    AgentUserResult,
)
from app.rag.service import Citation


USER_RESULT_VERSION = "agent-user-result-v1"
"""固定三态及引用字段的存储版本；未知版本拒绝读取。"""


class AgentResultIntegrityError(RuntimeError):
    """持久结果缺失、损坏或与 Run 不一致；异常消息不携带数据库正文。"""


class AgentResultNotReadyError(RuntimeError):
    """Run 尚在运行，尚无已提交的产品结果；不表示会自动续跑。"""


class AgentResultNotStoredError(RuntimeError):
    """旧版或离线 Run 未约定保存产品结果，不能从执行摘要推导答案。"""


@dataclass(frozen=True)
class StoredAgentUserResult:
    """经结构检查的已保存结果及服务端元信息；仅 user_result.to_public 可公开。"""

    run_id: str
    workspace_id: str
    document_id: str
    execution_config_version: str
    result_version: str
    user_result: AgentUserResult


def _text(value: object) -> str:
    """检查非空字符串，失败不回显输入。"""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("结果字段必须是非空字符串")
    return value


def _positive_int(value: object) -> int:
    """检查引用正整数并拒绝 bool。"""
    if type(value) is not int or value < 1:
        raise ValueError("引用字段必须是正整数")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """解析 JSON 对象时拒绝重复键，避免后值覆盖掩盖非法结构。"""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("结果存在重复字段")
        result[key] = value
    return result


def decode_user_result(payload: str, *, version: str) -> AgentUserResult:
    """按已知版本严格恢复三态；非法字段、类型或引用结构均抛安全一致性异常。

    此处只验证存储结构，不重做来源签发或语义评测；可信来源须在写入前核证。
    """
    try:
        if version != USER_RESULT_VERSION or not isinstance(payload, str):
            raise ValueError("不支持的结果版本或载荷")
        data = json.loads(payload, object_pairs_hook=_unique_object)
        if not isinstance(data, dict):
            raise ValueError("结果必须是对象")
        status = data.get("status")
        if status == "answered" and set(data) == {"status", "content", "citations"}:
            content = _text(data["content"])
            items = data["citations"]
            if not isinstance(items, list) or not items:
                raise ValueError("引用必须是非空列表")
            citations: list[Citation] = []
            for item in items:
                if not isinstance(item, dict) or set(item) != {
                    "number", "source_file", "page", "chunk_id"
                }:
                    raise ValueError("引用字段不合法")
                citations.append(Citation(
                    number=_positive_int(item["number"]),
                    source_file=_text(item["source_file"]),
                    page=_positive_int(item["page"]),
                    chunk_id=_text(item["chunk_id"]),
                ))
            body = re.sub(r"\[[1-9][0-9]*\]", "", content)
            numbers = list(dict.fromkeys(
                int(number) for number in re.findall(r"\[([1-9][0-9]*)\]", content)
            ))
            if (
                not body.strip() or "[" in body or "]" in body
                or numbers != [citation.number for citation in citations]
                or len({citation.source_file for citation in citations}) != 1
                or len({citation.chunk_id for citation in citations}) != len(citations)
            ):
                raise ValueError("正文与引用结构不一致")
            return AgentAnswer(content, tuple(citations))
        if status == "refusal" and set(data) == {"status", "reason"}:
            return AgentRefusal(AgentRefusalReason(_text(data["reason"])))
        if status == "system_error" and set(data) == {"status", "error_code"}:
            return AgentSystemError(AgentResultError(_text(data["error_code"])))
        raise ValueError("结果三态结构不合法")
    except (ValueError, TypeError, KeyError, RecursionError):
        raise AgentResultIntegrityError("已保存的用户结果不合法或版本不受支持") from None


def encode_user_result(result: AgentUserResult) -> str:
    """仅编码三种准确 DTO 类型的白名单，并反向检查；不序列化内部运行对象。"""
    data: dict[str, object]
    if type(result) is AgentAnswer:
        data = {
            "status": "answered",
            "content": result.content,
            "citations": [
                {"number": c.number, "source_file": c.source_file,
                 "page": c.page, "chunk_id": c.chunk_id}
                for c in result.citations
            ],
        }
    elif type(result) is AgentRefusal:
        data = {"status": "refusal", "reason": result.reason.value}
    elif type(result) is AgentSystemError:
        data = {"status": "system_error", "error_code": result.error_code.value}
    else:
        raise TypeError("只能保存已验证的三态用户结果")
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False)
    decode_user_result(payload, version=USER_RESULT_VERSION)
    return payload
