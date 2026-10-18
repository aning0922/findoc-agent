"""Rebuild only from frozen D21, then re-admit and append in one shared transaction."""

from contextlib import closing
import uuid
from typing import Any
from pydantic import ValidationError
from app.agent.revenue_confirmation import RevenueConfirmationError
from app.documents.source_models import SourceError
from app.research.models import canonical, sha
from app.research.repository import HistoryError
from app.research.task_repository import now
from app.reports.contracts import GenerateDraft
from app.reports.persistence_contracts import (
    SaveReport,
    CreateRevision,
    EditorRevision,
    ReportRevision,
)
from app.reports.repository import ReportRepository
from app.reports.service import ReportService


class ReportPersistenceService:
    def __init__(self, drafts: ReportService):
        self.drafts = drafts
        self.repository = ReportRepository(drafts.tasks)

    def admit_replay_kind(self, value: dict[str, Any]) -> None:
        simulated = value["trusted_snapshot"]["test_mode"] == "simulated_test"
        if simulated != (self.drafts.kind == "simulated_test"):
            raise HistoryError("report_production_confirmation_required", 409)

    async def save(self, request: SaveReport, report_id: str | None = None) -> dict[str, Any]:
        if (report_id is not None) != isinstance(request, CreateRevision):
            raise HistoryError("report_request_mismatch", 422)
        expected_report_revision = (
            request.expected_report_revision if isinstance(request, CreateRevision) else None
        )
        repo = self.repository
        digest = sha(
            canonical(
                dict(
                    action="append" if report_id else "create",
                    report_id=report_id,
                    request=request.model_dump(mode="json"),
                )
            )
        )
        try:
            # A committed operation is always replayed before PDF/build/admission, even if now invalid.
            with closing(repo.read_connection()) as conn, conn:
                conn.execute("BEGIN")
                old = repo.replay(conn, request.operation_id, digest)
                if old is not None:
                    self.admit_replay_kind(old)
                    return repo.public(conn, old)
                if report_id:
                    head = repo.head(conn, report_id)
                    if head["current_revision"] != expected_report_revision:
                        raise HistoryError("report_revision_conflict", 409)
                    previous = repo.load(conn, report_id, head["current_revision"])
                    if previous["trusted_snapshot"]["task_id"] != request.task_id:
                        raise HistoryError("report_parent_task_conflict", 409)
            admission = GenerateDraft(
                task_id=request.task_id, expected_revision=request.expected_task_revision
            )
            with closing(repo.tasks.registry._connect()) as conn, conn:
                conn.execute("BEGIN")
                task = self.drafts.admission(conn, admission)
            await self.drafts.pdf_evidence(task)
            snapshot = self.drafts.builder.build(task)
            await self.drafts.pdf_evidence(task)
            with closing(repo.tasks.registry._connect()) as conn, conn:
                conn.execute("BEGIN IMMEDIATE")
                old = repo.replay(conn, request.operation_id, digest)
                if old is not None:
                    self.admit_replay_kind(old)
                    saved = old
                else:
                    final = self.drafts.admission(conn, admission)
                    if canonical(task) != canonical(final):
                        raise HistoryError("report_task_changed", 409)
                    revision = 1
                    if report_id:
                        head = repo.head(conn, report_id)
                        if head["current_revision"] != expected_report_revision:
                            raise HistoryError("report_revision_conflict", 409)
                        parent = repo.load(conn, report_id, head["current_revision"])
                        if parent["trusted_snapshot"]["task_id"] != request.task_id:
                            raise HistoryError("report_parent_task_conflict", 409)
                        revision = head["current_revision"] + 1
                    saved = repo.append(
                        conn,
                        ReportRevision(
                            workspace_id=repo.workspace,
                            report_id=report_id or str(uuid.uuid4()),
                            revision=revision,
                            parent_revision=revision - 1 if revision > 1 else None,
                            operation_id=request.operation_id,
                            created_at=now(),
                            trusted_snapshot=snapshot,
                            editor_revision=EditorRevision(**request.edits.model_dump()),
                        ),
                        digest,
                    )
            # Commit, including deferred constraints, succeeded before publishing any ID/body.
            return repo.get(saved["report_id"], saved["revision"])
        except (SourceError, RevenueConfirmationError) as exc:
            raise HistoryError(exc.code, 409) from exc
        except (ValidationError, KeyError, TypeError, ValueError, StopIteration) as exc:
            raise HistoryError("report_content_integrity_error", 409) from exc
