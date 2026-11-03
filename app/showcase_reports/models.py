"""Server adapter contract; these DTOs are never accepted from HTTP clients."""

from typing import Literal, Protocol
from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Finding(Strict):
    finding_id: str
    kind: Literal[
        "confirmed_financial", "sourced_excerpt", "model_interpretation", "unresolved_question"
    ]
    text: str = Field(max_length=8000)
    financial_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[dict] = Field(default_factory=list)
    data_origin: Literal["live", "seed", "fake"]
    source_status: Literal["current", "stale", "unavailable"]
    transcription_review_status: str = "unreviewed"
    interpretation_review_status: str = "unreviewed"
    numeric_claim_status: Literal["no_numeric_claim", "numeric_claim_unverified"] | None = None


class VerifiedJobSnapshot(Strict):
    job_id: str
    workspace_id: str
    state: Literal["completed"]
    schema_version: Literal["verified-report-job-v2"] = "verified-report-job-v2"
    company_name: str
    period_label: str
    data_origin: Literal["live", "seed", "fake"]
    findings: list[Finding] = Field(max_length=100)
    limitations: list[str] = Field(default_factory=list)


class VerifiedJobReader(Protocol):
    async def __call__(self, job_id: str) -> VerifiedJobSnapshot:
        """Read-only: verify scope, completion, refs and deterministically rendered financial text.

        Must not call models or grant facts. Must reject inaccessible jobs. Re-read
        current source status on every call, preserving the published finding text.
        """
        ...
