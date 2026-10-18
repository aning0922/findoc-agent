"""Isolated D22 browser app, persisted D21 input, no model/retriever assembly."""

import os
from pathlib import Path
from tempfile import gettempdir
from app.api.research_tasks import create_task_router
from app.api.report_drafts import create_report_router
from app.agent.financial_analysis import IsolatedAnalysisTestConfig
from app.reports.service import ReportService
from app.research.task_repository import TaskRepository
from tests.support.d19_runtime import reopen


def create_d22_app():
    root = Path(os.environ["FINDOC_D22_RUNTIME_ROOT"]).resolve()
    if not root.name.startswith("findoc-d11-d22-") or not root.is_relative_to(
        Path(gettempdir()).resolve()
    ):
        raise ValueError("isolated_d22_root_required")
    h = reopen(root)
    app = h.client.app
    tasks = TaskRepository(h.registry, "demo")
    app.include_router(create_task_router(tasks))
    app.include_router(
        create_report_router(
            ReportService(tasks, h.service, isolated_test=IsolatedAnalysisTestConfig(root))
        )
    )
    return app
