"""Strict proposals and findings. Server scope/amount authority never comes from a model."""
from dataclasses import dataclass
from datetime import datetime
import math
from typing import Annotated, Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

UUIDText = Annotated[str, Field(pattern=r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")]
Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Metric = Literal["revenue", "net_profit_parent", "operating_cash_flow", "total_assets", "total_liabilities", "debt_asset_ratio"]


class ResearchError(Exception):
    def __init__(self, code, status=409):
        super().__init__(code)
        self.code, self.status = code, status


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Operation(Strict):
    operation_id: UUIDText


class IntentRequest(Operation):
    conversation_id: UUIDText
    text: str = Field(min_length=1, max_length=2000)
    requested_mode: Literal["quick", "synthesis", "deep"] | None = None


class HandoffRequest(Operation):
    conversation_id: UUIDText
    intent_id: UUIDText
    confirmed: Literal[True]

    @field_validator("confirmed", mode="before")
    @classmethod
    def explicit(cls, value):
        if value is not True:
            raise ValueError("Explicit confirmation required")
        return value


class IntentProposal(Strict):
    mode: Literal["quick", "synthesis", "deep"]
    goal: str = Field(min_length=1, max_length=2000)
    company_ids: list[str] = Field(max_length=4)
    periods: list[int] = Field(max_length=4)
    metric_keys: list[Metric] = Field(max_length=6)
    actions: list[Literal["read_evidence", "read_confirmed_facts", "create_task", "draft_report", "clarify"]] = Field(max_length=5)
    clarifying_question: str | None = Field(default=None, max_length=500)
    requires_confirmed_facts: bool
    source_turn_ids: list[UUIDText] = Field(max_length=8)


@dataclass(frozen=True)
class RuntimeIdentity:
    instance_id: str
    lease_generation: int
    lease_expires_at: float
    workspace_id: str
    principal_id: str

    def __post_init__(self):
        if (not self.instance_id or not self.workspace_id or not self.principal_id or
                type(self.lease_generation) is not int or self.lease_generation < 0 or
                not math.isfinite(self.lease_expires_at)):
            raise ValueError("Invalid server runtime identity")


def demo_identity(request, *, workspace_id, principal_id="demo-visitor"):
    marker = request.scope.get("findoc_private_identity")
    generation, instance = request.headers.get("X-Findoc-Generation"), request.headers.get("X-Findoc-Instance")
    if marker != (generation, instance) or not generation or not instance:
        raise ResearchError("private_runtime_identity_required", 403)
    try:
        expires = datetime.fromisoformat(request.headers["X-Findoc-Lease-Expires-At"])
        if expires.tzinfo is None:
            raise ValueError()
        return RuntimeIdentity(instance, int(generation), expires.timestamp(), workspace_id, principal_id)
    except (ValueError, KeyError):
        raise ResearchError("invalid_lease_deadline", 403) from None


class FindingBase(Strict):
    schema_version: Literal["research-finding-v2"] = "research-finding-v2"
    finding_id: UUIDText
    text: str = Field(min_length=1, max_length=4000)
    origin: Literal["deterministic_tool", "verified_source", "model_draft", "system"]
    data_origin: Literal["local_runtime", "ai_draft", "unresolved"]
    source_status: Literal["current_valid", "not_applicable", "unresolved"]
    transcription_review_status: Literal["fast_extraction_unreviewed", "human_reviewed", "not_applicable"]
    interpretation_review_status: Literal["ai_unreviewed", "deterministic", "not_applicable"]


class ConfirmedFinancial(FindingBase):
    kind: Literal["confirmed_financial"]
    financial_refs: list[dict[str, Any]] = Field(min_length=1)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)


class SourcedExcerpt(FindingBase):
    kind: Literal["sourced_excerpt"]
    evidence_refs: list[dict[str, Any]] = Field(min_length=1)
    financial_refs: list[dict[str, Any]] = Field(default_factory=list, max_length=0)


class ModelInterpretation(FindingBase):
    kind: Literal["model_interpretation"]
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    financial_refs: list[dict[str, Any]] = Field(default_factory=list, max_length=0)
    numeric_claim_status: Literal["no_numeric_claim", "numeric_claim_unverified"]


class UnresolvedQuestion(FindingBase):
    kind: Literal["unresolved_question"]
    unresolved_question: str = Field(min_length=1, max_length=1000)
    actions: list[dict[str, str]] = Field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    financial_refs: list[dict[str, Any]] = Field(default_factory=list, max_length=0)


ResearchFindingV2 = Annotated[ConfirmedFinancial | SourcedExcerpt | ModelInterpretation | UnresolvedQuestion, Field(discriminator="kind")]


class PlanRequest(Operation):
    intent_id: UUIDText


class JobRequest(Operation):
    approved_plan_id: UUIDText
    approved_plan_revision: int = Field(ge=1)
    approved_plan_sha256: Hash
    confirmed: Literal[True]

    @field_validator("confirmed", mode="before")
    @classmethod
    def explicit(cls, value):
        if value is not True:
            raise ValueError("Explicit plan confirmation required")
        return value


class AgentInterpretation(Strict):
    text: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=10)


class AgentDraft(Strict):
    interpretations: list[AgentInterpretation] = Field(default_factory=list, max_length=5)


class SupervisorProposal(Strict):
    roles: list[Literal["evidence", "finance", "risk_operations", "generalist"]] = Field(min_length=1, max_length=2)
    goal: str = Field(min_length=1, max_length=2000)
