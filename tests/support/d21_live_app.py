"""Explicit isolated simulated_test assembly with actual BGE/Milvus/LLM. Never production."""

import os
from pathlib import Path
import sys
from tempfile import gettempdir

from app.api.runtime_factory import create_runtime_app
from app.api.research_tasks import create_task_router
from app.agent.financial_analysis import IsolatedAnalysisTestConfig
from app.agent.operating_research_graph import PersistentTemplateService
from app.research.templates import TemplateService
from app.research.task_repository import TaskRepository
from tests.support.d19_runtime import reopen


def create_d21_app():
    root = Path(os.environ["FINDOC_D21_RUNTIME_ROOT"]).resolve()
    product = Path.cwd().resolve()
    if not root.name.startswith("findoc-d11-d21-") or not root.is_relative_to(
        Path(gettempdir()).resolve()
    ):
        raise RuntimeError("isolated_d21_simulated_root_required")

    def audit(event, args):
        if (
            event == "sqlite3.connect"
            and args[0] != ":memory:"
            and not Path(args[0]).resolve().is_relative_to(root)
        ):
            raise RuntimeError("sqlite_outside_d21_root")
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(args[0])).resolve()
            mode, flags = args[1:3]
            writes = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                isinstance(flags, int)
                and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            )
            if writes and any(
                path.is_relative_to(p)
                for p in (
                    product.parent / "findoc-rag",
                    product.parent / "findoc-v1-product-design",
                    product / "data/runtime",
                )
            ):
                raise RuntimeError("protected_d21_write")

    sys.addaudithook(audit)
    live = create_runtime_app(root)
    h = reopen(root)
    templates = TemplateService(
        preparer=live.state.selection_preparer,
        facts=h.confirmations,
        workspace_id="demo",
        scope=live.state.selected_scope_search,
        isolated_test=IsolatedAnalysisTestConfig(root),
        model=live.state.template_service.model,
    )
    repository = TaskRepository(h.registry, "demo")
    repository.recover_interrupted()
    app = h.client.app
    app.include_router(
        create_task_router(repository, PersistentTemplateService(templates, repository))
    )
    app.state.template_service = templates
    app.state.task_repository = repository
    app.state.financial_test_service = h.confirmations
    app.state.live_runtime = live
    app.router.on_shutdown.extend(live.router.on_shutdown)
    return app
