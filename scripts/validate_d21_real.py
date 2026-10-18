"""Four fixed-SHA real cases; real graph/retrieval/provider, isolated simulated_test receipts."""

import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import sys
import tempfile
import time
import uuid

from dotenv import dotenv_values
from fastapi.testclient import TestClient

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    assert os.environ.get(key) == "1"
for k, v in dotenv_values(root.parent / "findoc-rag/.env").items():
    if k.startswith("LLM_") and v is not None:
        os.environ[k] = v
os.environ["LLM_TIMEOUT_SECONDS"] = "90"
index = json.loads((root / "product/validation/d16-real-index.json").read_text())
runtime = (
    Path(sys.argv[1]) if sys.argv[1:] else Path(tempfile.mkdtemp(prefix="findoc-d11-d21-real-"))
)
if not sys.argv[1:]:
    shutil.copytree(index["runtime_root"], runtime, dirs_exist_ok=True)
os.environ["FINDOC_D21_RUNTIME_ROOT"] = str(runtime)
os.environ["FINDOC_RUNTIME_ROOT"] = str(runtime)
from tests.support.d21_live_app import create_d21_app  # noqa: E402
from app.agent.sqlite_financial_facts import disclosure_version_for_source  # noqa: E402

proof = dict(
    runtime_root=str(runtime),
    actual_bge=True,
    actual_milvus=True,
    actual_llm=True,
    bge="BAAI/bge-m3",
    llm=os.environ["LLM_MODEL"],
    index_rebuilt=False,
    acceptance_kind="simulated_test",
    human_acceptances=0,
    human_review="pending",
    cases=[],
)
output = root / "product/validation/d21-real-research.json"
full_output = root / "data/30d-foundation/d21-real-research-full.json"
if sys.argv[1:]:
    proof = json.loads(full_output.read_text())
    assert proof["runtime_root"] == str(runtime)


def save():
    from scripts.compact_d21_results import compact
    raw = json.dumps(proof, ensure_ascii=False, indent=2) + "\n"
    full_output.write_text(raw)
    output.write_text(json.dumps(compact(proof, str(full_output), hashlib.sha256(raw.encode()).hexdigest()),
                                 ensure_ascii=False, indent=2) + "\n")


def period(year):
    return dict(year=year, start=f"{year}-01-01", end=f"{year}-12-31", period_type="annual")


app = create_d21_app()
with TestClient(app) as client:
    repo = app.state.task_repository
    with repo.registry._connect() as conn:
        before = [
            dict(r)
            for r in conn.execute(
                "SELECT generation,manifest_sha256,state FROM index_publications ORDER BY generation"
            )
        ]
    sources = {
        r["report_id"]: client.get("/documents/" + r["document_id"] + "/source").json()
        for r in index["reports"]
    }
    for name, source in sources.items():
        expected = next(r for r in index["reports"] if r["report_id"] == name)["source"][
            "content_sha256"
        ]
        assert source["content_sha256"] == expected

    def side(name):
        s = sources[name]
        return dict(
            company_id=s["company_id"],
            period=period(s["report_year"]),
            choices=[
                dict(
                    metric_key=m,
                    document_id=s["document_id"],
                    disclosure_version=disclosure_version_for_source(s),
                    fact_set_id=None,
                    fact_id=None,
                )
                for m in ("revenue", "net_profit_parent", "operating_cash_flow")
            ],
        )

    cases = [
        ("A-midea", "company_period_change", "midea-2025", "midea-2024"),
        ("A-gree", "company_period_change", "gree-2025", "gree-2024"),
        ("B-2024", "company_same_period_comparison", "midea-2024", "gree-2024"),
        ("B-2025", "company_same_period_comparison", "midea-2025", "gree-2025"),
    ]
    if not sys.argv[1:]:
        waiting = []
        for name, template, a, b in cases:
            first, second = side(a), side(b)
            reports = [
                dict(
                    document_id=sources[n]["document_id"],
                    expected_source_revision=sources[n]["source_revision"],
                )
                for n in (a, b)
            ]
            request = dict(
                operation_id=str(uuid.uuid4()),
                run_version="d21-operating-graph-v2",
                input=dict(
                    schema_version="operating-research-input-v1",
                    template=template,
                    reports=reports,
                    first=first,
                    second=second,
                    direction="business_overview",
                ),
            )
            t = time.monotonic()
            response = client.post("/research/tasks", json=request)
            record = response.json()
            assert response.status_code == 200 and record["waiting_checkpoint"], record
            waiting.append((name, request, record))
            proof["cases"].append(
                dict(
                    name=name,
                    selected_sources=[sources[a], sources[b]],
                    waiting=record,
                    preparation_seconds=time.monotonic() - t,
                    simulated_test=True,
                )
            )
            save()
        groups = {}
        for name, s in sources.items():
            selection = dict(
                document_id=s["document_id"],
                company_id=s["company_id"],
                source_revision=s["source_revision"],
                metric_keys=["revenue", "net_profit_parent", "operating_cash_flow"],
                periods=[s["report_year"]],
                review_schema="financial-review-v1",
            )
            review = client.post("/financial-facts/reviews", json=selection).json()
            assert review["review_status"] == "ready_for_acceptance", review
            receipt = client.post(
                "/financial-facts/confirmations",
                json=dict(
                    **selection,
                    accepted=True,
                    snapshot_id=review["snapshot_id"],
                    request_id="d21-simulated-" + name,
                ),
            ).json()
            assert receipt["confirmation_kind"] == "simulated_test"
            group = client.post(
                "/financial-facts/persisted", json=dict(receipt_id=receipt["receipt_id"])
            ).json()
            assert (
                group["confirmation_kind"] == "simulated_test"
                and not group["production_calculable"]
            )
            groups[s["document_id"]] = group
    else:
        waiting = []
        for entry in proof["cases"]:
            wait = entry["waiting"]
            waiting.append((entry["name"], dict(input=wait["input"]), wait))
        groups = {}
        with repo.registry._connect() as conn:
            receipts = conn.execute(
                "SELECT receipt_id,document_id FROM financial_fact_sets WHERE confirmation_kind='simulated_test'"
            ).fetchall()
        for row in receipts:
            groups[row["document_id"]] = client.get(
                "/financial-facts/persisted/" + row["receipt_id"]
            ).json()
    (runtime / "manifest.json").write_text(
        json.dumps(
            dict(
                reports=[
                    dict(report_id=n, source=s, original_sha256=s["content_sha256"])
                    for n, s in sources.items()
                ],
                simulated_test=True,
            ),
            ensure_ascii=False,
        )
    )
    for entry, (_, request, wait) in zip(proof["cases"], waiting, strict=True):
        facts = [
            dict(
                side=side,
                metric_key=c["metric_key"],
                fact_set_id=groups[c["document_id"]]["fact_set_id"],
                fact_id=next(
                    f["fact_id"]
                    for f in groups[c["document_id"]]["facts"]
                    if f["metric_key"] == c["metric_key"]
                ),
            )
            for side in ("first", "second")
            for c in request["input"][side]["choices"]
        ]
        resume = entry.get("resume_request") or dict(
            operation_id=str(uuid.uuid4()), expected_revision=wait["revision"], facts=facts
        )
        t = time.monotonic()
        response = (
            client.get("/research/tasks/" + wait["task_id"])
            if entry.get("result", {}).get("status") == "completed"
            else client.post("/research/tasks/" + wait["task_id"] + "/resume", json=resume)
        )
        record = response.json()
        entry.update(
            resume_request=resume,
            http_status=response.status_code,
            result=record,
            resume_wall_seconds=time.monotonic() - t,
        )
        save()
        print(
            entry["name"],
            record.get("status"),
            record.get("error_code"),
            record.get("budget", {}).get("used"),
            flush=True,
        )
        assert response.status_code == 200 and record["status"] == "completed", record.get(
            "error_code"
        )
        content = record["final_research_content"]
        assert (
            content["human_review_status"] == "pending"
            and not content["verified_operating_attribution"]
        )
        for financial in content["financial_facts"]:
            fact = financial["fact"]
            group = groups[fact["document_id"]]
            original = next(f for f in group["facts"] if f["fact_id"] == fact["fact_id"])
            assert fact == original
        # Independently invoke the same D11/D13 service with the same IDs and compare whole contracts.
        from app.research.template_contracts import TemplateRequest
        from app.research.templates import TemplateSession

        session = TemplateSession(
            app.state.template_service, TemplateRequest.model_validate(record["active_input"])
        )
        import asyncio

        session.selection = asyncio.run(
            app.state.template_service.preparer.prepare_many(
                document_ids=[r["document_id"] for r in record["input"]["reports"]],
                query="财务结果独立核对",
            )
        )
        session.state = "analyzing"
        for analysis in content["deterministic_analysis"]:
            metric = analysis.get("metric_key") or analysis["rows"][0]["metric_key"]
            assert asyncio.run(session.analyze_metric(metric)) == analysis
        entry["financial_and_formula_check"] = (
            "Exact D10 fact snapshots and independent same-service D11/D13 whole-result equality"
        )
        citations = record["snapshot"]["operating_evidence"]["citations"]
        assert {c["document_id"] for c in citations} == {
            r["document_id"] for r in record["input"]["reports"]
        }
        entry["pdf_checks"] = []
        for citation in citations:
            pdf = client.get(
                "/documents/" + citation["document_id"] + "/file",
                params=dict(
                    company_id=citation["company_id"], source_revision=citation["source_revision"]
                ),
            )
            assert (
                pdf.status_code == 200
                and hashlib.sha256(pdf.content).hexdigest() == citation["content_sha256"]
            )
            import pymupdf

            with pymupdf.open(stream=pdf.content, filetype="pdf") as doc:
                assert 1 <= citation["physical_page"] <= len(doc)
                text = doc[citation["physical_page"] - 1].get_text()

                def normalized(s):
                    return "".join(s.split())

                # D6 parse text may normalize layout; verify a substantive substring on the physical page.
                phrases = re.findall(r"[\u4e00-\u9fff]{12,}", citation["text"])
                matches = [phrase for phrase in phrases if phrase in normalized(text)]
                assert len(matches) >= min(3, len(phrases)) and matches, (
                    "physical_page_text_mismatch",
                    citation["physical_page"],
                )
            entry["pdf_checks"].append(
                dict(
                    document_id=citation["document_id"],
                    physical_page=citation["physical_page"],
                    sha256=citation["content_sha256"],
                    page_text_match=True,
                    matched_original_phrases=matches[:3],
                )
            )
        assert (
            client.post("/research/tasks/" + wait["task_id"] + "/resume", json=resume).json()
            == record
        )
        assert client.get("/research/tasks/" + record["task_id"]).json() == record
        save()
    with repo.registry._connect() as conn:
        after = [
            dict(r)
            for r in conn.execute(
                "SELECT generation,manifest_sha256,state FROM index_publications ORDER BY generation"
            )
        ]
        assert (
            conn.execute(
                "SELECT count(*) FROM financial_acceptance_receipts WHERE confirmation_kind='local_operator'"
            ).fetchone()[0]
            == 0
        )
    assert before == after
    proof.update(
        publications_unchanged=True,
        status="four_cases_completed_engineering_only",
        ac30_19="pending",
        production_calculable=False,
        formal_report_module=False,
    )
    (runtime / "d21-results.json").write_text(
        json.dumps([c["result"] for c in proof["cases"]], ensure_ascii=False)
    )
    save()
print("D21 real four-case automation complete; human AC30-19 pending", flush=True)
