"""Isolated Chromium harness: real PDFs/SQLite/D19; simulated acceptance, empty retrieval.

No production switch. Restart reopens existing DB without parsing or generating facts.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
from tempfile import gettempdir

from app.api.research_tasks import create_task_router
from app.companies.models import CompanyCreate
from app.documents.models import DocumentStatus
from tests.support.d19_runtime import reopen, persistent
from tests.test_document_sources import Harness, metadata
from tests.test_financial_reviews import assemble


def create_d20_app():
    root = Path(os.environ["FINDOC_D20_RUNTIME_ROOT"]).resolve()
    product = Path.cwd().resolve()
    if not root.name.startswith("findoc-d11-d20-browser-") or not root.is_relative_to(Path(gettempdir()).resolve()) or root.is_relative_to(product):
        raise RuntimeError("isolated_d20_root_required")

    def audit(event, args):
        if event == "sqlite3.connect" and args[0] != ":memory:" and not Path(args[0]).resolve().is_relative_to(root):
            raise RuntimeError("sqlite_outside_d20_root")
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(args[0])).resolve()
            mode, flags = args[1], args[2]
            writes = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            if writes and any(path.is_relative_to(p) for p in (product.parent / "findoc-rag", product.parent / "findoc-v1-product-design", product / "data/runtime")):
                raise RuntimeError("protected_d20_write")
    sys.addaudithook(audit)
    if (root / "documents.db").exists():
        h = reopen(root)
    else:
        h = assemble(Harness(root))
        companies = {key: h.companies.create(CompanyCreate(name=name, security_code=code, exchange="SZSE")) for key, name, code in [("midea", "美的集团股份有限公司", "000333"), ("gree", "珠海格力电器股份有限公司", "000651")]}
        reports = []
        for original in json.loads((product / "product/validation/sources.json").read_text()):
            raw = (product / original["path"]).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == original["sha256"]
            key, year = original["id"].split("-")
            document = h.upload(raw, metadata(companies[key].company_id, int(year)), filename=original["id"] + ".pdf").json()["document_id"]
            assert h.processor.process(document).status == DocumentStatus.READY
            source = h.client.get(f"/documents/{document}/source").json()
            reports.append(dict(report_id=original["id"], source=source, original_sha256=original["sha256"]))
            print("D20 real PDF ready:", original["id"], flush=True)
        (root / "manifest.json").write_text(json.dumps(dict(reports=reports, human_acceptance="pending", simulated_test=True, retrieval="empty controlled substitute", model_calls=0), ensure_ascii=False, indent=2))
    repo, service = persistent(h, simulated=True)
    repo.recover_interrupted()
    app = h.client.app
    app.include_router(create_task_router(repo, service))
    # Explicit production admission probe, only in the isolated test assembly.
    _, production = persistent(h, simulated=False)
    app.include_router(create_task_router(repo, production), prefix="/__test__/production")
    return app
