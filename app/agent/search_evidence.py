"""为单次受控搜索分配引用编号，并核验实际成功工具结果的身份与一致性。"""

from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
import json
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.agent.tool_loop import LoopFailure, LoopOutcome, ToolExecutionContext, ToolResult
from app.agent.user_result import (
    AgentResultError,
    AgentSystemError,
    AgentUserResult,
    supports_document_query,
    validate_user_result,
)
from app.rag.retriever import SearchHit
from app.rag.service import NumberedContext


class EvidenceValidationError(ValueError):
    """本次工具证据的结构、范围、编号或来源一致性不符合合同。"""


class _EvidenceHit(BaseModel):
    """校验原始工具命中的字段和类型；身份必须由可信检索通道保留。"""

    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)

    workspace_id: str
    document_id: str
    source_file: str
    chunk_id: str
    text: str
    page: int = Field(ge=1)
    score: float
    type: Literal["paragraph", "table", "title"]
    section: str = ""
    table_md: str | None = None

    @field_validator("workspace_id", "document_id", "source_file", "chunk_id", "text")
    @classmethod
    def require_nonblank(cls, value: str) -> str:
        """拒绝空字段，保留原始字符串以便检查来源一致性。"""
        if not value.strip():
            raise ValueError("证据字段不能为空")
        return value

    def to_search_hit(self) -> SearchHit:
        """转换为既有 RAG 引用 DTO；身份已由调用方独立核对，不从正文猜测。"""
        return SearchHit(
            score=self.score,
            chunk_id=self.chunk_id,
            text=self.text,
            page=self.page,
            source_file=self.source_file,
            type=self.type,
            section=self.section,
            table_md=self.table_md,
        )


class _SearchOutput(BaseModel):
    """校验一次真实搜索的返回结构；empty/count 仍须与实际 hits 交叉检查。"""

    model_config = ConfigDict(strict=True, extra="forbid")

    query: str
    requested_top_k: int = Field(ge=1, le=5)
    result_count: int = Field(ge=0)
    empty: bool
    hits: list[_EvidenceHit]


class SearchEvidenceSession:
    """每次任务独享的搜索适配与证据映射，不增加检索或模型调用。

    输入：唯一搜索 handler、服务端核准的执行范围/文件名和原始任务。
    输出：search 返回带 evidence_number 的工具结果；validate 返回内存用户三态。
    失败：证据非法时 search 抛安全异常，由既有 loop 处理为工具失败；
    validate 核对实际 ToolResult 与本次签发记录，失败时不发布任何候选正文。
    边界：模型、普通 messages 与 Run 摘要均不能创建本次证据；对象不可跨任务共享。
    """

    def __init__(
        self,
        *,
        handler: Callable[..., dict[str, object]],
        execution_context: ToolExecutionContext,
        source_file: str,
        query: str,
    ) -> None:
        """保存核准范围并创建空映射；不检索、不调用模型，缺少范围时立即失败。"""
        if execution_context.filters is None or execution_context.filters.document_id is None:
            raise ValueError("证据会话必须绑定核准的单文档范围")
        if not isinstance(source_file, str) or not source_file.strip():
            raise ValueError("证据会话必须有服务端核准的文件名")
        self._handler = handler
        self._execution_context = execution_context
        self._document_id = execution_context.filters.document_id
        self._source_file = source_file
        self._query = query
        self._hits: dict[int, SearchHit] = {}
        self._numbers: dict[str, int] = {}
        self._issued_outputs: list[dict[str, object]] = []

    def search(
        self, execution_context: ToolExecutionContext, query: str, top_k: int = 5
    ) -> dict[str, object]:
        """执行既有搜索一次，检查真实字段并为证据分配本次稳定编号。

        同片段复用编号，允许检索相关分数变化；正文、页码或来源冲突则失败。
        不支持的任务即使模型申请工具也不会检索；它不能绕过任务合同。
        """
        if execution_context != self._execution_context or not supports_document_query(self._query):
            raise EvidenceValidationError("搜索不符合本次核准任务范围")
        output = self._handler(execution_context, query=query, top_k=top_k)
        try:
            parsed = _SearchOutput.model_validate(output)
        except ValidationError:
            raise EvidenceValidationError("搜索返回字段不符合证据合同") from None
        if (
            parsed.query != query
            or parsed.requested_top_k != top_k
            or parsed.result_count != len(parsed.hits)
            or parsed.empty != (len(parsed.hits) == 0)
            or len(parsed.hits) > top_k
        ):
            raise EvidenceValidationError("搜索摘要与实际证据不一致")

        # 整次返回验证成功后才更新会话，避免部分非法命中留下已签发编号。
        next_hits = dict(self._hits)
        next_numbers = dict(self._numbers)
        numbered_hits: list[dict[str, object]] = []
        for evidence in parsed.hits:
            if (
                evidence.workspace_id != execution_context.trusted_context.workspace_id
                or evidence.document_id != self._document_id
                or evidence.source_file != self._source_file
            ):
                raise EvidenceValidationError("搜索证据不属于本次核准来源")
            hit = evidence.to_search_hit()
            number = next_numbers.get(hit.chunk_id)
            if number is None:
                number = len(next_hits) + 1
                next_numbers[hit.chunk_id] = number
                next_hits[number] = hit
            elif replace(hit, score=next_hits[number].score) != next_hits[number]:
                raise EvidenceValidationError("同一片段的证据内容或来源发生冲突")
            numbered_hits.append({**evidence.model_dump(), "evidence_number": number})

        issued: dict[str, object] = {
            "query": parsed.query,
            "requested_top_k": parsed.requested_top_k,
            "result_count": parsed.result_count,
            "empty": parsed.empty,
            "hits": numbered_hits,
        }
        self._hits = next_hits
        self._numbers = next_numbers
        self._issued_outputs.append(deepcopy(issued))
        return issued

    def _verified_context(self, results: tuple[ToolResult, ...]) -> NumberedContext:
        """核对 loop 实际成功记录与本次签发证据；不读取或相信普通消息。

        数量、顺序、内容不一致或调用 ID 重复时失败；证据快照不受返回字典修改影响。
        """
        if len(results) != len(self._issued_outputs):
            raise EvidenceValidationError("实际工具结果与本次证据数量不一致")
        call_ids: set[str] = set()
        for result, issued in zip(results, self._issued_outputs, strict=True):
            try:
                same_output = json.dumps(result.output, sort_keys=True, allow_nan=False) == json.dumps(
                    issued, sort_keys=True, allow_nan=False
                )
            except (TypeError, ValueError):
                same_output = False
            if result.tool_call_id in call_ids or not same_output:
                raise EvidenceValidationError("实际工具结果与本次证据身份不一致")
            call_ids.add(result.tool_call_id)
        return NumberedContext(
            text="\n".join(f"[{number}]:{hit.text}" for number, hit in self._hits.items()),
            hits_by_number=MappingProxyType(dict(self._hits)),
        )

    def validate(self, outcome: LoopOutcome) -> AgentUserResult:
        """核验本次可信工具结果，再复用纯结果验证；不重新检索或生成。

        loop 失败优先保留原系统错误类别；结果记录被替换时不发布候选。
        """
        if isinstance(outcome, LoopFailure):
            return AgentSystemError(AgentResultError(outcome.failure_type.value))
        try:
            context = self._verified_context(outcome.trusted_tool_results)
        except EvidenceValidationError:
            return AgentSystemError(AgentResultError.EVIDENCE_VALIDATION_ERROR)
        return validate_user_result(
            query=self._query,
            outcome=outcome,
            numbered_context=context,
            successful_searches=len(outcome.trusted_tool_results),
        )
