"""D23 immutable server snapshot and independent, unverified editor declarations."""

from typing import Annotated, Literal
from pydantic import Field, model_validator
from app.research.template_contracts import StrictContract, Id
from app.research.task_contracts import UUIDText
from app.reports.contracts import ReportDraft

Positive = Annotated[int, Field(ge=1)]
Title = Annotated[str, Field(min_length=1, max_length=200)]
Conclusion = Annotated[str, Field(min_length=1, max_length=2000)]


class EditIntent(StrictContract):
    title: Title | None = None
    conclusions: Annotated[list[Conclusion], Field(max_length=4)] = Field(default_factory=list)


class SaveReport(StrictContract):
    operation_id: UUIDText
    task_id: UUIDText
    expected_task_revision: Positive
    edits: EditIntent = Field(default_factory=EditIntent)


class CreateRevision(SaveReport):
    expected_report_revision: Positive


class EditorRevision(EditIntent):
    origin: Literal["user_edit"] = "user_edit"
    validation_status: Literal["pending_semantic_review"] = "pending_semantic_review"
    verified_operating_attribution: Literal[False] = False
    qualification_limit: Literal["user_assertions_unverified"] = "user_assertions_unverified"


class ReportRevision(StrictContract):
    schema_version: Literal["report-revision-v1"] = "report-revision-v1"
    workspace_id: Id
    report_id: UUIDText
    revision: Positive
    parent_revision: Positive | None
    operation_id: UUIDText
    created_at: str
    persisted: Literal[True] = True
    trusted_snapshot: ReportDraft
    editor_revision: EditorRevision

    @model_validator(mode="after")
    def parent(self) -> "ReportRevision":
        if self.parent_revision != (self.revision - 1 if self.revision > 1 else None):
            raise ValueError("report_parent_revision_mismatch")
        return self
