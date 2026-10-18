"""Worst legal scope: four existing real reports, mixed 2024 disclosures, all-missing resume."""

import json
import hashlib
import os
from pathlib import Path
import sys
import time
import uuid

from dotenv import dotenv_values
from fastapi.testclient import TestClient

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
proof = json.loads((root / "product/validation/d21-real-research.json").read_text())
runtime = Path(proof["runtime_root"])
os.environ["FINDOC_D21_RUNTIME_ROOT"] = os.environ["FINDOC_RUNTIME_ROOT"] = str(runtime)
for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    assert os.environ[name] == "1"
for name, value in dotenv_values(root.parent / "findoc-rag/.env").items():
    if name.startswith("LLM_") and value is not None:
        os.environ[name] = value
from tests.support.d21_live_app import create_d21_app  # noqa: E402
from app.agent.sqlite_financial_facts import disclosure_version_for_source  # noqa: E402

repair = sys.argv[1:] == ["repair"]
prior = (
    json.loads((root / "product/validation/d21-four-document-capacity.json").read_text())
    if repair
    else None
)
app = create_d21_app()
record = dict(
    simulated_test=True, human_acceptance=0, actual_bge=True, actual_milvus=True, actual_llm=False
)
output = root / (
    "product/validation/d21-four-document-repair-capacity.json"
    if repair
    else "product/validation/d21-four-document-capacity.json"
)
if repair:
    from app.rag.openai_compatible_llm import ModelCompletion

    real_complete = app.state.template_service.model.complete
    attempts = []

    def first_response_fault(messages, tools):
        completion = real_complete(messages, tools)
        content = completion.message.get("content")
        attempts.append(
            dict(
                physical_attempt=len(attempts) + 1,
                original_response=content,
                original_sha256=hashlib.sha256(str(content).encode()).hexdigest(),
            )
        )
        if len(attempts) == 1 and isinstance(content, str):
            value = json.loads(content)
            value["controlled_extra_field"] = "D21 worst-branch fault injection"
            return ModelCompletion(
                {**completion.message, "content": json.dumps(value, ensure_ascii=False)},
                completion.finish_reason,
            )
        return completion

    app.state.template_service.model.complete = first_response_fault
    record["controlled_fault"] = (
        "Extra field injected only after first actual provider response; second attempt is actual provider protocol repair. No mock provider or synthetic PDF."
    )

with TestClient(app) as client:
    repo = app.state.task_repository
    with repo.registry._connect() as conn:
        publications = [
            dict(r)
            for r in conn.execute(
                "SELECT generation,manifest_sha256,state FROM index_publications ORDER BY generation"
            )
        ]
    sources = {
        r["report_id"]: client.get("/documents/" + r["source"]["document_id"] + "/source").json()
        for r in json.loads((runtime / "manifest.json").read_text())["reports"]
    }
    groups = {}
    for key in ("midea", "gree"):
        s = sources[key + "-2025"]
        if repair:
            with repo.registry._connect() as conn:
                rid = conn.execute(
                    "SELECT s.receipt_id FROM financial_fact_sets s JOIN confirmed_financial_facts f ON s.fact_set_id=f.fact_set_id WHERE s.document_id=? AND f.period=2024 AND f.metric_key='operating_cash_flow'",
                    (s["document_id"],),
                ).fetchone()[0]
            groups[s["document_id"]] = client.get("/financial-facts/persisted/" + rid).json()
            old = sources[key + "-2024"]
            with repo.registry._connect() as conn:
                rid = conn.execute(
                    "SELECT receipt_id FROM financial_fact_sets WHERE document_id=? ORDER BY saved_at LIMIT 1",
                    (old["document_id"],),
                ).fetchone()[0]
            groups[old["document_id"]] = client.get("/financial-facts/persisted/" + rid).json()
            continue
        selection = dict(
            document_id=s["document_id"],
            company_id=s["company_id"],
            source_revision=s["source_revision"],
            metric_keys=["operating_cash_flow"],
            periods=[2024],
            review_schema="financial-review-v1",
        )
        review = client.post("/financial-facts/reviews", json=selection).json()
        assert review["review_status"] == "ready_for_acceptance"
        receipt = client.post(
            "/financial-facts/confirmations",
            json=dict(
                **selection,
                accepted=True,
                snapshot_id=review["snapshot_id"],
                request_id="d21-four-doc-simulated-" + key,
            ),
        ).json()
        group = client.post(
            "/financial-facts/persisted", json=dict(receipt_id=receipt["receipt_id"])
        ).json()
        assert group["confirmation_kind"] == "simulated_test" and not group["production_calculable"]
        groups[s["document_id"]] = group
        old = sources[key + "-2024"]
        with repo.registry._connect() as conn:
            rid = conn.execute(
                "SELECT receipt_id FROM financial_fact_sets WHERE document_id=? ORDER BY saved_at LIMIT 1",
                (old["document_id"],),
            ).fetchone()[0]
        groups[old["document_id"]] = client.get("/financial-facts/persisted/" + rid).json()

    def side(key):
        return dict(
            company_id=sources[key + "-2024"]["company_id"],
            period=dict(year=2024, start="2024-01-01", end="2024-12-31", period_type="annual"),
            choices=[
                dict(
                    metric_key=m,
                    document_id=sources[key + ("-2025" if m == "operating_cash_flow" else "-2024")][
                        "document_id"
                    ],
                    disclosure_version=disclosure_version_for_source(
                        sources[key + ("-2025" if m == "operating_cash_flow" else "-2024")]
                    ),
                    fact_id=None,
                    fact_set_id=None,
                )
                for m in ("revenue", "net_profit_parent", "operating_cash_flow")
            ],
        )

    body = dict(
        operation_id=str(uuid.uuid4()),
        run_version="d21-operating-graph-v2",
        input=dict(
            schema_version="operating-research-input-v1",
            template="company_same_period_comparison",
            first=side("midea"),
            second=side("gree"),
            direction="business_overview",
            reports=[
                dict(document_id=s["document_id"], expected_source_revision=s["source_revision"])
                for s in sources.values()
            ],
        ),
    )
    if repair:
        body["parent_task_id"] = prior["task_id"]
    started = time.monotonic()
    waited = client.post("/research/tasks", json=body).json()
    assert waited["waiting_checkpoint"] and len(waited["snapshot"]["documents"]) == 4
    facts = []
    for name in ("first", "second"):
        for choice in waited["input"][name]["choices"]:
            g = groups[choice["document_id"]]
            fact = next(
                f
                for f in g["facts"]
                if f["period"] == 2024 and f["metric_key"] == choice["metric_key"]
            )
            facts.append(
                dict(
                    side=name,
                    metric_key=choice["metric_key"],
                    fact_set_id=g["fact_set_id"],
                    fact_id=fact["fact_id"],
                )
            )
    resumed = client.post(
        "/research/tasks/" + waited["task_id"] + "/resume",
        json=dict(
            operation_id=str(uuid.uuid4()), expected_revision=waited["revision"], facts=facts
        ),
    )
    result = resumed.json()
    local = runtime / (
        "d21-four-document-repair-result.json" if repair else "d21-four-document-result.json"
    )
    local.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    record.update(
        task_id=result["task_id"],
        status=result["status"],
        error_code=result["error_code"],
        http_status=resumed.status_code,
        budget=result["budget"],
        seconds=time.monotonic() - started,
        selected_reports=result["input"]["reports"],
        actual_llm=result["budget"]["used"]["model_calls"] > 0,
        full_local_result=str(local),
        operating_scope_caveat="Financial period 2024; cash-flow selected from 2025 comparative disclosure. Business excerpts disclose their actual report year, require semantic review.",
    )
    if result["final_research_content"]:
        c = result["final_research_content"]
        assert {d["citation"]["document_id"] for d in c["operating_descriptions"]} == {
            s["document_id"] for s in sources.values()
        }
        assert not c["verified_operating_attribution"] and c["human_review_status"] == "pending"
        record.update(
            citation_count=len(c["operating_descriptions"]),
            model_attempts=c["model_attempts"],
            financial_fact_ids=[f["fact"]["fact_id"] for f in c["financial_facts"]],
            human_review="pending",
        )
    with repo.registry._connect() as conn:
        after = [
            dict(r)
            for r in conn.execute(
                "SELECT generation,manifest_sha256,state FROM index_publications ORDER BY generation"
            )
        ]
    assert publications == after
    record["publications_unchanged"] = True
    if repair:
        record["original_physical_responses"] = attempts
        assert len(attempts) == result["budget"]["used"]["model_calls"] == 2
        assert result["budget"]["used"]["steps"] == 36
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(record, ensure_ascii=False))
    assert result["status"] == "completed", result["error_code"]
