"""D10 browser isolation: real four fixed-SHA PDFs/parser/SQLite/HTTP.

Embedding/index/chunk IDs are controlled via the existing D6 Harness. All financial accepts are server-labeled simulated_test. No human consent. No LLM,
Milvus, real BGE, RAG or Agent execution is asserted by this browser server.
Never point this factory at production or the learning repository runtime.
"""

import hashlib
import json
import os
from pathlib import Path
import sys

from tests.test_financial_reviews import assemble
from app.companies.models import CompanyCreate
from app.documents.models import DocumentStatus
from tests.test_document_sources import Harness, metadata


def create_real_financial_facts_app():
    root = Path(os.environ["FINDOC_D10_RUNTIME_ROOT"]).resolve()
    if not root.is_absolute() or not root.name.startswith("findoc-d10-"):
        raise RuntimeError("D10 requires a separate findoc-d10-* temporary root")
    product = Path.cwd().resolve()
    learning = product.parent / "findoc-rag"
    if root.is_relative_to(product) or root.is_relative_to(learning):
        raise RuntimeError("D10 requires a temporary root outside both repositories")
    root.mkdir(parents=True, exist_ok=True)
    if (root / "documents.db").exists() and os.environ.get("FINDOC_D10_ALLOW_REOPEN") != "1":
        raise RuntimeError("D10 browser seed requires an empty new runtime")

    def audit(event, args):
        if event == "sqlite3.connect" and args[0] != ":memory:":
            if not Path(args[0]).resolve().is_relative_to(root):
                raise RuntimeError("D10 rejected SQLite outside isolated runtime")
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(args[0])).resolve()
            mode, flags = args[1], args[2]
            writes = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                isinstance(flags, int)
                and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            )
            if writes and (
                path.is_relative_to(learning)
                or path.is_relative_to(product.parent / "findoc-v1-product-design")
                or path.is_relative_to(product / "data/runtime")
            ):
                raise RuntimeError("D10 rejected write to learning/default runtime")

    sys.addaudithook(audit)
    if (root / "documents.db").exists():
        # Explicit restart of the same isolated simulated runtime; no reseeding or extraction.
        from types import SimpleNamespace
        from unittest.mock import Mock
        from app.documents.sqlite_repository import SQLiteDocumentRepository
        from app.companies.sqlite_repository import SQLiteCompanyRepository
        from app.companies.service import CompanyService
        from app.documents.local_object_store import LocalObjectStore
        from app.documents.service import DocumentService
        from app.documents.source_repository import SQLiteSourceRepository
        from app.documents.source_service import DocumentSourceService

        h = SimpleNamespace(db=root / "documents.db")
        h.docs = SQLiteDocumentRepository(h.db)
        h.registry = SQLiteCompanyRepository(h.db)
        h.companies = CompanyService(h.registry, workspace_id="demo")
        h.objects = LocalObjectStore(root / "objects")
        h.documents = DocumentService(
            repository=h.docs, object_store=h.objects, dispatcher=Mock(), workspace_id="demo"
        )
        h.service = DocumentSourceService(
            documents=h.documents,
            objects=h.objects,
            companies=h.companies,
            repository=SQLiteSourceRepository(h.registry),
        )
        assemble(h)
        h.candidates.collect_metrics = Mock(side_effect=AssertionError("Restart reads must not extract"))
        print("D10 reopened existing simulated runtime; no PDF seed or extraction", flush=True)
        return h.client.app
    h = Harness(root)
    companies = {
        prefix: h.companies.create(CompanyCreate(name=name, security_code=code, exchange="SZSE"))
        for prefix, name, code in [
            ("midea", "美的集团股份有限公司", "000333"),
            ("gree", "珠海格力电器股份有限公司", "000651"),
        ]
    }
    reports = []
    for original in json.loads(Path("product/validation/sources.json").read_text()):
        raw = Path(original["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == original["sha256"]
        prefix, year = original["id"].split("-")
        result = h.upload(
            raw,
            {**metadata(companies[prefix].company_id, int(year)), "source_url": original["url"]},
            filename=f"{original['id']}.pdf",
        )
        assert result.status_code == 202, result.text
        doc = result.json()["document_id"]
        assert h.processor.process(doc).status == DocumentStatus.READY
        source = h.client.get(f"/documents/{doc}/source").json()
        source.pop("evidence_ids")
        reports.append({"report_id": original["id"], "source": source})
        print(f"D10 parsed {original['id']}: {source['physical_pages']} physical pages", flush=True)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "reports": reports,
                "isolation": str(root),
                "substitutions": ["embedding", "vector index", "chunk IDs"],
                "real": ["PDF", "parser", "SQLite", "source checks", "HTTP"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    assemble(h)
    return h.client.app
