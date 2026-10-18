"""D23 read-only history and transactional append; no startup migrations or execution."""

from contextlib import closing
import sqlite3
from typing import Any, cast
from app.agent.revenue_confirmation import RevenueConfirmationError
from app.agent.sqlite_financial_facts import SQLiteRevenueConfirmationRepository
from app.documents.source_models import SourceError
from app.documents.source_repository import SQLiteSourceRepository
from app.research.models import canonical, sha
from app.research.repository import HistoryError
from app.research.task_repository import TaskRepository
from app.reports.persistence_contracts import ReportRevision


def source_refs(value: dict[str, Any]) -> list[tuple[Any, ...]]:
    return sorted(
        (r["document_id"], r["source_revision"], r["content_sha256"])
        for r in value["trusted_snapshot"]["evidence_appendix"]["selected_reports"]
    )


def fact_refs(value: dict[str, Any]) -> list[tuple[Any, ...]]:
    return sorted(
        (
            r["side"],
            r["metric_key"],
            r["fact_id"],
            r["fact_set_id"],
            r["receipt_id"],
            r["disclosure_version"],
        )
        for r in value["trusted_snapshot"]["financial_facts"]
    )


class ReportRepository:
    def __init__(self, tasks: TaskRepository):
        self.tasks, self.workspace = tasks, tasks.workspace
        self.reader = SQLiteRevenueConfirmationRepository(
            tasks.registry._database_path, initialize=False
        )
        self.sources = SQLiteSourceRepository(tasks.registry)

    def read_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.tasks.registry._database_path.resolve().as_uri() + "?mode=ro", uri=True
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        return conn

    def head(self, conn: sqlite3.Connection, report_id: str) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM reports WHERE workspace_id=? AND report_id=?",
            (self.workspace, report_id),
        ).fetchone()
        if row is None:
            raise HistoryError("resource_not_found", 404)
        stats = conn.execute(
            "SELECT count(*),max(revision) FROM report_revisions "
            "WHERE workspace_id=? AND report_id=?",
            (self.workspace, report_id),
        ).fetchone()
        if stats[0] != row["current_revision"] or stats[1] != row["current_revision"]:
            raise HistoryError("report_integrity_error")
        return cast(sqlite3.Row, row)

    def load(self, conn: sqlite3.Connection, report_id: str, revision: int) -> dict[str, Any]:
        row = conn.execute(
            "SELECT * FROM report_revisions WHERE workspace_id=? AND report_id=? AND revision=?",
            (self.workspace, report_id, revision),
        ).fetchone()
        if row is None:
            raise HistoryError("resource_not_found", 404)
        try:
            if sha(row["canonical_payload"]) != row["payload_sha256"]:
                raise ValueError()
            value = ReportRevision.model_validate_json(row["canonical_payload"]).model_dump(
                mode="json"
            )
            snapshot = value["trusted_snapshot"]
            if (
                canonical(value) != row["canonical_payload"]
                or any(
                    value[k] != row[k]
                    for k in (
                        "workspace_id",
                        "report_id",
                        "revision",
                        "parent_revision",
                        "operation_id",
                        "created_at",
                        "schema_version",
                    )
                )
                or any(
                    snapshot[k] != row[k]
                    for k in (
                        "task_id",
                        "task_revision",
                        "builder_version",
                        "source_content_sha256",
                    )
                )
                or canonical(value["editor_revision"]) != row["editor_json"]
            ):
                raise ValueError()
            # Verify the D22 business digest using exactly its original builder input keys.
            business = {
                k: v
                for k, v in snapshot.items()
                if k
                not in {
                    "schema_version",
                    "builder_version",
                    "business_content_sha256",
                    "generated_at",
                    "persisted",
                    "human_review_status",
                    "verified_operating_attribution",
                }
            }
            if sha(canonical(business)) != snapshot["business_content_sha256"]:
                raise ValueError()
            key = (self.workspace, report_id, revision)
            sources = [
                tuple(r)
                for r in conn.execute(
                    "SELECT document_id,source_revision,content_sha256 FROM report_source_refs "
                    "WHERE workspace_id=? AND report_id=? AND revision=? ORDER BY document_id",
                    key,
                )
            ]
            facts = [
                tuple(r)
                for r in conn.execute(
                    "SELECT side,metric_key,fact_id,fact_set_id,receipt_id,disclosure_version "
                    "FROM report_fact_refs WHERE workspace_id=? AND report_id=? AND revision=? ORDER BY side,metric_key",
                    key,
                )
            ]
            op = conn.execute(
                "SELECT * FROM report_operations WHERE workspace_id=? AND operation_id=?",
                (self.workspace, value["operation_id"]),
            ).fetchone()
            if (
                sources != source_refs(value)
                or facts != fact_refs(value)
                or op is None
                or op["report_id"] != report_id
                or op["revision"] != revision
                or op["outcome"] != "stored"
            ):
                raise ValueError()
            return value
        except (ValueError, TypeError, KeyError):
            raise HistoryError("report_integrity_error") from None

    def eligibility(self, conn: sqlite3.Connection, value: dict[str, Any]) -> dict[str, Any]:
        snapshot = value["trusted_snapshot"]
        try:
            task = self.tasks.decode(self.tasks.row(conn, snapshot["task_id"]))
            if (
                task["revision"] != snapshot["task_revision"]
                or task["status"] != "completed"
                or task["execution_status"] != "idle"
                or task["error_code"]
                or sha(canonical(task["final_research_content"]))
                != snapshot["source_content_sha256"]
            ):
                return dict(status="invalidated", reason="report_task_changed")
            self.sources.verify_selection_in(
                conn, tuple(snapshot["evidence_appendix"]["selected_reports"])
            )
            groups = self.reader.recheck_financial_fact_sets_in(
                conn,
                workspace_id=self.workspace,
                receipt_ids=tuple(sorted({f["receipt_id"] for f in snapshot["financial_facts"]})),
                confirmation_kind="simulated_test" if snapshot["test_mode"] else "local_operator",
            )
            current = {g.receipt.receipt_id: g.to_payload() for g in groups}
            for f in snapshot["evidence_appendix"]["financial_facts"]:
                group = current[f["receipt_id"]]
                if (
                    not any(row == f["fact"] for row in group["facts"])
                    or group["disclosure_version"] != f["disclosure_version"]
                    or group["fact_set_id"] != f["fact_set_id"]
                ):
                    return dict(status="invalidated", reason="report_fact_changed")
            return dict(
                status="current_at_read",
                reason=None,
                semantic_review="pending",
                production_qualified=snapshot["test_mode"] is None,
                pdf_bytes_require_d6_recheck=True,
                check_scope="database_only",
            )
        except (SourceError, RevenueConfirmationError, HistoryError) as exc:
            return dict(status="invalidated", reason=exc.code)

    def public(self, conn: sqlite3.Connection, value: dict[str, Any]) -> dict[str, Any]:
        head = self.head(conn, value["report_id"])
        return dict(
            schema_version="report-detail-v1",
            report=value,
            payload_sha256=sha(canonical(value)),
            current_revision=head["current_revision"],
            current_eligibility=self.eligibility(conn, value),
        )

    def get(self, report_id: str, revision: int) -> dict[str, Any]:
        with closing(self.read_connection()) as conn, conn:
            conn.execute("BEGIN")
            return self.public(conn, self.load(conn, report_id, revision))

    def replay(
        self, conn: sqlite3.Connection, operation_id: str, digest: str | None = None
    ) -> dict[str, Any] | None:
        op = conn.execute(
            "SELECT * FROM report_operations WHERE workspace_id=? AND operation_id=?",
            (self.workspace, operation_id),
        ).fetchone()
        if op is None:
            return None
        if digest is not None and digest != op["request_sha"]:
            raise HistoryError("operation_request_conflict", 409)
        value = self.load(conn, op["report_id"], op["revision"])
        if value["operation_id"] != operation_id:
            raise HistoryError("report_integrity_error")
        return value

    def by_operation(self, operation_id: str) -> dict[str, Any]:
        with closing(self.read_connection()) as conn, conn:
            conn.execute("BEGIN")
            value = self.replay(conn, operation_id)
            if value is None:
                raise HistoryError("resource_not_found", 404)
            return self.public(conn, value)

    def page(self, limit: int, before: int | None) -> dict[str, Any]:
        with closing(self.read_connection()) as conn, conn:
            conn.execute("BEGIN")
            rows = conn.execute(
                "SELECT * FROM reports WHERE workspace_id=? AND sequence<? "
                "ORDER BY sequence DESC LIMIT ?",
                (self.workspace, before or 2**63 - 1, limit + 1),
            ).fetchall()
            items = []
            for row in rows[:limit]:
                value = self.load(conn, row["report_id"], row["current_revision"])
                self.head(conn, row["report_id"])
                snapshot = value["trusted_snapshot"]
                items.append(
                    dict(
                        report_id=value["report_id"],
                        current_revision=value["revision"],
                        title=value["editor_revision"]["title"] or snapshot["title"],
                        created_at=row["created_at"],
                        task_id=snapshot["task_id"],
                        task_revision=snapshot["task_revision"],
                        test_mode=snapshot["test_mode"],
                        watermark=snapshot["watermark"],
                        current_eligibility=self.eligibility(conn, value),
                    )
                )
            return dict(
                schema_version="report-history-v1",
                items=items,
                next_before=rows[limit - 1]["sequence"] if len(rows) > limit else None,
            )

    def append(
        self, conn: sqlite3.Connection, value: ReportRevision, digest: str
    ) -> dict[str, Any]:
        raw = value.model_dump(mode="json")
        s = raw["trusted_snapshot"]
        key = (self.workspace, value.report_id, value.revision)
        if value.revision == 1:
            conn.execute(
                "INSERT INTO reports(workspace_id,report_id,created_at,current_revision) VALUES(?,?,?,1)",
                (self.workspace, value.report_id, value.created_at),
            )
        conn.execute(
            "INSERT INTO report_revisions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                *key,
                value.parent_revision,
                value.operation_id,
                s["task_id"],
                s["task_revision"],
                value.schema_version,
                s["builder_version"],
                s["source_content_sha256"],
                canonical(raw),
                sha(canonical(raw)),
                canonical(raw["editor_revision"]),
                value.created_at,
            ),
        )
        for ref in source_refs(raw):
            conn.execute("INSERT INTO report_source_refs VALUES(?,?,?,?,?,?)", (*key, *ref))
        for ref in fact_refs(raw):
            conn.execute("INSERT INTO report_fact_refs VALUES(?,?,?,?,?,?,?,?,?)", (*key, *ref))
        conn.execute(
            "INSERT INTO report_operations VALUES(?,?,?,?,?,'stored')",
            (self.workspace, value.operation_id, digest, value.report_id, value.revision),
        )
        if value.parent_revision:
            updated = conn.execute(
                "UPDATE reports SET current_revision=? WHERE workspace_id=? AND report_id=? AND current_revision=?",
                (value.revision, self.workspace, value.report_id, value.parent_revision),
            )
            if updated.rowcount != 1:
                raise HistoryError("report_revision_conflict", 409)
        return self.load(conn, value.report_id, value.revision)
