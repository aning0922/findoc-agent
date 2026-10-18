"""Persisted sources, API scope/revision gates, and no lazy GET side effects."""

import asyncio
from contextlib import closing
import sqlite3
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from app.agent.revenue_extraction import RevenueCandidateService
from app.api.app import create_app
from app.documents.models import DocumentStatus
from app.documents.preparation import DocumentTaskPreparer
from app.rag.parse.models import DocChunk, PDFLayout
from tests.test_document_sources import Harness, metadata
from tests.test_metric_extraction import fixture_records


def candidate_harness(root):
    h = Harness(root)
    _, records = fixture_records()
    h.processor._parser = lambda content, source_file: [
        DocChunk(
            text=r["text"],
            page=r["physical_page"],
            type=r["kind"],
            source_file=source_file,
            layout=PDFLayout.model_validate(r["layout"]) if r["layout"] else None,
        )
        for r in records
    ]
    h.candidates = RevenueCandidateService(
        preparer=DocumentTaskPreparer(document_service=h.documents),
        retriever=Mock(),
        sources=h.service,
    )
    h.client = TestClient(
        create_app(h.documents, source_service=h.service, candidate_service=h.candidates)
    )
    # Captured fixture pages are bounded by the real PDF tree.
    from tests.test_document_sources import pdf_bytes

    h.id = h.upload(
        content=pdf_bytes(pages=4), payload=metadata(h.company.company_id, 2031)
    ).json()["document_id"]
    assert h.processor.process(h.id).status == DocumentStatus.READY
    h.source = asyncio.run(h.service.source(h.id))
    h.rev = h.source["source_revision"]
    return h


def query(h, **changes):
    params = dict(
        company_id=h.company.company_id,
        source_revision=h.rev,
        metric_keys=["revenue"],
        periods=[2031],
    )
    params.update(changes)
    return h.client.get(f"/documents/{h.id}/financial-candidates", params=params)


def test_api_persisted_geometry_roundtrip_no_retrieval_or_confirmation(tmp_path):
    h = candidate_harness(tmp_path)
    from tests.test_companies_migrations import snapshot

    tables = [
        "documents",
        "companies",
        "report_document_metadata",
        "document_sources",
        "document_evidence",
        "document_evidence_layout",
        "report_binding_corrections",
    ]
    before = snapshot(h.db, tables)
    r = query(h)
    assert r.status_code == 200, r.text
    item = r.json()["candidates"][0]
    # Ambiguous cover identity keeps controlled fixture unconfirmable.
    assert item["status"] == "needs_manual_review" and item["value_cny_yuan"] is None
    proof = item["evidence"][0]
    e = h.client.get(
        f"/documents/{h.id}/evidence/{proof['evidence_id']}",
        params=dict(source_revision=h.rev, company_id=h.company.company_id),
    )
    assert e.status_code == 200 and e.json()["layout"]
    assert e.json()["source_revision"] == item["source_revision"]
    h.candidates._retriever.retrieve.assert_not_called()
    assert query(h).json() == r.json()
    assert snapshot(h.db, tables) == before


@pytest.mark.parametrize(
    "changes,status",
    [
        (dict(company_id="other"), 404),
        (dict(source_revision="0" * 64), 409),
        (dict(metric_keys=["bad"]), 422),
        (dict(periods=[0]), 422),
        (dict(periods=[2031, 2031]), 422),
    ],
)
def test_api_selection_and_scope(tmp_path, changes, status):
    h = candidate_harness(tmp_path)
    assert query(h, **changes).status_code == status


def test_source_correction_and_retry_invalidates_candidates_and_old_evidence(tmp_path):
    h = candidate_harness(tmp_path)
    old = query(h).json()
    correction = h.client.post(
        f"/documents/{h.id}/binding-corrections",
        json=dict(
            expected_attempt=1,
            metadata=metadata(h.other.company_id, 2031),
            reason="simulated metadata correction",
        ),
    )
    assert correction.status_code == 200, correction.text
    assert query(h).status_code == 404
    assert query(h, company_id=h.other.company_id).status_code == 409
    asyncio.run(h.documents.retry_document(h.id))
    assert h.processor.process(h.id).status == DocumentStatus.READY
    new = asyncio.run(h.service.source(h.id))
    h.rev = new["source_revision"]
    assert query(h).status_code == 404
    response = query(h, company_id=h.other.company_id).json()
    assert response["candidates"][0]["candidate_id"] != old["candidates"][0]["candidate_id"]
    eid = old["candidates"][0]["evidence_id"]
    assert (
        h.client.get(
            f"/documents/{h.id}/evidence/{eid}", params=dict(source_revision=h.rev)
        ).status_code
        == 404
    )


@pytest.mark.parametrize("change", ["payload", "sha", "parser", "snapshot"])
def test_corrupt_or_missing_captured_source_never_backfilled(tmp_path, change):
    h = candidate_harness(tmp_path)
    with closing(sqlite3.connect(h.db)) as c, c:
        if change == "payload":
            c.execute("DROP TRIGGER d7_layout_immutable_update")
            c.execute("UPDATE document_evidence_layout SET payload_json='{}'")
        if change == "sha":
            c.execute("UPDATE documents SET content_sha256=?", ("0" * 64,))
        if change == "parser":
            h.service.parser_version = "future-parser"
        if change == "snapshot":
            c.execute("UPDATE document_sources SET invalidated_at='fixture'")
    result = query(h)
    assert result.status_code == 409, result.text
    h.candidates._retriever.retrieve.assert_not_called()


def test_unknown_document_and_no_dependency_safe_errors(tmp_path):
    h = candidate_harness(tmp_path)
    h.id = "unknown"
    assert query(h).status_code == 404
    client = TestClient(create_app(h.documents))
    assert (
        client.get(
            "/documents/x/financial-candidates",
            params=dict(
                company_id="x", source_revision="0" * 64, metric_keys="revenue", periods=2031
            ),
        ).status_code
        == 503
    )


def test_v4_upgrade_failure_rolls_back_preserving_v3(tmp_path, monkeypatch):
    from app.companies import migrations
    from app.companies.sqlite_repository import SQLiteCompanyRepository

    plan = migrations.MIGRATIONS
    monkeypatch.setattr(migrations, "MIGRATIONS", plan[:3])
    db = tmp_path / "v3.db"
    SQLiteCompanyRepository(db)
    version, name, ddl = plan[3]
    monkeypatch.setattr(
        migrations, "MIGRATIONS", (*plan[:3], (version, name, (*ddl, "INVALID D7 DDL")))
    )
    with pytest.raises(sqlite3.OperationalError):
        SQLiteCompanyRepository(db)
    with closing(sqlite3.connect(db)) as c:
        assert c.execute("SELECT version FROM analyst_schema_migrations").fetchall() == [
            (1,),
            (2,),
            (3,),
        ]
        assert not c.execute(
            "SELECT name FROM sqlite_master WHERE name='document_evidence_layout'"
        ).fetchall()
    monkeypatch.setattr(migrations, "MIGRATIONS", plan)
    SQLiteCompanyRepository(db)
    with closing(sqlite3.connect(db)) as c:
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


@pytest.mark.parametrize("year", [2031, 2025])
def test_real_borderless_pdf_third_company_and_nonbenchmark_year(tmp_path, year):
    import pymupdf
    from app.companies.models import CompanyCreate

    h = Harness(tmp_path)
    third = h.companies.create(
        CompanyCreate(name="海川科技股份有限公司", security_code="600123", exchange="SSE")
    )
    with pymupdf.open() as pdf:

        def put(page, x, y, text):
            page.insert_text((x, y), text, fontname="china-s", fontsize=10)

        p = pdf.new_page()
        put(p, 50, 100, third.name)
        put(p, 50, 130, f"{year}年年度报告")
        for title, label, value in [
            ("合并利润表", "营业收入", "1,234.50"),
            ("合并利润表", "归属于母公司股东的净利润", "-12.75"),
            ("合并现金流量表", "经营活动产生的现金流量净额", "(41.25)"),
        ]:
            p = pdf.new_page()
            put(p, 50, 70, title)
            put(p, 50, 90, "单位：人民币万元")
            put(p, 300, 115, f"{year}年度")
            put(p, 430, 115, f"{year - 1}年度")
            put(p, 50, 145, label)
            put(p, 300, 145, value)
            put(p, 430, 145, "25.00")
        p = pdf.new_page()
        put(p, 50, 100, "遵循企业会计准则的声明")
        put(p, 50, 130, "本公司财务报表符合企业会计准则的要求")
        raw = pdf.tobytes()
    h.id = h.upload(raw, metadata(third.company_id, year)).json()["document_id"]
    assert h.processor.process(h.id).status == DocumentStatus.READY
    h.source = asyncio.run(h.service.source(h.id))
    h.rev = h.source["source_revision"]
    h.company = third
    h.candidates = RevenueCandidateService(
        preparer=DocumentTaskPreparer(document_service=h.documents),
        retriever=Mock(),
        sources=h.service,
    )
    h.client = TestClient(
        create_app(h.documents, source_service=h.service, candidate_service=h.candidates)
    )
    response = query(
        h,
        metric_keys=["revenue", "net_profit_parent", "operating_cash_flow"],
        periods=[year - 1, year],
    )
    assert response.status_code == 200, response.text
    result = response.json()["candidates"]
    assert all(c["status"] == "candidate" for c in result), [
        (c["metric_key"], c["failure_reason"]) for c in result
    ]
    assert [c["value_cny_yuan"] for c in result] == [
        "250000.00",
        "12345000.00",
        "250000.00",
        "-127500.00",
        "250000.00",
        "-412500.00",
    ]
    assert len(h.companies.list()) == 3
    h.candidates._retriever.retrieve.assert_not_called()
    if year == 2025:
        from app.agent.revenue_confirmation import (
            RevenueConfirmationError,
            RevenueConfirmationService,
            RevenueSourceReader,
        )
        from app.agent.sqlite_financial_facts import SQLiteRevenueConfirmationRepository
        from decimal import Decimal

        service = RevenueConfirmationService(
            source_reader=RevenueSourceReader(
                documents=h.documents, objects=h.objects, candidates=h.candidates
            ),
            repository=SQLiteRevenueConfirmationRepository(h.db),
        )
        review = asyncio.run(service.preview(document_id=h.id))
        with pytest.raises(RevenueConfirmationError, match="confirmation_required"):
            asyncio.run(
                service.confirm(
                    document_id=h.id,
                    reviewed_snapshot_id=review.snapshot_id,
                    accepted=False,
                    confirmation_kind="simulated_test",
                )
            )
        confirmation = asyncio.run(
            service.confirm(
                document_id=h.id,
                reviewed_snapshot_id=review.snapshot_id,
                accepted=True,
                confirmation_kind="simulated_test",
            )
        )
        calculated = asyncio.run(
            service.calculate(document_id=h.id, confirmation_id=confirmation.confirmation_id)
        )
        assert calculated.result.value == Decimal("4838.00")
        assert calculated.confirmation.confirmation_kind == "simulated_test"
        h.objects.put_bytes(h.docs.get(h.id).object_key, b"changed fixture source")
        with pytest.raises(RevenueConfirmationError, match="source_changed"):
            asyncio.run(
                service.calculate(document_id=h.id, confirmation_id=confirmation.confirmation_id)
            )
