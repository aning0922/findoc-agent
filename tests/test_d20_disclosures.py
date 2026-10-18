"""Read-only adapter uses the exact D10 identity; no invented pending versions."""
from tests.test_financial_reviews import h as h, preview, accept_payload
from tests.test_d10_financial_facts import fact_counts
from app.agent.sqlite_financial_facts import disclosure_version_for_source


def test_pending_disclosure_matches_eventual_d10_fact_identity(h):
    before = fact_counts(h)
    source = h.source
    url = f"/research/disclosures/{h.id}"
    params = dict(company_id=source["company_id"], source_revision=source["source_revision"])
    result = h.client.get(url, params=params)
    assert result.status_code == 200
    assert result.json()["disclosure_versions"] == [disclosure_version_for_source(source)]
    assert result.json()["confirmed"] is False
    assert fact_counts(h) == before
    receipt = h.client.post("/financial-facts/confirmations", json=accept_payload(h, preview(h)))
    saved = h.client.post("/financial-facts/persisted", json={"receipt_id": receipt.json()["receipt_id"]})
    assert saved.status_code == 200
    assert saved.json()["disclosure_version"] == result.json()["disclosure_versions"][0]


def test_disclosure_rejects_stale_wrong_company_and_unknown_query(h):
    before = fact_counts(h)
    url = f"/research/disclosures/{h.id}"
    params = dict(company_id=h.source["company_id"], source_revision=h.source["source_revision"])
    assert h.client.get(url, params={**params, "source_revision": "0" * 64}).status_code == 409
    assert h.client.get(url, params={**params, "company_id": "wrong"}).status_code == 404
    assert h.client.get(url, params={**params, "budget": 100}).status_code == 422
    assert fact_counts(h) == before
