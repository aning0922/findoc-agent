"""D8 browser isolation: real four fixed-SHA PDFs/parser/SQLite/HTTP.

Embedding/index/chunk IDs are controlled via the existing D6 Harness. No LLM,
Milvus, real BGE, RAG or Agent execution is asserted by this browser server.
Never point this factory at production or the learning repository runtime.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
from unittest.mock import Mock

from app.agent.revenue_extraction import RevenueCandidateService
from app.api.app import create_app
from app.companies.models import CompanyCreate
from app.documents.models import DocumentStatus
from app.documents.preparation import DocumentTaskPreparer
from tests.test_document_sources import Harness, metadata


def create_real_evidence_app():
    root = Path(os.environ["FINDOC_D8_RUNTIME_ROOT"]).resolve()
    if not root.is_absolute() or not root.name.startswith("findoc-d8-"):
        raise RuntimeError("D8 requires a separate findoc-d8-* temporary root")
    product = Path.cwd().resolve()
    learning = product.parent / 'findoc-rag'
    if root.is_relative_to(product) or root.is_relative_to(learning):
        raise RuntimeError('D8 requires a temporary root outside both repositories')
    root.mkdir(parents=True, exist_ok=True)
    if (root / "documents.db").exists():
        raise RuntimeError("D8 browser seed requires an empty new runtime")

    def audit(event, args):
        if event == "sqlite3.connect" and args[0] != ":memory:":
            if not Path(args[0]).resolve().is_relative_to(root):
                raise RuntimeError("D8 rejected SQLite outside isolated runtime")
        if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(args[0])).resolve()
            mode, flags = args[1], args[2]
            writes = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            )
            if writes and (path.is_relative_to(learning) or path.is_relative_to(product / 'data/runtime')):
                raise RuntimeError('D8 rejected write to learning/default runtime')
    sys.addaudithook(audit)
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
        result = h.upload(raw, {**metadata(companies[prefix].company_id, int(year)), "source_url": original["url"]}, filename=f"{original['id']}.pdf")
        assert result.status_code == 202, result.text
        doc = result.json()["document_id"]
        assert h.processor.process(doc).status == DocumentStatus.READY
        source = h.client.get(f"/documents/{doc}/source").json()
        source.pop("evidence_ids")
        reports.append({"report_id": original["id"], "source": source})
        print(f"D8 parsed {original['id']}: {source['physical_pages']} physical pages", flush=True)
    (root / "manifest.json").write_text(json.dumps({"reports": reports, "isolation": str(root), "substitutions": ["embedding", "vector index", "chunk IDs"], "real": ["PDF", "parser", "SQLite", "source checks", "HTTP"]}, ensure_ascii=False, indent=2))
    candidates = RevenueCandidateService(preparer=DocumentTaskPreparer(document_service=h.documents), retriever=Mock(), sources=h.service)
    return create_app(h.documents, company_service=h.companies, source_service=h.service, candidate_service=candidates)
