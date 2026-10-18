"""Reopen only this round's stopped simulated seed; no source/company re-creation."""

import os
from pathlib import Path
from app.api.research_tasks import create_task_router
from tests.support.d26_report_app import create_app as guarded_readers
from tests.support.d19_runtime import reopen, persistent


def create_app():
    app = guarded_readers()  # Installs fresh-root SQLite/socket/protected-worktree guards.
    h = reopen(Path(os.environ["FINDOC_UX_RUNTIME_ROOT"]).resolve())
    repo, service = persistent(h, simulated=True)
    app.include_router(create_task_router(repo, service))
    return app
