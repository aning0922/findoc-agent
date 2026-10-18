"""D11 arithmetic and admission. Local-operator API success uses a read substitute.

All actual SQLite receipts here are simulated_test. A substituted local-operator
projection verifies the HTTP contract only; it does not prove human acceptance.
"""

import asyncio
from contextlib import closing
from dataclasses import replace
from decimal import Decimal, localcontext, Inexact
import json
import sqlite3
from unittest.mock import AsyncMock, Mock

from fastapi.testclient import TestClient
import pytest

from app.agent.finance_tools import financial_period_change_v1, revenue_growth_rate_v1
from app.agent.financial_analysis import (
    FinancialAnalysisService,
    FinancialFactReference,
    IsolatedAnalysisTestConfig,
)
from app.agent.revenue_confirmation import (
    ConfirmedFinancialFact,
    RevenueConfirmationError,
    canonical_payload,
)
from app.api.app import create_app
from tests.test_d10_financial_facts import receipt, persist, fact_counts
from tests.test_financial_reviews import financial_harness, assemble
from tests.test_document_sources import metadata
from app.documents.models import DocumentStatus


def reference(group, metric, year):
    p = group.to_payload() if hasattr(group, "to_payload") else group
    f = next(f for f in p["facts"] if f["metric_key"] == metric and f["period"] == year)
    return FinancialFactReference(
        p["fact_set_id"], f["fact_id"], year, p["source_revision"], p["disclosure_version"]
    )


def run(service, company, metric, current, previous):
    return asyncio.run(
        service.analyze(company_id=company, metric_key=metric, current=current, previous=previous)
    )


@pytest.fixture
def saved(tmp_path):
    root = tmp_path / "findoc-d11-analysis"
    h = financial_harness(root)
    r, _ = receipt(h)
    assert persist(h, r).status_code == 200
    group = h.receipts.load_financial_facts(
        workspace_id="demo", receipt_id=r["receipt_id"], confirmation_kind="simulated_test"
    )
    analysis = FinancialAnalysisService(
        facts=h.confirmations,
        workspace_id="demo",
        isolated_test=IsolatedAnalysisTestConfig(root),
    )
    return h, group, analysis


@pytest.mark.parametrize(
    "current,previous,delta,percent,transition",
    [
        ("120", "100", "20.00", "20.00", "ordinary"),
        ("1.005", "0", "1.01", None, "ordinary"),
        ("0", "0", "0.00", None, "ordinary"),
        ("50", "-100", "150.00", "-150.00", "negative_to_positive"),
        ("-50", "100", "-150.00", "-150.00", "positive_to_negative"),
        ("-50", "-100", "50.00", "-50.00", "both_negative"),
        ("-200", "-100", "-100.00", "100.00", "both_negative"),
        ("0", "-100", "100.00", "-100.00", "ordinary"),
        ("100.005", "100", "0.01", "0.01", "ordinary"),
        ("99.995", "100", "-0.01", "-0.01", "ordinary"),
    ],
)
def test_decimal_signs_zero_and_half_up(current, previous, delta, percent, transition):
    c, p = Decimal(current), Decimal(previous)
    result = financial_period_change_v1(c, p)
    assert result["absolute_change"] == delta and result["percentage_change"] == percent
    assert result["sign_transition"] == transition
    assert bool(result["limitations"]) == (p < 0)
    assert result["percentage_reason"] == ("zero_base" if p == 0 else None)
    assert "Infinity" not in str(result) and "NaN" not in str(result)
    if p:
        assert revenue_growth_rate_v1(c, p) == Decimal(percent)


def test_operand_precision_is_exact_and_independent_of_ambient_context():
    c = Decimal("1234567890123456789012345678901234567890.015")
    p = Decimal("1234567890123456789012345678901234567889.010")
    with localcontext() as ctx:
        ctx.prec = 3
        ctx.traps[Inexact] = True
        r = financial_period_change_v1(c, p)
        assert r["absolute_change"] == "1.01" and r["percentage_change"] == "0.00"
        assert ctx.prec == 3 and ctx.traps[Inexact]
    assert financial_period_change_v1(Decimal("1E+60"), Decimal("1"))["percentage_change"] == (
        "9" * 60 + "00.00"
    )


@pytest.mark.parametrize("invalid", [Decimal("NaN"), Decimal("Infinity"), 1.1, 0])
def test_arithmetic_rejects_non_decimal_or_nonfinite(invalid):
    with pytest.raises(ValueError):
        financial_period_change_v1(invalid, Decimal(1))


def test_three_metrics_read_only_restart_and_no_extraction(saved, monkeypatch):
    h, group, service = saved
    before = fact_counts(h)
    assemble(h)
    service = FinancialAnalysisService(
        facts=h.confirmations,
        workspace_id="demo",
        isolated_test=IsolatedAnalysisTestConfig(h.root),
    )
    monkeypatch.setattr(
        h.candidates, "collect_metrics", AsyncMock(side_effect=AssertionError("extract"))
    )
    monkeypatch.setattr(h.processor, "process", Mock(side_effect=AssertionError("parse")))
    for metric, percent in [
        ("revenue", "4838.00"),
        ("net_profit_parent", "-151.00"),
        ("operating_cash_flow", "-265.00"),
    ]:
        r = run(
            service,
            h.company.company_id,
            metric,
            reference(group, metric, 2031),
            reference(group, metric, 2030),
        )
        assert r["status"] == "analyzed" and r["percentage_change"] == percent
        assert not r["production_calculable"] and r["confirmation_kind"] == "simulated_test"
        assert r["current"]["raw_unit"] == "万元" and r["current"]["unit"] == "CNY_YUAN"
        for role in ("current", "previous"):
            assert r[role]["evidence"] and r[role]["basis_evidence"] and r[role]["source"]
        assert (
            run(
                service,
                h.company.company_id,
                metric,
                reference(group, metric, 2031),
                reference(group, metric, 2030),
            )
            == r
        )
    assert fact_counts(h) == before
    h.candidates.collect_metrics.assert_not_called()
    h.candidates._retriever.retrieve.assert_not_called()


@pytest.mark.parametrize(
    "case,reason",
    [
        ("current_missing", "missing_current_fact"),
        ("previous_missing", "missing_previous_fact"),
        ("version", "version_selection_required"),
        ("fact_id", "selection_mismatch"),
        ("period", "selection_mismatch"),
        ("source", "selection_mismatch"),
        ("wrong_version", "selection_mismatch"),
        ("metric", "metric_mismatch"),
        ("company", "company_mismatch"),
        ("reversed", "invalid_period_order"),
        ("same_period", "invalid_period_order"),
    ],
)
def test_bad_selections_block_without_values(saved, case, reason):
    h, g, service = saved
    c, p = reference(g, "revenue", 2031), reference(g, "revenue", 2030)
    company, metric = h.company.company_id, "revenue"
    if case == "current_missing":
        c = None
    elif case == "previous_missing":
        p = None
    elif case == "version":
        c = replace(c, disclosure_version=None)
    elif case == "fact_id":
        c = replace(c, fact_id="missing")
    elif case == "period":
        c = replace(c, period=2032)
    elif case == "source":
        c = replace(c, source_revision="0" * 64)
    elif case == "wrong_version":
        c = replace(c, disclosure_version="unselected")
    elif case == "metric":
        metric = "net_profit_parent"
    elif case == "company":
        company = "other"
    elif case == "reversed":
        c, p = p, c
    elif case == "same_period":
        c = p
    r = run(service, company, metric, c, p)
    assert r["status"] == "blocked" and r["reasons"][0]["code"] == reason
    assert r["absolute_change"] is r["percentage_change"] is r["current"] is None


def test_unknown_unconfirmed_wrong_workspace_and_simulated_production_fail(saved):
    h, g, service = saved
    c, p = reference(g, "revenue", 2031), reference(g, "revenue", 2030)
    for candidate_service, current in [
        (service, replace(c, fact_set_id="acceptance-with-no-facts")),
        (FinancialAnalysisService(facts=h.confirmations, workspace_id="other"), c),
        (FinancialAnalysisService(facts=h.confirmations, workspace_id="demo"), c),
    ]:
        with pytest.raises(RevenueConfirmationError, match="facts_not_found"):
            run(candidate_service, h.company.company_id, "revenue", current, p)
    body = api_body(h, g)
    response = h.client.post("/analyses", json=body)
    assert response.status_code == 404 and response.json()["detail"]["code"] == "facts_not_found"
    assert "absolute_change" not in response.json()


def api_body(h, g):
    from dataclasses import asdict

    return dict(
        schema_version="financial-analysis-v1",
        company_id=h.company.company_id,
        metric_key="revenue",
        current=asdict(reference(g, "revenue", 2031)),
        previous=asdict(reference(g, "revenue", 2030)),
    )


def test_isolated_config_bound_to_real_sqlite_path(saved, tmp_path):
    h, _, _ = saved
    for root in [tmp_path, tmp_path / "findoc-d11-wrong", h.root.parent / "findoc-d11-other"]:
        root.mkdir(exist_ok=True)
        with pytest.raises(ValueError, match="isolated"):
            FinancialAnalysisService(
                facts=h.confirmations,
                workspace_id="demo",
                isolated_test=IsolatedAnalysisTestConfig(root),
            )
    with pytest.raises(ValueError):
        FinancialAnalysisService(facts=h.confirmations, workspace_id=" ")


def substituted_group(g, changes, local_operator=False):
    facts = []
    for f in g.facts:
        payload = f.to_payload()
        payload.pop("fact_id")
        payload.pop("fact_set_id")
        payload.pop("confirmation_status")
        payload.pop("unit")
        payload.update(changes)
        facts.append(ConfirmedFinancialFact(f.fact_id, f.fact_set_id, canonical_payload(payload)))
    return replace(
        g,
        facts=tuple(facts),
        receipt=replace(
            g.receipt, confirmation_kind="local_operator" if local_operator else "simulated_test"
        ),
    )


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"currency": "USD"}, "unit_conflict"),
        ({"scope": "company"}, "scope_conflict"),
        ({"accounting_basis": "IFRS"}, "basis_conflict"),
        ({"period_type": "quarterly"}, "invalid_period"),
        ({"period_start": "2031-02-01"}, "invalid_period"),
        ({"status": "conflict"}, "facts_not_calculable"),
    ],
)
def test_defensive_admission_guards_with_controlled_read_substitute(saved, changes, reason):
    h, g, service = saved
    bad = substituted_group(g, changes)
    service._facts = Mock(read_financial_facts=AsyncMock(return_value=bad))
    r = run(
        service,
        h.company.company_id,
        "revenue",
        reference(g, "revenue", 2031),
        reference(g, "revenue", 2030),
    )
    assert r["status"] == "blocked" and r["reasons"][0]["code"] == reason


def test_actual_source_bytes_and_group_corruption_rejected(saved):
    h, g, service = saved
    c, p = reference(g, "revenue", 2031), reference(g, "revenue", 2030)
    raw = h.objects.read_bytes(h.docs.get(h.id).object_key)
    h.objects.put_bytes(h.docs.get(h.id).object_key, b"stale PDF")
    with pytest.raises(RevenueConfirmationError, match="source_changed"):
        run(service, h.company.company_id, "revenue", c, p)
    h.objects.put_bytes(h.docs.get(h.id).object_key, raw)
    with closing(sqlite3.connect(h.db)) as conn, conn:
        conn.execute("DROP TRIGGER d10_fact_immutable_update")
        conn.execute(
            "UPDATE confirmed_financial_facts SET value_text='0' WHERE metric_key='net_profit_parent'"
        )
    # Even a request for revenue must reject damage in another row of the group.
    with pytest.raises(RevenueConfirmationError, match="confirmation_integrity_error"):
        run(service, h.company.company_id, "revenue", c, p)


def test_correction_during_second_final_source_check_rejects_first_input(saved, monkeypatch):
    h, g, service = saved
    real = h.confirmations._source_reader.verify_financial_source
    calls = 0

    async def verify(review):
        nonlocal calls
        calls += 1
        await real(review)
        if calls == 4:
            result = h.client.post(
                f"/documents/{h.id}/binding-corrections",
                json=dict(
                    expected_attempt=1,
                    metadata={**metadata(h.company.company_id, 2031), "basis": "unknown"},
                    reason="D11 controlled race after second final source verification",
                ),
            )
            assert result.status_code == 200

    monkeypatch.setattr(h.confirmations._source_reader, "verify_financial_source", verify)
    with pytest.raises(RevenueConfirmationError, match="source_changed"):
        run(
            service,
            h.company.company_id,
            "revenue",
            reference(g, "revenue", 2031),
            reference(g, "revenue", 2030),
        )
    assert calls == 4


def test_explicit_conflicting_version_choice_and_nonadjacent_partial(saved):
    h, old, service = saved
    other = financial_harness(h.root / "other", year=2032, previous_value="99.00")
    raw = other.objects.read_bytes(other.docs.get(other.id).object_key)
    h.id = h.upload(raw, metadata(h.company.company_id, 2032)).json()["document_id"]
    assert h.processor.process(h.id).status == DocumentStatus.READY
    h.source = asyncio.run(h.service.source(h.id))
    h.selection.update(
        document_id=h.id, source_revision=h.source["source_revision"], periods=[2031, 2032]
    )
    r, _ = receipt(h, "conflict-disclosure")
    new = persist(h, r).json()
    assert h.client.get(
        "/financial-facts", params=dict(company_id=h.company.company_id, period=2031)
    ).json()["requires_version_selection"]
    missing = run(
        service,
        h.company.company_id,
        "revenue",
        replace(reference(new, "revenue", 2032), disclosure_version=None),
        reference(old, "revenue", 2031),
    )
    assert missing["reasons"][0]["code"] == "version_selection_required"
    original = run(
        service,
        h.company.company_id,
        "revenue",
        reference(new, "revenue", 2032),
        reference(old, "revenue", 2031),
    )
    restated = run(
        service,
        h.company.company_id,
        "revenue",
        reference(new, "revenue", 2032),
        reference(new, "revenue", 2031),
    )
    assert original["percentage_change"] == "0.00" and restated["percentage_change"] == "1146.97"
    gap = run(
        service,
        h.company.company_id,
        "revenue",
        reference(new, "revenue", 2032),
        reference(old, "revenue", 2030),
    )
    assert gap["status"] == "partial" and gap["absolute_change"] == "12095000.00"
    assert (
        gap["percentage_change"] is None
        and gap["percentage_reason"] == "non_adjacent_annual_periods"
    )


def contract_client(h, group):
    # No local_operator receipt is written: this substitute exercises serialization only.
    reader = Mock()
    reader.read_financial_facts = AsyncMock(return_value=group)
    reader.recheck_financial_analysis_sources = AsyncMock()
    client = TestClient(
        create_app(h.documents, revenue_service=reader, revenue_workspace_id="demo")
    )
    return client, reader


def test_http_success_contract_with_explicit_controlled_reader(saved):
    h, g, _ = saved
    client, reader = contract_client(h, substituted_group(g, {}, local_operator=True))
    before = fact_counts(h)
    r = client.post("/analyses", json=api_body(h, g))
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["schema"] == "financial-analysis-v1" and p["status"] == "analyzed"
    assert p["absolute_change"] == "12095000.00" and p["percentage_change"] == "4838.00"
    assert p["formula"]["legacy_formula_id"] == "revenue_growth_rate_v1"
    assert r.headers["cache-control"] == "no-store" and fact_counts(h) == before
    assert reader.read_financial_facts.await_count == 2
    reader.recheck_financial_analysis_sources.assert_awaited_once()
    reader.read_financial_facts.assert_awaited_with(
        workspace_id="demo", receipt_id=g.fact_set_id, confirmation_kind="local_operator"
    )
    assert {
        row[0]
        for row in sqlite3.connect(h.db).execute(
            "SELECT confirmation_kind FROM financial_fact_sets"
        )
    } == {"simulated_test"}


@pytest.mark.parametrize(
    "path,value",
    [
        ("amount", "123"),
        ("workspace_id", "other"),
        ("confirmation_kind", "simulated_test"),
        ("formula_id", "mine"),
        ("value_cny_yuan", "123"),
        ("isolated_test", True),
    ],
)
def test_api_rejects_money_and_control_fields(saved, path, value):
    h, g, _ = saved
    body = api_body(h, g)
    body[path] = value
    assert h.client.post("/analyses", json=body).status_code == 422
    body = api_body(h, g)
    body["current"][path] = value
    assert h.client.post("/analyses", json=body).status_code == 422


@pytest.mark.parametrize(
    "code,status",
    [("source_changed", 409), ("facts_not_found", 404), ("confirmation_integrity_error", 500)],
)
def test_api_safe_failures_publish_no_calculation(saved, code, status):
    h, g, _ = saved
    client, reader = contract_client(h, g)
    reader.read_financial_facts.side_effect = RevenueConfirmationError(code)
    r = client.post("/analyses", json=api_body(h, g))
    assert r.status_code == status and r.json()["detail"]["code"] == code
    assert "absolute_change" not in r.json() and r.headers["cache-control"] == "no-store"


def test_api_missing_versions_missing_facts_and_disabled(saved):
    h, g, _ = saved
    body = api_body(h, g)
    body["current"]["disclosure_version"] = None
    r = h.client.post("/analyses", json=body)
    assert r.status_code == 409 and r.json()["status"] == "blocked"
    body["current"] = None
    assert (
        h.client.post("/analyses", json=body).json()["reasons"][0]["code"] == "missing_current_fact"
    )
    disabled = TestClient(create_app(h.documents))
    assert disabled.post("/analyses", json=api_body(h, g)).status_code == 503


def test_actual_accepted_receipt_without_saved_facts_cannot_analyze(saved):
    h, g, service = saved
    accepted, _ = receipt(h, "d11-unpersisted-acceptance")
    assert accepted["facts_status"] == "pending_d10"
    with pytest.raises(RevenueConfirmationError, match="facts_not_found"):
        run(
            service,
            h.company.company_id,
            "revenue",
            replace(reference(g, "revenue", 2031), fact_set_id=accepted["receipt_id"]),
            reference(g, "revenue", 2030),
        )


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"production_calculable": False}, "production_calculable_required"),
        ({"confirmation_kind": "simulated_test"}, "production_calculable_required"),
        ({"current_valid": False}, "facts_not_calculable"),
        ({"calculable": False}, "facts_not_calculable"),
    ],
)
def test_production_checks_calculability_even_with_controlled_reader(saved, change, reason):
    h, g, _ = saved
    local = substituted_group(g, {}, local_operator=True)
    stub = Mock(wraps=local)
    stub.receipt = local.receipt
    stub.to_payload.return_value = {**local.to_payload(), **change}
    client, _ = contract_client(h, stub)
    r = client.post("/analyses", json=api_body(h, g))
    assert r.status_code == 409 and r.json()["reasons"][0]["code"] == reason
    assert r.json()["current"] is None and r.json()["absolute_change"] is None


def test_unit_conflict_is_not_automatically_converted_from_untrusted_read(saved):
    h, g, service = saved
    stub = Mock(wraps=g)
    stub.receipt = g.receipt
    payload = g.to_payload()
    payload["facts"][0]["unit"] = "CNY_100_MILLION"
    # Use the actual selected revenue row, independent of SQLite row order.
    next(f for f in payload["facts"] if f["metric_key"] == "revenue" and f["period"] == 2031)[
        "unit"
    ] = "CNY_100_MILLION"
    stub.to_payload.return_value = payload
    service._facts = Mock(read_financial_facts=AsyncMock(return_value=stub))
    r = run(
        service,
        h.company.company_id,
        "revenue",
        reference(g, "revenue", 2031),
        reference(g, "revenue", 2030),
    )
    assert r["status"] == "blocked" and r["reasons"][0]["code"] == "unit_conflict"


def test_http_zero_base_partial_and_final_gate_failure(saved):
    h, g, _ = saved
    zero = substituted_group(g, {"raw_value": "0", "value_cny_yuan": "0"}, local_operator=True)
    client, reader = contract_client(h, zero)
    r = client.post("/analyses", json=api_body(h, g))
    assert r.status_code == 200 and r.json()["status"] == "partial"
    assert r.json()["absolute_change"] == "0.00" and r.json()["percentage_change"] is None
    assert r.json()["percentage_reason"] == "zero_base"
    reader.recheck_financial_analysis_sources.side_effect = RevenueConfirmationError(
        "source_changed"
    )
    failed = client.post("/analyses", json=api_body(h, g))
    assert failed.status_code == 409 and "absolute_change" not in failed.json()


@pytest.mark.parametrize("precision", [16, 28, 50])
def test_legacy_formula_matches_frozen_expression_in_its_original_context(precision):
    with localcontext() as ctx:
        ctx.prec = precision
        for c, p in [
            (Decimal("407149600000"), Decimal("373710000000")),
            (Decimal("120"), Decimal("100")),
            (Decimal("50"), Decimal("-100")),
            (Decimal("99.995"), Decimal("100")),
        ]:
            from decimal import ROUND_HALF_UP

            expected = ((c - p) / p * Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            assert revenue_growth_rate_v1(c, p) == expected


def test_two_documents_final_transaction_rechecks_first_after_second_pdf(saved, monkeypatch):
    h, old, service = saved
    other = financial_harness(h.root / "second-report", year=2032)
    raw = other.objects.read_bytes(other.docs.get(other.id).object_key)
    h.id = h.upload(raw, metadata(h.company.company_id, 2032)).json()["document_id"]
    assert h.processor.process(h.id).status == DocumentStatus.READY
    h.source = asyncio.run(h.service.source(h.id))
    h.selection.update(
        document_id=h.id, source_revision=h.source["source_revision"], periods=[2032]
    )
    accepted, _ = receipt(h, "second-document-race")
    new = persist(h, accepted).json()
    real = h.confirmations._source_reader.verify_financial_source
    calls = 0

    async def verify(review):
        nonlocal calls
        calls += 1
        await real(review)
        if calls == 4:
            # The second (old) report was checked, while the FIRST input is corrected.
            assert review.to_payload()["source"]["document_id"] == old.to_payload()["document_id"]
            correction = h.client.post(
                f"/documents/{h.id}/binding-corrections",
                json=dict(
                    expected_attempt=1,
                    metadata={**metadata(h.company.company_id, 2032), "basis": "unknown"},
                    reason="D11 explicit two-document final-admission race",
                ),
            )
            assert correction.status_code == 200

    monkeypatch.setattr(h.confirmations._source_reader, "verify_financial_source", verify)
    with pytest.raises(RevenueConfirmationError, match="source_changed"):
        run(
            service,
            h.company.company_id,
            "revenue",
            reference(new, "revenue", 2032),
            reference(old, "revenue", 2031),
        )
    assert calls == 4


@pytest.mark.parametrize(
    "metric,transition",
    [
        ("net_profit_parent", "loss_to_profit"),
        ("operating_cash_flow", "negative_to_positive"),
        ("revenue", "negative_to_positive"),
    ],
)
def test_sign_transition_labels_only_call_net_profit_profit_or_loss(saved, metric, transition):
    h, g, service = saved
    facts = []
    for f in g.facts:
        payload = json.loads(f.candidate_json)
        payload.update(
            raw_value="50" if payload["period"] == 2031 else "-100",
            value_cny_yuan="500000" if payload["period"] == 2031 else "-1000000",
        )
        facts.append(ConfirmedFinancialFact(f.fact_id, f.fact_set_id, canonical_payload(payload)))
    controlled = replace(g, facts=tuple(facts))
    service._facts = Mock(
        read_financial_facts=AsyncMock(return_value=controlled),
        recheck_financial_analysis_sources=AsyncMock(),
    )
    r = run(
        service,
        h.company.company_id,
        metric,
        reference(g, metric, 2031),
        reference(g, metric, 2030),
    )
    assert r["sign_transition"] == transition and r["percentage_change"] == "-150.00"
    assert r["limitations"][0]["code"] == "negative_base"
