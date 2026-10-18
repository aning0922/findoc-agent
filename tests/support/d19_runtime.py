"""Isolated test-only reassembly over existing SQLite/PDFs; never production switches."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock

from app.companies.service import CompanyService
from app.companies.sqlite_repository import SQLiteCompanyRepository
from app.documents.sqlite_repository import SQLiteDocumentRepository
from app.documents.local_object_store import LocalObjectStore
from app.documents.service import DocumentService
from app.documents.source_service import DocumentSourceService
from app.documents.source_repository import SQLiteSourceRepository
from tests.test_financial_reviews import assemble
from tests.test_d18_templates import service
from app.research.task_repository import TaskRepository
from app.agent.operating_research_graph import PersistentTemplateService


def reopen(root: Path):
    h = SimpleNamespace(root=root, db=root / "documents.db")
    h.docs = SQLiteDocumentRepository(h.db)
    h.registry = SQLiteCompanyRepository(h.db)
    h.companies = CompanyService(h.registry, workspace_id="demo")
    h.objects = LocalObjectStore(root / "objects")
    h.documents = DocumentService(
        repository=h.docs, object_store=h.objects, dispatcher=Mock(), workspace_id="demo"
    )
    h.sources = SQLiteSourceRepository(h.registry)
    h.service = DocumentSourceService(
        documents=h.documents, objects=h.objects, companies=h.companies, repository=h.sources
    )
    return assemble(h)


def persistent(h, simulated=False):
    templates = service(h, simulated)
    templates.scope.search = AsyncMock(
        return_value=()
    )  # D21 semantic retrieval/model chain excluded.
    repo = TaskRepository(h.registry, "demo")
    return repo, PersistentTemplateService(templates, repo)
