"""Read-only exact-revision export with two PDF checks and a fresh final DB fence."""

from contextlib import closing
from typing import Any
from pydantic import ValidationError
from app.agent.revenue_confirmation import RevenueConfirmationError
from app.documents.source_models import SourceError
from app.research.models import canonical, sha
from app.research.repository import HistoryError
from app.reports.contracts import GenerateDraft
from app.reports.repository import ReportRepository
from app.reports.service import ReportService
from app.reports.markdown import filename, render


class ReportExportService:
    def __init__(self, verifier: ReportService):
        self.verifier = verifier
        self.repository = ReportRepository(verifier.tasks)

    def read(
        self, conn: Any, report_id: str, revision: int
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        repo = self.repository
        head = repo.head(conn, report_id)
        value = repo.load(conn, report_id, revision)
        s = value["trusted_snapshot"]
        # Verify every chain member's schema/SHA/refs/operation and common parent research.
        for rev in range(1, head["current_revision"] + 1):
            member = repo.load(conn, report_id, rev)
            if member["trusted_snapshot"]["task_id"] != s["task_id"]:
                raise HistoryError("report_parent_task_conflict", 409)
        task = self.verifier.admission(
            conn, GenerateDraft(task_id=s["task_id"], expected_revision=s["task_revision"])
        )
        # Compare all business fields with their frozen upstream projection, without generation,
        # arithmetic, model execution or modifying either persisted object.
        projected = self.verifier.builder.business_fields(task)
        if sha(canonical(projected)) != s["business_content_sha256"]:
            raise HistoryError("report_saved_snapshot_mismatch", 409)
        return value, task

    async def export(self, report_id: str, revision: int) -> tuple[bytes, str, str, bool]:
        try:
            with closing(self.repository.read_connection()) as conn, conn:
                conn.execute("BEGIN")
                value, task = self.read(conn, report_id, revision)
            await self.verifier.pdf_evidence(task)
            content = render(value)
            await self.verifier.pdf_evidence(task)
            with closing(self.repository.read_connection()) as conn, conn:
                conn.execute("BEGIN")
                final, final_task = self.read(conn, report_id, revision)
                if canonical(final) != canonical(value) or canonical(final_task) != canonical(task):
                    raise HistoryError("report_export_changed", 409)
            return (
                content,
                filename(value),
                sha(canonical(value)),
                bool(value["trusted_snapshot"]["test_mode"]),
            )
        except (SourceError, RevenueConfirmationError) as exc:
            raise HistoryError(exc.code, 409) from exc
        except (ValidationError, KeyError, TypeError, ValueError, StopIteration) as exc:
            raise HistoryError("report_content_integrity_error", 409) from exc
