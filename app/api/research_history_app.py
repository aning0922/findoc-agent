"""DB-only recovery deployment, with D6 PDF routes and no model/search dependencies."""

from fastapi import FastAPI
import os
from pathlib import Path

from app.api.app import create_app
from app.api.research_runs import create_research_runs_router
from app.api.runtime_paths import DEFAULT_RUNTIME_ROOT
from app.companies.service import CompanyService
from app.companies.sqlite_repository import SQLiteCompanyRepository
from app.documents.local_object_store import LocalObjectStore
from app.documents.service import DocumentService
from app.documents.preparation import DocumentTaskPreparer
from app.documents.source_repository import SQLiteSourceRepository
from app.documents.source_service import DocumentSourceService
from app.documents.sqlite_repository import SQLiteDocumentRepository
from app.research.repository import ResearchOwner, ResearchRepository
from app.research.task_repository import TaskRepository
from app.api.research_tasks import create_task_router


class ReadOnlyDispatcher:
    def dispatch(self, document_id: str) -> bool:
        raise RuntimeError("history_only")


def create_history_app_from_env() -> FastAPI:
    root = Path(os.environ["FINDOC_RUNTIME_ROOT"])
    if not root.is_absolute() or root.resolve() == DEFAULT_RUNTIME_ROOT.resolve():
        raise ValueError("isolated_root_required")
    owner = ResearchOwner(root)
    try:
        registry = SQLiteCompanyRepository(root / "documents.db")
        history = ResearchRepository(registry, "demo")
        history.recover_interrupted()
        tasks = TaskRepository(registry, "demo")
        tasks.recover_interrupted()
        companies = CompanyService(registry, workspace_id="demo")
        objects = LocalObjectStore(root / "objects")
        documents = DocumentService(
            repository=SQLiteDocumentRepository(root / "documents.db"),
            object_store=objects,
            dispatcher=ReadOnlyDispatcher(),
            workspace_id="demo",
        )
        sources = DocumentSourceService(
            documents=documents,
            objects=objects,
            companies=companies,
            repository=SQLiteSourceRepository(registry),
        )
        app = create_app(documents, company_service=companies, source_service=sources)
        # Only read routes are installed on this recovery deployment.
        app.router.routes = [
            r for r in app.router.routes if not getattr(r, "methods", set()) - {"GET", "HEAD"}
        ]
        app.include_router(create_research_runs_router(history, focus_preparer=DocumentTaskPreparer(
            document_service=documents, sources=sources, workspace_id="demo",
        )))
        app.include_router(create_task_router(tasks))
        app.add_event_handler("shutdown", owner.close)
        return app
    except Exception:
        owner.close()
        raise
