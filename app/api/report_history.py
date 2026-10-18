"""D23 history-only assembly over an already migrated DB; no sources/models/index needed."""

from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
from fastapi import FastAPI
from app.api.companies import create_company_router
from app.api.report_drafts import create_report_router
from app.api.research_tasks import create_task_router
from app.companies.migrations import MIGRATIONS
from app.companies.service import CompanyService
from app.companies.sqlite_repository import SQLiteCompanyRepository
from app.research.task_repository import TaskRepository
from app.reports.repository import ReportRepository
from app.reports.service import ReportService
from app.documents.source_service import DocumentSourceService
from app.agent.financial_analysis import IsolatedAnalysisTestConfig


class ReadOnlyReportRegistry(SQLiteCompanyRepository):
    def __init__(self, database_path: Path):
        self._database_path = database_path.resolve()
        with closing(self._connect()) as conn:
            actual = [
                tuple(r)
                for r in conn.execute(
                    "SELECT version,name,checksum FROM analyst_schema_migrations ORDER BY version"
                )
            ]
        expected = [
            (v, n, hashlib.sha256("\n".join(ddl).encode()).hexdigest()) for v, n, ddl in MIGRATIONS
        ]
        if actual != expected:
            raise RuntimeError("report_history_requires_reviewed_migration_9")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._database_path.as_uri() + "?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        return conn


def create_report_history_app(
    database_path: Path,
    workspace: str = "demo",
    *,
    sources: DocumentSourceService | None = None,
    isolated_test: IsolatedAnalysisTestConfig | None = None,
) -> FastAPI:
    registry = ReadOnlyReportRegistry(database_path)
    tasks = TaskRepository(registry, workspace)
    app = FastAPI(title="FinDoc report history · read only")
    companies = create_company_router(CompanyService(registry, workspace_id=workspace))
    companies.routes = [
        r for r in companies.routes if getattr(r, "methods", set()) <= {"GET", "HEAD"}
    ]
    app.include_router(companies)
    app.include_router(create_task_router(tasks))
    if sources is not None:
        if sources.repository.registry._database_path.resolve() != database_path.resolve():
            raise ValueError("report_history_source_database_mismatch")
        service = ReportService(tasks, sources, isolated_test=isolated_test)
        reports = create_report_router(service)
        # A verifier enables deterministic GET export, never draft/save/resume routes.
        reports.routes = [
            r for r in reports.routes if getattr(r, "methods", set()) <= {"GET", "HEAD"}
        ]
    else:
        reports = create_report_router(repository=ReportRepository(tasks))
    app.include_router(reports)
    return app
