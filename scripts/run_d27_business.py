"""Performance through real services/model; isolated simulated consent is explicit.

The production runtime gates remain unchanged. This test-only assembly cannot
issue a local_operator receipt or make a simulated fact production calculable.
"""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import time
import uuid


def run_business(live, runtime, proof, events, label, save):
    from app.agent.financial_analysis import IsolatedAnalysisTestConfig
    from app.agent.operating_research_graph import PersistentTemplateService
    from app.agent.sqlite_financial_facts import disclosure_version_for_source
    from app.api.research_tasks import create_task_router
    from app.api.report_drafts import create_report_router
    from app.research.templates import TemplateService
    from app.research.task_repository import TaskRepository
    from app.reports.service import ReportService
    from tests.support.d19_runtime import reopen

    h = reopen(runtime)
    isolated = IsolatedAnalysisTestConfig(runtime)
    templates = TemplateService(
        preparer=live.state.selection_preparer,
        facts=h.confirmations,
        workspace_id="demo",
        scope=live.state.selected_scope_search,
        isolated_test=isolated,
        model=live.state.template_service.model,
    )
    repo = TaskRepository(h.registry, "demo")
    repo.recover_interrupted()
    h.client.app.include_router(
        create_task_router(repo, PersistentTemplateService(templates, repo))
    )
    h.client.app.include_router(
        create_report_router(ReportService(repo, h.service, isolated_test=isolated))
    )
    client = h.client
    sources = {r["report_id"]: r["source"] for r in proof["reports"]}
    proof["business"] = dict(
        simulated_test=True, production_calculable=False, human_review="pending", calls=[], cases=[]
    )
    b = proof["business"]

    def request(method, path, body=None):
        t = time.perf_counter()
        response = getattr(client, method)(path, **({"json": body} if body is not None else {}))
        b["calls"].append(
            dict(
                label=label["value"],
                method=method,
                path=path,
                seconds=time.perf_counter() - t,
                http_status=response.status_code,
            )
        )
        save()
        if response.status_code not in (200, 202):
            b["calls"][-1]["failure_response"] = response.json()
            save()
            assert (
                path.endswith("/resume")
                and response.json().get("schema_version") == "persistent-template-task-v2"
            ), response.text
        return response

    def period(year):
        return dict(year=year, start=f"{year}-01-01", end=f"{year}-12-31", period_type="annual")

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

    waiting = []
    for name, template, first, second in [
        ("single-company", "company_period_change", "midea-2025", "midea-2024"),
        ("two-company", "company_same_period_comparison", "midea-2025", "gree-2025"),
    ]:
        label["value"] = name + "-create"
        body = dict(
            operation_id=str(uuid.uuid4()),
            run_version="d21-operating-graph-v2",
            input=dict(
                schema_version="operating-research-input-v1",
                template=template,
                reports=[
                    dict(
                        document_id=sources[n]["document_id"],
                        expected_source_revision=sources[n]["source_revision"],
                    )
                    for n in (first, second)
                ],
                first=side(first),
                second=side(second),
                direction="business_overview",
            ),
        )
        value = request("post", "/research/tasks", body).json()
        assert value["waiting_checkpoint"] and value["execution_status"] == "idle"
        assert not value["final_research_content"]
        waiting.append((name, body, value))
        b["cases"].append(dict(name=name, request=body, waiting=value))
    groups = {}
    for name in ("midea-2025", "midea-2024", "gree-2025"):
        label["value"] = name + "-simulated-financial-review"
        s = sources[name]
        selection = dict(
            document_id=s["document_id"],
            company_id=s["company_id"],
            source_revision=s["source_revision"],
            metric_keys=["revenue", "net_profit_parent", "operating_cash_flow"],
            periods=[s["report_year"]],
            review_schema="financial-review-v1",
        )
        review = request("post", "/financial-facts/reviews", selection).json()
        assert review["review_status"] == "ready_for_acceptance"
        receipt = request(
            "post",
            "/financial-facts/confirmations",
            dict(
                **selection,
                accepted=True,
                snapshot_id=review["snapshot_id"],
                request_id="d27-simulated-" + name,
            ),
        ).json()
        assert (
            receipt["confirmation_kind"] == "simulated_test"
            and receipt["facts_status"] == "pending_d10"
        )
        group = request(
            "post", "/financial-facts/persisted", dict(receipt_id=receipt["receipt_id"])
        ).json()
        assert group["confirmation_kind"] == "simulated_test" and not group["production_calculable"]
        groups[s["document_id"]] = group
    for entry, (name, body, wait) in zip(b["cases"], waiting, strict=True):
        label["value"] = name + "-resume"
        refs = [
            dict(
                side=side_name,
                metric_key=c["metric_key"],
                fact_set_id=groups[c["document_id"]]["fact_set_id"],
                fact_id=next(
                    f["fact_id"]
                    for f in groups[c["document_id"]]["facts"]
                    if f["metric_key"] == c["metric_key"]
                ),
            )
            for side_name in ("first", "second")
            for c in body["input"][side_name]["choices"]
        ]
        resume = dict(
            operation_id=str(uuid.uuid4()), expected_revision=wait["revision"], facts=refs
        )
        before, t = len(events), time.perf_counter()
        result = request("post", "/research/tasks/" + wait["task_id"] + "/resume", resume).json()
        entry.update(
            resume=resume,
            result=result,
            resume_seconds=time.perf_counter() - t,
            events=events[before:],
        )
        save()
        print(
            json.dumps(
                dict(
                    case=name,
                    status=result["status"],
                    error=result.get("error_code"),
                    seconds=entry["resume_seconds"],
                )
            ),
            flush=True,
        )
        if result["status"] != "completed":
            continue  # Preserve a real provider/quality failure; never fake a completed report.
        assert result["final_research_content"]["human_review_status"] == "pending"
        assert not result["final_research_content"]["verified_operating_attribution"]
        stable = len(events)
        assert (
            request("post", "/research/tasks/" + wait["task_id"] + "/resume", resume).json()
            == result
        )
        assert len(events) == stable
        label["value"] = name + "-reports"
        report_body = dict(
            operation_id=str(uuid.uuid4()),
            task_id=result["task_id"],
            expected_task_revision=result["revision"],
        )
        first = request("post", "/reports", report_body).json()
        rid = first["report"]["report_id"]
        second = request(
            "post",
            f"/reports/{rid}/revisions",
            report_body
            | dict(
                operation_id=str(uuid.uuid4()),
                expected_report_revision=1,
                edits=dict(
                    title="D27 性能验收模拟编辑", conclusions=["待人工审阅的模拟用户断言。"]
                ),
            ),
        ).json()
        entry["reports"] = [first, second]
        entry["exports"] = []
        stable = len(events)
        for revision in (1, 2):
            path = f"/reports/{rid}/revisions/{revision}/markdown"
            response = request("get", path)
            digest = hashlib.sha256(response.content).hexdigest()
            assert request("get", path).content == response.content
            (runtime / f"{rid}-v{revision}.md").write_bytes(response.content)
            entry["exports"].append(
                dict(revision=revision, markdown_sha256=digest, bytes=len(response.content))
            )
        # Read-only concurrency with identical exact version results.
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(
                pool.map(lambda _: request("get", f"/reports/{rid}/revisions/1/markdown"), range(4))
            )
        assert all(
            hashlib.sha256(r.content).hexdigest() == entry["exports"][0]["markdown_sha256"]
            for r in responses
        )
        assert len(events) == stable, "report/history invoked execution"
        entry["concurrent_reads"] = 4
        save()
    with repo.registry._connect() as conn:
        b["human_receipt_count"] = conn.execute(
            "SELECT count(*) FROM financial_acceptance_receipts WHERE confirmation_kind='local_operator'"
        ).fetchone()[0]
    assert b["human_receipt_count"] == 0
    (runtime / "d27-business-proof.json").write_text(json.dumps(b, ensure_ascii=False, indent=2))
    save()
