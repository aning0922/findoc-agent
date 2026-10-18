"""Faults reach real isolated SQLite transactions and real ASGI business routes.

Response loss is injected after server response, never by fabricating a successful
body. TCP delivery loss and actual visible prompts are independently browser-tested.
"""

import json
import os
import sqlite3
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from app.api.research_tasks import create_task_router
from app.api.report_drafts import create_report_router
from app.documents.models import DocumentStatus
from app.reports.persistence_service import ReportPersistenceService
from app.agent.execution_budget import ExecutionBudget
from app.rag.openai_compatible_llm import ProviderCallError
from tests.test_document_sources import Harness
from tests.test_financial_reviews import (
    financial_harness,
    preview,
    accept_payload,
    recovery,
    assemble,
)
from tests.test_d10_financial_facts import fact_counts, persist
from tests.test_d11_financial_analysis import saved  # noqa: F401
from tests.test_d21_research import configured, request, response
from tests.test_d19_tasks import resume
from tests.test_d18_templates import Scripted, final, run
from tests.test_d22_reports import reports as d22_reports  # noqa: F401
from tests.test_d23_reports import req, counts as report_counts


class DropAfterResponse(httpx.BaseTransport):
    def __init__(self, delegate):
        self.delegate = delegate
        self.requests = []
        self.responses = []

    def handle_request(self, request):
        self.requests.append(
            dict(
                method=request.method,
                url=str(request.url),
                body=request.read().decode(errors="replace"),
            )
        )
        response = self.delegate.handle_request(request)
        self.responses.append(
            dict(status=response.status_code, body=response.read().decode(errors="replace"))
        )
        raise httpx.ReadTimeout(
            "D26 injected response loss AFTER business handler returned", request=request
        )


def dropped(client, path, **kwargs):
    transport = DropAfterResponse(client._transport)
    c = httpx.Client(transport=transport, base_url="http://testserver")
    with pytest.raises(httpx.ReadTimeout):
        c.post(path, **kwargs)
    assert len(transport.requests) == 1
    return transport


def proof(name, **data):
    if os.environ.get("FINDOC_D26_EVIDENCE_DIR"):
        (Path(os.environ["FINDOC_D26_EVIDENCE_DIR"]) / f"b-{name}.json").write_text(
            json.dumps(
                dict(
                    injection="real ASGI response delivery loss or real SQLite transaction fault as specified",
                    simulated_test=True,
                    human_acceptances=0,
                    **data,
                ),
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )


def snapshot(h, tables):
    with h.registry._connect() as c:
        return {
            t: [list(r) for r in c.execute(f"SELECT * FROM {t} ORDER BY rowid")] for t in tables
        }


def test_upload_response_unknown_get_only_recovery(tmp_path):
    h = Harness(tmp_path)
    from tests.test_document_sources import pdf_bytes, metadata

    content = pdf_bytes("D26 independent upload loss fixture")
    p = metadata(h.company.company_id)
    loss = dropped(
        h.client,
        "/report-documents",
        files={"file": ("d26-upload.pdf", content, "application/pdf")},
        data={"metadata": json.dumps(p)},
    )
    real = json.loads(loss.responses[0]["body"])
    assert loss.responses[0]["status"] == 202
    did = real["document_id"]
    initial = h.docs.get(did)
    for _ in range(3):
        assert h.client.get(f"/documents/{did}").json()["document_id"] == did
    assert h.docs.get(did) == initial
    assert len(run(h.documents.list_documents())) == 1 and h.dispatcher.dispatch.call_count == 1
    proof(
        "upload",
        requests=loss.requests,
        responses=loss.responses,
        document_id=did,
        server_state=h.client.get(f"/documents/{did}").json(),
        document_writes=1,
        upload_attempts=1,
        recovery_gets=3,
        automatic_resubmits=0,
        runtime_root=str(tmp_path),
    )


def test_acceptance_unknown_and_accepted_without_facts_remain_separate(tmp_path):
    h = financial_harness(tmp_path)
    p = accept_payload(h, preview(h), request_id="d26-lost-acceptance")
    loss = dropped(h.client, "/financial-facts/confirmations", json=p)
    assert loss.responses[0]["status"] == 200
    r = json.loads(loss.responses[0]["body"])
    assert fact_counts(h) == (0, 0)
    assemble(h)
    for _ in range(3):
        assert recovery(h, p).json() == r
    assert fact_counts(h) == (0, 0)
    assert h.client.get(f"/financial-facts/persisted/{r['receipt_id']}").status_code == 404
    with h.registry._connect() as c:
        assert c.execute("SELECT count(*) FROM financial_acceptance_receipts").fetchone()[0] == 1
    proof(
        "acceptance",
        request=p,
        receipt=r,
        requests=loss.requests,
        receipt_writes=1,
        fact_set_writes=0,
        fact_writes=0,
        recovery_gets=4,
        automatic_resubmits=0,
    )


def test_fact_transaction_rollback_then_explicit_save_unknown_recovery(tmp_path):
    h = financial_harness(tmp_path)
    p = accept_payload(h, preview(h), request_id="d26-facts")
    r = h.client.post("/financial-facts/confirmations", json=p).json()
    with h.registry._connect() as c:
        c.execute(
            "CREATE TRIGGER d26_abort AFTER INSERT ON confirmed_financial_facts WHEN NEW.metric_key='revenue' AND NEW.period=2031 BEGIN SELECT RAISE(ABORT,'D26 actual final-row failure'); END"
        )
        c.commit()
    failed = persist(h, r)
    assert failed.status_code == 500 and fact_counts(h) == (0, 0)
    assert h.client.get(f"/financial-facts/persisted/{r['receipt_id']}").status_code == 404
    assert recovery(h, p).json() == r
    with h.registry._connect() as c:
        c.execute("DROP TRIGGER d26_abort")
        c.commit()
    loss = dropped(h.client, "/financial-facts/persisted", json={"receipt_id": r["receipt_id"]})
    assert loss.responses[0]["status"] == 200
    saved_facts = json.loads(loss.responses[0]["body"])
    assert fact_counts(h) == (1, 6)
    assemble(h)
    for _ in range(3):
        assert h.client.get(f"/financial-facts/persisted/{r['receipt_id']}").json() == saved_facts
    assert fact_counts(h) == (1, 6)
    proof(
        "facts",
        receipt_id=r["receipt_id"],
        first_response=failed.json(),
        injection_trigger="actual AFTER INSERT on last revenue row: transaction rollback",
        committed_after_failure={"sets": 0, "facts": 0, "receipts": 1},
        explicit_save_attempts=2,
        committed_after_unknown={"sets": 1, "facts": 6, "receipts": 1},
        requests=loss.requests,
        saved=saved_facts,
        automatic_resubmits=0,
    )


def test_explicit_parser_upgrade_invalidates_qualification_preserves_snapshots(tmp_path):
    h = financial_harness(tmp_path)
    p = accept_payload(h, preview(h), request_id="d26-old-source")
    receipt = h.client.post("/financial-facts/confirmations", json=p).json()
    assert persist(h, receipt).status_code == 200
    tables = [
        "document_evidence",
        "document_evidence_layout",
        "financial_acceptance_receipts",
        "financial_fact_sets",
        "confirmed_financial_facts",
    ]
    before = snapshot(h, tables)
    old = h.source
    original = h.objects.read_bytes(h.docs.get(h.id).object_key)
    h.service.parser_version += ";explicit-upgrade-fixture"
    # Changing runtime parser configuration alone cannot create an implicit new source.
    assert h.client.get(f"/documents/{h.id}/source").status_code == 409
    assert snapshot(h, tables) == before
    result = h.client.post(f"/documents/{h.id}/reindex", json={"expected_attempt": old["attempt"]})
    assert result.status_code == 202, result.text
    assert h.processor.process(h.id).status == DocumentStatus.READY
    new = h.client.get(f"/documents/{h.id}/source").json()
    assert new["source_revision"] != old["source_revision"] and new["attempt"] > old["attempt"]
    after = snapshot(h, tables)
    for table in tables:
        assert after[table][: len(before[table])] == before[table]
    assert h.objects.read_bytes(h.docs.get(h.id).object_key) == original
    assert recovery(h, p).status_code == 409
    oldfacts = h.client.get(
        f"/financial-facts/persisted/{receipt['receipt_id']}", params={"include_invalid": True}
    ).json()
    assert not oldfacts["calculable"]
    h.selection["source_revision"] = new["source_revision"]
    reviewed = preview(h)
    assert (
        reviewed["review_status"] == "ready_for_acceptance"
        and reviewed["snapshot_id"] != p["snapshot_id"]
    )
    assert fact_counts(h) == (1, 6)
    proof(
        "source-upgrade",
        old=old,
        new=new,
        receipt_id=receipt["receipt_id"],
        historical_row_counts={t: len(v) for t, v in before.items()},
        all_old_rows_exact=True,
        original_pdf_exact=True,
        old_facts_calculable=False,
        new_receipts=0,
        new_fact_sets=0,
        explicit_reindex_requests=1,
        implicit_upgrade_writes=0,
    )


def test_create_resume_unknown_reads_never_reexecute(saved):  # noqa: F811
    h, g, _ = saved
    svc, repo, graph = configured(h)
    h.client.app.include_router(create_task_router(repo, graph))
    create = request(g, confirmed=False)
    loss = dropped(h.client, "/research/tasks", json=create.model_dump(mode="json"))
    wait = repo.by_operation(create.operation_id)
    assert wait["status"] == "awaiting_human_confirmation" and svc.model.calls == 0
    for _ in range(3):
        assert (
            h.client.get(f"/research/tasks/by-operation/{create.operation_id}").json()["task_id"]
            == wait["task_id"]
        )
    continued = resume(g, wait)
    loss2 = dropped(
        h.client,
        f"/research/tasks/{wait['task_id']}/resume",
        json=continued.model_dump(mode="json"),
    )
    real = repo.by_operation(continued.operation_id)
    assert real["status"] == "completed" and svc.model.calls == 1
    for _ in range(3):
        assert (
            h.client.get(f"/research/tasks/by-operation/{continued.operation_id}").json()["task_id"]
            == real["task_id"]
        )
    assert repo.get(real["task_id"]) == real and svc.model.calls == 1
    proof(
        "research-unknown",
        create=create.model_dump(mode="json"),
        resume=continued.model_dump(mode="json"),
        requests=loss.requests + loss2.requests,
        task_id=real["task_id"],
        create_state=wait,
        resume_state=real,
        model_calls=svc.model.calls,
        create_writes=1,
        resume_writes=1,
        automatic_resubmits=0,
    )


@pytest.mark.parametrize(
    "kind", ["provider_unknown", "known_protocol_failure", "tool_budget", "insufficient"]
)
def test_distinct_failure_terminals_no_uncertain_model_retry(saved, kind):  # noqa: F811
    h, g, _ = saved
    svc, repo, graph = configured(h)
    if kind == "provider_unknown":
        svc.model = Scripted(ProviderCallError(retryable=True), final(response()))
    elif kind == "known_protocol_failure":
        svc.model = Scripted(final("invalid JSON"), final("invalid JSON"))
    elif kind == "insufficient":
        from unittest.mock import AsyncMock

        svc.scope.search = AsyncMock(return_value=())
    else:
        normal = repo.start

        def exhaust(req):
            record, claim = normal(req)
            b = ExecutionBudget.restore(
                record["budget"], checkpoint=lambda v: repo.reserve(record["task_id"], claim, v)
            )
            b.tool_calls = b.limits.tool_calls
            b.checkpoint()
            return repo.get(record["task_id"]), claim

        repo.start = exhaust
    p = request(g)
    record = run(graph.start(p))
    assert record["status"] in ("failed", "refused") and record["final_research_content"] is None
    if kind == "provider_unknown":
        assert svc.model.calls == 1 and record["error_code"] == "operating_provider_unknown"
    if kind == "tool_budget":
        assert svc.model.calls == 0 and record["error_code"] == "budget_tool_calls_exhausted"
    if kind == "insufficient":
        assert svc.model.calls == 0 and record["status"] == "refused"
    assert repo.get(record["task_id"]) == record
    proof(
        kind,
        operation_id=p.operation_id,
        server_state=record,
        model_calls=svc.model.calls,
        task_writes=1,
        automatic_resubmits=0,
    )


def test_report_commit_unknown_history_failure_readonly_recovery(d22_reports, monkeypatch):  # noqa: F811
    h, _, drafts, task = d22_reports
    service = ReportPersistenceService(drafts)
    h.client.app.include_router(create_report_router(drafts))
    body = req(task).model_dump(mode="json")
    loss = dropped(h.client, "/reports", json=body)
    assert loss.responses[0]["status"] == 200
    value = json.loads(loss.responses[0]["body"])
    assert report_counts(service.repository)[:3] == (1, 1, 1)
    for _ in range(3):
        assert (
            h.client.get(f"/reports/by-operation/{body['operation_id']}").json()["report"]
            == value["report"]
        )
    with monkeypatch.context() as m:
        m.setattr(
            service.repository,
            "read_connection",
            Mock(side_effect=sqlite3.OperationalError("D26 injected SELECT unavailable")),
        )
        with pytest.raises(sqlite3.Error):
            service.repository.page(20, None)
    assert report_counts(service.repository)[:3] == (1, 1, 1)
    assert service.repository.get(value["report"]["report_id"], 1)["report"] == value["report"]
    proof(
        "report",
        operation_id=body["operation_id"],
        request=body,
        requests=loss.requests,
        saved=value,
        report_writes=1,
        revision_writes=1,
        operation_writes=1,
        history_read_injection="actual repository SELECT connection raises sqlite3.OperationalError; restored for GET",
        automatic_resubmits=0,
    )


def test_readonly_history_factory_exports_exact_saved_version_without_writes(d22_reports):  # noqa: F811
    from fastapi.testclient import TestClient
    from app.api.report_history import create_report_history_app
    from app.agent.financial_analysis import IsolatedAnalysisTestConfig
    from app.reports.markdown import render

    h, _, drafts, task = d22_reports
    saved_version = run(ReportPersistenceService(drafts).save(req(task)))
    before = {str(p.relative_to(h.root)): p.read_bytes() for p in h.root.rglob("*") if p.is_file()}
    app = create_report_history_app(
        h.db, sources=h.service, isolated_test=IsolatedAnalysisTestConfig(h.root)
    )
    client = TestClient(app)
    r = saved_version["report"]
    path = f"/reports/{r['report_id']}/revisions/1"
    assert client.get(path).json()["report"] == r
    exported = client.get(path + "/markdown")
    assert exported.status_code == 200, exported.text
    assert exported.content == render(r) and exported.headers["x-report-revision"] == "1"
    for url in [
        "/reports",
        "/reports/drafts",
        f"/reports/{r['report_id']}/revisions",
        f"/research/tasks/{task['task_id']}/resume",
    ]:
        assert client.post(url, json={}).status_code in (404, 405)
    assert {
        str(p.relative_to(h.root)): p.read_bytes() for p in h.root.rglob("*") if p.is_file()
    } == before
    proof(
        "readonly-export",
        report_id=r["report_id"],
        revision=1,
        payload_sha256=saved_version["payload_sha256"],
        markdown_sha256=exported.headers["x-markdown-sha256"],
        all_runtime_files_exact=True,
        http_mutation_routes_absent=True,
        model_calls=0,
        retrieval_calls=0,
    )
