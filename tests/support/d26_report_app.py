"""D26 report-only assembly, fresh stopped simulated seed; no model or index."""

import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse
from app.api.research_tasks import create_task_router
from app.api.report_drafts import create_report_router
from app.agent.financial_analysis import IsolatedAnalysisTestConfig
from app.reports.service import ReportService
from app.research.task_repository import TaskRepository
from tests.support.d19_runtime import reopen


def create_app():
    runtime = Path(os.environ["FINDOC_UX_RUNTIME_ROOT"]).resolve()
    product = Path(__file__).resolve().parents[2]
    protected = [p.resolve() for p in product.parent.glob("findoc-*") if p.resolve() != product]

    def audit(event, args):
        if event == "socket.connect":
            raise RuntimeError("D26 reports: outgoing connections forbidden")
        if event == "sqlite3.connect" and args[0] != ":memory:":
            raw = args[0]
            path = Path(
                unquote(urlparse(raw).path) if str(raw).startswith("file:") else raw
            ).resolve()
            if not path.is_relative_to(runtime):
                raise RuntimeError("D26 reports: foreign SQLite rejected")
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            if any(Path(os.fsdecode(args[0])).resolve().is_relative_to(d) for d in protected):
                raise RuntimeError("D26 reports: protected worktree access rejected")

    sys.addaudithook(audit)
    h = reopen(runtime)
    app = h.client.app
    tasks = TaskRepository(h.registry, "demo")
    app.include_router(create_task_router(tasks))
    app.include_router(
        create_report_router(
            ReportService(tasks, h.service, isolated_test=IsolatedAnalysisTestConfig(runtime))
        )
    )

    @app.get("/__test__/d26-counts")
    def counts():
        with h.registry._connect() as conn:
            return {
                t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                for t in [
                    "reports",
                    "report_revisions",
                    "report_operations",
                    "template_tasks",
                    "template_operations",
                ]
            }

    return app


def create_readonly_app():
    from app.api.report_history import create_report_history_app

    runtime = Path(os.environ["FINDOC_UX_RUNTIME_ROOT"]).resolve()
    # Existing initialized D26 source assembly; no graph, model or vector index.
    create_app()  # Install isolation guards, then discard write HTTP assembly.
    h = reopen(runtime)
    return create_report_history_app(
        h.db, sources=h.service, isolated_test=IsolatedAnalysisTestConfig(runtime)
    )
