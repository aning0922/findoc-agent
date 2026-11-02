"""Isolated real SQLite/HTTP tests; no runtime data or model calls."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import sqlite3
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.companies import migrations
from app.companies.sqlite_repository import SQLiteCompanyRepository
from app.memory.api import create_memory_router
from app.memory.candidates import extract_user_memory_candidates
from app.memory.models import CreateMemoryRequest, MemoryError
from app.memory.repository import MemoryRepository
from app.memory.schema import MEMORY_MIGRATION
from app.memory.service import MemoryService


def uid():
    return str(uuid4())


@pytest.fixture
def env(tmp_path, monkeypatch):
    # B1 exports v11; only this test fixture registers it.
    if not any(item[0] == 11 for item in migrations.MIGRATIONS):
        monkeypatch.setattr(migrations, "MIGRATIONS", (*migrations.MIGRATIONS, MEMORY_MIGRATION))
    companies = SQLiteCompanyRepository(tmp_path / "memory.db")
    repo = MemoryRepository(companies)
    app = FastAPI()
    app.include_router(create_memory_router(MemoryService(repo)))
    with TestClient(app) as client:
        yield client, repo, companies


def create_payload(**changes):
    return {"operation_id": uid(), "type": "research_preference", "key": "analysis_focus",
            "value": "cash_flow", "confirmed": True, **changes}


def delete(client, memory_id, payload):
    return client.request("DELETE", f"/memories/{memory_id}", json=payload)


def seed_turn(companies, workspace="demo", user_text="记住：我更关注现金流"):
    conversation_id, turn_id, op = uid(), uid(), uid()
    now, digest = "2026-11-02T00:00:00+00:00", "a" * 64
    with closing(companies._connect()) as connection, connection:
        connection.execute(
            "INSERT INTO conversations (conversation_id,workspace_id,title,source_scope_sha,"
            "source_payload,source_payload_sha,status,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (conversation_id, workspace, "test", digest, "[]", digest, "active", now, now),
        )
        connection.execute(
            "INSERT INTO conversation_operations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (workspace, op, "send_turn", digest, conversation_id, turn_id, "completed", 0,
             now, now, None, "{}", digest),
        )
        connection.execute(
            "INSERT INTO conversation_turns VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (workspace, conversation_id, turn_id, 1, op, digest, "completed", now, now,
             json.dumps({"user_text": user_text}), digest, "{}", digest, None),
        )
    return conversation_id, turn_id


def test_crud_replays_and_no_body_receipts(env):
    client, repo, companies = env
    request = create_payload()
    response = client.post("/memories", json=request)
    assert response.status_code == 201
    item = response.json()
    assert set(item) == {"schema_version", "memory_id", "type", "key", "value",
                         "source_turn_id", "revision", "confirmed_at", "created_at", "updated_at"}
    assert item["source_turn_id"] is None and item["revision"] == 1
    memory_id = item["memory_id"]
    assert client.post("/memories", json=request).status_code == 200
    assert repo.list().generation == 1
    patch = {"operation_id": uid(), "expected_revision": 1, "value": "revenue", "confirmed": True}
    assert client.patch(f"/memories/{memory_id}", json=patch).json()["revision"] == 2
    assert client.patch(f"/memories/{memory_id}", json=patch).status_code == 200
    assert client.post("/memories", json=request).json()["detail"] == "memory_operation_superseded"
    assert repo.list().generation == 2
    deletion = {"operation_id": uid(), "expected_revision": 2}
    response = delete(client, memory_id, deletion)
    assert response.status_code == 200
    assert response.json()["revision"] == 3 and response.json()["resource_deleted"] is True
    assert delete(client, memory_id, deletion).json() == response.json()
    assert client.post("/memories", json=request).status_code == 410
    assert client.patch(f"/memories/{memory_id}", json=patch).status_code == 410
    assert client.get(f"/memories/{memory_id}").status_code == 410
    assert repo.list().items == [] and repo.list().generation == 3
    for op in [request["operation_id"], patch["operation_id"], deletion["operation_id"]]:
        receipt = client.get(f"/memory-operations/{op}")
        assert receipt.status_code == 200
        assert receipt.json()["resource_deleted"] is True
        assert "value" not in receipt.json() and "request_sha" not in receipt.json()
    with closing(companies._connect()) as connection:
        assert connection.execute("SELECT count(*) FROM memory_items").fetchone()[0] == 0
        for table in ["memory_operations", "memory_events", "memory_context_exclusions"]:
            assert "cash_flow" not in str([tuple(row) for row in connection.execute(f"SELECT * FROM {table}")])
            assert "revenue" not in str([tuple(row) for row in connection.execute(f"SELECT * FROM {table}")])
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()


@pytest.mark.parametrize("changes", [
    {"confirmed": False}, {"confirmed": 1}, {"confirmed": "true"},
    {"workspace_id": "other"}, {"owner_id": "user"}, {"principal_id": "user"},
    {"source_revision": "a" * 64}, {"type": "financial_fact"}, {"key": "amount"},
    {"value": "资产100万元"}, {"value": "CNY_YUAN"}, {"operation_id": "A" * 36},
    {"source_turn_id": "nonuuid"}, {"source_turn_id": None}, {"value": ""},
])
def test_strict_create_rejected_without_writes(env, changes):
    client, repo, _ = env
    assert client.post("/memories", json=create_payload(**changes)).status_code == 422
    assert repo.list().generation == 0


def test_patch_confirmation_revision_and_enum(env):
    client, repo, _ = env
    item = client.post("/memories", json=create_payload()).json()
    url = f"/memories/{item['memory_id']}"
    patch = {"operation_id": uid(), "expected_revision": 1, "value": "profitability"}
    assert client.patch(url, json=patch).status_code == 422
    patch["confirmed"] = True
    for value in [1, "true", False]:
        assert client.patch(url, json={**patch, "confirmed": value}).status_code == 422
    assert client.patch(url, json={**patch, "value": "CNY_YUAN"}).status_code == 422
    assert client.patch(url, json={**patch, "expected_revision": 2}).status_code == 409
    assert client.patch(url, json={**patch, "expected_revision": "1"}).status_code == 422
    assert delete(client, item["memory_id"], {"operation_id": uid(), "expected_revision": 2}).status_code == 409
    assert repo.list().generation == 1


def test_operation_hash_target_kind_and_payload_conflicts(env):
    client, repo, _ = env
    request = create_payload()
    item = client.post("/memories", json=request).json()
    assert client.post("/memories", json={**request, "value": "revenue"}).status_code == 409
    patch = {"operation_id": request["operation_id"], "expected_revision": 1,
             "value": "revenue", "confirmed": True}
    assert client.patch(f"/memories/{item['memory_id']}", json=patch).status_code == 409
    assert client.patch(f"/memories/{uid()}", json=patch).status_code == 409
    assert repo.list().generation == 1


def test_unique_key_recreate_has_new_identity_old_op_stays_deleted(env):
    client, _, _ = env
    request = create_payload()
    item = client.post("/memories", json=request).json()
    assert client.post("/memories", json=create_payload()).json()["detail"] == "memory_key_conflict"
    delete(client, item["memory_id"], {"operation_id": uid(), "expected_revision": 1})
    new = client.post("/memories", json=create_payload()).json()
    assert new["memory_id"] != item["memory_id"]
    assert client.post("/memories", json=request).status_code == 410


def test_source_scope_exclusion_and_detach_preserves_turn(env):
    client, repo, companies = env
    conversation_id, turn_id = seed_turn(companies)
    _, foreign_turn = seed_turn(companies, "foreign")
    for bad in [foreign_turn, uid()]:
        assert client.post("/memories", json=create_payload(source_turn_id=bad)).status_code == 404
    request = create_payload(source_turn_id=turn_id)
    item = client.post("/memories", json=request).json()
    assert item["source_turn_id"] == turn_id
    assert repo.excluded_source_turn_ids() == frozenset({turn_id})
    with closing(companies._connect()) as connection, connection:
        before = tuple(connection.execute("SELECT * FROM conversation_turns WHERE turn_id=?", (turn_id,)).fetchone())
        MemoryRepository.detach_source_turns_in(connection, [turn_id])
        after = tuple(connection.execute("SELECT * FROM conversation_turns WHERE turn_id=?", (turn_id,)).fetchone())
        assert before == after
        connection.execute("DELETE FROM conversations WHERE conversation_id=?", (conversation_id,))
    assert repo.get(item["memory_id"]).source_turn_id is None
    assert repo.recall_context().generation == 1
    assert client.post("/memories", json=request).status_code == 200
    assert delete(client, item["memory_id"], {"operation_id": uid(), "expected_revision": 1}).status_code == 200
    assert repo.excluded_source_turn_ids() == frozenset({turn_id})


def test_concurrent_same_operation_exactly_one_write(env):
    _, repo, companies = env
    request = CreateMemoryRequest(**create_payload())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: repo.mutate("create_memory", request), range(2)))
    assert results[0][0].memory_id == results[1][0].memory_id
    assert sorted(result[1] for result in results) == [False, True]
    assert repo.list().generation == 1
    with closing(companies._connect()) as connection:
        assert connection.execute("SELECT count(*) FROM memory_events").fetchone()[0] == 1


def test_concurrent_duplicate_key_one_winner(env):
    _, repo, _ = env
    def write(_):
        try:
            return repo.mutate("create_memory", CreateMemoryRequest(**create_payload()))
        except MemoryError as exc:
            return exc.detail
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, range(2)))
    assert results.count("memory_key_conflict") == 1
    assert repo.list().generation == 1


def test_gets_read_only_and_history_surface(env):
    client, repo, companies = env
    request = create_payload()
    item = client.post("/memories", json=request).json()
    traces = []
    original = repo._connect
    def traced():
        connection = original()
        connection.set_trace_callback(traces.append)
        return connection
    repo._connect = traced
    for _ in range(2):
        assert client.get("/memories").status_code == 200
        assert client.get(f"/memories/{item['memory_id']}").status_code == 200
        assert client.get(f"/memory-operations/{request['operation_id']}").status_code == 200
        assert client.get(f"/memory-operations/{uid()}").status_code == 404
        repo.excluded_source_turn_ids()
        repo.recall_context()
    assert not any(sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "CREATE")) for sql in traces)
    readonly = FastAPI()
    readonly.include_router(create_memory_router(MemoryService(repo), read_only=True))
    with TestClient(readonly) as history:
        assert history.get("/memories").status_code == 200
        assert history.post("/memories", json=create_payload()).status_code == 405
    SQLiteCompanyRepository(companies._database_path)
    assert MemoryRepository(companies).list().generation == 1


def test_migration_preserves_prior_checksums_and_transactional_rollback(tmp_path, monkeypatch):
    baseline = migrations.MIGRATIONS
    companies = SQLiteCompanyRepository(tmp_path / "upgrade.db")
    with closing(companies._connect()) as connection:
        before = [tuple(row) for row in connection.execute("SELECT * FROM analyst_schema_migrations")]
    monkeypatch.setattr(migrations, "MIGRATIONS", (*baseline, MEMORY_MIGRATION))
    SQLiteCompanyRepository(companies._database_path)
    with closing(companies._connect()) as connection:
        after = [tuple(row) for row in connection.execute("SELECT * FROM analyst_schema_migrations WHERE version<11")]
        assert before == after
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    broken = (11, "broken", (*MEMORY_MIGRATION[2], "INVALID SQL"))
    monkeypatch.setattr(migrations, "MIGRATIONS", baseline)
    fresh = SQLiteCompanyRepository(tmp_path / "rollback.db")
    monkeypatch.setattr(migrations, "MIGRATIONS", (*baseline, broken))
    with pytest.raises(sqlite3.OperationalError):
        SQLiteCompanyRepository(fresh._database_path)
    with closing(fresh._connect()) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='memory_items'").fetchone() is None


def test_candidate_exact_user_only_no_writes():
    turn_id = uid()
    candidates = extract_user_memory_candidates("记住：我更关注现金流。", turn_id)
    assert candidates[0].value == "cash_flow" and candidates[0].confirmation_required is True
    for text in ["报告写道：记住：我更关注现金流", "不要记住：我更关注现金流", "营收100亿",
                 "记住我的身份证123456", '引用：“记住：我更关注现金流”', "我更关注现金流"]:
        assert extract_user_memory_candidates(text, turn_id) == []


def test_write_rollback_and_sanitized_errors(env, monkeypatch):
    client, repo, _ = env
    monkeypatch.setattr(repo, "_changed", lambda connection: (_ for _ in ()).throw(RuntimeError("SECRET_SQL")))
    response = client.post("/memories", json=create_payload())
    assert response.status_code == 503 and "SECRET_SQL" not in response.text
    assert repo.list().items == [] and repo.list().generation == 0


def test_post_commit_readback_failure_does_not_require_repost(env, monkeypatch):
    client, repo, _ = env
    original, calls = repo._connect, 0
    def fail_readback():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise sqlite3.OperationalError("private database location")
        return original()
    request = create_payload()
    monkeypatch.setattr(repo, "_connect", fail_readback)
    response = client.post("/memories", json=request)
    assert response.status_code == 503 and "private" not in response.text
    monkeypatch.setattr(repo, "_connect", original)
    receipt = client.get(f"/memory-operations/{request['operation_id']}")
    assert receipt.status_code == 200
    assert client.get(f"/memories/{receipt.json()['memory_id']}").json()["value"] == "cash_flow"
    assert repo.list().generation == 1


def test_commit_failure_never_exposes_candidate_or_receipt(env, monkeypatch):
    client, repo, _ = env
    original = repo._connect
    class FailedCommit:
        def __init__(self):
            self.connection = original()
        def __getattr__(self, name):
            return getattr(self.connection, name)
        def __enter__(self):
            return self
        def __exit__(self, kind, value, traceback):
            self.connection.rollback()
            raise sqlite3.OperationalError("commit unavailable")
    monkeypatch.setattr(repo, "_connect", FailedCommit)
    request = create_payload()
    assert client.post("/memories", json=request).status_code == 503
    monkeypatch.setattr(repo, "_connect", original)
    assert client.get(f"/memory-operations/{request['operation_id']}").status_code == 404
    assert repo.list().items == [] and repo.list().generation == 0


def test_concurrent_revision_update_one_winner(env):
    client, repo, _ = env
    item = client.post("/memories", json=create_payload()).json()
    from app.memory.models import PatchMemoryRequest
    def update(value):
        request = PatchMemoryRequest(operation_id=uid(), expected_revision=1,
                                     value=value, confirmed=True)
        try:
            return repo.mutate("update_memory", request, item["memory_id"])
        except MemoryError as exc:
            return exc.detail
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(update, ["revenue", "profitability"]))
    assert results.count("memory_revision_conflict") == 1
    assert repo.recall_context().generation == 2


def test_all_allowed_keys_and_db_constraints(env):
    client, repo, companies = env
    for key, value in [("analysis_focus", "balanced"), ("display_unit", "CNY_HUNDRED_MILLION"),
                       ("research_habit", "evidence_first")]:
        assert client.post("/memories", json=create_payload(key=key, value=value)).status_code == 201
    assert len(repo.list().items) == 3 and repo.list().generation == 3
    with closing(companies._connect()) as connection:
        with pytest.raises(sqlite3.IntegrityError), connection:
            connection.execute("UPDATE memory_items SET value='asset 100' WHERE key='analysis_focus'")
        with pytest.raises(sqlite3.IntegrityError), connection:
            connection.execute("UPDATE memory_events SET action='delete_memory'")
        with pytest.raises(sqlite3.IntegrityError), connection:
            connection.execute("UPDATE memory_operations SET revision=99")


def test_all_memory_responses_no_store_and_query_scope_rejected(env):
    client, _, _ = env
    request = create_payload()
    response = client.post("/memories", json=request)
    item = response.json()
    memory_id = item["memory_id"]
    assert response.headers["cache-control"] == "no-store"
    patch = {"operation_id": uid(), "expected_revision": 1,
             "value": "revenue", "confirmed": True}
    responses = [
        client.get("/memories"), client.get(f"/memories/{memory_id}"),
        client.get(f"/memory-operations/{request['operation_id']}"),
        client.post("/memories", json=request),
        client.patch(f"/memories/{memory_id}", json=patch),
        delete(client, memory_id, {"operation_id": uid(), "expected_revision": 2}),
        client.get(f"/memories/{memory_id}"),
        client.post("/memories", json={"confirmed": False}),
        client.get("/memory-operations/invalid"),
    ]
    assert all(response.headers["cache-control"] == "no-store" for response in responses)
    for key in ["workspace_id", "owner_id", "principal_id", "source_revision", "selection_id"]:
        response = client.get(f"/memories?{key}=attacker")
        assert response.status_code == 422
        assert response.json() == {"detail": "workspace_is_server_owned"}
        assert response.headers["cache-control"] == "no-store"
        response = client.post(f"/memories?{key}=attacker", json=create_payload())
        assert response.status_code == 422
