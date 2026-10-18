"""D10 receipt conversion, transactional persistence and read-only version queries."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
import pytest
from app.agent.revenue_confirmation import canonical_payload, FinancialReview
from contextlib import closing
import json
import sqlite3

from app.companies.models import CompanyCreate
from app.documents.models import DocumentStatus
from tests.test_financial_reviews import (
    financial_harness,
    assemble,
    preview,
    accept_payload,
    recovery,
)
from tests.test_document_sources import metadata


def test_correction_reprocess_accept_and_readback_keeps_old_receipt_invalid(tmp_path):
    h = financial_harness(tmp_path)
    # Same cover name, different security identity: initial binding is the wrong company.
    actual = h.companies.create(
        CompanyCreate(name=h.company.name, security_code="600456", exchange="SSE")
    )
    old_source = h.source
    old_review = preview(h)
    old_request = accept_payload(h, old_review, request_id="old-wrong-binding")
    old = h.client.post("/financial-facts/confirmations", json=old_request)
    assert old.status_code == 200, old.text
    assert persist(h, old.json()).status_code == 200
    corrected = h.client.post(
        f"/documents/{h.id}/binding-corrections",
        json=dict(
            expected_attempt=1,
            metadata=metadata(actual.company_id, 2031),
            reason="Explicit simulated correction of wrong security identity",
        ),
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["new_metadata"]["company_id"] == actual.company_id
    assert recovery(h, old_request).status_code in (404, 409)
    assert h.client.get(
        f"/documents/{h.id}/source",
        params=dict(company_id=h.company.company_id, source_revision=old_source["source_revision"]),
    ).status_code in (404, 409)
    assert h.client.post(f"/documents/{h.id}/retry").status_code == 202
    assert h.processor.process(h.id).status == DocumentStatus.READY
    h.source = asyncio.run(h.service.source(h.id))
    assert h.source["source_revision"] != old_source["source_revision"]
    h.selection.update(company_id=actual.company_id, source_revision=h.source["source_revision"])
    new_review = preview(h)
    assert new_review["review_status"] == "ready_for_acceptance"
    assert new_review["snapshot_id"] != old_review["snapshot_id"]
    for c in new_review["candidates"]:
        assert c["company_id"] == actual.company_id and c["status"] == "candidate"
    new_request = accept_payload(h, new_review, request_id="new-correct-binding")
    new = h.client.post("/financial-facts/confirmations", json=new_request)
    assert new.status_code == 200, new.text
    saved = persist(h, new.json())
    assert saved.status_code == 200, saved.text
    assert fact_counts(h) == (2, 12)
    assert not h.client.get(
        f"/financial-facts/persisted/{old.json()['receipt_id']}", params={"include_invalid": True}
    ).json()["calculable"]
    assemble(h)
    assert (
        h.client.get(f"/financial-facts/persisted/{new.json()['receipt_id']}").json()
        == saved.json()
    )
    assert recovery(h, new_request).json() == new.json()
    assert recovery(h, old_request).status_code in (404, 409)
    with closing(sqlite3.connect(h.db)) as conn:
        assert conn.execute("SELECT count(*) FROM report_binding_corrections").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM financial_acceptance_receipts").fetchone()[0] == 2
    (tmp_path / "d10-correction-proof.json").write_text(
        json.dumps(
            dict(
                old_snapshot=old_review["snapshot_id"],
                new_snapshot=new_review["snapshot_id"],
                correction=corrected.json(),
                new_receipt=new.json(),
                new_facts=saved.json(),
                old_receipt_invalid=True,
                old_facts_invalid=True,
                human_acceptance="pending",
                confirmation_kind="simulated_test",
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


@pytest.fixture
def h(tmp_path):
    return financial_harness(tmp_path)


def receipt(h, request_id="d10-simulated"):
    p = accept_payload(h, preview(h), request_id=request_id)
    r = h.client.post("/financial-facts/confirmations", json=p)
    assert r.status_code == 200, r.text
    return r.json(), p


def persist(h, r):
    return h.client.post("/financial-facts/persisted", json={"receipt_id": r["receipt_id"]})


def fact_counts(h):
    with closing(sqlite3.connect(h.db)) as c:
        return tuple(
            c.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("financial_fact_sets", "confirmed_financial_facts")
        )


def test_three_metrics_decimal_atomic_idempotent_restart_and_read_only(h, monkeypatch):
    r, request = receipt(h)
    assert fact_counts(h) == (0, 0)
    with ThreadPoolExecutor(max_workers=2) as pool:
        submitted = list(pool.map(lambda _: persist(h, r), range(2)))
    assert all(x.status_code == 200 for x in submitted), [x.text for x in submitted]
    saved = submitted[0].json()
    assert saved == submitted[1].json() and fact_counts(h) == (1, 6)
    assert saved["integrity"] == "verified" and saved["current_valid"]
    assert not saved["production_calculable"] and saved["confirmation_kind"] == "simulated_test"
    assert saved["review"] == r["review"]
    expected = {
        "revenue": "12345000.00",
        "net_profit_parent": "-127500.00",
        "operating_cash_flow": "-412500.00",
    }
    for fact in saved["facts"]:
        assert fact["confirmation_status"] == "confirmed"
        assert fact["basis_evidence"] and fact["evidence"] and fact["unit"] == "CNY_YUAN"
        if fact["period"] == 2031:
            assert fact["value_cny_yuan"] == expected[fact["metric_key"]]
    assemble(h)
    monkeypatch.setattr(
        h.candidates, "collect_metrics", Mock(side_effect=AssertionError("read extracted"))
    )
    monkeypatch.setattr(h.processor, "process", Mock(side_effect=AssertionError("read parsed")))
    read = h.client.get(f"/financial-facts/persisted/{r['receipt_id']}")
    assert read.status_code == 200 and read.json() == saved
    assert recovery(h, request).json() == r
    query = h.client.get(
        "/financial-facts",
        params=dict(
            company_id=h.company.company_id,
            period=2031,
            period_start="2031-01-01",
            period_end="2031-12-31",
            metric_key="net_profit_parent",
            document_id=h.id,
            source_revision=h.source["source_revision"],
            disclosure_version=saved["disclosure_version"],
        ),
    )
    assert query.status_code == 200, query.text
    assert len(query.json()["facts"]) == 1 and not query.json()["requires_version_selection"]
    assert fact_counts(h) == (1, 6)


@pytest.mark.parametrize(
    "body,status",
    [
        ({"receipt_id": "missing"}, 404),
        ({"receipt_id": "missing", "value_cny_yuan": "1"}, 422),
        ({"receipt_id": "missing", "confirmation_kind": "local_operator"}, 422),
        ({"accepted": False}, 422),
        ({"receipt_id": "missing", "workspace_id": "demo"}, 422),
    ],
)
def test_missing_cancelled_unaccepted_custom_amount_and_kind_rejected(h, body, status):
    preview(h)
    result = h.client.post("/financial-facts/persisted", json=body)
    assert result.status_code == status and fact_counts(h) == (0, 0)


@pytest.mark.parametrize("at", ["financial_fact_sets", "confirmed_financial_facts"])
def test_transaction_failure_rolls_back_all_rows_but_keeps_receipt(h, at):
    r, _ = receipt(h)
    with closing(sqlite3.connect(h.db)) as c, c:
        # Fail on the last of the 6 rows, after previous rows have been inserted.
        condition = (
            " WHEN NEW.metric_key='revenue' AND NEW.period=2031"
            if at == "confirmed_financial_facts"
            else ""
        )
        c.execute(
            f"CREATE TRIGGER d10_fault AFTER INSERT ON {at}{condition} BEGIN SELECT RAISE(ABORT,'test'); END"
        )
    assert persist(h, r).status_code == 500
    assert fact_counts(h) == (0, 0)
    assert h.client.get(f"/financial-facts/persisted/{r['receipt_id']}").status_code == 404
    with closing(sqlite3.connect(h.db)) as c:
        assert c.execute("SELECT count(*) FROM financial_acceptance_receipts").fetchone()[0] == 1


@pytest.mark.parametrize(
    "damage",
    [
        "amount",
        "unit",
        "row_missing",
        "all_rows_missing",
        "evidence",
        "layout",
        "header",
        "receipt",
    ],
)
def test_corruption_never_returns_calculable_facts(h, damage):
    r, _ = receipt(h)
    assert persist(h, r).status_code == 200
    with closing(sqlite3.connect(h.db)) as c, c:
        for name in (
            "d10_fact_immutable_update",
            "d10_fact_immutable_delete",
            "d10_set_immutable_update",
            "d9_acceptance_immutable_update",
            "d7_layout_immutable_update",
        ):
            c.execute(f"DROP TRIGGER {name}")
        if damage == "amount":
            c.execute(
                "UPDATE confirmed_financial_facts SET value_text='1' WHERE metric_key='revenue'"
            )
        elif damage == "unit":
            c.execute(
                "UPDATE confirmed_financial_facts SET raw_unit='元' WHERE metric_key='revenue'"
            )
        elif damage == "row_missing":
            c.execute("DELETE FROM confirmed_financial_facts WHERE metric_key='revenue'")
        elif damage == "all_rows_missing":
            c.execute("DELETE FROM confirmed_financial_facts")
        elif damage == "evidence":
            c.execute(
                "UPDATE document_evidence SET text='tampered' WHERE evidence_id=?",
                (r["review"]["source_evidence"][0]["evidence_id"],),
            )
        elif damage == "layout":
            c.execute("UPDATE document_evidence_layout SET payload_json='{}'")
        elif damage == "header":
            c.execute("UPDATE financial_fact_sets SET fact_count=1")
        else:
            c.execute("UPDATE financial_acceptance_receipts SET review_json='{}'")
    read = h.client.get(
        f"/financial-facts/persisted/{r['receipt_id']}", params={"include_invalid": True}
    )
    assert read.status_code == 500, read.text
    assert read.json()["detail"]["code"] == "confirmation_integrity_error"
    assert (
        h.client.get(
            "/financial-facts",
            params=dict(company_id=h.company.company_id, metric_key="net_profit_parent"),
        ).status_code
        == 500
    )


def test_unknown_after_commit_recovers_only_by_known_id(h, monkeypatch):
    r, _ = receipt(h)
    real = h.receipts.load_financial_facts
    monkeypatch.setattr(
        h.receipts, "load_financial_facts", Mock(side_effect=sqlite3.OperationalError("lost read"))
    )
    assert persist(h, r).status_code == 500 and fact_counts(h) == (1, 6)
    monkeypatch.setattr(h.receipts, "load_financial_facts", real)
    assert h.client.get(f"/financial-facts/persisted/{r['receipt_id']}").status_code == 200
    assert fact_counts(h) == (1, 6)


def test_receipt_changed_candidate_conflict_and_bad_unit_refused(h, monkeypatch):
    r, _ = receipt(h)
    original = h.confirmations.preview_financial
    for change in ({"status": "conflict"}, {"raw_unit": "元"}, {"value_cny_yuan": "42"}):

        async def corrupt(**kwargs):
            review = await original(**kwargs)
            p = review.to_payload()
            p["candidates"][0].update(change)
            return FinancialReview(review.workspace_id, canonical_payload(p))

        monkeypatch.setattr(h.confirmations, "preview_financial", corrupt)
        assert persist(h, r).status_code == 409
        assert fact_counts(h) == (0, 0)


def test_correction_between_reconstruction_and_fact_transaction_rolls_back(h, monkeypatch):
    r, _ = receipt(h)
    real = h.receipts.save_financial_facts

    def correct(**kwargs):
        assert (
            h.client.post(
                f"/documents/{h.id}/binding-corrections",
                json=dict(
                    expected_attempt=1,
                    metadata={**metadata(h.company.company_id, 2031), "basis": "unknown"},
                    reason="Explicit simulated transaction race",
                ),
            ).status_code
            == 200
        )
        return real(**kwargs)

    monkeypatch.setattr(h.receipts, "save_financial_facts", correct)
    result = persist(h, r)
    assert result.status_code == 409 and fact_counts(h) == (0, 0)


def test_source_correction_retains_history_and_excludes_old_facts(h):
    r, _ = receipt(h)
    assert persist(h, r).status_code == 200
    assert (
        h.client.post(
            f"/documents/{h.id}/binding-corrections",
            json=dict(
                expected_attempt=1,
                metadata={**metadata(h.company.company_id, 2031), "basis": "unknown"},
                reason="Explicit simulated invalidation",
            ),
        ).status_code
        == 200
    )
    assert h.client.get(f"/financial-facts/persisted/{r['receipt_id']}").status_code == 409
    historical = h.client.get(
        f"/financial-facts/persisted/{r['receipt_id']}", params={"include_invalid": True}
    )
    assert historical.status_code == 200 and not historical.json()["calculable"]
    assert historical.json()["invalid_reason"] == "source_changed"
    assert (
        h.client.get("/financial-facts", params=dict(company_id=h.company.company_id)).json()[
            "facts"
        ]
        == []
    )
    assert (
        len(
            h.client.get(
                "/financial-facts",
                params=dict(company_id=h.company.company_id, include_invalid=True),
            ).json()["facts"]
        )
        == 6
    )
    assert fact_counts(h) == (1, 6)


def test_byte_or_parser_change_invalidates_without_reparsing(h, monkeypatch):
    r, _ = receipt(h)
    assert persist(h, r).status_code == 200
    monkeypatch.setattr(
        h.candidates, "collect_metrics", Mock(side_effect=AssertionError("query extraction"))
    )
    monkeypatch.setattr(h.service, "parser_version", "future-parser")
    assert h.client.get(f"/financial-facts/persisted/{r['receipt_id']}").status_code == 409
    assert (
        h.client.get("/financial-facts", params=dict(company_id=h.company.company_id)).json()[
            "facts"
        ]
        == []
    )
    monkeypatch.undo()
    doc = h.docs.get(h.id)
    h.objects.put_bytes(doc.object_key, b"changed")
    assert h.client.get(f"/financial-facts/persisted/{r['receipt_id']}").status_code == 409


def test_scope_and_operator_kind_cannot_cross_receipts(h):
    r, _ = receipt(h)
    assert persist(h, r).status_code == 200
    from app.agent.revenue_confirmation import RevenueConfirmationError

    for kwargs in (
        dict(workspace_id="other", confirmation_kind="simulated_test"),
        dict(workspace_id="demo", confirmation_kind="local_operator"),
    ):
        with pytest.raises(RevenueConfirmationError, match="facts_not_found"):
            h.receipts.load_financial_facts(receipt_id=r["receipt_id"], **kwargs)
    assert h.client.get("/financial-facts", params=dict(company_id="missing")).status_code == 404
    assert (
        h.client.get(
            "/financial-facts", params=dict(company_id=h.company.company_id, scope="company")
        ).status_code
        == 422
    )


def test_conflicting_disclosures_preserved_and_require_explicit_version(h):
    old, _ = receipt(h)
    old_facts = persist(h, old).json()
    other = financial_harness(h.root / "other-pdf", year=2032, previous_value="99.00")
    raw = other.objects.read_bytes(other.docs.get(other.id).object_key)
    uploaded = h.upload(raw, metadata(h.company.company_id, 2032))
    assert uploaded.status_code == 202
    h.id = uploaded.json()["document_id"]
    assert h.processor.process(h.id).status == DocumentStatus.READY
    h.source = asyncio.run(h.service.source(h.id))
    h.selection.update(
        document_id=h.id, source_revision=h.source["source_revision"], periods=[2031]
    )
    new, _ = receipt(h, "new-disclosure")
    new_facts = persist(h, new).json()
    assert new_facts["disclosure_version"] != old_facts["disclosure_version"]
    found = h.client.get(
        "/financial-facts",
        params=dict(company_id=h.company.company_id, period=2031, metric_key="revenue"),
    ).json()
    assert len(found["facts"]) == 2 and found["requires_version_selection"]
    assert len(found["conflicting_periods"]) == 1 and found["automatic_selection"] is False
    assert {f["value_cny_yuan"] for f in found["facts"]} == {"12345000.00", "990000.00"}
    selected = h.client.get(
        "/financial-facts",
        params=dict(
            company_id=h.company.company_id,
            period=2031,
            metric_key="revenue",
            disclosure_version=new_facts["disclosure_version"],
        ),
    ).json()
    assert len(selected["facts"]) == 1 and not selected["requires_version_selection"]
    assert h.client.get(f"/financial-facts/persisted/{old['receipt_id']}").json() == old_facts


@pytest.mark.parametrize("field", ["review_json", "snapshot_id", "company_id"])
def test_corrupt_receipt_before_conversion_is_rejected_with_zero_facts(h, field):
    r, _ = receipt(h)
    with closing(sqlite3.connect(h.db)) as c, c:
        c.execute("DROP TRIGGER d9_acceptance_immutable_update")
        c.execute(
            f"UPDATE financial_acceptance_receipts SET {field}=?",
            ("{}" if field == "review_json" else "broken",),
        )
    result = persist(h, r)
    assert (
        result.status_code == 500
        and result.json()["detail"]["code"] == "confirmation_integrity_error"
    )
    assert fact_counts(h) == (0, 0)


@pytest.mark.parametrize(
    "params",
    [
        dict(period_start="2031-02-30"),
        dict(period_start="2031-12-31", period_end="2031-01-01"),
        dict(period=10000),
    ],
)
def test_query_rejects_invalid_actual_periods(h, params):
    result = h.client.get(
        "/financial-facts", params=dict(company_id=h.company.company_id, **params)
    )
    assert result.status_code == 422 and fact_counts(h) == (0, 0)


def test_acceptance_known_id_recovery_does_not_reconstruct_or_parse(h, monkeypatch):
    r, _ = receipt(h)
    monkeypatch.setattr(
        h.candidates, "collect_metrics", Mock(side_effect=AssertionError("GET extracted"))
    )
    monkeypatch.setattr(h.processor, "process", Mock(side_effect=AssertionError("GET parsed")))
    assert h.client.get(f"/financial-facts/acceptances/{r['receipt_id']}").json() == r
    assert h.client.get("/financial-facts/acceptances/missing").status_code == 404
    assert fact_counts(h) == (0, 0)
