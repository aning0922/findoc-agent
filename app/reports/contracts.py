"""D22 strict, ephemeral draft; D23 must re-admit before saving this contract."""

from typing import Annotated, Any, Literal
from pydantic import Field, model_validator, ConfigDict, JsonValue, with_config
from typing_extensions import TypedDict
from app.research.template_contracts import StrictContract, Hash, Id, Metric, TemplateRequest
from app.research.task_contracts import UUIDText
from app.research.operating_result import Interpretation

DecimalText = Annotated[str, Field(pattern=r"^-?\d+(?:\.\d+)?$")]


class GenerateDraft(StrictContract):
    task_id: UUIDText
    expected_revision: Annotated[int, Field(ge=1)]


class FieldVerification(StrictContract):
    path: str
    origin: Literal["D10", "D11_D13", "D21_PDF", "D21_pending", "D21_scope"]
    identity: str
    snapshot_sha256: Hash
    status: Literal["verified_snapshot", "pending_semantic_review"]


class FactRow(StrictContract):
    side: Literal["first", "second"]
    company_id: Id
    company_name: str
    period: int
    metric_key: Metric
    raw_value: str
    raw_unit: str
    value_cny_yuan: DecimalText
    unit: Literal["CNY_YUAN"]
    currency: Literal["CNY"]
    scope: Literal["consolidated"]
    accounting_basis: Literal["PRC_GAAP"]
    fact_id: Id
    fact_set_id: Id
    receipt_id: Id
    disclosure_version: Id
    document_id: Id
    source_revision: Hash
    content_sha256: Hash
    physical_page: Annotated[int, Field(ge=1)]
    confirmation_kind: Literal["local_operator", "simulated_test"]


class AnalysisRow(StrictContract):
    metric_key: Metric
    direction: Literal["current_minus_previous", "B_minus_A"]
    first_fact_id: Id
    second_fact_id: Id
    absolute_change: DecimalText
    percentage_change: DecimalText | None
    percentage_reason: str | None
    absolute_change_unit: Literal["CNY_YUAN"]
    percentage_change_unit: Literal["PERCENT"]
    absolute_formula_id: Literal["financial_absolute_change_v1"]
    percentage_formula_id: Literal[
        "financial_yoy_signed_base_v1", "financial_company_relative_signed_base_v1"
    ]
    absolute_expression: str
    percentage_expression: str
    limitations: list[dict[str, Any]]


class Citation(StrictContract):
    number: Annotated[int, Field(ge=1, le=12)]
    workspace_id: Id
    company_id: Id
    report_year: int
    report_type: Literal["annual"]
    period_start: str
    period_end: str
    basis: Literal["PRC_GAAP"]
    document_id: Id
    source_revision: Hash
    content_sha256: Hash
    attempt: int
    parser_version: str
    physical_page: Annotated[int, Field(ge=1)]
    chunk_id: Id
    source_file: str
    text: Annotated[str, Field(min_length=1)]
    kind: Literal["paragraph", "table"]
    verification: Literal["exact_original_with_context"]


class OperatingParagraph(StrictContract):
    text: Annotated[str, Field(min_length=1)]
    citation: Citation
    verification: Literal["exact_original_with_context"]
    human_review_status: Literal["pending"]


class PendingInterpretation(Interpretation):
    validation_status: Literal["pending_semantic_review"]
    verified_operating_attribution: Literal[False]


@with_config(ConfigDict(extra="forbid", strict=True))
class ReportEvidence(TypedDict):
    selected_reports: Annotated[list[dict[str, JsonValue]], Field(min_length=1, max_length=4)]
    financial_facts: Annotated[list[dict[str, JsonValue]], Field(min_length=6, max_length=6)]
    deterministic_analysis: Annotated[list[dict[str, JsonValue]], Field(min_length=3, max_length=3)]
    operating_evidence: dict[str, JsonValue]
    citations: Annotated[list[dict[str, JsonValue]], Field(min_length=1, max_length=8)]


class ReportDraft(StrictContract):
    schema_version: Literal["report-draft-v1"] = "report-draft-v1"
    builder_version: Literal["deterministic-report-builder-v1"] = "deterministic-report-builder-v1"
    task_id: UUIDText
    task_revision: int
    source_content_sha256: Hash
    business_content_sha256: Hash
    generated_at: str
    title: Annotated[str, Field(min_length=1)]
    report_type: Literal["company_period_change", "company_same_period_comparison"]
    research_question: Annotated[str, Field(min_length=1)]
    research_scope: TemplateRequest
    executive_summary: list[str]
    side_labels: Annotated[dict[Literal["first", "second"], str], Field(min_length=2, max_length=2)]
    financial_facts: Annotated[list[FactRow], Field(min_length=6, max_length=6)]
    financial_analysis: Annotated[list[AnalysisRow], Field(min_length=3, max_length=3)]
    operating_information: Annotated[list[OperatingParagraph], Field(min_length=1, max_length=8)]
    model_interpretations: Annotated[list[PendingInterpretation], Field(max_length=4)]
    unresolved_questions: list[str]
    limitations: list[str]
    evidence_appendix: ReportEvidence  # Complete upstream audit snapshots, never free model prose.
    field_verification: list[FieldVerification]
    status: Literal["qualified_draft", "simulated_draft"]
    test_mode: Literal["simulated_test"] | None
    watermark: str | None
    persisted: Literal[False] = False
    human_review_status: Literal["pending"] = "pending"
    verified_operating_attribution: Literal[False] = False

    @model_validator(mode="after")
    def trustworthy_identity(self) -> "ReportDraft":
        simulated = self.test_mode == "simulated_test"
        if (self.status == "simulated_draft") != simulated or bool(self.watermark) != simulated:
            raise ValueError("report_simulation_label_mismatch")
        if self.report_type != self.research_scope.template:
            raise ValueError("report_template_mismatch")
        expected_kind = "simulated_test" if simulated else "local_operator"
        slots = {(f.side, f.metric_key) for f in self.financial_facts}
        if len(slots) != 6 or any(
            f.confirmation_kind != expected_kind for f in self.financial_facts
        ):
            raise ValueError("report_fact_group_mismatch")
        for f in self.financial_facts:
            side = getattr(self.research_scope, f.side)
            choice = next(c for c in side.choices if c.metric_key == f.metric_key)
            if (
                f.company_id != side.company_id
                or f.period != side.period.year
                or (f.fact_id, f.fact_set_id, f.document_id, f.disclosure_version)
                != (
                    choice.fact_id,
                    choice.fact_set_id,
                    choice.document_id,
                    choice.disclosure_version,
                )
            ):
                raise ValueError("report_scope_fact_mismatch")
        comparison = self.report_type == "company_same_period_comparison"
        if len({a.metric_key for a in self.financial_analysis}) != 3:
            raise ValueError("report_duplicate_analysis")
        for a in self.financial_analysis:
            ids = {f.side: f.fact_id for f in self.financial_facts if f.metric_key == a.metric_key}
            if (
                (a.first_fact_id, a.second_fact_id) != (ids["first"], ids["second"])
                or a.direction != ("B_minus_A" if comparison else "current_minus_previous")
                or a.percentage_formula_id
                != (
                    "financial_company_relative_signed_base_v1"
                    if comparison
                    else "financial_yoy_signed_base_v1"
                )
            ):
                raise ValueError("report_analysis_fact_mismatch")
        numbers = {d.citation.number for d in self.operating_information}
        if len(numbers) != len(self.operating_information):
            raise ValueError("report_duplicate_citation")
        for d in self.operating_information:
            if d.text != d.citation.text:
                raise ValueError("report_original_mismatch")
        for interpretation in self.model_interpretations:
            if not set(interpretation.citations) <= numbers:
                raise ValueError("report_pending_citation_mismatch")
        return self
