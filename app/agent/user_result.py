"""验证单次 Agent 的候选结果；不执行检索、模型调用或结果持久化。"""

from dataclasses import dataclass, field
from enum import StrEnum
import re
from typing import Literal

from app.agent.tool_loop import LoopFailure, LoopOutcome
from app.rag.service import (
    Citation,
    CitationValidationError,
    NumberedContext,
    RAGResult,
    parse_answer_candidate,
    validate_and_build_citations,
)


SUPPORTED_QUERY_PATTERN = re.compile(r"查询[0-9]{4}年度(?:营业收入|净利润|员工平均年龄)")
"""当前完整请求合同；只支持指定年度与指标的原文查询，不识别任意自然语言意图。"""


def supports_document_query(query: str) -> bool:
    """接收任务文本，完整匹配有限原文查询合同；只忽略首尾空白。

    返回 True 仅表示任务类型受支持，不证明文档有答案；非法类型返回 False。
    """
    return isinstance(query, str) and SUPPORTED_QUERY_PATTERN.fullmatch(query.strip()) is not None


class AgentRefusalReason(StrEnum):
    """服务端可核证的有限拒答依据，不包含模型自报的资料不足。"""

    EMPTY_RETRIEVAL = "empty_retrieval"
    CAPABILITY_LIMIT = "capability_limit"


class AgentResultError(StrEnum):
    """用户结果允许公开的稳定错误类别，不保存原始异常。"""

    PROTOCOL_ERROR = "protocol_error"
    TOOL_ERROR = "tool_error"
    PROVIDER_ERROR = "provider_error"
    MAX_STEPS_REACHED = "max_steps_reached"
    OUTPUT_VALIDATION_ERROR = "output_validation_error"
    EVIDENCE_VALIDATION_ERROR = "evidence_validation_error"
    CITATION_VALIDATION_ERROR = "citation_validation_error"
    UNVERIFIED_REFUSAL = "unverified_refusal"


@dataclass(frozen=True)
class AgentAnswer:
    """保存经校验的正文与服务端引用；为空时沿用 RAG 成功对象的失败边界。"""

    content: str
    citations: tuple[Citation, ...]
    status: Literal["answered"] = field(default="answered", init=False)

    def __post_init__(self) -> None:
        """复用 RAGResult 的成功不变量；此 DTO 不自行证明引用来源或语义支持。"""
        RAGResult(content=self.content, citations=self.citations)

    def to_public(self) -> dict[str, object]:
        """显式生成用户白名单字段；不自动序列化运行对象或内部证据。"""
        return {
            "status": self.status,
            "content": self.content,
            "citations": [
                {
                    "number": citation.number,
                    "source_file": citation.source_file,
                    "page": citation.page,
                    "chunk_id": citation.chunk_id,
                }
                for citation in self.citations
            ],
        }


@dataclass(frozen=True)
class AgentRefusal:
    """保存核证后的拒答原因；说明由服务器按原因生成，不接收模型正文。"""

    reason: AgentRefusalReason
    status: Literal["refusal"] = field(default="refusal", init=False)

    def __post_init__(self) -> None:
        """拒绝不属于有限原因集合的值。"""
        if not isinstance(self.reason, AgentRefusalReason):
            raise TypeError("拒答原因必须是 AgentRefusalReason")

    def to_public(self) -> dict[str, object]:
        """返回稳定原因与固定安全说明；不声称整份文档不存在答案。"""
        message = (
            "本次检索未取得证据，无法基于本次结果回答。"
            if self.reason is AgentRefusalReason.EMPTY_RETRIEVAL
            else "当前仅支持指定格式和指标的原文查询，暂不支持此请求。"
        )
        return {"status": self.status, "reason": self.reason.value, "message": message}


@dataclass(frozen=True)
class AgentSystemError:
    """保存稳定系统错误码；不提供承载候选正文或原始异常的字段。"""

    error_code: AgentResultError
    status: Literal["system_error"] = field(default="system_error", init=False)

    def __post_init__(self) -> None:
        """拒绝模型文本或任意字符串充当正式错误类别。"""
        if not isinstance(self.error_code, AgentResultError):
            raise TypeError("错误类别必须是 AgentResultError")

    def to_public(self) -> dict[str, object]:
        """返回白名单错误码与安全说明，不附带内部诊断。"""
        return {
            "status": self.status,
            "error_code": self.error_code.value,
            "message": "本次执行或结果校验未通过，未发布答案。",
        }


AgentUserResult = AgentAnswer | AgentRefusal | AgentSystemError
"""内存用户结果三态；不得以 loop 终态或 Run 安全摘要替代。"""


def validate_user_result(
    *,
    query: str,
    outcome: LoopOutcome,
    numbered_context: NumberedContext,
    successful_searches: int,
) -> AgentUserResult:
    """依据已核验的本次证据，解析候选并决定产品三态。

    输入：原任务、现有 loop 终态，以及调用方从可信工具结果核验的编号映射/次数。
    输出：只能是白名单用户结果；候选无效时不携带候选正文。
    边界：本函数不从 messages 恢复证据，不执行检索、生成或语义裁判；
    numbered_context 必须由本次 SearchEvidenceSession 核验得到，不能由模型构造。
    """
    if isinstance(outcome, LoopFailure):
        return AgentSystemError(AgentResultError(outcome.failure_type.value))
    try:
        content = parse_answer_candidate(outcome.final_answer)
    except ValueError:
        return AgentSystemError(AgentResultError.OUTPUT_VALIDATION_ERROR)

    if not supports_document_query(query):
        if content is None:
            return AgentRefusal(AgentRefusalReason.CAPABILITY_LIMIT)
        return AgentSystemError(AgentResultError.OUTPUT_VALIDATION_ERROR)

    if content is None:
        if successful_searches > 0 and not numbered_context.hits_by_number:
            return AgentRefusal(AgentRefusalReason.EMPTY_RETRIEVAL)
        return AgentSystemError(AgentResultError.UNVERIFIED_REFUSAL)

    # 方括号在候选正文中专用于正整数引用，不接受负号、前导零或混合声明。
    without_citations = re.sub(r"\[[1-9][0-9]*\]", "", content)
    if "[" in without_citations or "]" in without_citations:
        return AgentSystemError(AgentResultError.CITATION_VALIDATION_ERROR)
    try:
        citations = validate_and_build_citations(content, numbered_context)
    except (CitationValidationError, TypeError, ValueError):
        return AgentSystemError(AgentResultError.CITATION_VALIDATION_ERROR)
    return AgentAnswer(content=content, citations=citations)
