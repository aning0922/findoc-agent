"""D17 real SQLite/source transactions; controlled model/search fault injection."""

import asyncio
from contextlib import closing
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import AsyncMock, Mock
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.research_runs import create_research_runs_router
from app.companies.sqlite_repository import SQLiteCompanyRepository
from app.documents.preparation import DocumentTaskPreparer
from app.rag.retriever import SearchHit
from app.rag.service import RAGService
from app.research.models import Result, canonical, sha
from app.research.repository import HistoryError, ResearchOwner, ResearchRepository
from tests.test_document_sources import Harness


@pytest.fixture
def setup(tmp_path):
    h = Harness(tmp_path).ready()
    source = {
        **h.source,
        "assessment": dict.fromkeys(("company", "report_year", "report_type"), "matches_cover"),
    }
    p = DocumentTaskPreparer(
        document_service=h.documents,
        workspace_id="demo",
        sources=Mock(
            source=AsyncMock(return_value=source), verify_selection=h.service.verify_selection
        ),
    )
    selection = asyncio.run(p.prepare_many(document_ids=[h.id], query="主营业务"))
    model = Mock(generate=Mock(return_value='{"decision":"answer","quotes":[{"number":1}]}'))
    adapter = Mock(
        search=AsyncMock(
            return_value=(
                SearchHit(
                    score=0.9,
                    chunk_id="chunk-0",
                    text="已核验原文",
                    page=1,
                    source_file="misleading-1900.pdf",
                    type="paragraph",
                    workspace_id="demo",
                    document_id=h.id,
                    source_revision=h.rev,
                ),
            )
        ),
        table_context=AsyncMock(return_value={}),
        revalidate=AsyncMock(side_effect=p.revalidate),
    )
    rag = RAGService(
        retriever=Mock(),
        llm_client=model,
        evidence_gate=Mock(allows=Mock(return_value=True)),
        max_evidence_chars=4000,
    )
    repo = ResearchRepository(h.registry, "demo")
    app = FastAPI()
    app.include_router(create_research_runs_router(repo, p, adapter, rag))
    client = TestClient(app)
    body = dict(operation_id=str(uuid.uuid4()), document_ids=[h.id], query=selection.query)
    return h, repo, client, body, adapter, model, selection, p, rag


def post(setup):
    response = setup[2].post("/research/runs", json=setup[3])
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize(
    "state", ["answered", "refused", "retrieval_error", "llm_error", "citation_validation_error"]
)
def test_three_states_restart_reads_zero_execution(setup, state):
    h, repo, client, body, adapter, model, *_ = setup
    if state == "refused":
        model.generate.return_value = '{"decision":"refuse"}'
    elif state == "retrieval_error":
        adapter.search.side_effect = RuntimeError("SECRET retrieval")
    elif state == "llm_error":
        model.generate.side_effect = RuntimeError("SECRET key/provider")
    elif state == "citation_validation_error":
        model.generate.return_value = '{"decision":"answer","quotes":[{"number":99}]}'
    value = post(setup)
    expected = state if state in ("answered", "refused") else "system_error"
    assert value["status"] == expected and "SECRET" not in json.dumps(value)
    if expected != "answered":
        assert value["result"]["content"] == "" and value["result"]["citations"] == []
    # Re-open only persistent DB with a router without any execution dependencies.
    restarted = ResearchRepository(SQLiteCompanyRepository(h.db), "demo")
    app = FastAPI()
    app.include_router(create_research_runs_router(restarted))
    reader = TestClient(app)
    before = (
        adapter.search.call_count,
        model.generate.call_count,
        h.embedder.call_count,
        h.indexer.call_count,
    )
    for path in (
        f"/research/runs/{value['run_id']}",
        f"/research/runs/by-operation/{body['operation_id']}",
    ):
        assert reader.get(path).json() == value
    assert reader.get("/research/runs").json()["items"][0]["status"] == expected
    assert before == (
        adapter.search.call_count,
        model.generate.call_count,
        h.embedder.call_count,
        h.indexer.call_count,
    )


def test_duplicate_conflict_response_loss_and_final_immutability(setup):
    h, repo, client, body, adapter, model, *_ = setup
    value = post(setup)
    assert post(setup) == value
    assert client.get("/research/runs/by-operation/" + body["operation_id"]).json() == value
    assert model.generate.call_count == 1 and adapter.search.call_count == 1
    assert client.post("/research/runs", json={**body, "query": "different"}).status_code == 409
    h.correct()
    # Known operations replay saved history even after the source has become stale.
    replay = post(setup)
    assert replay["result"] == value["result"] and replay["source_states"][0]["status"] == "expired"
    with closing(h.registry._connect()) as c, pytest.raises(Exception):
        c.execute("UPDATE research_runs SET payload='{}'")
    with pytest.raises(HistoryError):
        repo.finish(value["run_id"], Result.model_validate(value["result"]))
    assert model.generate.call_count == 1


def test_concurrent_duplicate_executes_once(setup):
    _, _, client, body, _, model, *_ = setup
    entered, release = Event(), Event()

    def generate(prompt):
        entered.set()
        assert release.wait(10)
        return '{"decision":"answer","quotes":[{"number":1}]}'

    model.generate.side_effect = generate
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(client.post, "/research/runs", json=body)
        assert entered.wait(10)
        duplicate = client.post("/research/runs", json=body)
        assert duplicate.status_code == 202 and duplicate.json()["status"] == "running"
        release.set()
        assert first.result().json()["status"] == "answered"
    assert model.generate.call_count == 1


def test_transaction_failure_never_publishes_success_or_reexecutes(setup):
    h, repo, client, body, _, model, *_ = setup
    with closing(h.registry._connect()) as c, c:
        c.execute(
            "CREATE TRIGGER fail_save BEFORE UPDATE ON research_runs BEGIN SELECT RAISE(ABORT,'private'); END"
        )
    response = client.post("/research/runs", json=body)
    assert response.status_code == 503 and response.json() == {"detail": "research_save_failed"}
    assert "run_id" not in response.text
    old = repo.get(body["operation_id"], by_operation=True)
    assert old.status == "running" and old.result is None
    assert client.post("/research/runs", json=body).status_code == 202
    assert model.generate.call_count == 1
    with closing(h.registry._connect()) as c, c:
        c.execute("DROP TRIGGER fail_save")
    assert repo.recover_interrupted() == 1
    assert repo.get(old.run_id).result.error_code == "interrupted"
    assert repo.recover_interrupted() == 0


def test_register_failure_runs_no_model(setup):
    h, _, client, body, adapter, model, *_ = setup
    with closing(h.registry._connect()) as c, c:
        c.execute(
            "CREATE TRIGGER fail_register BEFORE INSERT ON research_runs BEGIN SELECT RAISE(ABORT,'private'); END"
        )
    assert client.post("/research/runs", json=body).json() == {"detail": "research_save_failed"}
    adapter.search.assert_not_called()
    model.generate.assert_not_called()


def test_source_change_between_validation_and_commit_is_safe_error(setup):
    h, _, _, _, adapter, *_ = setup
    adapter.revalidate.side_effect = lambda s: h.correct()
    value = post(setup)
    assert value["status"] == "system_error" and value["result"]["error_code"] == "source_changed"
    assert not value["result"]["content"]


def test_snapshot_source_correction_and_pdf_d6_denial(setup):
    h, repo, client, *_ = setup
    value = post(setup)
    assert h.correct().status_code == 200
    detail = client.get("/research/runs/" + value["run_id"]).json()
    assert detail["result"] == value["result"] and detail["source_states"][0]["status"] == "expired"
    assert detail["integrity_sha256"] == value["integrity_sha256"]
    assert h.query("file", company_id=h.company.company_id).status_code == 404


def test_scope_and_unknown_identity_and_client_authority(setup):
    h, repo, client, body, *_ = setup
    value = post(setup)
    foreign = ResearchRepository(h.registry, "foreign")
    assert foreign.page()["items"] == []
    with pytest.raises(HistoryError) as exc:
        foreign.get(value["run_id"])
    assert exc.value.status == 404
    for path in ("/research/runs/no-such-id", "/research/runs/by-operation/no-such-id"):
        assert client.get(path).status_code == 404
    assert client.get("/research/runs?workspace_id=other").status_code == 422
    for field in ("workspace_id", "selection_id", "source_revision"):
        assert client.post("/research/runs", json={**body, field: "fake"}).status_code == 422


def test_pagination_stable_ties_new_inserts_workspace_and_cursor_binding(setup, monkeypatch):
    h, repo, _, _, _, _, selection, *_ = setup
    from app.research import repository as module
    from datetime import datetime, UTC

    clock = Mock()
    clock.now.return_value = datetime(2026, 10, 10, tzinfo=UTC)
    monkeypatch.setattr(module, "datetime", clock)
    ids = [repo.register(str(uuid.uuid4()), selection, {})[0].run_id for _ in range(13)]
    first = repo.page(3, company_id=h.company.company_id)
    repo.register(str(uuid.uuid4()), selection, {})
    seen = [v["run_id"] for v in first["items"]]
    cursor = first["next_cursor"]
    for bad in (cursor + "x", "invalid"):
        with pytest.raises(HistoryError):
            repo.page(3, bad, h.company.company_id)
    with pytest.raises(HistoryError):
        repo.page(3, cursor, h.other.company_id)
    with pytest.raises(HistoryError):
        ResearchRepository(h.registry, "other").page(3, cursor, h.company.company_id)
    while cursor:
        page = repo.page(3, cursor, h.company.company_id)
        seen.extend(v["run_id"] for v in page["items"])
        cursor = page["next_cursor"]
    assert seen == sorted(ids, reverse=True) and len(set(seen)) == 13


@pytest.mark.parametrize("corruption", ["digest", "version", "content", "identity", "refusal_body"])
def test_corrupt_history_is_not_published(setup, corruption):
    h, repo, client, *_ = setup
    value = post(setup)
    with closing(h.registry._connect()) as c, c:
        c.execute("DROP TRIGGER research_terminal_immutable")
        row = c.execute("SELECT * FROM research_runs").fetchone()
        payload = json.loads(row["payload"])
        if corruption == "version":
            payload["schema_version"] = "future"
        elif corruption == "content":
            payload["result"]["content"] = "model authored false answer"
        elif corruption == "identity":
            payload["result"]["citations"][0]["document_id"] = "foreign"
        elif corruption == "refusal_body":
            payload["result"]["outcome"] = "refused"
        text = canonical(payload)
        c.execute(
            "UPDATE research_runs SET payload=?,payload_sha=?",
            (text, "bad" if corruption == "digest" else sha(text)),
        )
    for path in ("/research/runs/" + value["run_id"], "/research/runs"):
        response = client.get(path)
        assert (
            response.status_code == 503 and response.json()["detail"] == "history_integrity_error"
        )


def test_single_owner_lock_released_on_close(tmp_path):
    first = ResearchOwner(tmp_path)
    with pytest.raises(RuntimeError):
        ResearchOwner(tmp_path)
    first.close()
    second = ResearchOwner(tmp_path)
    second.close()


def test_v7_migration_failure_preserves_old_tables_and_existing_history(tmp_path, monkeypatch):
    from app.companies import migrations
    from tests.test_companies_migrations import snapshot

    plan = migrations.MIGRATIONS
    monkeypatch.setattr(migrations, "MIGRATIONS", plan[:6])
    h = Harness(tmp_path).ready()
    tables = [
        "documents",
        "companies",
        "report_document_metadata",
        "document_sources",
        "analyst_schema_migrations",
    ]
    before = snapshot(h.db, tables)
    version, name, ddl = plan[6]
    monkeypatch.setattr(
        migrations, "MIGRATIONS", (*plan[:6], (version, name, (*ddl, "INVALID D17 DDL")))
    )
    with pytest.raises(Exception):
        SQLiteCompanyRepository(h.db)
    assert snapshot(h.db, tables) == before
    with closing(h.registry._connect()) as conn:
        assert (
            conn.execute("SELECT 1 FROM sqlite_master WHERE name='research_runs'").fetchone()
            is None
        )
    monkeypatch.setattr(migrations, "MIGRATIONS", plan)
    SQLiteCompanyRepository(h.db)
    assert {
        k: v for k, v in snapshot(h.db, tables).items() if k != "analyst_schema_migrations"
    } == {k: v for k, v in before.items() if k != "analyst_schema_migrations"}


def test_d17_provider_disables_sdk_retries_without_mutating_old_client():
    from app.rag.openai_compatible_llm import OpenAICompatibleLLMClient
    import httpx
    from openai import OpenAI, InternalServerError

    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(500, json={"error": {"message": "controlled failure"}})

    client = OpenAI(
        api_key="controlled-test-key",
        base_url="https://example.invalid/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(respond)),
        max_retries=2,
    )
    model = OpenAICompatibleLLMClient("controlled-model", client)
    with pytest.raises(InternalServerError):
        model.generate_once("question")
    assert len(calls) == 1 and client.max_retries == 2
    client.close()


def test_cancelled_execution_closes_safely_without_retry(setup):
    h, repo, _, body, scope, model, selection, p, rag = setup
    scope.search.side_effect = asyncio.CancelledError()
    app = FastAPI()
    app.include_router(create_research_runs_router(repo, p, scope, rag))
    with pytest.raises(BaseException):
        TestClient(app).post("/research/runs", json=body)
    value = repo.get(body["operation_id"], by_operation=True)
    assert value.status == "system_error" and value.result.error_code == "interrupted"
    model.generate.assert_not_called()
