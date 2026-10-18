"""New disposable records; never import historic databases or operator consent."""

import copy
import uuid
import httpx


def seed_task_states(client, api, reports):
    metrics = ["revenue", "net_profit_parent", "operating_cash_flow"]
    with httpx.Client(timeout=120) as client:
        groups = {}
        for key in ["midea-2025", "midea-2024"]:
            s = next(r["source"] for r in reports if r["report_id"] == key)
            year = int(key[-4:])
            selection = dict(review_schema="financial-review-v1", company_id=s["company_id"],
                             document_id=s["document_id"], source_revision=s["source_revision"],
                             periods=[year], metric_keys=metrics)
            review = client.post(api + "/financial-facts/reviews", json=selection).json()
            receipt = client.post(api + "/financial-facts/confirmations", json={**selection,
                "snapshot_id": review["snapshot_id"], "request_id": str(uuid.uuid4()), "accepted": True}).json()
            group = client.post(api + "/financial-facts/persisted", json={"receipt_id": receipt["receipt_id"]}).json()
            assert group["confirmation_kind"] == "simulated_test" and not group["production_calculable"]
            groups[year] = group
        company = groups[2025]["company_id"]
        facts = client.get(api + "/financial-facts", params=dict(company_id=company, include_invalid="true")).json()["facts"]
        def side(year):
            g = groups[year]
            return dict(company_id=company, period=dict(year=year, start=f"{year}-01-01", end=f"{year}-12-31", period_type="annual"),
                        choices=[dict(metric_key=m, document_id=g["document_id"], disclosure_version=g["disclosure_version"],
                                      fact_set_id=g["fact_set_id"], fact_id=next(f["fact_id"] for f in facts if f["fact_set_id"] == g["fact_set_id"] and f["period"] == year and f["metric_key"] == m)) for m in metrics])
        frozen = dict(schema_version="operating-research-input-v1", template="company_period_change",
                      first=side(2025), second=side(2024), direction="business_overview",
                      reports=[dict(document_id=g["document_id"], expected_source_revision=g["source_revision"]) for g in groups.values()])
        tasks = {}
        for status in ["waiting", "completed", "failed"]:
            body = copy.deepcopy(frozen)
            if status == "waiting":
                for name in ["first", "second"]:
                    for c in body[name]["choices"]:
                        c["fact_id"] = c["fact_set_id"] = None
            client.post(api + "/__test__/ux-state/" + ("failed" if status == "failed" else "normal"))
            response = client.post(api + "/research/tasks", json=dict(operation_id=str(uuid.uuid4()), input=body, run_version="d21-operating-graph-v2"))
            t = response.json()
            assert t["status"] == ("awaiting_human_confirmation" if status == "waiting" else status), t
            tasks[status] = t
        client.post(api + "/__test__/ux-state/normal")
        return tasks
