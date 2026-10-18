"""Isolated GET-only browser recovery with simulated facts; no BGE/Milvus/model assembly."""
import os
from pathlib import Path
from tempfile import gettempdir

from app.api.research_tasks import create_task_router
from app.research.repository import ResearchOwner
from app.research.task_repository import TaskRepository
from tests.support.d19_runtime import reopen


def create_d21_history_app():
    root = Path(os.environ['FINDOC_D21_RUNTIME_ROOT']).resolve()
    if not root.name.startswith('findoc-d11-d21-') or not root.is_relative_to(Path(gettempdir()).resolve()):
        raise ValueError('isolated_d21_history_root_required')
    owner = ResearchOwner(root)
    h = reopen(root)
    tasks = TaskRepository(h.registry, 'demo')
    tasks.recover_interrupted()
    app = h.client.app
    app.router.routes = [r for r in app.router.routes if not getattr(r,'methods',set()) - {'GET','HEAD'}]
    app.include_router(create_task_router(tasks))
    app.add_event_handler('shutdown', owner.close)
    return app
