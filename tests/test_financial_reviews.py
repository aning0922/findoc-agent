"""D9 uses real parser/SQLite and explicit simulated acceptance, never human consent."""

import asyncio
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
import sqlite3
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pymupdf
import pytest

from app.agent.revenue_confirmation import RevenueConfirmationService, RevenueSourceReader
from app.agent.revenue_extraction import RevenueCandidateService
from app.agent.sqlite_financial_facts import SQLiteRevenueConfirmationRepository
from app.api.app import create_app
from app.companies.models import CompanyCreate
from app.documents.models import DocumentStatus
from app.documents.preparation import DocumentTaskPreparer
from tests.test_document_sources import Harness, metadata


def assemble(h):
    h.candidates = RevenueCandidateService(
        preparer=DocumentTaskPreparer(document_service=h.documents),
        retriever=Mock(),
        sources=h.service,
    )
    h.receipts = SQLiteRevenueConfirmationRepository(h.db)
    h.confirmations = RevenueConfirmationService(
        source_reader=RevenueSourceReader(
            documents=h.documents, objects=h.objects, candidates=h.candidates, sources=h.service
        ),
        repository=h.receipts,
    )
    h.client = TestClient(
        create_app(
            h.documents,
            company_service=h.companies,
            source_service=h.service,
            candidate_service=h.candidates,
            revenue_service=h.confirmations,
            revenue_workspace_id="demo",
            financial_confirmation_kind="simulated_test",
        )
    )
    return h


def financial_harness(root, year=2031, previous_value="25.00"):
    h = assemble(Harness(root))
    h.company = h.companies.create(
        CompanyCreate(name="海川科技股份有限公司", security_code="600123", exchange="SSE")
    )
    with pymupdf.open() as pdf:

        def put(p, x, y, text):
            p.insert_text((x, y), text, fontname="china-s", fontsize=10)

        p = pdf.new_page()
        put(p, 50, 100, h.company.name)
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
            put(p, 430, 115, f"{year-1}年度")
            put(p, 50, 145, label)
            put(p, 300, 145, value)
            put(p, 430, 145, previous_value)
        p = pdf.new_page()
        put(p, 50, 100, "遵循企业会计准则的声明")
        put(p, 50, 130, "本公司财务报表符合企业会计准则的要求")
        raw = pdf.tobytes()
    h.id = h.upload(raw, metadata(h.company.company_id, year)).json()["document_id"]
    assert h.processor.process(h.id).status == DocumentStatus.READY
    h.source = asyncio.run(h.service.source(h.id))
    h.selection = dict(
        review_schema="financial-review-v1",
        company_id=h.company.company_id,
        document_id=h.id,
        source_revision=h.source["source_revision"],
        metric_keys=["revenue", "net_profit_parent", "operating_cash_flow"],
        periods=[year-1, year],
    )
    return h


@pytest.fixture
def h(tmp_path):
    return financial_harness(tmp_path)


def counts(h):
    with closing(sqlite3.connect(h.db)) as c:
        return tuple(
            c.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            for name in (
                "financial_acceptance_receipts",
                "revenue_confirmations",
                "confirmed_revenue_facts",
            )
        )


def preview(h):
    r = h.client.post("/financial-facts/reviews", json=h.selection)
    assert r.status_code == 200, r.text
    return r.json()


def accept_payload(h, review, **changes):
    return {
        **h.selection,
        "snapshot_id": review["snapshot_id"],
        "accepted": True,
        "request_id": "simulated-d9",
        **changes,
    }


def recovery(h, payload):
    return h.client.get(
        f"/financial-facts/confirmations/{payload['request_id']}",
        params={k: v for k, v in payload.items() if k not in ("accepted", "request_id")},
    )


def test_dynamic_snapshot_no_writes_and_receipt_recovery_after_restart(h):
    review = preview(h)
    assert review["review_status"] == "ready_for_acceptance" and counts(h) == (0, 0, 0)
    assert len(review["candidates"]) == 6 and len(review["source_evidence"]) == 4
    assert {c["period"] for c in review["candidates"]} == {2030, 2031}
    payload = accept_payload(h, review)
    r = h.client.post("/financial-facts/confirmations", json=payload)
    assert r.status_code == 200, r.text
    receipt = r.json()
    assert (
        receipt["confirmation_kind"] == "simulated_test"
        and receipt["facts_status"] == "pending_d10"
    )
    assert receipt["analysis_started"] is False and counts(h) == (1, 0, 0)
    assemble(h)
    assert recovery(h, payload).json() == receipt
    assert h.client.post("/financial-facts/confirmations", json=payload).json() == receipt
    assert counts(h) == (1, 0, 0)
    h.candidates._retriever.retrieve.assert_not_called()


@pytest.mark.parametrize(
    "changes,status",
    [
        ({"accepted": False}, 409),
        ({"accepted": "true"}, 422),
        ({"value_cny_yuan": "123"}, 422),
        ({"confirmation_kind": "local_operator"}, 422),
        ({"company_id": "wrong"}, 404),
        ({"source_revision": "0" * 64}, 409),
        ({"snapshot_id": "financial-review-v1:" + "0" * 64}, 409),
        ({"review_schema": "v2"}, 422),
        ({"snapshot_id": "financial-review-v2:" + "0" * 64}, 422),
        ({"periods": [2031, 2031]}, 422),
        ({"metric_keys": ["bad"]}, 422),
        ({"periods": [True]}, 422),
        ({"periods": [0]}, 422),
    ],
)
def test_rejections_have_zero_writes(h, changes, status):
    r = h.client.post(
        "/financial-facts/confirmations", json=accept_payload(h, preview(h), **changes)
    )
    assert r.status_code == status, r.text
    assert counts(h) == (0, 0, 0)


def test_missing_selection_cannot_become_valid_and_cancel_does_nothing(h):
    h.selection["periods"] = [1900]
    review = preview(h)
    assert review["review_status"] == "blocked"
    assert all(c["value_cny_yuan"] is None for c in review["candidates"])
    assert (
        h.client.post("/financial-facts/confirmations", json=accept_payload(h, review)).status_code
        == 409
    )
    # Cancellation has no endpoint and preview is read-only.
    assert counts(h) == (0, 0, 0)


@pytest.mark.parametrize("status", ["conflict", "needs_manual_review", "unsupported"])
def test_blocked_and_incomplete_evidence_fail_the_same_service_gate(h, status):
    current = asyncio.run(
        h.confirmations.preview_financial(
            **{k: v for k, v in h.selection.items() if k != "review_schema"}
        )
    )
    p = current.to_payload()
    p["candidates"][0]["status"] = status
    # Defensive invariant: even a faulty trusted extractor cannot make an invalid candidate acceptable.
    from app.agent.revenue_confirmation import canonical_payload

    changed = replace(current, payload_json=canonical_payload(p))
    assert not changed.acceptable
    p["candidates"][0]["status"] = "candidate"
    p["source_evidence"] = []
    assert not replace(current, payload_json=canonical_payload(p)).acceptable
    assert counts(h) == (0, 0, 0)


def test_double_submit_and_key_reuse(h):
    payload = accept_payload(h, preview(h))
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda _: h.client.post("/financial-facts/confirmations", json=payload), range(2)
            )
        )
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    assert responses[0].json() == responses[1].json() and counts(h) == (1, 0, 0)
    h.selection["periods"] = [2031]
    r = h.client.post("/financial-facts/confirmations", json=accept_payload(h, preview(h)))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "idempotency_conflict"


def test_source_correction_invalidates_saved_receipt(h):
    payload = accept_payload(h, preview(h))
    assert h.client.post("/financial-facts/confirmations", json=payload).status_code == 200
    r = h.client.post(
        f"/documents/{h.id}/binding-corrections",
        json=dict(
            expected_attempt=1,
            metadata={**metadata(h.company.company_id, 2031), "basis": "unknown"},
            reason="simulated D9 correction",
        ),
    )
    assert r.status_code == 200, r.text
    assert recovery(h, payload).status_code == 409
    assert h.client.post("/financial-facts/confirmations", json=payload).status_code == 409
    assert counts(h) == (1, 0, 0)


def test_failure_rollback_and_corrupt_receipt_never_success(h):
    payload = accept_payload(h, preview(h))
    with closing(sqlite3.connect(h.db)) as c, c:
        c.execute(
            "CREATE TRIGGER d9_fault AFTER INSERT ON financial_acceptance_receipts BEGIN SELECT RAISE(ABORT, 'test'); END"
        )
    assert h.client.post("/financial-facts/confirmations", json=payload).status_code == 500
    assert counts(h) == (0, 0, 0) and recovery(h, payload).status_code == 404
    with closing(sqlite3.connect(h.db)) as c, c:
        c.execute("DROP TRIGGER d9_fault")
    assert h.client.post("/financial-facts/confirmations", json=payload).status_code == 200
    with closing(sqlite3.connect(h.db)) as c, c:
        with pytest.raises(sqlite3.IntegrityError):
            c.execute("UPDATE financial_acceptance_receipts SET review_json='{}'")
        c.execute("DROP TRIGGER d9_acceptance_immutable_update")
        c.execute("UPDATE financial_acceptance_receipts SET review_json='{}'")
    assert recovery(h, payload).status_code == 500


def test_post_commit_read_failure_is_recoverable_unknown(h, monkeypatch):
    payload = accept_payload(h, preview(h))
    original = h.receipts.load_acceptance
    monkeypatch.setattr(
        h.receipts,
        "load_acceptance",
        Mock(side_effect=sqlite3.OperationalError("simulated lost read")),
    )
    assert h.client.post("/financial-facts/confirmations", json=payload).status_code == 500
    assert counts(h) == (1, 0, 0)
    monkeypatch.setattr(h.receipts, "load_acceptance", original)
    assert recovery(h, payload).status_code == 200 and counts(h) == (1, 0, 0)


def test_public_snapshot_recomputes_and_selection_order_is_canonical(h):
    review = preview(h)
    body = {
        k: v for k, v in review.items() if k not in ("snapshot_id", "review_status", "facts_status")
    }
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert (
        review["snapshot_id"]
        == "financial-review-v1:" + hashlib.sha256(canonical.encode()).hexdigest()
    )
    h.selection["metric_keys"].reverse()
    h.selection["periods"].reverse()
    assert preview(h)["snapshot_id"] == review["snapshot_id"] and counts(h) == (0, 0, 0)


def test_binding_correction_between_service_review_and_transaction_is_rejected(h, monkeypatch):
    payload = accept_payload(h, preview(h))
    original = h.receipts.save_acceptance

    def change_before_save(**kwargs):
        correction = h.client.post(
            f"/documents/{h.id}/binding-corrections",
            json=dict(
                expected_attempt=1,
                metadata={**metadata(h.company.company_id, 2031), "basis": "unknown"},
                reason="simulated transaction race",
            ),
        )
        assert correction.status_code == 200
        return original(**kwargs)

    monkeypatch.setattr(h.receipts, "save_acceptance", change_before_save)
    result = h.client.post("/financial-facts/confirmations", json=payload)
    assert result.status_code == 409 and result.json()["detail"]["code"] == "source_changed"
    assert counts(h) == (0, 0, 0)


def test_invalid_recovery_selection_uses_422_and_does_not_write(h):
    payload = accept_payload(h, preview(h), periods=[2031, 2031])
    assert recovery(h, payload).status_code == 422
    assert counts(h) == (0, 0, 0)
