"""A1 real SQLite/source identity and HTTP; explicit fake handler, no provider.

Generated PDF fixtures are not commercial reports or human financial acceptance.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
import sqlite3
from threading import Barrier
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app.companies import migrations
from app.companies.sqlite_repository import SQLiteCompanyRepository
from app.conversations.api import create_conversation_router
from app.conversations.models import (
    Action, CreateConversationRequest, CreateTurnRequest, EvidenceRef, ResolvedQuery, TurnResult,
)
from app.conversations.repository import ConversationError, ConversationRepository
from app.conversations.service import ConversationService, fake_handler
from app.documents.preparation import DocumentTaskPreparer
from tests.test_document_sources import Harness


def uid():
    return str(uuid4())


@pytest.fixture
def setup(tmp_path):
    h = Harness(tmp_path).ready()
    source = {**h.source,
              "assessment": dict.fromkeys(("company", "report_year", "report_type"), "matches_cover")}
    reader = Mock(source=AsyncMock(return_value=source),
                  verify_selection=h.service.verify_selection)
    preparer = DocumentTaskPreparer(document_service=h.documents, sources=reader,
                                   workspace_id="demo")
    repository = ConversationRepository(h.registry, "demo")
    handler = AsyncMock(side_effect=fake_handler)
    service = ConversationService(repository, preparer, handler=handler)
    app = FastAPI()
    app.include_router(create_conversation_router(repository, service))
    return h, repository, preparer, handler, service, TestClient(app), reader


def create(setup, **updates):
    body = {"operation_id": uid(), "document_ids": [setup[0].id], **updates}
    response = setup[5].post("/conversations", json=body)
    assert response.status_code == 201, response.text
    return response.json(), body


def send(setup, cid, **updates):
    body = {"operation_id": uid(), "text": "营业收入原文", **updates}
    response = setup[5].post(f"/conversations/{cid}/turns", json=body)
    assert response.status_code == 200, response.text
    return response.json(), body


def all_rows(registry):
    with closing(registry._connect()) as conn:
        names = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {name: conn.execute(f'SELECT * FROM "{name}" ORDER BY rowid').fetchall()
                for name in names}


def assert_error(call, code, status):
    with pytest.raises(ConversationError) as caught:
        call()
    assert (caught.value.code, caught.value.status) == (code, status)


def test_create_send_replay_read_only_restart_and_exact_public_fields(setup):
    h, repo, preparer, handler, service, client, reader = setup
    conversation, body = create(setup)
    cid = conversation["conversation_id"]
    assert conversation["turns"] == [] and conversation["sources"][0]["source_revision"] == h.rev
    assert set(conversation) == {"schema_version", "conversation_id", "title", "status",
        "source_scope_sha", "sources", "source_states", "created_at", "updated_at",
        "last_turn_seq", "active_turn_id", "turns", "next_before_seq"}
    assert client.post("/conversations", json=body).status_code == 200
    assert client.get("/conversations/by-operation/" + body["operation_id"]).json() == conversation
    turn, request = send(setup, cid)
    assert turn["status"] == "completed" and turn["seq"] == 1
    assert turn["result"]["kind"] == "clarification"
    assert turn["usage"] == {"model_attempts": 0, "tool_calls": 0}
    assert turn["financial_fact_validity"] == "not_applicable"
    assert turn["result"]["interpretation_status"] == "not_generated"
    assert turn["result"]["memory_candidates"] == []
    assert set(turn) == {"schema_version", "conversation_id", "turn_id", "operation_id", "seq",
        "status", "user_text", "resolved_query", "fact_selections", "result", "research_run_id",
        "tool_events", "created_at", "ended_at", "provider_outcome", "usage", "historical_snapshot",
        "source_states", "financial_fact_validity", "integrity_sha256"}
    assert client.post(f"/conversations/{cid}/turns", json=request).json() == turn
    assert handler.await_count == 1
    before = all_rows(h.registry)
    reader.source.reset_mock()
    restarted = ConversationRepository(SQLiteCompanyRepository(h.db), "demo")
    app = FastAPI()
    app.include_router(create_conversation_router(restarted))
    reader_client = TestClient(app)
    for path in ("/conversations", f"/conversations/{cid}",
                 f"/conversations/{cid}/turns/{turn['turn_id']}",
                 f"/conversations/{cid}/turns/by-operation/{request['operation_id']}",
                 f"/conversation-operations/{request['operation_id']}"):
        response = reader_client.get(path)
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
    assert reader_client.post("/conversations", json=body).status_code == 405
    assert all_rows(h.registry) == before
    assert handler.await_count == 1 and reader.source.await_count == 0


def test_global_operation_payload_conflicts_and_no_duplicate_source_io(setup):
    _, _, _, handler, _, client, reader = setup
    first, body = create(setup)
    cid = first["conversation_id"]
    assert client.post("/conversations", json={**body, "title": "different"}).status_code == 409
    turn, request = send(setup, cid)
    reader.source.reset_mock()
    assert client.post(f"/conversations/{cid}/turns", json=request).json() == turn
    assert reader.source.await_count == 0
    assert client.post(f"/conversations/{cid}/turns", json={**request, "text": "other"}).status_code == 409
    other, _ = create(setup)
    assert client.post(f"/conversations/{other['conversation_id']}/turns", json=request).status_code == 409
    assert client.post(f"/conversations/{cid}/turns", json={**request,
        "operation_id": body["operation_id"]}).status_code == 409
    assert client.get(f"/conversations/{other['conversation_id']}/turns/{turn['turn_id']}").status_code == 404
    assert handler.await_count == 1


@pytest.mark.parametrize("payload", [
    {"workspace_id": "other"}, {"owner_id": "other"}, {"source_revision": "a" * 64},
    {"document_ids": []}, {"document_ids": ["duplicate", "duplicate"]},
    {"operation_id": "not-a-uuid"}, {"title": None}, {"title": " "}, {"title": "x" * 121},
])
def test_create_rejects_invalid_and_untrusted_fields(setup, payload):
    body = {"operation_id": uid(), "document_ids": [setup[0].id], **payload}
    response = setup[5].post("/conversations", json=body)
    assert response.status_code == 422
    assert setup[1].page().items == [] and setup[3].await_count == 0


@pytest.mark.parametrize("extra", [{"text": " "}, {"text": "x" * 1001},
    {"workspace_id": "other"}, {"source_revision": "a" * 64}, {"fact_id": "invented"}])
def test_turn_rejects_invalid_and_untrusted_fields(setup, extra):
    conversation, _ = create(setup)
    response = setup[5].post(f"/conversations/{conversation['conversation_id']}/turns", json={
        "operation_id": uid(), "text": "question", **extra})
    assert response.status_code == 422 and setup[3].await_count == 0


def test_scope_query_rejected_and_foreign_document_not_authorized(setup):
    _, repo, _, handler, _, client, _ = setup
    assert client.get("/conversations?workspace_id=other").status_code == 422
    assert client.get("/conversations?owner_id=other").status_code == 422
    response = client.post("/conversations", json={"operation_id": uid(), "document_ids": [uid()]})
    assert response.status_code == 404 and repo.page().items == [] and handler.await_count == 0


def test_unverified_cover_and_non_annual_rejected(setup):
    h, repo, preparer, handler, _, client, reader = setup
    reader.source.return_value = h.source
    response = client.post("/conversations", json={"operation_id": uid(), "document_ids": [h.id]})
    assert response.status_code == 409 and response.json()["detail"] == "report_identity_unverified"
    reader.source.return_value = {**h.source,
        "assessment": dict.fromkeys(("company", "report_year", "report_type"), "matches_cover")}
    selection = asyncio.run(preparer.prepare_many(document_ids=[h.id], query="q"))
    changed = replace(selection, documents=(replace(selection.documents[0], report_type="quarterly"),))
    assert_error(lambda: repo.create(CreateConversationRequest(operation_id=uid(), document_ids=[h.id]),
                                     changed), "invalid_request", 422)
    assert handler.await_count == 0


def test_source_changed_cannot_register_new_turn_old_replay_remains_history(setup):
    h, repo, _, handler, _, client, _ = setup
    conversation, _ = create(setup)
    cid = conversation["conversation_id"]
    turn, request = send(setup, cid)
    assert h.correct().status_code == 200
    replay = client.post(f"/conversations/{cid}/turns", json=request)
    assert replay.status_code == 200 and replay.json()["result"] == turn["result"]
    assert replay.json()["source_states"][0]["status"] == "expired"
    response = client.post(f"/conversations/{cid}/turns", json={"operation_id": uid(), "text": "new"})
    assert response.status_code == 409 and handler.await_count == 1
    assert repo.detail(cid).last_turn_seq == 1


def test_complete_identity_compared_not_just_selection_document_id(setup):
    h, repo, preparer, _, _, _, _ = setup
    conversation, _ = create(setup)
    cid = conversation["conversation_id"]
    pinned = repo.selection(cid, "q")
    for changes in ({"basis": "IFRS"}, {"report_year": 2024}, {"parser_version": "changed"},
                    {"attempt": 2}, {"company_id": h.other.company_id},
                    {"period_end": "2025-12-30"}, {"content_sha256": "b" * 64}):
        changed = replace(pinned, documents=(replace(pinned.documents[0], **changes),))
        assert_error(lambda: repo.register(cid, CreateTurnRequest(operation_id=uid(), text="q"),
                                          changed), "source_changed", 409)
    assert repo.detail(cid).last_turn_seq == 0


def test_two_connections_register_at_most_one_running_and_old_op_priority(setup):
    _, repo, _, _, _, _, _ = setup
    conversation, _ = create(setup)
    cid = conversation["conversation_id"]
    selection = repo.selection(cid, "q")
    barrier = Barrier(2)

    def worker():
        other = ConversationRepository(repo.registry, "demo")
        request = CreateTurnRequest(operation_id=uid(), text="q")
        barrier.wait(timeout=5)
        try:
            return other.register(cid, request, selection)
        except ConversationError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: worker(), range(2)))
    assert sum(isinstance(v, tuple) for v in outcomes) == 1
    assert "conversation_busy" in outcomes
    value, claim, _ = next(v for v in outcomes if isinstance(v, tuple))
    request = CreateTurnRequest(operation_id=value.operation_id, text=value.user_text)
    replay = repo.register(cid, request, selection)
    assert not replay[2] and replay[0] == value
    with closing(repo.registry._connect()) as conn:
        # The DB constraint also protects callers that bypass service-level busy checks.
        row = conn.execute("SELECT * FROM conversation_turns WHERE turn_id=?", (value.turn_id,)).fetchone()
        other_op, other_turn = uid(), uid()
        receipt = repo.operation(value.operation_id).model_copy(update={
            "operation_id": other_op, "turn_id": other_turn})
        repo._save_op(conn, receipt, row["request_sha"], insert=True)
        with pytest.raises(sqlite3.IntegrityError, match="workspace_id, conversation_turns.conversation_id"):
            conn.execute("""INSERT INTO conversation_turns
                (workspace_id,conversation_id,turn_id,seq,operation_id,request_sha,status,
                 created_at,ended_at,payload,payload_sha,execution_json,execution_sha,claim)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                ("demo", cid, other_turn, 2, other_op, row["request_sha"], "running",
                 row["created_at"], None, row["payload"], row["payload_sha"],
                 row["execution_json"], row["execution_sha"], uid()))
    assert repo.detail(cid).active_turn_id == value.turn_id
    repo.finish(cid, value.turn_id, claim, TurnResult(kind="clarification", answer_text="请澄清"))
    second = repo.register(cid, CreateTurnRequest(operation_id=uid(), text="q"), selection)
    assert second[0].seq == 2
    assert repo.register(cid, request, selection)[0].status == "completed"


def test_duplicate_running_http_is_202_and_delete_is_busy(setup):
    _, repo, _, handler, _, client, _ = setup
    conversation, _ = create(setup)
    cid = conversation["conversation_id"]
    request = CreateTurnRequest(operation_id=uid(), text="q")
    turn, _, _ = repo.register(cid, request, repo.selection(cid, "q"))
    replay = client.post(f"/conversations/{cid}/turns", json=request.model_dump())
    assert replay.status_code == 202 and replay.json()["result"] is None
    assert client.get(f"/conversations/{cid}/turns/{turn.turn_id}").status_code == 200
    response = client.request("DELETE", f"/conversations/{cid}", json={"operation_id": uid()})
    assert response.status_code == 409 and handler.await_count == 0


def test_reservation_persists_before_call_recovery_and_late_claim_cannot_publish(setup):
    _, repo, _, handler, _, _, _ = setup
    conversation, _ = create(setup)
    cid = conversation["conversation_id"]
    turn, claim, _ = repo.register(cid, CreateTurnRequest(operation_id=uid(), text="q"),
                                   repo.selection(cid, "q"))
    repo.reserve(cid, turn.turn_id, claim, "model_attempts")
    assert repo.get_turn(cid, turn.turn_id).provider_outcome == "unknown"
    assert repo.get_turn(cid, turn.turn_id).usage.model_attempts == 1
    restarted = ConversationRepository(repo.registry, "demo")
    assert restarted.recover_interrupted() == 1
    assert restarted.recover_interrupted() == 0
    terminal = repo.get_turn(cid, turn.turn_id)
    assert terminal.status == "interrupted" and terminal.result.error_code == "interrupted"
    assert terminal.provider_outcome == "unknown" and terminal.usage.model_attempts == 1
    assert_error(lambda: repo.finish(cid, turn.turn_id, claim,
        TurnResult(kind="clarification", answer_text="late")), "turn_claim_expired", 409)
    assert_error(lambda: repo.reserve(cid, turn.turn_id, claim, "model_attempts"),
                 "turn_claim_expired", 409)
    assert handler.await_count == 0


def test_service_cancellation_records_interrupted_and_no_rerun(setup):
    _, repo, preparer, _, _, client, _ = setup
    conversation, _ = create(setup)
    cid = conversation["conversation_id"]
    started = asyncio.Event()
    count = []

    async def handler(execution):
        count.append(1)
        repo.reserve(cid, execution.turn.turn_id, execution.claim, "model_attempts")
        started.set()
        await asyncio.Event().wait()

    request = CreateTurnRequest(operation_id=uid(), text="q")
    service = ConversationService(repo, preparer, handler=handler)

    async def cancel():
        task = asyncio.create_task(service.send(cid, request))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel())
    value = repo.turn_by_operation(cid, request.operation_id)
    assert value.status == "interrupted" and value.provider_outcome == "unknown"
    assert asyncio.run(service.send(cid, request)).status == "interrupted"
    assert len(count) == 1


def test_terminal_database_immutable_and_payload_damage_fails_closed(setup):
    h, repo, _, _, _, client, _ = setup
    conversation, _ = create(setup)
    cid = conversation["conversation_id"]
    turn, request = send(setup, cid)
    with closing(h.registry._connect()) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE conversation_turns SET payload='{}' WHERE turn_id=?", (turn["turn_id"],))
    with closing(h.registry._connect()) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE conversation_sources SET basis='IFRS'")
    with closing(h.registry._connect()) as conn, conn:
        conn.execute("UPDATE conversation_operations SET payload_sha=? WHERE operation_id=?",
                     ("0" * 64, request["operation_id"]))
    response = client.get(f"/conversations/{cid}/turns/{turn['turn_id']}")
    assert response.status_code == 503 and response.json()["detail"] == "conversation_integrity_error"


def test_finish_source_change_withdraws_candidate(setup):
    h, repo, _, _, _, _, _ = setup
    conversation, _ = create(setup)
    cid = conversation["conversation_id"]
    turn, claim, _ = repo.register(cid, CreateTurnRequest(operation_id=uid(), text="q"),
                                   repo.selection(cid, "q"))
    assert h.correct().status_code == 200
    repo.finish(cid, turn.turn_id, claim, TurnResult(kind="clarification", answer_text="candidate"))
    result = repo.get_turn(cid, turn.turn_id)
    assert result.status == "failed" and result.result.error_code == "source_changed"
    assert "candidate" not in result.result.answer_text


def test_commit_failure_does_not_publish_and_same_operation_does_not_rerun(setup, monkeypatch):
    _, repo, _, handler, _, client, _ = setup
    conversation, _ = create(setup)
    cid = conversation["conversation_id"]
    original = repo._finish_in

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise sqlite3.OperationalError("private database path")

    monkeypatch.setattr(repo, "_finish_in", fail)
    request = {"operation_id": uid(), "text": "q"}
    failed = client.post(f"/conversations/{cid}/turns", json=request)
    assert failed.status_code == 503 and "private" not in failed.text
    replay = client.post(f"/conversations/{cid}/turns", json=request)
    assert replay.status_code == 202 and replay.json()["result"] is None
    assert handler.await_count == 1
    monkeypatch.setattr(repo, "_finish_in", original)
    assert repo.recover_interrupted() == 1


def test_commit_success_readback_failure_recovers_with_get_without_rerun(setup, monkeypatch):
    _, repo, _, handler, _, client, _ = setup
    conversation, _ = create(setup)
    cid = conversation["conversation_id"]
    original = repo.get_turn
    monkeypatch.setattr(repo, "get_turn", Mock(side_effect=sqlite3.OperationalError("private")))
    request = {"operation_id": uid(), "text": "q"}
    response = client.post(f"/conversations/{cid}/turns", json=request)
    assert response.status_code == 503
    monkeypatch.setattr(repo, "get_turn", original)
    recovered = client.get(f"/conversations/{cid}/turns/by-operation/{request['operation_id']}")
    assert recovered.status_code == 200 and recovered.json()["status"] == "completed"
    assert client.post(f"/conversations/{cid}/turns", json=request).json() == recovered.json()
    assert handler.await_count == 1


def test_delete_content_tombstone_replay_and_old_business_tables_unchanged(setup):
    h, repo, _, handler, _, client, _ = setup
    conversation, created = create(setup)
    cid = conversation["conversation_id"]
    turn, sent = send(setup, cid, text="private question")
    with closing(h.registry._connect()) as conn:
        before = {table: conn.execute(f"SELECT * FROM {table}").fetchall()
                  for table in ("documents", "document_sources", "research_runs", "template_tasks")}
    request = {"operation_id": uid()}
    response = client.request("DELETE", f"/conversations/{cid}", json=request)
    assert response.status_code == 200 and response.json()["resource_deleted"]
    assert client.request("DELETE", f"/conversations/{cid}", json=request).json() == response.json()
    assert client.get(f"/conversation-operations/{request['operation_id']}").json() == response.json()
    for op in (created["operation_id"], sent["operation_id"]):
        assert client.get(f"/conversation-operations/{op}").json()["resource_deleted"]
    assert client.post("/conversations", json=created).status_code == 410
    assert client.post(f"/conversations/{cid}/turns", json=sent).status_code == 410
    assert client.get(f"/conversations/{cid}").status_code == 410
    assert client.get("/conversations/by-operation/" + created["operation_id"]).status_code == 410
    with closing(h.registry._connect()) as conn:
        for table, rows in before.items():
            assert conn.execute(f"SELECT * FROM {table}").fetchall() == rows
        assert conn.execute("SELECT count(*) FROM conversation_turns").fetchone()[0] == 0
        assert "private question" not in str(conn.execute("SELECT * FROM conversation_operations").fetchall())
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert handler.await_count == 1


def test_history_pagination_is_bounded_and_stable_while_new_conversation_added(setup):
    _, repo, _, _, _, _, _ = setup
    ids = [create(setup)[0]["conversation_id"] for _ in range(3)]
    page = repo.page(1)
    assert page.items[0].conversation_id == ids[2] and page.next_cursor
    create(setup)
    second = repo.page(1, page.next_cursor)
    third = repo.page(1, second.next_cursor)
    assert [second.items[0].conversation_id, third.items[0].conversation_id] == ids[1::-1]
    assert third.next_cursor is None
    assert_error(lambda: repo.page(20, "garbage"), "invalid_cursor_or_limit", 422)
    foreign = ConversationRepository(repo.registry, "other")
    assert_error(lambda: foreign.page(1, page.next_cursor), "invalid_cursor_or_limit", 422)
    cid = ids[0]
    for _ in range(3):
        send(setup, cid)
    detail = repo.detail(cid, limit=2)
    assert [v.seq for v in detail.turns] == [2, 3] and detail.next_before_seq == 2
    previous = repo.detail(cid, limit=2, before_seq=detail.next_before_seq)
    assert [v.seq for v in previous.turns] == [1] and previous.next_before_seq is None


def test_v9_upgrade_retains_prior_checksums_and_rows_failure_rolls_back(tmp_path, monkeypatch):
    path = tmp_path / "documents.db"
    old = tuple(m for m in migrations.MIGRATIONS if m[0] <= 9)
    monkeypatch.setattr(migrations, "MIGRATIONS", old)
    registry = SQLiteCompanyRepository(path)
    before = all_rows(registry)
    plans = (*old, (10, "conversations_v1", (*migrations.CONVERSATION_MIGRATION[2],
                                             "INSERT INTO missing_conversation_table VALUES(1)")))
    monkeypatch.setattr(migrations, "MIGRATIONS", plans)
    with pytest.raises(sqlite3.OperationalError):
        SQLiteCompanyRepository(path)
    assert all_rows(registry) == before
    with closing(registry._connect()) as conn:
        assert conn.execute("SELECT count(*) FROM sqlite_master WHERE name='conversations'").fetchone()[0] == 0
    monkeypatch.setattr(migrations, "MIGRATIONS", (*old, migrations.CONVERSATION_MIGRATION))
    SQLiteCompanyRepository(path)
    after = all_rows(registry)
    for table, rows in before.items():
        if table == "analyst_schema_migrations":
            assert after[table][:9] == rows
        else:
            assert after[table] == rows
    assert after["analyst_schema_migrations"][-1][0] == 10
    frozen = all_rows(registry)
    SQLiteCompanyRepository(path)
    assert all_rows(registry) == frozen
    with closing(registry._connect()) as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("href", ["https://example.com", "//example.com", "javascript:alert(1)",
    "/research?mode=operating&resume=true", "/research?mode=qa", "/research#fragment"])
def test_actions_are_site_allowlist_not_model_urls(href):
    with pytest.raises(ValidationError):
        Action(kind="review_facts", label="核对", href=href)


def test_no_evidence_in_nonanswer_and_no_free_interpretation():
    with pytest.raises(ValidationError):
        TurnResult(kind="clarification", answer_text="x", interpretation_status="pending_human_review")
    with pytest.raises(ValidationError):
        TurnResult(kind="error", answer_text="x")


def test_source_action_exact_real_api_route_page_fragment_and_identity():
    valid = dict(kind="open_source", label="原文", document_id="a/b", source_revision="a" * 64,
                 physical_page=2, href="/api/documents/a%2Fb/file?source_revision=" + "a" * 64 + "#page=2")
    assert Action(**valid).physical_page == 2
    for change in ({"physical_page": None}, {"physical_page": 3},
                   {"href": valid["href"].replace("#page=2", "#page=3")},
                   {"href": valid["href"].replace("/file?", "/source/file?")},
                   {"href": valid["href"] + "&resume=true"}):
        with pytest.raises(ValidationError):
            Action(**{**valid, **change})


def test_fake_exception_is_terminal_no_raw_error_or_replay(setup):
    _, repo, _, handler, _, client, _ = setup
    conversation, _ = create(setup)
    cid = conversation["conversation_id"]
    handler.side_effect = RuntimeError("SECRET credentials / private path")
    turn, body = send(setup, cid)
    assert turn["status"] == "failed" and turn["result"]["error_code"] == "execution_error"
    assert "SECRET" not in str(turn)
    assert client.post(f"/conversations/{cid}/turns", json=body).json() == turn
    assert handler.await_count == 1 and repo.detail(cid).active_turn_id is None


def test_reservation_limits_wrong_claim_and_independent_conversations(setup):
    _, repo, _, _, _, _, _ = setup
    first, _ = create(setup)
    second, _ = create(setup)
    ids = [first["conversation_id"], second["conversation_id"]]
    turns = [repo.register(cid, CreateTurnRequest(operation_id=uid(), text="q"),
                           repo.selection(cid, "q")) for cid in ids]
    turn, claim, _ = turns[0]
    assert_error(lambda: repo.reserve(ids[0], turn.turn_id, uid(), "model_attempts"),
                 "turn_claim_expired", 409)
    for counter, maximum in (("model_attempts", 2), ("tool_calls", 3)):
        for _ in range(maximum):
            repo.reserve(ids[0], turn.turn_id, claim, counter)
        assert_error(lambda: repo.reserve(ids[0], turn.turn_id, claim, counter),
                     "budget_exhausted", 409)
    assert repo.get_turn(ids[0], turn.turn_id).usage.model_attempts == 2
    assert repo.detail(ids[1]).active_turn_id == turns[1][0].turn_id


def test_damaged_running_payload_and_scope_rows_rejected_without_execution(setup):
    h, repo, _, _, _, client, _ = setup
    conversation, _ = create(setup)
    cid = conversation["conversation_id"]
    turn, _, _ = repo.register(cid, CreateTurnRequest(operation_id=uid(), text="q"),
                               repo.selection(cid, "q"))
    with closing(h.registry._connect()) as conn, conn:
        conn.execute("UPDATE conversation_turns SET payload_sha=? WHERE turn_id=?",
                     ("a" * 64, turn.turn_id))
    assert client.get(f"/conversations/{cid}").status_code == 503
    assert_error(repo.recover_interrupted, "conversation_integrity_error", 503)


def test_free_text_cannot_be_committed_as_original_quote_or_cross_scope_focus(setup):
    _, repo, _, _, _, _, _ = setup
    conversation, _ = create(setup)
    cid = conversation["conversation_id"]
    selection = repo.selection(cid, "q")
    turn, claim, _ = repo.register(cid, CreateTurnRequest(operation_id=uid(), text="q"), selection)
    doc = conversation["sources"][0]
    ref = EvidenceRef(**doc, ref_id="e1", number=1, chunk_id="chunk-0", physical_page=1,
        source_file="fixture.pdf", text="原文", kind="paragraph", verification="exact_original_with_context")
    with pytest.raises(ConversationError):
        repo.finish(cid, turn.turn_id, claim, TurnResult(kind="source_quote",
                                                       answer_text="自由改写", evidence_refs=[ref]))
    assert repo.get_turn(cid, turn.turn_id).status == "running"
    with pytest.raises(ConversationError):
        repo.finish(cid, turn.turn_id, claim, TurnResult(kind="clarification", answer_text="澄清"),
                    resolved=ResolvedQuery(text="q", intent="clarify", company_id="out-of-scope",
                        metric_key=None, periods=[], resolution="explicit", context_turn_ids=[]))
    assert repo.get_turn(cid, turn.turn_id).status == "running"


def test_same_operation_parallel_registration_and_creation_single_identity(setup):
    _, repo, preparer, _, _, _, _ = setup
    selection = asyncio.run(preparer.prepare_many(document_ids=[setup[0].id], query="q"))
    request = CreateConversationRequest(operation_id=uid(), document_ids=[setup[0].id])
    barrier = Barrier(2)

    def create_worker():
        barrier.wait(timeout=5)
        return repo.create(request, selection)

    with ThreadPoolExecutor(max_workers=2) as pool:
        creates = list(pool.map(lambda _: create_worker(), range(2)))
    assert len({v[0] for v in creates}) == 1 and sum(v[1] for v in creates) == 1
    cid = creates[0][0]
    body = CreateTurnRequest(operation_id=uid(), text="q")
    barrier = Barrier(2)

    def turn_worker():
        barrier.wait(timeout=5)
        return repo.register(cid, body, selection)

    with ThreadPoolExecutor(max_workers=2) as pool:
        turns = list(pool.map(lambda _: turn_worker(), range(2)))
    assert len({v[0].turn_id for v in turns}) == 1 and sum(v[2] for v in turns) == 1


def test_context_turn_ids_must_be_committed_same_conversation_history(setup):
    _, repo, _, _, _, _, _ = setup
    conversation, _ = create(setup)
    other, _ = create(setup)
    foreign, _ = send(setup, other["conversation_id"])
    cid = conversation["conversation_id"]
    turn, claim, _ = repo.register(cid, CreateTurnRequest(operation_id=uid(), text="q"),
                                   repo.selection(cid, "q"))
    with pytest.raises(ConversationError):
        repo.finish(cid, turn.turn_id, claim, TurnResult(kind="clarification", answer_text="澄清"),
                    resolved=ResolvedQuery(text="q", intent="clarify", company_id=None,
                        metric_key=None, periods=[], resolution="context",
                        context_turn_ids=[foreign["turn_id"]]))


def test_create_commit_then_readback_failure_uses_original_operation(setup, monkeypatch):
    _, repo, _, handler, _, client, _ = setup
    original = repo.detail
    monkeypatch.setattr(repo, "detail", Mock(side_effect=sqlite3.OperationalError("private")))
    request = {"operation_id": uid(), "document_ids": [setup[0].id]}
    response = client.post("/conversations", json=request)
    assert response.status_code == 503 and "private" not in response.text
    receipt = client.get("/conversation-operations/" + request["operation_id"])
    assert receipt.status_code == 200 and receipt.json()["status"] == "completed"
    monkeypatch.setattr(repo, "detail", original)
    replay = client.post("/conversations", json=request)
    assert replay.status_code == 200
    assert replay.json()["conversation_id"] == receipt.json()["conversation_id"]
    assert len(repo.page().items) == 1 and handler.await_count == 0


def test_delete_commit_then_readback_failure_keeps_content_deleted(setup, monkeypatch):
    _, repo, _, handler, _, client, _ = setup
    conversation, _ = create(setup)
    cid = conversation["conversation_id"]
    original = repo.operation
    monkeypatch.setattr(repo, "operation", Mock(side_effect=sqlite3.OperationalError("private")))
    request = {"operation_id": uid()}
    response = client.request("DELETE", f"/conversations/{cid}", json=request)
    assert response.status_code == 503 and "private" not in response.text
    assert client.get(f"/conversations/{cid}").status_code == 410
    monkeypatch.setattr(repo, "operation", original)
    receipt = client.get("/conversation-operations/" + request["operation_id"])
    assert receipt.status_code == 200 and receipt.json()["resource_deleted"]
    assert client.request("DELETE", f"/conversations/{cid}", json=request).json() == receipt.json()
    assert repo.page().items == [] and handler.await_count == 0


def test_history_factory_mounts_read_only_routes_without_provider(setup, monkeypatch):
    from app.api.research_history_app import create_history_app_from_env
    h, repo, _, handler, _, _, _ = setup
    conversation, _ = create(setup)
    cid = conversation["conversation_id"]
    turn, claim, _ = repo.register(cid, CreateTurnRequest(operation_id=uid(), text="q"),
                                   repo.selection(cid, "q"))
    monkeypatch.setenv("FINDOC_RUNTIME_ROOT", str(h.root))
    app = create_history_app_from_env()
    with TestClient(app) as client:
        response = client.get(f"/conversations/{cid}")
        assert response.status_code == 200
        assert response.json()["turns"][0]["status"] == "interrupted"
        before = all_rows(h.registry)
        assert client.get(f"/conversations/{cid}").status_code == 200
        assert all_rows(h.registry) == before
        assert client.post("/conversations", json={"operation_id": uid(),
            "document_ids": [h.id]}).status_code == 405
    assert handler.await_count == 0
