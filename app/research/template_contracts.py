"""D18 two P0 inputs and D19 handoff vocabulary. No amounts or client permissions."""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

Id = Annotated[str, StringConstraints(min_length=1, max_length=100,
                                     pattern=r"^[^\s\x00-\x1f\x7f]+$")]
Hash = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
Metric = Literal["revenue", "net_profit_parent", "operating_cash_flow"]
State = Literal[
    "prepared", "collecting_evidence", "awaiting_human_confirmation", "ready_for_analysis",
    "analyzing", "collecting_explanation", "completed", "refused", "failed",
]
STEPS = (
    "approve_input_and_sources", "read_candidates_or_fact_status", "verify_evidence_and_versions",
    "require_human_confirmation", "deterministic_analysis", "retrieve_business_excerpts",
    "validate_result_eligibility", "produce_versioned_limited_result",
)


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class AnnualPeriod(StrictContract):
    year: Annotated[int, Field(ge=1, le=9999)]
    start: Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$")]
    end: Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$")]
    period_type: Literal["annual"]

    @model_validator(mode="after")
    def complete_annual(self) -> "AnnualPeriod":
        if date.fromisoformat(self.start) != date(self.year, 1, 1) or (
            date.fromisoformat(self.end) != date(self.year, 12, 31)
        ):
            raise ValueError("complete_natural_annual_period_required")
        return self


class ReportChoice(StrictContract):
    document_id: Id
    expected_source_revision: Hash  # Optimistic version choice; never grants access.


class FactChoice(StrictContract):
    metric_key: Metric
    document_id: Id
    disclosure_version: Id  # Required even when no confirmed fact exists yet.
    fact_set_id: Id | None
    fact_id: Id | None

    @model_validator(mode="after")
    def paired_ids(self) -> "FactChoice":
        if (self.fact_id is None) != (self.fact_set_id is None):
            raise ValueError("fact_ids_must_be_paired")
        return self


class ResearchSide(StrictContract):
    company_id: Id
    period: AnnualPeriod
    choices: Annotated[tuple[FactChoice, ...], Field(min_length=3, max_length=3)]

    @field_validator("choices", mode="before")
    @classmethod
    def immutable_choices(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def three_metrics(self) -> "ResearchSide":
        if len({c.metric_key for c in self.choices}) != 3:
            raise ValueError("all_three_unique_metrics_required")
        return self


class TemplateRequest(StrictContract):
    schema_version: Literal["operating-research-input-v1"]
    template: Literal["company_period_change", "company_same_period_comparison"]
    reports: Annotated[tuple[ReportChoice, ...], Field(min_length=1, max_length=4)]
    first: ResearchSide  # A: current; B: enterprise A.
    second: ResearchSide  # A: previous; B: enterprise B.
    direction: Literal["business_overview", "products_and_operations"]

    @field_validator("reports", mode="before")
    @classmethod
    def immutable_reports(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def relationships(self) -> "TemplateRequest":
        docs = {r.document_id for r in self.reports}
        if len(docs) != len(self.reports):
            raise ValueError("duplicate_reports")
        referenced = {c.document_id for s in (self.first, self.second) for c in s.choices}
        if referenced != docs:
            raise ValueError("report_choices_must_exactly_cover_input")
        if self.template == "company_period_change":
            if self.first.company_id != self.second.company_id:
                raise ValueError("same_company_required")
            if self.first.period.year <= self.second.period.year:
                raise ValueError("invalid_period_order")
        elif self.first.company_id == self.second.company_id:
            raise ValueError("different_companies_required")
        elif self.first.period != self.second.period:
            raise ValueError("same_complete_period_required")
        return self


class EmptyArguments(StrictContract):
    pass


class SlotArguments(StrictContract):
    side: Literal["first", "second"]
    metric_key: Metric


class MetricArguments(StrictContract):
    metric_key: Metric


class EvidenceArguments(StrictContract):
    direction: Literal["business_overview", "products_and_operations"]
    top_k: Annotated[int, Field(ge=1, le=12)]


TRANSITIONS: dict[str, frozenset[str]] = {
    "prepared": frozenset(("collecting_evidence", "refused", "failed")),
    "collecting_evidence": frozenset(("awaiting_human_confirmation", "ready_for_analysis",
                                      "refused", "failed")),
    # D18 cannot implement these resumes/completions. D19 must freshly re-admit IDs.
    "awaiting_human_confirmation": frozenset(("refused", "failed")),
    "ready_for_analysis": frozenset(("analyzing", "refused", "failed")),
    "analyzing": frozenset(("collecting_explanation", "refused", "failed")),
    "collecting_explanation": frozenset(("refused", "failed")),
    "completed": frozenset(), "refused": frozenset(), "failed": frozenset(),
}


def transition(old: State, new: State) -> State:
    if new not in TRANSITIONS[old]:
        raise ValueError("unsupported_d18_transition")
    return new


class HandoffContract(StrictContract):
    schema_version: Literal["operating-research-handoff-v1"]
    resume_implemented: Literal[False]
    fresh_source_and_receipt_admission_required: Literal[True]
    confirmation_path: Literal["existing_d9_d10_only"]
    amount_snapshots_are_resume_credentials: Literal[False]


class PlanResult(StrictContract):
    """Versioned D18 output invariant: no final prose or completed research."""
    schema_version: Literal["operating-research-plan-v1"]
    template: Literal["company_period_change", "company_same_period_comparison"]
    input: TemplateRequest
    status: State
    error_code: str | None
    facts: list[dict[str, object]]
    documents: list[dict[str, object]]
    tools: dict[str, dict[str, object]]
    budget: dict[str, object]
    steps: list[dict[str, str]]
    must_wait_for_human: bool
    analysis_results: list[dict[str, object]]
    operating_evidence: dict[str, object] | None
    final_research_content: None
    verified_operating_attribution: Literal[False]
    persistence: Literal["not_persisted"]
    automatic_resume: Literal[False]
    checkpointer: Literal[False]
    test_mode: Literal["simulated_test"] | None
    handoff: HandoffContract

    @model_validator(mode="after")
    def incomplete_result(self) -> "PlanResult":
        if self.template != self.input.template:
            raise ValueError("template_input_mismatch")
        if self.schema_version == "operating-research-plan-v1" and self.status == "completed":
            raise ValueError("d18_completed_unsupported")
        if self.must_wait_for_human != (self.status == "awaiting_human_confirmation"):
            raise ValueError("wait_status_mismatch")
        if self.status in ("awaiting_human_confirmation", "refused", "failed") and (
            self.analysis_results or self.operating_evidence is not None
        ):
            raise ValueError("unqualified_results")
        return self
