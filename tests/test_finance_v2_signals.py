"""UNIT_FAKE arithmetic and synthetic SQLite/source checks; human approvals=0, LLM=0.

Confirmed dictionaries in the arithmetic test are simulated internal adapter inputs,
not receipts minted through the production service.
"""
from copy import deepcopy
from decimal import Decimal
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.finance_v2.api import create_finance_v2_router
from app.finance_v2.contracts import FinanceError
from app.finance_v2.extraction import extract
from app.finance_v2.service import ExtendedFinanceService, OwnerAuthorization
from app.finance_v2.signals import build_signals
from tests.test_finance_v2 import assembled, geometry, operation, synthetic_pdf


def simulated_admitted():
    source, records = geometry()
    metrics = extract(source, records)
    for m in metrics:
        # Internal DTO fixture only; no actual local_operator receipt exists.
        m.update(status="confirmed", source_status="current_valid",
                 confirmation_ref={"receipt_id": "UNIT_FAKE_NOT_A_RECEIPT", "confirmation_kind": "local_operator"})
        m["as_of_date"] = "2031-01-01" if m["as_of_date"] == "2030-12-31" else m["as_of_date"]
        m["period"] = 2031
    return source, metrics


def test_simulated_decimal_exact_dates_and_denominator_rules():
    source, metrics = simulated_admitted()
    for m in metrics:
        old = m["as_of_date"] == "2031-01-01"
        m["value_decimal"] = ("9007199254740993.01" if old else "9007199254740993.04") if m["metric_key"] == "total_assets" else ("4503599627370496.505" if old else "4503599627370496.52")
    result = build_signals(source, metrics)
    assets, liabilities, ratio = result["signals"]
    assert assets["delta_decimal"] == "0.03" and liabilities["delta_decimal"] == "0.015"
    assert assets["from_date"] == "2031-01-01" and assets["to_date"] == "2031-12-31"
    assert ratio["from_percent_decimal"] == ratio["to_percent_decimal"] == "50.000000"
    assert ratio["delta_percentage_points_decimal"] == "0.000000"
    for m in metrics:
        m["value_decimal"] = "0" if m["as_of_date"] == "2031-01-01" else "3"
    result = build_signals(source, metrics)
    assert result["signals"][0]["change_percent_decimal"] is None
    assert result["signals"][0]["percent_unavailable_reason"] == "zero_baseline"
    assert result["signals"][2]["status"] == "missing" and result["notices"] == []
    metrics[0]["value_decimal"] = "-1"
    assert build_signals(source, metrics)["signals"][0]["change_percent_decimal"] is None
    source, metrics = simulated_admitted()
    # A nontrivial percentage/percentage-point result, not just equal ratios.
    result = build_signals(source, metrics)
    assert result["signals"][0]["change_percent_decimal"] == "23.450000"
    assert Decimal(result["signals"][2]["delta_percentage_points_decimal"]) == Decimal("-1.397327")


def test_simulated_missing_untrusted_and_duplicate_dates_fail_closed():
    source, metrics = simulated_admitted()
    for field, value in [("status", "candidate"), ("source_status", "unavailable"),
                         ("confirmation_ref", {"confirmation_kind": "simulated_test"})]:
        changed = deepcopy(metrics)
        for m in changed:
            m[field] = value
        assert all(s["status"] == "missing" for s in build_signals(source, changed)["signals"])
    with pytest.raises(FinanceError, match="ambiguous_signal_metric_date"):
        build_signals(source, metrics + [deepcopy(metrics[0])])
    extra = {**metrics[0], "as_of_date": "2031-06-30", "period": 2031}
    with pytest.raises(FinanceError, match="ambiguous_signal_date_pair"):
        build_signals(source, metrics + [extra])
    metrics[0]["source_revision"] = "f" * 64
    with pytest.raises(FinanceError, match="signal_source_mismatch"):
        build_signals(source, metrics)


def test_readonly_api_simulated_receipt_never_admitted_and_stale_source(tmp_path):
    root = tmp_path / "findoc-finance-v2-test-signals"
    h, company, document, source = assembled(root, synthetic_pdf())
    service = ExtendedFinanceService(root, h.service, confirmation_kind="simulated_test")
    app = FastAPI()
    authorization = OwnerAuthorization(root, "simulated-nohuman", time.time() + 60)
    app.include_router(create_finance_v2_router(service, owner_authorizer=lambda request: authorization))
    client = TestClient(app)
    params = dict(company_id=company, document_id=document, source_revision=source["source_revision"])
    url = "/financial/extended-signals"
    response = client.get(url, params=params)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert all(s["status"] == "missing" for s in response.json()["signals"])
    collected = client.post("/financial/extended-metrics/collect", json=operation(
        company_id=company, document_id=document, expected_source_revision=source["source_revision"])).json()
    review = client.post("/financial/extended-reviews", json=operation(metric_refs=[m["metric_id"] for m in collected["metrics"]])).json()
    receipt = client.post("/financial/extended-confirmations", json=operation(
        review_id=review["review_id"], review_sha256=review["review_sha256"], confirmed=True))
    assert receipt.status_code == 200 and receipt.json()["confirmation_kind"] == "simulated_test"
    with service.store.tx() as db:
        counts = [db.execute("SELECT count(*) FROM " + table).fetchone()[0] for table in ("fv2_operations", "fv2_analyses")]
    for _ in range(2):
        response = client.get(url, params=params)
        assert response.status_code == 200 and all(s["status"] == "missing" for s in response.json()["signals"])
    with service.store.tx() as db:
        assert counts == [db.execute("SELECT count(*) FROM " + table).fetchone()[0] for table in ("fv2_operations", "fv2_analyses")]
    assert client.get(url, params={**params, "latest": "true"}).status_code == 422
    assert client.get(url, params=[*params.items(), ("source_revision", source["source_revision"])]).status_code == 422
    doc = h.docs.get(document)
    h.objects._resolve_object_path(doc.object_key).write_bytes(b"%PDF-corrupt-simulated-source")
    response = client.get(url, params=params)
    assert response.status_code == 409 and "signals" not in response.json()
