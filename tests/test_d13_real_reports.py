"""Four original PDFs -> persisted simulated facts -> shared D13 service, no human claims."""

import asyncio
from contextlib import closing
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sqlite3
from unittest.mock import AsyncMock, Mock

from app.agent.financial_analysis import FinancialAnalysisService, IsolatedAnalysisTestConfig
from app.companies.models import CompanyCreate
from app.documents.models import DocumentStatus
from tests.test_document_sources import Harness, metadata
from tests.test_financial_reviews import assemble
from tests.test_d10_financial_facts import receipt, persist
from tests.test_d11_financial_analysis import reference

EXPECTED = {
    2024: {
        "revenue": ("-217985945935.36", "-53.54"),
        "net_profit_parent": ("-6352666627.72", "-16.48"),
        "operating_cash_flow": ("-31142321429.34", "-51.47"),
    },
    2025: {
        "revenue": ("-286004672466.43", "-62.66"),
        "net_profit_parent": ("-14942307588.34", "-34.00"),
        "operating_cash_flow": ("-6962815245.98", "-13.05"),
    },
}


def test_four_original_reports_same_period_comparison(tmp_path, monkeypatch):
    root = tmp_path / "findoc-d11-d13-real"
    h = assemble(Harness(root))
    companies = {
        key: h.companies.create(CompanyCreate(name=name, security_code=code, exchange="SZSE"))
        for key, name, code in [
            ("midea", "美的集团股份有限公司", "000333"),
            ("gree", "珠海格力电器股份有限公司", "000651"),
        ]
    }
    originals = json.loads(Path("product/validation/sources.json").read_text())
    gold = json.loads(Path("product/validation/manual-benchmark.json").read_text())["facts"]
    groups = {}
    sources = []
    for original in originals:
        key, year_text = original["id"].split("-")
        year = int(year_text)
        company = companies[key]
        raw = Path(original["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == original["sha256"]
        upload = h.upload(
            raw, {**metadata(company.company_id, year), "source_url": original["url"]}
        )
        assert upload.status_code == 202
        h.id = upload.json()["document_id"]
        assert h.processor.process(h.id).status == DocumentStatus.READY
        source = h.client.get(f"/documents/{h.id}/source").json()
        h.selection = dict(
            review_schema="financial-review-v1",
            company_id=company.company_id,
            document_id=h.id,
            source_revision=source["source_revision"],
            metric_keys=list(EXPECTED[year]),
            periods=[2024] if year == 2024 else [2024, 2025],
        )
        r, _ = receipt(h, "d13-simulated-" + original["id"])
        saved = persist(h, r)
        assert saved.status_code == 200
        g = saved.json()
        groups[key, year] = g
        assert g["confirmation_kind"] == "simulated_test" and not g["production_calculable"]
        for f in g["facts"]:
            expected = next(
                v
                for v in gold
                if v["document_id"] == original["id"]
                and v["period"] == f["period"]
                and v["metric"] == f["metric_key"]
            )
            for field in (
                "raw_value",
                "raw_unit",
                "value_cny_yuan",
                "currency",
                "scope",
                "accounting_basis",
                "period_start",
                "period_end",
            ):
                assert f[field] == expected[field]
        sources.append(
            dict(
                report=original["id"],
                sha256=original["sha256"],
                url=original["url"],
                source=source,
                fact_set_id=g["fact_set_id"],
                disclosure_version=g["disclosure_version"],
            )
        )
    assemble(h)
    monkeypatch.setattr(
        h.candidates, "collect_metrics", AsyncMock(side_effect=AssertionError("extract"))
    )
    monkeypatch.setattr(h.processor, "process", Mock(side_effect=AssertionError("parse")))
    service = FinancialAnalysisService(
        facts=h.confirmations, workspace_id="demo", isolated_test=IsolatedAnalysisTestConfig(root)
    )

    def database_rows():
        with closing(sqlite3.connect(h.db)) as c:
            return {
                t: c.execute(f'SELECT * FROM "{t}" ORDER BY rowid').fetchall()
                for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }

    before = database_rows()
    results = []
    for year, report_year in [(2025, 2025), (2024, 2024), (2024, 2025)]:
        selections = {
            m: (
                reference(groups["midea", report_year], m, year),
                reference(groups["gree", report_year], m, year),
            )
            for m in EXPECTED[year]
        }
        response = asyncio.run(
            service.compare(
                company_a_id=companies["midea"].company_id,
                company_b_id=companies["gree"].company_id,
                period=year,
                selections=selections,
            )
        )
        assert response["status"] == "compared" and not response["production_calculable"]
        for row in response["rows"]:
            assert (row["absolute_change"], row["percentage_change"]) == EXPECTED[year][
                row["metric_key"]
            ]
            for side, key in [("a", "midea"), ("b", "gree")]:
                f = row[side]
                assert f["raw_unit"] == ("千元" if key == "midea" else "元")
                for evidence in [*f["evidence"], *f["basis_evidence"]]:
                    r = h.client.get(
                        f"/documents/{f['document_id']}/evidence/{evidence['evidence_id']}",
                        params=dict(
                            company_id=f["company_id"], source_revision=f["source_revision"]
                        ),
                    )
                    assert (
                        r.status_code == 200
                        and r.json()["physical_page"] == evidence["physical_page"]
                    )
        formal = h.client.post(
            "/analyses/company-comparison",
            json=dict(
                schema_version="financial-company-comparison-v1",
                company_a_id=companies["midea"].company_id,
                company_b_id=companies["gree"].company_id,
                period=year,
                selections=[
                    dict(metric_key=m, a=asdict(a), b=asdict(b)) for m, (a, b) in selections.items()
                ],
            ),
        )
        assert formal.status_code == 404
        results.append(
            dict(year=year, report_year=report_year, response=response, formal_status=404)
        )
    assert before == database_rows()
    h.candidates.collect_metrics.assert_not_called()
    h.processor.process.assert_not_called()
    h.candidates._retriever.retrieve.assert_not_called()
    (tmp_path / "d13-comparison-proof.json").write_text(
        json.dumps(
            dict(
                sources=sources,
                comparisons=results,
                read_only_database_unchanged=True,
                parser_candidate_retrieval_calls=0,
                confirmation_kind="simulated_test",
                human_acceptance="pending",
            ),
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
