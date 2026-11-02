"""Frozen conversation-v1 DTOs. Model/provider text never supplies authority."""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal, Self
from urllib.parse import parse_qs, quote, urlsplit

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.research.models import Citation, Identity, Result, Strict, operation

Id = Annotated[str, Field(min_length=1, max_length=200)]
Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Metric = Literal["revenue", "net_profit_parent", "operating_cash_flow"]
TurnStatus = Literal["running", "completed", "refused", "failed", "interrupted"]
Intent = Literal["source_quote", "confirmed_metric", "compare_metric", "clarify", "unsupported"]


def instant(value: str) -> str:
    if datetime.fromisoformat(value).tzinfo is None:
        raise ValueError("timezone_required")
    return value


class FactSelection(Strict):
    company_id: Id
    metric_key: Metric
    period: int = Field(ge=1, le=9999)
    fact_set_id: Id
    fact_id: Id
    disclosure_version: Id


class CreateConversationRequest(Strict):
    operation_id: str
    document_ids: list[Id] = Field(min_length=1, max_length=4)
    title: str | None = Field(default=None, min_length=1, max_length=120)

    _operation = field_validator("operation_id")(operation)

    @field_validator("document_ids")
    @classmethod
    def unique_ids(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value) or any(not item.strip() for item in value):
            raise ValueError("invalid_selection")
        return sorted(value)

    @field_validator("title")
    @classmethod
    def nonblank_title(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            raise ValueError("invalid_title")
        return value


class CreateTurnRequest(Strict):
    operation_id: str
    text: str = Field(min_length=1, max_length=1000)
    fact_selections: list[FactSelection] = Field(default_factory=list, max_length=6)

    _operation = field_validator("operation_id")(operation)

    @field_validator("text")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("invalid_question")
        return value

    @field_validator("fact_selections")
    @classmethod
    def unique_facts(cls, value: list[FactSelection]) -> list[FactSelection]:
        keys = [(v.company_id, v.metric_key, v.period) for v in value]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate_fact_selection")
        return sorted(value, key=lambda v: (v.company_id, v.metric_key, v.period))


class DeleteRequest(Strict):
    operation_id: str

    _operation = field_validator("operation_id")(operation)


class SourceState(Strict):
    document_id: str
    source_revision: Hash
    status: Literal["current_at_read", "expired", "unavailable"]


class EvidenceRef(Citation):
    ref_id: Id


class FinancialFactRef(Strict):
    ref_id: Id
    fact_set_id: Id
    fact_id: Id
    receipt_id: Id
    document_id: Id
    company_id: Id
    source_revision: Hash
    disclosure_version: Id
    report_year: int = Field(ge=1, le=9999)
    period: int = Field(ge=1, le=9999)
    metric_key: Metric
    value_cny_yuan: str
    currency: Literal["CNY"]
    unit: Literal["CNY_YUAN"]
    confirmation_kind: Literal["local_operator"]
    validated_at: str

    _instant = field_validator("validated_at")(instant)

    @field_validator("value_cny_yuan")
    @classmethod
    def finite_decimal(cls, value: str) -> str:
        try:
            if not value.strip() or not Decimal(value).is_finite():
                raise ValueError("invalid_financial_decimal")
        except InvalidOperation:
            raise ValueError("invalid_financial_decimal") from None
        return value


class Action(Strict):
    kind: Literal["open_source", "review_facts", "open_research_run", "new_conversation"]
    label: str = Field(min_length=1, max_length=120)
    href: str = Field(min_length=1, max_length=2000)
    document_id: str | None = None
    source_revision: Hash | None = None
    physical_page: int | None = Field(default=None, ge=1)
    research_run_id: str | None = None

    @model_validator(mode="after")
    def allowed_href(self) -> Self:
        parts = urlsplit(self.href)
        if (parts.scheme or parts.netloc or "\\" in self.href
                or not self.href.startswith("/") or self.href.startswith("//")):
            raise ValueError("invalid_action_url")
        if self.kind == "new_conversation":
            if self.href != "/conversations":
                raise ValueError("invalid_action_url")
        elif self.kind == "review_facts":
            if self.href != "/research?mode=operating":
                raise ValueError("invalid_action_url")
        elif self.kind == "open_source":
            expected = f"/api/documents/{quote(self.document_id or '', safe='')}/file"
            query = parse_qs(parts.query, strict_parsing=True)
            if (self.document_id is None or self.source_revision is None
                    or self.physical_page is None
                    or parts.path != expected
                    or query != {"source_revision": [self.source_revision]}
                    or parts.fragment != f"page={self.physical_page}"):
                raise ValueError("invalid_source_action")
        else:
            # No fabricated legacy links in conversation-v1. Add only with a
            # verified old run and a separately reviewed UI route builder.
            raise ValueError("research_run_action_unavailable")
        return self


class ResolvedQuery(Strict):
    text: str = Field(min_length=1, max_length=2000)
    intent: Intent
    company_id: str | None
    metric_key: Metric | None
    periods: list[int]
    resolution: Literal["explicit", "context", "ambiguous"]
    context_turn_ids: list[str]

    @model_validator(mode="after")
    def bounded_focus(self) -> Self:
        if (len(self.periods) > 2 or len(set(self.periods)) != len(self.periods)
                or any(type(p) is not int or not 1 <= p <= 9999 for p in self.periods)
                or len(self.context_turn_ids) > 8
                or len(set(self.context_turn_ids)) != len(self.context_turn_ids)
                or (self.resolution == "context" and not self.context_turn_ids)):
            raise ValueError("invalid_focus")
        for value in self.context_turn_ids:
            operation(value)
        return self


class Analysis(Strict):
    model_config = ConfigDict(extra="forbid", strict=True, serialize_by_alias=True)
    schema_name: Literal["financial-analysis-v1"] = Field(alias="schema")
    status: Literal["compared", "partial"]
    metric_key: Metric
    current_ref_id: str
    previous_ref_id: str
    absolute_change: str
    percentage_change: str | None
    percentage_reason: str | None
    warnings: list[str]
    formula_id: Literal["financial_absolute_change_v1"]
    percentage_formula_id: Literal["financial_yoy_signed_base_v1"]


class MemoryCandidate(Strict):
    type: Literal["research_preference"]
    key: Literal["analysis_focus", "display_unit", "research_habit"]
    value: str = Field(min_length=1, max_length=200)
    source_turn_id: str
    confirmation_required: Literal[True]


class TurnResult(Strict):
    kind: Literal["source_quote", "confirmed_metric", "comparison", "clarification",
                  "needs_human_review", "unsupported", "error"]
    answer_text: str
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=8)
    verified_financial_fact_refs: list[FinancialFactRef] = Field(default_factory=list, max_length=6)
    analysis: Analysis | None = None
    interpretation_status: Literal["not_generated"] = "not_generated"
    reason_code: str | None = None
    error_code: str | None = None
    actions: list[Action] = Field(default_factory=list, max_length=8)
    memory_candidates: list[MemoryCandidate] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def typed_result(self) -> Self:
        refs = [v.ref_id for v in self.evidence_refs] + [
            v.ref_id for v in self.verified_financial_fact_refs
        ]
        if len(set(refs)) != len(refs):
            raise ValueError("duplicate_ref")
        if self.kind not in ("source_quote", "confirmed_metric", "comparison"):
            if self.evidence_refs or self.verified_financial_fact_refs or self.analysis:
                raise ValueError("nonanswer_has_evidence")
        if self.kind == "source_quote" and (
            not self.evidence_refs or self.verified_financial_fact_refs or self.analysis
        ):
            raise ValueError("invalid_quote")
        if self.kind == "confirmed_metric" and (
            len(self.verified_financial_fact_refs) != 1 or self.analysis or self.evidence_refs
        ):
            raise ValueError("invalid_metric")
        if self.kind == "comparison" and (
            len(self.verified_financial_fact_refs) != 2 or self.analysis is None
            or self.evidence_refs
            or {self.analysis.current_ref_id, self.analysis.previous_ref_id} != set(refs)
        ):
            raise ValueError("invalid_comparison")
        if (self.kind == "error") != (self.error_code is not None):
            raise ValueError("invalid_error")
        return self


class ToolEvent(Strict):
    sequence: int = Field(ge=1)
    tool_name: Literal["search_annual_report", "get_confirmed_metric", "compare_confirmed_metrics"]
    status: Literal["started", "completed", "refused", "failed", "unknown"]
    summary: str = Field(max_length=200)
    evidence_ref_ids: list[str]
    created_at: str

    _instant = field_validator("created_at")(instant)


class Usage(Strict):
    model_attempts: int = Field(default=0, ge=0, le=2)
    tool_calls: int = Field(default=0, ge=0, le=3)


class TurnData(Strict):
    schema_version: Literal["conversation-turn-v1"] = "conversation-turn-v1"
    conversation_id: str
    turn_id: str
    operation_id: str
    seq: int = Field(ge=1)
    status: TurnStatus = "running"
    user_text: str = Field(min_length=1, max_length=1000)
    resolved_query: ResolvedQuery | None = None
    fact_selections: list[FactSelection] = Field(default_factory=list)
    result: TurnResult | None = None
    research_run_id: str | None = None
    tool_events: list[ToolEvent] = Field(default_factory=list)
    created_at: str
    ended_at: str | None = None
    provider_outcome: Literal["not_started", "returned", "unknown"] = "not_started"
    usage: Usage = Field(default_factory=Usage)

    _operation = field_validator("conversation_id", "turn_id", "operation_id")(operation)
    _created = field_validator("created_at")(instant)

    @model_validator(mode="after")
    def terminal(self) -> Self:
        if self.status == "running":
            if self.result is not None or self.ended_at is not None:
                raise ValueError("running_with_result")
        else:
            if self.result is None or self.ended_at is None:
                raise ValueError("missing_terminal_result")
            instant(self.ended_at)
            if datetime.fromisoformat(self.ended_at) < datetime.fromisoformat(self.created_at):
                raise ValueError("invalid_end")
            kinds = {
                "completed": {"source_quote", "confirmed_metric", "comparison", "clarification"},
                "refused": {"needs_human_review", "unsupported"},
                "failed": {"error"}, "interrupted": {"error"},
            }
            if self.result.kind not in kinds[self.status]:
                raise ValueError("status_result_mismatch")
        if [v.sequence for v in self.tool_events] != list(range(1, len(self.tool_events) + 1)):
            raise ValueError("invalid_event_sequence")
        if (self.provider_outcome == "not_started") != (self.usage.model_attempts == 0):
            raise ValueError("invalid_provider_outcome")
        return self


class Turn(TurnData):
    historical_snapshot: bool = True
    source_states: list[SourceState]
    financial_fact_validity: Literal["not_applicable", "validated_at_completion_only"]
    integrity_sha256: Hash


class OperationRecord(Strict):
    schema_version: Literal["conversation-operation-v1"] = "conversation-operation-v1"
    operation_id: str
    kind: Literal["create_conversation", "send_turn", "delete_conversation"]
    status: TurnStatus
    conversation_id: str
    turn_id: str | None
    resource_deleted: bool = False
    created_at: str
    ended_at: str | None
    error_code: str | None = None

    _operation = field_validator("operation_id", "conversation_id")(operation)
    _created = field_validator("created_at")(instant)

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if (self.status == "running") != (self.ended_at is None):
            raise ValueError("invalid_operation_state")
        if self.turn_id is not None:
            operation(self.turn_id)
        if (self.kind == "send_turn") != (self.turn_id is not None):
            raise ValueError("invalid_operation_target")
        if self.ended_at is not None:
            instant(self.ended_at)
            if datetime.fromisoformat(self.ended_at) < datetime.fromisoformat(self.created_at):
                raise ValueError("invalid_operation_end")
        return self


class ConversationSummary(Strict):
    conversation_id: str
    title: str
    status: Literal["active"] = "active"
    source_scope_sha: Hash
    sources: list[Identity]
    source_states: list[SourceState]
    created_at: str
    updated_at: str
    last_turn_seq: int
    active_turn_id: str | None


class ConversationDetail(ConversationSummary):
    schema_version: Literal["conversation-v1"] = "conversation-v1"
    turns: list[Turn]
    next_before_seq: int | None


class ConversationList(Strict):
    schema_version: Literal["conversation-list-v1"] = "conversation-list-v1"
    items: list[ConversationSummary]
    next_cursor: str | None


def validate_quote(result: TurnResult, sources: list[Identity], selection_id: str) -> None:
    """Keep the existing strict original-excerpt protocol intact."""
    if result.kind == "source_quote":
        Result(
            selection_id=selection_id, documents=sources, outcome="answered",
            content=result.answer_text,
            citations=[Citation.model_validate(v.model_dump(exclude={"ref_id"}))
                       for v in result.evidence_refs],
            answer_mode="verified_excerpts", human_review="pending",
        )


def error_result(code: str) -> TurnResult:
    return TurnResult(kind="error", answer_text="本轮未能完成，请查看本轮状态后再决定下一步。",
                      error_code=code)
