"""Persistent graph engineering tests; all actual receipts are isolated simulated_test."""

from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import sqlite3
from unittest.mock import AsyncMock
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.agent.operating_research_graph import PersistentTemplateService
from app.api.research_tasks import create_task_router
from app.research.repository import HistoryError
from app.research.task_contracts import StartTask, ResumeTask
from app.research.task_repository import TaskRepository
from tests.test_d11_financial_analysis import saved as saved
from tests.test_d13_company_comparison import paired as paired
from tests.test_d18_templates import body, service, run
from tests.test_d10_financial_facts import fact_counts


def setup(h, simulated=True):
    svc = service(h, simulated)
    svc.scope.search = AsyncMock(return_value=())
    repo = TaskRepository(h.companies._repository, "demo")
    return svc, repo, PersistentTemplateService(svc, repo)


def start(g, confirmed=False):
    return StartTask.model_validate(
        dict(operation_id=str(uuid.uuid4()), input=body(g, confirmed=confirmed))
    )


def resume(g, record):
    request = body(g)
    return ResumeTask.model_validate(
        dict(
            operation_id=str(uuid.uuid4()),
            expected_revision=record["revision"],
            facts=[
                dict(
                    side=side,
                    metric_key=c["metric_key"],
                    fact_set_id=c["fact_set_id"],
                    fact_id=c["fact_id"],
                )
                for side in ("first", "second")
                for c in request[side]["choices"]
            ],
        )
    )


def http(svc, repo):
    app = FastAPI()
    app.include_router(create_task_router(repo, svc))
    return TestClient(app)


def test_wait_checkpoint_and_safe_resume(saved, monkeypatch):
    h, g, _ = saved
    svc, repo, persistent = setup(h)
    before = fact_counts(h)
    monkeypatch.setattr(
        h.confirmations, "confirm_financial", AsyncMock(side_effect=AssertionError("confirm"))
    )
    monkeypatch.setattr(
        h.confirmations, "persist_financial", AsyncMock(side_effect=AssertionError("persist"))
    )
    record = run(persistent.start(start(g)))
    assert record["status"] == "awaiting_human_confirmation", record
    assert record["waiting_checkpoint"] and record["execution_status"] == "idle"
    assert record["snapshot"]["analysis_results"] == []
    assert record["budget"]["used"] == dict(
        steps=16, tool_calls=13, model_calls=0, retrieval_total=0
    )
    request = resume(g, record)
    response = http(persistent, repo).post(
        "/research/tasks/" + record["task_id"] + "/resume", json=request.model_dump(mode="json")
    )
    assert response.status_code == 200, response.text
    continued = response.json()
    assert continued["status"] == "collecting_explanation", continued
    assert len(continued["snapshot"]["analysis_results"]) == 3
    assert continued["budget"]["used"] == dict(
        steps=30, tool_calls=24, model_calls=0, retrieval_total=12
    )
    assert all(f["receipt_id"] == g.receipt.receipt_id for f in continued["snapshot"]["facts"])
    assert continued["final_research_content"] is None
    assert not continued["waiting_checkpoint"]
    assert run(persistent.resume(record["task_id"], request)) == continued
    svc.scope.search.assert_awaited_once()
    assert fact_counts(h) == before
    # GET remains DB only even when all trusted business dependencies are unavailable.
    monkeypatch.setattr(
        svc.preparer, "prepare_many", AsyncMock(side_effect=AssertionError("prepare"))
    )
    monkeypatch.setattr(svc.analysis, "analyze", AsyncMock(side_effect=AssertionError("analysis")))
    monkeypatch.setattr(
        svc.facts, "read_financial_facts", AsyncMock(side_effect=AssertionError("facts"))
    )
    client = http(persistent, repo)
    assert client.get("/research/tasks/" + record["task_id"]).json() == continued
    assert client.get("/research/tasks").json()["items"] == [continued]
    assert client.get("/research/tasks/by-operation/" + request.operation_id).json() == continued


def test_same_period_persistent_uses_same_tools(paired):
    h, a, b, _ = paired
    svc, repo, persistent = setup(h)
    req = StartTask.model_validate(dict(operation_id=str(uuid.uuid4()), input=body(a, b)))
    record = run(persistent.start(req))
    assert record["status"] == "collecting_explanation", record
    assert all(
        r["schema"] == "financial-company-comparison-v1"
        for r in record["snapshot"]["analysis_results"]
    )
    assert run(persistent.start(req)) == record
    with pytest.raises(HistoryError, match="operation_request_conflict"):
        run(
            persistent.start(
                StartTask.model_validate(
                    dict(operation_id=req.operation_id, input=body(a, b, False))
                )
            )
        )


def test_concurrent_resume_claim_once_and_stale_revision(saved):
    h, g, _ = saved
    svc, repo, persistent = setup(h)
    record = run(persistent.start(start(g)))
    request = resume(g, record)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: run(persistent.resume(record["task_id"], request)), range(2))
        )
    assert {r["task_id"] for r in results} == {record["task_id"]}
    assert all(r["execution_status"] in ("running", "idle") for r in results)
    svc.scope.search.assert_awaited_once()
    with pytest.raises(HistoryError, match="task_revision_conflict"):
        run(persistent.resume(record["task_id"], resume(g, record)))


def test_different_concurrent_operations_are_busy(saved):
    h, g, _ = saved
    _, repo, persistent = setup(h)
    record = run(persistent.start(start(g)))
    claimed, token = repo.resume(record["task_id"], resume(g, record))
    assert token
    with pytest.raises(HistoryError, match="task_busy"):
        repo.resume(record["task_id"], resume(g, record))
    assert repo.get(record["task_id"]) == claimed
    assert repo.recover_interrupted() == 1
    failed = repo.get(record["task_id"])
    assert failed["error_code"] == "interrupted_unknown_execution"
    assert failed["snapshot"]["analysis_results"] == []
    with pytest.raises(HistoryError, match="stale_execution_claim"):
        repo.reserve(record["task_id"], token, claimed["budget"])
    with pytest.raises(HistoryError, match="task_revision_conflict"):
        repo.resume(record["task_id"], resume(g, record))


@pytest.mark.parametrize(
    "kind", ["source", "receipt", "fact", "group", "production", "cross_space", "version"]
)
def test_resume_re_admits_every_identity_and_permission(saved, kind):
    h, g, _ = saved
    svc, repo, persistent = setup(h)
    record = run(persistent.start(start(g)))
    request = resume(g, record)
    if kind == "source":
        from tests.test_document_sources import metadata

        h.client.post(
            f"/documents/{h.id}/binding-corrections",
            json=dict(
                expected_attempt=1,
                metadata={**metadata(h.company.company_id, 2031), "basis": "unknown"},
                reason="D19 isolated correction",
            ),
        )
    elif kind == "receipt":
        response = h.client.post(
            "/financial-facts/acceptances/" + g.receipt.receipt_id + "/revoke",
            json={"reason": "D19 isolated simulated operator withdrawal"},
        )
        assert response.status_code == 200, response.text
        assert h.client.get("/financial-facts/persisted/" + g.receipt.receipt_id).status_code == 409
        historical = h.client.get(
            "/financial-facts/persisted/" + g.receipt.receipt_id + "?include_invalid=true"
        )
        assert historical.json()["invalid_reason"] == "acceptance_revoked"
    elif kind == "fact":
        raw = request.model_dump(mode="json")
        raw["facts"][0]["fact_id"] = "missing"
        request = ResumeTask.model_validate(raw)
    elif kind == "group":
        with closing(sqlite3.connect(h.db)) as conn, conn:
            conn.execute(
                "DROP TRIGGER d10_fact_immutable_delete"
            )  # Isolated corruption injection only.
            conn.execute(
                "DELETE FROM confirmed_financial_facts WHERE fact_id=?", (request.facts[0].fact_id,)
            )
    elif kind == "production":
        persistent.templates = service(h, simulated=False)
    elif kind == "cross_space":
        foreign = TaskRepository(repo.registry, "foreign")
        with pytest.raises(HistoryError, match="resource_not_found"):
            foreign.resume(record["task_id"], request)
        with pytest.raises(HistoryError, match="resource_not_found"):
            foreign.get(record["task_id"])
        assert foreign.page(20, None)["items"] == []
        return
    elif kind == "version":
        # Explicitly frozen disclosure cannot be changed during resume.
        with closing(repo.registry._connect()) as conn, conn:
            value = repo.get(record["task_id"])
            value["active_input"]["first"]["choices"][0]["disclosure_version"] = "wrong-disclosure"
            repo.write(conn, value, None)
    result = run(persistent.resume(record["task_id"], request))
    assert result["status"] in ("refused", "failed"), result
    assert (
        result["snapshot"]["analysis_results"] == []
        and result["snapshot"]["operating_evidence"] is None
    )
    svc.scope.search.assert_not_called()


@pytest.mark.parametrize(
    "counter", ["steps", "tool_calls", "model_calls", "retrieval_total", "elapsed_seconds"]
)
def test_cumulative_budget_never_resets(saved, counter):
    from app.agent.execution_budget import TEMPLATE_LIMITS

    h, g, _ = saved
    svc, repo, persistent = setup(h)
    record = run(persistent.start(start(g)))
    with closing(repo.registry._connect()) as conn, conn:
        value = repo.get(record["task_id"])
        if counter == "elapsed_seconds":
            value["budget"][counter] = 120
        else:
            value["budget"]["used"][counter] = getattr(TEMPLATE_LIMITS, counter)
        repo.write(conn, value, None)
    # model count at its limit remains 4 because D19 never dispatches a model.
    result = run(persistent.resume(record["task_id"], resume(g, record)))
    if counter == "model_calls":
        assert result["budget"]["used"]["model_calls"] == 4
        assert result["status"] == "collecting_explanation"
    else:
        assert result["status"] == "failed", result
        assert result["error_code"].startswith("budget_")
        assert result["snapshot"]["analysis_results"] == []


def test_persistence_failure_blocks_effects_and_unknown_replay(saved, monkeypatch):
    h, g, _ = saved
    svc, repo, persistent = setup(h)
    record = run(persistent.start(start(g)))
    request = resume(g, record)
    with closing(repo.registry._connect()) as conn, conn:
        conn.execute(
            "CREATE TRIGGER fail_d19 BEFORE UPDATE ON template_tasks WHEN NEW.payload LIKE '%resume:%' BEGIN SELECT RAISE(ABORT,'injected'); END"
        )
    with pytest.raises(HistoryError, match="task_save_or_execution_unknown"):
        run(persistent.resume(record["task_id"], request))
    assert run(persistent.resume(record["task_id"], request))["execution_status"] == "running"
    svc.scope.search.assert_not_called()
    with closing(repo.registry._connect()) as conn, conn:
        conn.execute("DROP TRIGGER fail_d19")
    assert repo.recover_interrupted() == 1
    assert run(persistent.resume(record["task_id"], request))["status"] == "failed"


def test_checkpoint_corruption_and_read_integrity(saved):
    h, g, _ = saved
    _, repo, persistent = setup(h)
    record = run(persistent.start(start(g)))
    with closing(repo.registry._connect()) as conn, conn:
        conn.execute("UPDATE template_checkpoint_writes SET payload=x'00'")
    with pytest.raises(HistoryError, match="task_save_or_execution_unknown"):
        run(persistent.resume(record["task_id"], resume(g, record)))
    with closing(repo.registry._connect()) as conn, conn:
        conn.execute("UPDATE template_tasks SET payload_sha='invalid'")
    assert http(persistent, repo).get("/research/tasks/" + record["task_id"]).status_code == 503


def test_requests_cannot_confirm_change_scope_or_run_get(saved):
    h, g, _ = saved
    svc, repo, persistent = setup(h)
    client = http(persistent, repo)
    req = start(g)
    record = client.post("/research/tasks", json=req.model_dump(mode="json")).json()
    r = resume(g, record).model_dump(mode="json")
    for extra in (
        "amount",
        "input",
        "workspace_id",
        "confirmation_kind",
        "model",
        "budget",
        "confirm",
    ):
        bad = {**r, extra: "forbidden"}
        assert (
            client.post("/research/tasks/" + record["task_id"] + "/resume", json=bad).status_code
            == 422
        )
    assert (
        client.post(
            "/research/tasks?workspace_id=foreign", json=req.model_dump(mode="json")
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/research/tasks/" + record["task_id"] + "/resume?confirm=true", json=r
        ).status_code
        == 422
    )
    assert client.get("/research/tasks?workspace_id=foreign").status_code == 422
    assert client.get("/research/tasks/" + record["task_id"] + "?resume=true").status_code == 422
    assert client.get("/research/tasks/missing").status_code == 404
    readonly = http(None, repo)
    assert readonly.post("/research/tasks", json=req.model_dump(mode="json")).status_code == 405
    assert fact_counts(h) == (1, 6)


def test_migration8_old_checksums_and_atomic_rollback(tmp_path, monkeypatch):
    from app.companies import migrations
    from app.documents.sqlite_repository import SQLiteDocumentRepository
    from app.companies.sqlite_repository import SQLiteCompanyRepository

    db = tmp_path / "migration.db"
    SQLiteDocumentRepository(db)
    # Test the original migration 8 independently of later additive migrations.
    full = migrations.MIGRATIONS[:8]
    monkeypatch.setattr(migrations, "MIGRATIONS", full[:7])
    SQLiteCompanyRepository(db)
    with closing(sqlite3.connect(db)) as conn:
        old = conn.execute("SELECT version,name,checksum FROM analyst_schema_migrations").fetchall()
    v, n, ddl = full[7]
    monkeypatch.setattr(migrations, "MIGRATIONS", (*full[:7], (v, n, (*ddl, "INVALID D19 SQL"))))
    with pytest.raises(sqlite3.Error):
        SQLiteCompanyRepository(db)
    with closing(sqlite3.connect(db)) as conn:
        assert not conn.execute(
            "SELECT name FROM sqlite_master WHERE name='template_tasks'"
        ).fetchall()
    monkeypatch.setattr(migrations, "MIGRATIONS", full)
    SQLiteCompanyRepository(db)
    SQLiteCompanyRepository(db)
    with closing(sqlite3.connect(db)) as conn:
        assert (
            conn.execute(
                "SELECT version,name,checksum FROM analyst_schema_migrations WHERE version<=7"
            ).fetchall()
            == old
        )
        assert conn.execute("SELECT count(*) FROM analyst_schema_migrations").fetchone()[0] == 8


def test_late_release_revocation_withholds_prepared_numbers(saved, monkeypatch):
    h, g, _ = saved
    _, repo, persistent = setup(h)
    record = run(persistent.start(start(g)))
    original = repo.release

    def revoked(*args, **kwargs):
        h.receipts.revoke_financial_receipt(
            workspace_id="demo",
            receipt_id=g.receipt.receipt_id,
            confirmation_kind="simulated_test",
            reason="D19 final commit race injection",
        )
        return original(*args, **kwargs)

    monkeypatch.setattr(repo, "release", revoked)
    result = run(persistent.resume(record["task_id"], resume(g, record)))
    assert result["status"] == "refused" and result["error_code"] == "acceptance_revoked"
    assert (
        not result["snapshot"]["analysis_results"]
        and result["snapshot"]["operating_evidence"] is None
    )
    assert result["budget"]["used"]["tool_calls"] == 24


def test_release_persistence_failure_never_publishes_unknown_numbers(saved, monkeypatch):
    h, g, _ = saved
    _, repo, persistent = setup(h)
    record = run(persistent.start(start(g)))
    request = resume(g, record)
    monkeypatch.setattr(
        repo, "release", lambda *a, **k: (_ for _ in ()).throw(sqlite3.OperationalError("injected"))
    )
    with pytest.raises(HistoryError, match="task_save_or_execution_unknown"):
        run(persistent.resume(record["task_id"], request))
    client = http(persistent, repo)
    unknown = client.get("/research/tasks/" + record["task_id"])
    assert unknown.status_code == 202
    assert unknown.json()["snapshot"]["analysis_results"] == []
    assert unknown.json()["snapshot"]["operating_evidence"] is None
    assert client.get("/research/tasks").json()["items"][0]["snapshot"]["analysis_results"] == []
    assert repo.recover_interrupted() == 1
    assert repo.get(record["task_id"])["status"] == "failed"


def test_persisted_loop_reservation_failure_does_not_call_provider():
    from app.agent.execution_budget import ExecutionBudget
    from app.agent.tool_loop import run_tool_loop, ToolExecutionContext
    from app.rag.retriever import TrustedContext
    from tests.test_d18_templates import Scripted, final

    def reject(value):
        if value["used"]["model_calls"]:
            raise HistoryError("injected_reservation_failure")

    budget = ExecutionBudget(checkpoint=reject)
    model = Scripted(final())
    # A failing durable reservation must propagate before provider invocation.
    with pytest.raises(HistoryError):
        run_tool_loop(
            model=model,
            messages=[],
            registry={},
            execution_context=ToolExecutionContext(TrustedContext("demo"), None),
            budget=budget,
        )
    assert model.calls == 0 and budget.model_calls == 1


def test_revocation_does_not_create_or_replace_confirmation(saved):
    h, g, _ = saved
    before = fact_counts(h)
    path = "/financial-facts/acceptances/" + g.receipt.receipt_id + "/revoke"
    a = h.client.post(path, json={"reason": "First explicit simulated revocation"})
    b = h.client.post(path, json={"reason": "Repeated explicit simulated revocation"})
    assert a.status_code == 200 and b.json() == a.json()
    assert fact_counts(h) == before
    foreign = TaskRepository(h.registry, "foreign")
    with pytest.raises(Exception):
        h.receipts.revoke_financial_receipt(
            workspace_id=foreign.workspace,
            receipt_id=g.receipt.receipt_id,
            confirmation_kind="simulated_test",
            reason="cross space",
        )
