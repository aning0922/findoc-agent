"""D11 six actual annual-report changes; simulation is explicitly isolated.

Original bytes, real parser, SQLite and HTTP confirmation pipeline prepare D10
facts. Analysis then uses only persisted reads. All acceptance stays simulated.
"""

import asyncio
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
from unittest.mock import Mock, AsyncMock

import pytest

from app.agent.financial_analysis import FinancialAnalysisService, IsolatedAnalysisTestConfig
from app.companies.models import CompanyCreate
from app.documents.models import DocumentStatus
from tests.test_d10_financial_facts import receipt, persist
from tests.test_d11_financial_analysis import reference
from tests.test_document_sources import Harness, metadata
from tests.test_financial_reviews import assemble

EXPECTED = {
    "midea": {
        "revenue": ("49302131000.00", "12.11"),
        "net_profit_parent": ("5408174000.00", "14.03"),
        "operating_cash_flow": ("-7165642000.00", "-11.84"),
    },
    "gree": {
        "revenue": ("-18716595531.07", "-9.89"),
        "net_profit_parent": ("-3181466960.62", "-9.89"),
        "operating_cash_flow": ("17013864183.36", "57.93"),
    },
}


@pytest.mark.local_data
@pytest.mark.parametrize("company_key", ["midea", "gree"])
def test_two_original_disclosures_three_metrics(tmp_path, company_key, monkeypatch):
    root = tmp_path / "findoc-d11-real-pdfs"
    h = assemble(Harness(root))
    company = h.companies.create(
        CompanyCreate(
            name="美的集团股份有限公司" if company_key == "midea" else "珠海格力电器股份有限公司",
            security_code="000333" if company_key == "midea" else "000651",
            exchange="SZSE",
        )
    )
    h.company = company
    manifest = json.loads(Path("product/validation/sources.json").read_text())
    gold = json.loads(Path("product/validation/manual-benchmark.json").read_text())["facts"]
    groups, source_proofs = {}, []
    for year in (2024, 2025):
        report_id = f"{company_key}-{year}"
        original = next(x for x in manifest if x["id"] == report_id)
        raw = Path(original["path"]).read_bytes()  # Originals required; never skip.
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
            metric_keys=list(EXPECTED[company_key]),
            periods=[2024] if year == 2024 else [2024, 2025],
        )
        r, _ = receipt(h, f"d11-simulated-{report_id}")
        saved = persist(h, r)
        assert saved.status_code == 200, saved.text
        groups[year] = saved.json()
        assert groups[year]["confirmation_kind"] == "simulated_test"
        assert not groups[year]["production_calculable"]
        for fact in groups[year]["facts"]:
            expected = next(
                x
                for x in gold
                if x["document_id"] == report_id
                and x["metric"] == fact["metric_key"]
                and x["period"] == fact["period"]
            )
            for field in (
                "value_cny_yuan",
                "raw_value",
                "raw_unit",
                "currency",
                "scope",
                "accounting_basis",
                "period_start",
                "period_end",
            ):
                assert fact[field] == expected[field], (report_id, field)
        source_proofs.append(
            dict(
                report_id=report_id,
                original_path=original["path"],
                original_url=original["url"],
                sha256=original["sha256"],
                source=source,
                fact_set_id=groups[year]["fact_set_id"],
                disclosure_version=groups[year]["disclosure_version"],
            )
        )
    # Reopen reader and prohibit parser/candidate/model/retrieval during all analysis.
    assemble(h)
    monkeypatch.setattr(
        h.candidates, "collect_metrics", AsyncMock(side_effect=AssertionError("extract"))
    )
    monkeypatch.setattr(h.processor, "process", Mock(side_effect=AssertionError("parse")))
    analysis = FinancialAnalysisService(
        facts=h.confirmations, workspace_id="demo", isolated_test=IsolatedAnalysisTestConfig(root)
    )
    with closing(sqlite3.connect(h.db)) as c:
        tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        before = {t: c.execute(f'SELECT * FROM "{t}" ORDER BY rowid').fetchall() for t in tables}
    results = []
    for metric, expected in EXPECTED[company_key].items():
        current, previous = (
            reference(groups[2025], metric, 2025),
            reference(groups[2024], metric, 2024),
        )
        result = asyncio.run(
            analysis.analyze(
                company_id=company.company_id, metric_key=metric, current=current, previous=previous
            )
        )
        assert result["status"] == "analyzed" and not result["production_calculable"]
        assert (result["absolute_change"], result["percentage_change"]) == expected
        assert result["current"]["source"]["content_sha256"] == source_proofs[1]["sha256"]
        assert result["previous"]["source"]["content_sha256"] == source_proofs[0]["sha256"]
        for role in ("current", "previous"):
            fact = result[role]
            for evidence in [*fact["evidence"], *fact["basis_evidence"]]:
                response = h.client.get(
                    f"/documents/{fact['document_id']}/evidence/{evidence['evidence_id']}",
                    params=dict(
                        company_id=company.company_id, source_revision=fact["source_revision"]
                    ),
                )
                assert response.status_code == 200
                assert response.json()["physical_page"] == evidence["physical_page"]
        # Selecting 2024 comparison disclosure explicitly is valid; nothing chooses it automatically.
        alternative = asyncio.run(
            analysis.analyze(
                company_id=company.company_id,
                metric_key=metric,
                current=current,
                previous=reference(groups[2025], metric, 2024),
            )
        )
        assert alternative["percentage_change"] == result["percentage_change"]
        assert (
            alternative["previous"]["disclosure_version"]
            != result["previous"]["disclosure_version"]
        )
        from dataclasses import asdict

        denied = h.client.post(
            "/analyses",
            json=dict(
                schema_version="financial-analysis-v1",
                company_id=company.company_id,
                metric_key=metric,
                current=asdict(current),
                previous=asdict(previous),
            ),
        )
        assert denied.status_code == 404 and denied.json()["detail"]["code"] == "facts_not_found"
        results.append(
            dict(
                result=result,
                expected_absolute_change=expected[0],
                expected_percentage_change=expected[1],
                success=True,
                production_api_status=denied.status_code,
                human_acceptance="pending",
            )
        )
    with closing(sqlite3.connect(h.db)) as c:
        after = {t: c.execute(f'SELECT * FROM "{t}" ORDER BY rowid').fetchall() for t in tables}
    assert before == after
    h.candidates.collect_metrics.assert_not_called()
    h.candidates._retriever.retrieve.assert_not_called()
    (tmp_path / "d11-analysis-proof.json").write_text(
        json.dumps(
            dict(
                company_id=company.company_id,
                company_name=company.name,
                sqlite_path=str(h.db),
                sources=source_proofs,
                analyses=results,
                read_only_database_unchanged=True,
                analysis_parser_calls=0,
                analysis_candidate_calls=0,
                analysis_retrieval_calls=0,
                confirmation_kind="simulated_test",
                human_acceptance="pending",
            ),
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
