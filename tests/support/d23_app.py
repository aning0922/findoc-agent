"""Isolated D23 write assembly from real persisted inputs; no model/index configuration."""

import os
from pathlib import Path
from tempfile import gettempdir
from app.api.report_history import create_report_history_app
from tests.support.d22_app import create_d22_app


def create_d23_app():
    # D22 test assembly remains the one existing source/fact API wiring.
    return create_d22_app()


def create_d23_history_app():
    root = Path(os.environ["FINDOC_D22_RUNTIME_ROOT"]).resolve()
    if not root.name.startswith("findoc-d11-d22-") or not root.is_relative_to(
        Path(gettempdir()).resolve()
    ):
        raise ValueError("isolated_d23_root_required")
    return create_report_history_app(root / "documents.db")
