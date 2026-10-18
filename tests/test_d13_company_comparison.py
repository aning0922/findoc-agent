"""D13 shared admission + API. Persisted acceptance is simulated_test only."""

import asyncio
from dataclasses import asdict, replace
from unittest.mock import AsyncMock, Mock

import pytest
from app.agent.revenue_confirmation import RevenueConfirmationError
from app.companies.models import CompanyCreate
from app.documents.models import DocumentStatus
from tests.test_d11_financial_analysis import (
    saved as saved,
    reference,
    substituted_group,
    contract_client,
)
from tests.test_d10_financial_facts import receipt, persist, fact_counts
from tests.test_document_sources import metadata
from tests.test_financial_reviews import financial_harness


@pytest.fixture
def paired(saved):
    h, a, service = saved
    other = financial_harness(h.root / "second", previous_value="26.00")
    company_b = h.companies.create(
        CompanyCreate(name=h.company.name, security_code="600124", exchange="SSE")
    )
    raw = other.objects.read_bytes(other.docs.get(other.id).object_key)
    document = h.upload(raw, metadata(company_b.company_id, 2031)).json()["document_id"]
    assert h.processor.process(document).status == DocumentStatus.READY
    source = h.client.get(f"/documents/{document}/source").json()
    h.selection = dict(
        review_schema="financial-review-v1",
        company_id=company_b.company_id,
        document_id=document,
        source_revision=source["source_revision"],
        metric_keys=["revenue", "net_profit_parent", "operating_cash_flow"],
        periods=[2030, 2031],
    )
    r, _ = receipt(h, "d13-company-b")
    assert persist(h, r).status_code == 200
    b = h.receipts.load_financial_facts(
        workspace_id="demo", receipt_id=r["receipt_id"], confirmation_kind="simulated_test"
    )
    return h, a, b, service


def compare(paired, *, period=2031, selections=None, a_id=None, b_id=None):
    h, a, b, service = paired
    return asyncio.run(
        service.compare(
            company_a_id=a_id or h.company.company_id,
            company_b_id=b_id or b.to_payload()["company_id"],
            period=period,
            selections=selections
            if selections is not None
            else {
                m: (reference(a, m, period), reference(b, m, period))
                for m in ("revenue", "net_profit_parent", "operating_cash_flow")
            },
        )
    )


def body(paired, period=2031):
    h, a, b, _ = paired
    return dict(
        schema_version="financial-company-comparison-v1",
        company_a_id=h.company.company_id,
        company_b_id=b.to_payload()["company_id"],
        period=period,
        selections=[
            dict(metric_key=m, a=asdict(reference(a, m, period)), b=asdict(reference(b, m, period)))
            for m in ("revenue", "net_profit_parent", "operating_cash_flow")
        ],
    )


def test_durable_two_companies_same_year_signed_base_and_read_only(paired):
    h, _, _, _ = paired
    before = fact_counts(h)
    r = compare(paired)
    assert r["status"] == "compared" and not r["production_calculable"]
    assert all(row["absolute_change"] == "0.00" for row in r["rows"])
    assert r["formula"]["percentage_change_id"] == "financial_company_relative_signed_base_v1"
    assert r["formula"]["base"] == "company_a"
    assert len(r["rows"][1]["limitations"]) == 1
    assert fact_counts(h) == before
    r = compare(paired, period=2030)
    assert all(row["absolute_change"] == "10000.00" for row in r["rows"])
    assert all(row["percentage_change"] == "4.00" for row in r["rows"])


@pytest.mark.parametrize("missing", ["a", "b", "both"])
def test_incomplete_only_affects_missing_metric(paired, missing):
    _, a, b, _ = paired
    selections = {
        m: (reference(a, m, 2031), reference(b, m, 2031))
        for m in ("revenue", "net_profit_parent", "operating_cash_flow")
    }
    selections["revenue"] = (
        None if missing in ("a", "both") else reference(a, "revenue", 2031),
        None if missing in ("b", "both") else reference(b, "revenue", 2031),
    )
    r = compare(paired, selections=selections)
    row = r["rows"][0]
    assert row["status"] == "incomplete" and row["absolute_change"] is None
    assert all(row["status"] == "compared" for row in r["rows"][1:])
    if missing != "both":
        assert row["b" if missing == "a" else "a"] is not None
    empty = compare(paired, selections={"revenue": (None, None)})
    assert empty["rows"][0]["status"] == "incomplete"


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"currency": "USD"}, "unit_conflict"),
        ({"scope": "company"}, "scope_conflict"),
        ({"accounting_basis": "IFRS"}, "basis_conflict"),
        ({"period_type": "quarterly"}, "invalid_period"),
        ({"period_end": "2031-06-30"}, "invalid_period"),
        ({"status": "conflict"}, "facts_not_calculable"),
        ({"metric_key": "net_profit_parent"}, "metric_mismatch"),
    ],
)
def test_shared_admission_rejects_incompatible_read_contracts(paired, changes, code):
    h, a, b, s = paired
    bad = substituted_group(b, changes)
    s._facts = Mock(
        read_financial_facts=AsyncMock(side_effect=[a, bad]),
        recheck_financial_analysis_sources=AsyncMock(),
    )
    r = compare(
        paired,
        selections={"revenue": (reference(a, "revenue", 2031), reference(b, "revenue", 2031))},
    )
    row = r["rows"][0]
    assert row["status"] == "blocked" and row["reasons"][0]["code"] == code
    assert row["a"] is None and row["b"] is None
    assert row["absolute_change"] is None


@pytest.mark.parametrize(
    "a_value,b_value,delta,percent",
    [
        ("0", "100", "1000000.00", None),
        ("0", "0", "0.00", None),
        ("-100", "50", "1500000.00", "-150.00"),
        ("100", "-50", "-1500000.00", "-150.00"),
        ("-100", "-50", "500000.00", "-50.00"),
    ],
)
def test_zero_negative_and_cross_zero_use_original_decimal_kernel(
    paired, a_value, b_value, delta, percent
):
    _, a, b, s = paired

    def amount(g, v):
        from decimal import Decimal

        return substituted_group(g, {"raw_value": v, "value_cny_yuan": str(Decimal(v) * 10000)})

    s._facts = Mock(
        read_financial_facts=AsyncMock(side_effect=[amount(a, a_value), amount(b, b_value)]),
        recheck_financial_analysis_sources=AsyncMock(),
    )
    row = compare(
        paired,
        selections={"revenue": (reference(a, "revenue", 2031), reference(b, "revenue", 2031))},
    )["rows"][0]
    assert (row["absolute_change"], row["percentage_change"]) == (delta, percent)
    assert row["status"] == ("partial" if percent is None else "compared")
    assert bool(row["limitations"]) == a_value.startswith("-")


@pytest.mark.parametrize(
    "change,code",
    [
        ({"period": 2030}, "period_mismatch"),
        ({"disclosure_version": None}, "version_selection_required"),
        ({"source_revision": "a" * 64}, "selection_mismatch"),
        ({"fact_id": "wrong"}, "selection_mismatch"),
    ],
)
def test_explicit_period_and_version_identity(paired, change, code):
    _, a, b, _ = paired
    row = compare(
        paired,
        selections={
            "revenue": (
                reference(a, "revenue", 2031),
                replace(reference(b, "revenue", 2031), **change),
            )
        },
    )["rows"][0]
    assert row["status"] == "blocked" and row["reasons"][0]["code"] == code


def test_same_company_rejected_and_production_refuses_actual_simulation(paired):
    h, _, _, _ = paired
    assert (
        compare(paired, b_id=h.company.company_id)["rows"][0]["reasons"][0]["code"]
        == "same_company"
    )
    r = h.client.post("/analyses/company-comparison", json=body(paired))
    assert r.status_code == 404 and r.json()["detail"]["code"] == "facts_not_found"


@pytest.mark.parametrize(
    "field,value",
    [
        ("value_cny_yuan", "100"),
        ("confirmation_kind", "local_operator"),
        ("production_calculable", True),
        ("isolated_test", True),
    ],
)
def test_formal_api_rejects_client_money_and_operator_fields(paired, field, value):
    h, _, _, _ = paired
    for where in ("root", "selection", "ref"):
        p = body(paired)
        target = (
            p
            if where == "root"
            else p["selections"][0]
            if where == "selection"
            else p["selections"][0]["a"]
        )
        target[field] = value
        assert h.client.post("/analyses/company-comparison", json=p).status_code == 422


def test_controlled_local_operator_contract_final_recheck_and_no_publication_on_failure(paired):
    h, a, b, _ = paired
    client, reader = contract_client(h, a)
    reader.read_financial_facts.side_effect = lambda **kw: substituted_group(
        a if kw["receipt_id"] == a.fact_set_id else b, {}, local_operator=True
    )
    r = client.post("/analyses/company-comparison", json=body(paired))
    assert r.status_code == 200 and r.json()["production_calculable"]
    assert r.headers["cache-control"] == "no-store"
    groups = reader.recheck_financial_analysis_sources.await_args.kwargs["groups"]
    assert len(groups) == 6 and len({g.to_payload()["company_id"] for g in groups}) == 2
    reader.recheck_financial_analysis_sources.side_effect = RevenueConfirmationError(
        "source_changed"
    )
    failed = client.post("/analyses/company-comparison", json=body(paired))
    assert failed.status_code == 409 and "rows" not in failed.json()
    assert failed.json()["schema"] == "financial-company-comparison-v1"
    p = body(paired)
    p["selections"].append(p["selections"][0])
    assert client.post("/analyses/company-comparison", json=p).status_code == 422


def test_real_correction_during_second_final_source_check_blocks_both_companies(
    paired, monkeypatch
):
    h, a, b, s = paired
    real = h.confirmations._source_reader.verify_financial_source
    calls = 0

    async def verify(review):
        nonlocal calls
        calls += 1
        await real(review)
        if calls == 4:
            result = h.client.post(
                f"/documents/{a.to_payload()['document_id']}/binding-corrections",
                json=dict(
                    expected_attempt=1,
                    metadata={**metadata(h.company.company_id, 2031), "basis": "unknown"},
                    reason="D13 isolated final dual-company race",
                ),
            )
            assert result.status_code == 200

    monkeypatch.setattr(h.confirmations._source_reader, "verify_financial_source", verify)
    with pytest.raises(RevenueConfirmationError, match="source_changed"):
        compare(
            paired,
            selections={"revenue": (reference(a, "revenue", 2031), reference(b, "revenue", 2031))},
        )
    assert calls == 4
