"""Strict D19 requests: IDs are re-admission hints, never confirmation authority."""

from typing import Any
from typing import Annotated, Literal
from pydantic import Field, TypeAdapter, field_validator, model_validator
from app.research.operating_result import PlanResultV2, LimitedResearchContent
from app.research.template_contracts import (
    StrictContract,
    TemplateRequest,
    Id,
    Metric,
    PlanResult,
    State,
)

UUIDText = Annotated[
    str, Field(pattern=r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")
]


class StartTask(StrictContract):
    operation_id: UUIDText
    input: TemplateRequest


class ResumeFact(StrictContract):
    side: Literal["first", "second"]
    metric_key: Metric
    fact_set_id: Id
    fact_id: Id


class ResumeTask(StrictContract):
    operation_id: UUIDText
    expected_revision: Annotated[int, Field(ge=1)]
    facts: Annotated[tuple[ResumeFact, ...], Field(min_length=6, max_length=6)]

    @field_validator("facts", mode="before")
    @classmethod
    def immutable(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def complete(self) -> "ResumeTask":
        if len({(f.side, f.metric_key) for f in self.facts}) != 6:
            raise ValueError("six_unique_slots_required")
        return self


class TaskRecord(StrictContract):
    schema_version: Literal["persistent-template-task-v1"] = "persistent-template-task-v1"
    graph_version: Literal["d19-operating-graph-v1"] = "d19-operating-graph-v1"
    task_id: UUIDText
    workspace_id: Id
    operation_id: UUIDText
    created_at: str
    revision: int
    status: State
    execution_status: Literal["running", "idle"]
    input: TemplateRequest
    active_input: TemplateRequest
    budget: dict[str, Any]
    trace: list[dict[str, Any]]
    snapshot: PlanResult | None = None
    error_code: str | None = None
    waiting_checkpoint: bool = False
    persistence: Literal["persisted"] = "persisted"
    checkpointer: Literal[True] = True
    automatic_resume: Literal[False] = False
    final_research_content: None = None

    @model_validator(mode="after")
    def invariant(self) -> "TaskRecord":
        expected = ("template-budget-v1" if self.schema_version == "persistent-template-task-v1"
                    else "template-budget-v2")
        if self.budget.get("schema_version") != expected:
            raise ValueError("task_budget_version_mismatch")
        if self.schema_version == "persistent-template-task-v1" and self.status == "completed":
            raise ValueError("d21_completion_unsupported")
        if self.snapshot is not None and self.snapshot.status != self.status:
            raise ValueError("snapshot_status_mismatch")
        if self.waiting_checkpoint and (
            self.status != "awaiting_human_confirmation" or self.execution_status != "idle"
        ):
            raise ValueError("invalid_wait_checkpoint")
        return self


class StartTaskV2(StartTask):
    """Explicit new research; never changes a v1 task or its checkpoint."""
    run_version: Literal["d21-operating-graph-v2"]
    parent_task_id: UUIDText | None = None


class TaskRecordV2(TaskRecord):
    schema_version: Literal["persistent-template-task-v2"] = "persistent-template-task-v2"  # type: ignore[assignment]
    graph_version: Literal["d21-operating-graph-v2"] = "d21-operating-graph-v2"  # type: ignore[assignment]
    snapshot: PlanResultV2 | PlanResult | None = None
    final_research_content: LimitedResearchContent | None = None  # type: ignore[assignment]
    parent_task_id: UUIDText | None = None
    parent_budget_audit: dict[str, Any] | None = None


    @model_validator(mode="after")
    def result_identity(self) -> "TaskRecordV2":
        content = self.final_research_content
        if self.snapshot and self.snapshot.final_research_content != content:
            raise ValueError("task_result_mismatch")
        if (self.status == "completed") != (content is not None):
            raise ValueError("task_completion_requires_result")
        if content and (content.task_id != self.task_id or content.template != self.input.template
                        or content.input != self.active_input.model_dump(mode="json")):
            raise ValueError("result_task_identity_mismatch")
        return self


TASK_RECORD: TypeAdapter[TaskRecord | TaskRecordV2] = TypeAdapter(TaskRecord | TaskRecordV2)
