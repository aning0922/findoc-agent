"""Versioned, strict research envelope. Never deserialize arbitrary model output."""

from datetime import datetime
import hashlib
import json
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

VERSION = "research-run-v1"
CONFIG = "d17-verified-excerpts-v1-no-retry"
ERRORS = {
    "retrieval_error",
    "evidence_validation_error",
    "context_budget_error",
    "llm_error",
    "citation_validation_error",
    "source_changed",
    "interrupted",
    "execution_error",
}
REASONS = {"empty_retrieval", "insufficient_evidence", "requires_confirmed_financial_analysis", "unsupported_table_structure"}


def canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def operation(value: str) -> str:
    if str(UUID(value)) != value:
        raise ValueError("invalid_operation_id")
    return value


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Identity(Strict):
    workspace_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    report_year: int = Field(ge=1, le=9999)
    report_type: str
    period_start: str
    period_end: str
    basis: str
    source_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    attempt: int = Field(ge=1)
    parser_version: str = Field(min_length=1)


class Citation(Identity):
    number: int = Field(ge=1)
    chunk_id: str = Field(min_length=1)
    physical_page: int = Field(ge=1)
    source_file: str = Field(min_length=1)
    text: str = Field(min_length=1)
    kind: Literal["paragraph", "table"]
    verification: Literal["exact_original_with_context"]


class Result(Strict):
    schema_version: Literal["research-answer-v1"] = "research-answer-v1"
    selection_id: str
    documents: list[Identity]
    outcome: Literal["answered", "refused", "system_error"]
    content: str
    citations: list[Citation]
    reason: str | None = None
    error_code: str | None = None
    answer_mode: Literal["verified_excerpts"] | None = None
    human_review: Literal["pending"] | None = None

    @model_validator(mode="after")
    def check(self) -> Self:
        if self.outcome == "answered":
            if (
                not 1 <= len(self.citations) <= 8
                or self.reason is not None
                or self.error_code is not None
                or self.answer_mode != "verified_excerpts"
                or self.human_review != "pending"
            ):
                raise ValueError("invalid_answer")
            docs = {d.document_id: d.model_dump() for d in self.documents}
            numbers = set()
            keys = set()
            for c in self.citations:
                identity = {k: getattr(c, k) for k in Identity.model_fields}
                key = (c.workspace_id, c.document_id, c.source_revision, c.chunk_id)
                if docs.get(c.document_id) != identity or c.number in numbers or key in keys:
                    raise ValueError("invalid_citation_identity")
                numbers.add(c.number)
                keys.add(key)
            expected = "\n\n".join(
                f"{c.report_year}年报《{c.source_file}》原文：\n{c.text}\n[{c.number}]"
                for c in self.citations
            )
            if self.content != expected:
                raise ValueError("content_not_original_excerpts")
        else:
            if self.content or self.citations or self.answer_mode or self.human_review:
                raise ValueError("non_answer_has_content")
            if self.outcome == "refused":
                if self.reason not in REASONS or self.error_code is not None:
                    raise ValueError("invalid_refusal")
            elif self.error_code not in ERRORS or self.reason is not None:
                raise ValueError("invalid_error")
        return self


class Envelope(Strict):
    schema_version: Literal["research-run-v1"] = "research-run-v1"
    execution_config_version: Literal["d17-verified-excerpts-v1-no-retry"] = (
        "d17-verified-excerpts-v1-no-retry"
    )
    execution_config: dict[str, str | int]
    run_id: str
    operation_id: str
    workspace_id: str
    query: str = Field(min_length=1, max_length=1000)
    document_ids: list[str]
    selection_id: str
    documents: list[Identity] = Field(min_length=1)
    created_at: str
    ended_at: str | None = None
    status: Literal["running", "answered", "refused", "system_error"] = "running"
    result: Result | None = None

    @model_validator(mode="after")
    def check(self) -> Self:
        operation(self.run_id)
        operation(self.operation_id)
        started = datetime.fromisoformat(self.created_at)
        if started.tzinfo is None or not self.query.strip():
            raise ValueError("invalid_start")
        if (
            self.document_ids != sorted(set(self.document_ids))
            or self.document_ids != [d.document_id for d in self.documents]
            or any(d.workspace_id != self.workspace_id for d in self.documents)
        ):
            raise ValueError("invalid_scope")
        # D15 selection hash uses ASCII canonical serialization; retain its exact contract.
        expected = hashlib.sha256(
            json.dumps(
                [d.model_dump() for d in self.documents], sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        if self.selection_id != expected:
            raise ValueError("invalid_selection_hash")
        if self.status == "running":
            if self.result is not None or self.ended_at is not None:
                raise ValueError("running_with_result")
        else:
            if (
                self.result is None
                or self.result.outcome != self.status
                or self.ended_at is None
                or self.result.documents != self.documents
                or self.result.selection_id != self.selection_id
            ):
                raise ValueError("invalid_terminal")
            ended = datetime.fromisoformat(self.ended_at)
            if ended.tzinfo is None or ended < started:
                raise ValueError("invalid_end")
        return self


def request_sha(document_ids: list[str], query: str) -> str:
    return sha(canonical(dict(document_ids=sorted(document_ids), query=query)))


def safe_error(envelope: Envelope, code: str) -> Result:
    return Result(
        selection_id=envelope.selection_id,
        documents=envelope.documents,
        outcome="system_error",
        content="",
        citations=[],
        error_code=code,
    )
