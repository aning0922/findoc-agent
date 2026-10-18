"""Transactional claims and budget reservations; GET never enters the graph."""

from contextlib import closing
from collections.abc import Callable
import copy
from datetime import UTC, datetime
import sqlite3
import uuid
from typing import Any, cast

from app.agent.execution_budget import ExecutionBudget
from app.companies.sqlite_repository import SQLiteCompanyRepository
from app.agent.revenue_confirmation import RevenueConfirmationError
from app.documents.source_models import SourceError
from app.research.models import canonical, sha
from app.research.repository import HistoryError
from app.research.task_contracts import TaskRecord, TaskRecordV2, TASK_RECORD, StartTask, StartTaskV2, ResumeTask


def now() -> str:
    return datetime.now(UTC).isoformat()


class TaskRepository:
    def __init__(self, registry: SQLiteCompanyRepository, workspace: str):
        self.registry, self.workspace = registry, workspace

    def decode(self, row: sqlite3.Row) -> dict[str, Any]:
        try:
            if sha(row["payload"]) != row["payload_sha"]:
                raise ValueError()
            record = TASK_RECORD.validate_json(row["payload"])
            if any(
                getattr(record, k) != row[k]
                for k in ("task_id", "workspace_id", "operation_id", "revision")
            ):
                raise ValueError()
            value = record.model_dump(mode="json")
            if canonical(value) != row["payload"]:
                raise ValueError()
            ExecutionBudget.restore(value["budget"], checkpoint=lambda _: None)
            if sha(canonical(value["input"])) != row["request_sha"]:
                raise ValueError()
            return value
        except (ValueError, TypeError, KeyError):
            raise HistoryError("task_integrity_error") from None

    def row(self, conn: sqlite3.Connection, task_id: str) -> sqlite3.Row:
        value = conn.execute(
            "SELECT * FROM template_tasks WHERE workspace_id=? AND task_id=?",
            (self.workspace, task_id),
        ).fetchone()
        if value is None:
            raise HistoryError("resource_not_found", 404)
        return cast(sqlite3.Row, value)

    def get(self, task_id: str) -> dict[str, Any]:
        with closing(self.registry._connect()) as conn:
            return self.decode(self.row(conn, task_id))

    def public(self, value: dict[str, Any]) -> dict[str, Any]:
        value = copy.deepcopy(value)
        # Graph output is not publishable until checkpoint and release both commit.
        if value["execution_status"] == "running" and value["snapshot"]:
            value["snapshot"]["analysis_results"] = []
            value["snapshot"]["operating_evidence"] = None
            if value["schema_version"] == "persistent-template-task-v2":
                value["final_research_content"] = None
                value["snapshot"]["final_research_content"] = None
                if value["status"] == "completed":
                    value["status"] = value["snapshot"]["status"] = "collecting_explanation"
        if value["schema_version"] == "persistent-template-task-v2":
            value["publication_eligibility"] = self.publication_eligibility(value)
            value["execution_outcome"] = (
                "interrupted/unknown" if value["error_code"] in
                ("operating_provider_unknown", "interrupted_unknown_execution", "task_save_or_execution_unknown")
                else "running" if value["execution_status"] == "running"
                else value["status"]
            )
        return value

    def publication_eligibility(self, value: dict[str, Any]) -> dict[str, Any]:
        """DB-only current qualification, separate from immutable historical content."""
        if value["execution_status"] != "idle" or value["status"] != "completed":
            return dict(status="not_publishable", reason="research_not_completed")
        from app.documents.source_repository import SQLiteSourceRepository
        from app.agent.sqlite_financial_facts import SQLiteRevenueConfirmationRepository
        snap = value["snapshot"]
        try:
            with closing(self.registry._connect()) as conn, conn:
                conn.execute("BEGIN")
                SQLiteSourceRepository(self.registry).verify_selection_in(conn, tuple(snap["documents"]))
                reader = SQLiteRevenueConfirmationRepository(self.registry._database_path, initialize=False)
                reader.recheck_financial_fact_sets_in(conn, workspace_id=self.workspace,
                    receipt_ids=tuple(sorted({f["receipt_id"] for f in snap["facts"]})),
                    confirmation_kind="simulated_test" if snap["test_mode"] else "local_operator")
            return dict(status="current_at_read", reason=None,
                        semantic_review="pending", pdf_bytes_require_d6_recheck=True)
        except (SourceError, RevenueConfirmationError) as exc:
            return dict(status="invalidated", reason=exc.code)

    def by_operation(self, operation_id: str) -> dict[str, Any]:
        with closing(self.registry._connect()) as conn:
            row = conn.execute(
                "SELECT task_id FROM template_operations WHERE workspace_id=? AND operation_id=?",
                (self.workspace, operation_id),
            ).fetchone()
            if row is None:
                raise HistoryError("resource_not_found", 404)
            return self.decode(self.row(conn, row["task_id"]))

    def page(self, limit: int, before: int | None) -> dict[str, Any]:
        with closing(self.registry._connect()) as conn:
            rows = conn.execute(
                """SELECT * FROM template_tasks WHERE workspace_id=? AND sequence<?
                ORDER BY sequence DESC LIMIT ?""",
                (self.workspace, before or 2**63 - 1, limit + 1),
            ).fetchall()
            return dict(
                schema_version="template-task-history-v1",
                items=[self.public(self.decode(r)) for r in rows[:limit]],
                next_before=rows[limit - 1]["sequence"] if len(rows) > limit else None,
            )

    def write(
        self, conn: sqlite3.Connection, value: dict[str, Any], claim: str | None
    ) -> dict[str, Any]:
        value = TASK_RECORD.validate_python(value).model_dump(mode="json")
        payload = canonical(value)
        conn.execute(
            """UPDATE template_tasks SET revision=?,claim=?,payload=?,payload_sha=?
                        WHERE workspace_id=? AND task_id=?""",
            (value["revision"], claim, payload, sha(payload), self.workspace, value["task_id"]),
        )
        return self.decode(self.row(conn, value["task_id"]))

    def fence(self, conn: sqlite3.Connection, task_id: str, claim: str) -> dict[str, Any]:
        row = self.row(conn, task_id)
        if row["claim"] != claim:
            raise HistoryError("stale_execution_claim", 409)
        return self.decode(row)

    def replay(
        self, conn: sqlite3.Connection, op: str, digest: str, task_id: str | None = None
    ) -> dict[str, Any] | None:
        row = conn.execute(
            "SELECT * FROM template_operations WHERE workspace_id=? AND operation_id=?",
            (self.workspace, op),
        ).fetchone()
        if row is None:
            return None
        if row["request_sha"] != digest or (task_id and row["task_id"] != task_id):
            raise HistoryError("operation_request_conflict", 409)
        return self.decode(self.row(conn, row["task_id"]))

    def start(self, request: StartTask | StartTaskV2) -> tuple[dict[str, Any], str | None]:
        digest = sha(canonical(request.model_dump(mode="json")))
        with closing(self.registry._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            old = self.replay(conn, request.operation_id, digest)
            if old is not None:
                return old, None
            task_id, claim = str(uuid.uuid4()), str(uuid.uuid4())
            parent: dict[str, Any] | None = None
            if isinstance(request, StartTaskV2) and request.parent_task_id:
                parent = self.decode(self.row(conn, request.parent_task_id))
            extra: dict[str, Any] = (dict(parent_task_id=request.parent_task_id,
                          parent_budget_audit=parent["budget"] if parent else None)
                     if isinstance(request, StartTaskV2) else {})
            record_type = TaskRecordV2 if isinstance(request, StartTaskV2) else TaskRecord
            value = record_type(
                task_id=task_id,
                workspace_id=self.workspace,
                operation_id=request.operation_id,
                created_at=now(),
                revision=1,
                input=request.input,
                active_input=request.input,
                status="prepared",
                execution_status="running",
                budget=ExecutionBudget(version="template-budget-v2" if isinstance(request, StartTaskV2)
                                       else "template-budget-v1").durable(),
                trace=[dict(event="registered", at=now(), revision=1)],
                **extra,
            ).model_dump(mode="json")
            payload = canonical(value)
            conn.execute(
                """INSERT INTO template_tasks
                (task_id,workspace_id,operation_id,request_sha,revision,claim,payload,payload_sha)
                VALUES(?,?,?,?,?,?,?,?)""",
                (
                    task_id,
                    self.workspace,
                    request.operation_id,
                    sha(canonical(value["input"])),
                    1,
                    claim,
                    payload,
                    sha(payload),
                ),
            )
            conn.execute(
                "INSERT INTO template_operations VALUES(?,?,?,?,?)",
                (self.workspace, request.operation_id, task_id, digest, "running"),
            )
            return self.decode(self.row(conn, task_id)), claim

    def resume(self, task_id: str, request: ResumeTask) -> tuple[dict[str, Any], str | None]:
        raw = request.model_dump(mode="json")
        raw["facts"] = sorted(raw["facts"], key=lambda f: (f["side"], f["metric_key"]))
        digest = sha(canonical(raw))
        with closing(self.registry._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            old = self.replay(conn, request.operation_id, digest, task_id)
            if old is not None:
                return old, None
            row = self.row(conn, task_id)
            old = self.decode(row)
            if row["claim"]:
                raise HistoryError("task_busy", 409)
            if old["revision"] != request.expected_revision:
                raise HistoryError("task_revision_conflict", 409)
            if old["status"] != "awaiting_human_confirmation" or not old["waiting_checkpoint"]:
                raise HistoryError("task_not_resumable", 409)
            claim = str(uuid.uuid4())
            old.update(
                revision=old["revision"] + 1, execution_status="running", waiting_checkpoint=False
            )
            old["trace"].append(
                dict(
                    event="resume_claimed",
                    at=now(),
                    revision=old["revision"],
                    operation_id=request.operation_id,
                )
            )
            conn.execute(
                "INSERT INTO template_operations VALUES(?,?,?,?,?)",
                (self.workspace, request.operation_id, task_id, digest, "running"),
            )
            return self.write(conn, old, claim), claim

    def reserve(self, task_id: str, claim: str, budget: dict[str, Any]) -> None:
        with closing(self.registry._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            value = self.fence(conn, task_id, claim)
            if any(budget["used"][k] < v for k, v in value["budget"]["used"].items()):
                raise HistoryError("budget_regression")
            previous = value["budget"]
            if budget["schema_version"] != previous["schema_version"] or budget["limits"] != previous["limits"]:
                raise HistoryError("budget_version_change_forbidden")
            changed = {k: v for k, v in budget["used"].items() if v != previous["used"][k]}
            operations = [
                op for op in budget["operations"] if list(op) not in previous["operations"]
            ]
            if changed or operations:
                value["trace"].append(
                    dict(
                        event="budget_reserved",
                        at=now(),
                        revision=value["revision"],
                        counters=changed,
                        operations=operations,
                    )
                )
            value["budget"] = budget
            self.write(conn, value, claim)

    def save_session(
        self, task_id: str, claim: str, snapshot: dict[str, Any], budget: dict[str, Any]
    ) -> None:
        with closing(self.registry._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            value = self.fence(conn, task_id, claim)
            value.update(
                snapshot=snapshot,
                status=snapshot["status"],
                active_input=snapshot["input"],
                budget=budget,
                error_code=snapshot["error_code"],
            )
            if value["schema_version"] == "persistent-template-task-v2":
                value["final_research_content"] = snapshot["final_research_content"]
            value["trace"].append(
                dict(
                    event=snapshot["status"],
                    at=now(),
                    revision=value["revision"],
                    budget_used=budget["used"],
                    error_code=snapshot["error_code"],
                )
            )
            self.write(conn, value, claim)

    def release(
        self,
        task_id: str,
        claim: str,
        op: str,
        *,
        waiting: bool,
        admission: Callable[[sqlite3.Connection, dict[str, Any]], None],
    ) -> dict[str, Any]:
        with closing(self.registry._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            value = self.fence(conn, task_id, claim)
            try:
                admission(conn, value)
            except (SourceError, RevenueConfirmationError) as exc:
                waiting = False
                value.update(status="refused", error_code=exc.code)
                value["snapshot"].update(
                    status="refused",
                    must_wait_for_human=False,
                    error_code=exc.code,
                    analysis_results=[],
                    operating_evidence=None,
                )
                if value["schema_version"] == "persistent-template-task-v2":
                    value["final_research_content"] = None
                    value["snapshot"]["final_research_content"] = None
                for fact in value["snapshot"]["facts"]:
                    fact["readiness"] = "unverified_after_failure"
            value.update(
                execution_status="idle", waiting_checkpoint=waiting, revision=value["revision"] + 1
            )
            value["trace"].append(
                dict(event="checkpoint_committed", at=now(), revision=value["revision"])
            )
            conn.execute(
                "UPDATE template_operations SET outcome=? WHERE workspace_id=? AND operation_id=?",
                ("stored", self.workspace, op),
            )
            return self.write(conn, value, None)

    def recover_interrupted(self) -> int:
        # Startup only under the existing ResearchOwner. No lease takeover or unknown retries.
        with closing(self.registry._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT * FROM template_tasks WHERE workspace_id=? AND claim IS NOT NULL",
                (self.workspace,),
            ).fetchall()
            for row in rows:
                value = self.decode(row)
                snapshot = value["snapshot"]
                if snapshot:
                    snapshot.update(
                        status="failed",
                        must_wait_for_human=False,
                        error_code="interrupted_unknown_execution",
                        analysis_results=[],
                        operating_evidence=None,
                    )
                    if value["schema_version"] == "persistent-template-task-v2":
                        snapshot["final_research_content"] = None
                        value["final_research_content"] = None
                    for fact in snapshot["facts"]:
                        fact["readiness"] = "unverified_after_failure"
                value.update(
                    status="failed",
                    execution_status="idle",
                    waiting_checkpoint=False,
                    error_code="interrupted_unknown_execution",
                    revision=value["revision"] + 1,
                )
                value["trace"].append(
                    dict(
                        event="interrupted_unknown_execution", at=now(), revision=value["revision"]
                    )
                )
                self.write(conn, value, None)
                conn.execute(
                    "UPDATE template_operations SET outcome='interrupted' WHERE workspace_id=? AND task_id=? AND outcome='running'",
                    (self.workspace, value["task_id"]),
                )
            return len(rows)
