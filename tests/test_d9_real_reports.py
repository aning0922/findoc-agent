"""Four original PDFs and 18 golden rows; acceptance is simulated_test only."""

import hashlib
import json
from pathlib import Path

import pytest

from app.documents.models import DocumentStatus
from tests.test_d7_real_reports import batch  # noqa: F401
from tests.test_document_sources import metadata
from tests.test_financial_reviews import assemble, counts, recovery


@pytest.mark.local_data
@pytest.mark.parametrize("report_id", ["midea-2024", "midea-2025", "gree-2024", "gree-2025"])
def test_d9_original_review_and_simulated_receipt(batch, report_id, tmp_path):  # noqa: F811
    h = assemble(batch)
    original = next(
        r
        for r in json.loads(Path("product/validation/sources.json").read_text())
        if r["id"] == report_id
    )
    raw = Path(original["path"]).read_bytes()  # Required, never skip D9 originals.
    assert hashlib.sha256(raw).hexdigest() == original["sha256"]
    gold = [
        r
        for r in json.loads(Path("product/validation/manual-benchmark.json").read_text())["facts"]
        if r["document_id"] == report_id
    ]
    company = h.original_companies[gold[0]["company"]]
    year = int(report_id.rsplit("-", 1)[1])
    h.id = h.upload(
        raw, {**metadata(company.company_id, year), "source_url": original["url"]}
    ).json()["document_id"]
    assert h.processor.process(h.id).status == DocumentStatus.READY
    source = h.client.get(f"/documents/{h.id}/source").json()
    h.selection = dict(
        review_schema="financial-review-v1",
        company_id=company.company_id,
        document_id=h.id,
        source_revision=source["source_revision"],
        metric_keys=list(dict.fromkeys(r["metric"] for r in gold)),
        periods=sorted({r["period"] for r in gold}),
    )
    before = counts(h)
    response = h.client.post("/financial-facts/reviews", json=h.selection)
    assert response.status_code == 200, response.text
    review = response.json()
    assert review["review_status"] == "ready_for_acceptance" and counts(h) == before
    results = []
    for expected in gold:
        actual = next(
            c
            for c in review["candidates"]
            if c["metric_key"] == expected["metric"] and c["period"] == expected["period"]
        )
        for field in (
            "value_cny_yuan",
            "raw_value",
            "raw_unit",
            "physical_page",
            "currency",
            "scope",
            "accounting_basis",
            "period_start",
            "period_end",
        ):
            assert actual[field] == expected[field], (expected["id"], field)
        for e in [*actual["evidence"], *actual["basis_evidence"]]:
            proof = h.client.get(
                f"/documents/{h.id}/evidence/{e['evidence_id']}",
                params=dict(
                    company_id=company.company_id, source_revision=source["source_revision"]
                ),
            )
            assert proof.status_code == 200 and proof.json()["physical_page"] == e["physical_page"]
        results.append(
            dict(id=expected["id"], actual=actual, success=True, human_acceptance="pending")
        )
    payload = {
        **h.selection,
        "snapshot_id": review["snapshot_id"],
        "accepted": False,
        "request_id": f"simulated-{report_id}",
    }
    assert h.client.post("/financial-facts/confirmations", json=payload).status_code == 409
    assert counts(h) == before
    payload["accepted"] = True
    result = h.client.post("/financial-facts/confirmations", json=payload)
    assert result.status_code == 200, result.text
    receipt = result.json()
    assert (
        receipt["confirmation_kind"] == "simulated_test"
        and receipt["facts_status"] == "pending_d10"
    )
    assemble(h)
    assert recovery(h, payload).json() == receipt
    assert counts(h) == (before[0] + 1, before[1], before[2])
    h.candidates._retriever.retrieve.assert_not_called()
    (tmp_path / "d9-review-proof.json").write_text(
        json.dumps(
            dict(
                report_id=report_id,
                source=source,
                snapshot_id=review["snapshot_id"],
                receipt=receipt,
                results=results,
                human_acceptance="pending",
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
