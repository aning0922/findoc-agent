"""D12-only browser harness; no production HTTP switch, no local_operator writes.

Uses four fixed-SHA PDFs and shared D10/D11 services. Test analysis is mounted
only here, under __test__; the official /analyses still rejects simulated facts.
"""

import hashlib
import json
import os
from pathlib import Path
import sys
from tempfile import gettempdir

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app.agent.financial_analysis import FinancialAnalysisService, FinancialFactReference
from app.agent.financial_analysis import IsolatedAnalysisTestConfig
from app.agent.revenue_confirmation import RevenueConfirmationError
from app.api.financial_analyses import FinancialAnalysisRequest, CompanyComparisonRequest
from app.companies.models import CompanyCreate
from app.documents.models import DocumentStatus
from tests.test_d10_financial_facts import receipt, persist
from tests.test_document_sources import Harness, metadata
from tests.test_financial_reviews import assemble


def create_real_product_app():
    root = Path(os.environ["FINDOC_D12_RUNTIME_ROOT"]).resolve()
    product = Path.cwd().resolve()
    if (
        not root.name.startswith("findoc-d11-d12-")
        or not root.is_relative_to(Path(gettempdir()).resolve())
        or root.is_relative_to(product)
        or (root / "documents.db").exists()
    ):
        raise RuntimeError("Requires a new isolated D12 temporary runtime")
    root.mkdir(parents=True, exist_ok=True)

    def audit(event, args):
        if event == "sqlite3.connect" and args[0] != ":memory:":
            if not Path(args[0]).resolve().is_relative_to(root):
                raise RuntimeError("D12 rejected SQLite outside isolated runtime")
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(args[0])).resolve()
            mode, flags = args[1], args[2]
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
                raise RuntimeError("D12 rejected protected runtime write")

    sys.addaudithook(audit)
    h = assemble(Harness(root))
    companies = {
        key: h.companies.create(CompanyCreate(name=name, security_code=code, exchange="SZSE"))
        for key, name, code in (
            ("midea", "美的集团股份有限公司", "000333"),
            ("gree", "珠海格力电器股份有限公司", "000651"),
        )
    }
    reports, groups = [], []
    for original in json.loads((product / "product/validation/sources.json").read_text()):
        raw = Path(original["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == original["sha256"]
        key, year = original["id"].split("-")
        company = companies[key]
        upload = h.upload(
            raw,
            {**metadata(company.company_id, int(year)), "source_url": original["url"]},
            filename=original["id"] + ".pdf",
        )
        assert upload.status_code == 202, upload.text
        h.id = upload.json()["document_id"]
        assert h.processor.process(h.id).status == DocumentStatus.READY
        source = h.client.get(f"/documents/{h.id}/source").json()
        source.pop("evidence_ids")
        h.selection = dict(
            review_schema="financial-review-v1",
            company_id=company.company_id,
            document_id=h.id,
            source_revision=source["source_revision"],
            metric_keys=["revenue", "net_profit_parent", "operating_cash_flow"],
            periods=[2024] if int(year) == 2024 else [2024, 2025],
        )
        r, _ = receipt(h, "d12-simulated-" + original["id"])
        saved = persist(h, r)
        assert saved.status_code == 200, saved.text
        group = saved.json()
        assert group["confirmation_kind"] == "simulated_test"
        assert not group["production_calculable"]
        groups.append(group)
        reports.append(dict(report_id=original["id"], source=source))
        print(f"D12 real PDF seed: {original['id']}; simulated facts only", flush=True)
    analysis = FinancialAnalysisService(
        facts=h.confirmations, workspace_id="demo", isolated_test=IsolatedAnalysisTestConfig(root)
    )
    app = h.client.app

    @app.post("/__test__/analyses")
    async def isolated_analysis(payload: FinancialAnalysisRequest):
        try:
            result = await analysis.analyze(
                company_id=payload.company_id,
                metric_key=payload.metric_key,
                current=FinancialFactReference(**payload.current.model_dump())
                if payload.current
                else None,
                previous=FinancialFactReference(**payload.previous.model_dump())
                if payload.previous
                else None,
            )
        except RevenueConfirmationError as e:
            raise HTTPException(409, str(e)) from e
        return JSONResponse(
            result,
            status_code=409 if result["status"] == "blocked" else 200,
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/__test__/company-comparison")
    async def isolated_comparison(payload: CompanyComparisonRequest):
        try:
            result = await analysis.compare(
                company_a_id=payload.company_a_id,
                company_b_id=payload.company_b_id,
                period=payload.period,
                selections={
                    s.metric_key: (
                        FinancialFactReference(**s.a.model_dump()) if s.a else None,
                        FinancialFactReference(**s.b.model_dump()) if s.b else None,
                    )
                    for s in payload.selections
                },
            )
        except RevenueConfirmationError as e:
            raise HTTPException(409, str(e)) from e
        return JSONResponse(
            result,
            status_code=409 if result["status"] == "blocked" else 200,
            headers={"Cache-Control": "no-store"},
        )

    (root / "manifest.json").write_text(
        json.dumps(
            dict(
                reports=reports,
                groups=groups,
                companies=[c.model_dump(mode="json") for c in companies.values()],
                confirmation_kind="simulated_test",
                human_acceptance="pending",
                real=["PDF", "parser", "SQLite", "ObjectStore", "D10 query", "D11 service", "HTTP"],
                substitutions=[
                    "embedding",
                    "vector index",
                    "chunk IDs",
                    "test-only analysis HTTP adapter",
                ],
                production_analysis_unchanged=True,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return app
