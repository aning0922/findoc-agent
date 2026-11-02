"""B2 deterministic summaries on real temporary SQLite; no live provider."""
# ruff: noqa: F811

from contextlib import closing
import sqlite3
from uuid import uuid4

import pytest

from app.companies import migrations
from app.companies.sqlite_repository import SQLiteCompanyRepository
from app.conversations.context import load_context, resolve, tokens
from app.conversations.models import CreateTurnRequest
from app.conversations.repository import ConversationError, ConversationRepository
from app.conversations.service import TurnExecution
from app.conversations.summaries import SummaryRepository
from app.memory.models import CreateMemoryRequest, DeleteMemoryRequest
from tests.test_conversation_a1 import setup  # noqa: F401
from tests.test_conversation_graph import graph_env, ask  # noqa: F401


def uid():
    return str(uuid4())


def count(env):
    with closing(env[1].registry._connect()) as conn:
        return conn.execute("SELECT version,payload FROM conversation_summaries ORDER BY version").fetchall()


def prepare(env, text="同比变化呢？"):
    exrepo = ConversationRepository(env[1].registry, "demo")
    turn, claim, _ = exrepo.register(env[9], CreateTurnRequest(operation_id=uid(), text=text),
                                    exrepo.selection(env[9], text))
    ex = TurnExecution(exrepo, turn, exrepo.selection(env[9], text), claim)
    SummaryRepository(exrepo).refresh(ex, env[6])
    return ex, load_context(ex, env[6])


def test_25_turn_bounds_persistence_provenance_and_get_zero_write(graph_env):
    env = graph_env
    for _ in range(25):
        value, _ = ask(env, "2025年营业收入原文")
        assert value["status"] == "completed"
    before = count(env)
    assert len(before) == 2
    assert all("这是可信业务原文" not in row["payload"] and "answer_text" not in row["payload"]
               and "user_text" not in row["payload"] and "value_cny_yuan" not in row["payload"]
               for row in before)
    for _ in range(2):
        assert env[8].get(f"/conversations/{env[9]}").status_code == 200
    assert count(env) == before
    ex, context = prepare(env)
    assert context.summary.covered_through_seq == 17
    assert len(context.turns) <= 8 and len(context.summary.source_turn_ids) <= 32
    assert tokens(context.prompt_data) < 5000
    resolved, reason = resolve(ex, context)
    assert reason is None and resolved.periods == [2025, 2024]
    assert context.summary.source_scope_sha == ex.selection.selection_id


def test_restart_uses_summary_when_recent_eight_are_excluded_preferences(graph_env):
    env = graph_env
    first, _ = ask(env, "2025年营业收入原文")
    for _ in range(9):
        ask(env, "记住：我更关注现金流。")
    ex, context = prepare(env)
    assert context.turns == () and context.summary.focus_turn_id == first["turn_id"]
    resolved, reason = resolve(ex, context)
    assert reason is None and resolved.context_turn_ids == [first["turn_id"]]
    assert resolved.periods == [2025, 2024]
    assert "cash_flow" not in context.prompt_data and "记住" not in context.prompt_data


def test_summary_unknown_subject_barrier_survives_restart_and_excluded_recent(graph_env):
    env = graph_env
    ask(env, "2025年营业收入原文")
    barrier, _ = ask(env, "苹果同一年呢？")
    for _ in range(9):
        ask(env, "记住：我更关注现金流。")
    ex, context = prepare(env)
    assert context.summary.barrier and context.summary.focus is None
    assert context.summary.focus_turn_id == barrier["turn_id"]
    resolved, reason = resolve(ex, context)
    assert reason is not None and resolved.context_turn_ids == []
    assert resolved.metric_key is None


def test_deleted_preference_generation_invalidates_old_summary_then_refreshes_without_value(graph_env):
    env = graph_env
    user, _ = ask(env, "记住：我更关注现金流。")
    item, _ = env[6].create(CreateMemoryRequest(operation_id=uid(), type="research_preference",
        key="analysis_focus", value="cash_flow", source_turn_id=user["turn_id"], confirmed=True))
    for _ in range(12):
        ask(env, "2025年营业收入原文")
    repo = SummaryRepository(env[1])
    generation = env[6].recall_context().generation
    assert repo.read(env[9], generation, env[6].excluded_source_turn_ids()) is not None
    env[6].delete(item.memory_id, DeleteMemoryRequest(operation_id=uid(), expected_revision=1))
    newer = env[6].recall_context().generation
    assert repo.read(env[9], newer, env[6].excluded_source_turn_ids()) is None
    ex, context = prepare(env)
    assert context.summary.memory_generation == newer
    assert "cash_flow" not in context.prompt_data
    assert all("cash_flow" not in r["payload"] for r in count(env))


def test_corrupt_summary_fails_closed_and_never_generates_provider(graph_env):
    env = graph_env
    for _ in range(11):
        ask(env, "2025年营业收入原文")
    with closing(env[1].registry._connect()) as conn, conn:
        # Simulate storage damage, without removing the immutable guard.
        conn.execute("DROP TRIGGER conversation_summary_immutable")
        conn.execute("UPDATE conversation_summaries SET payload_sha=?", ("0" * 64,))
    with pytest.raises(ConversationError, match="summary_integrity_error"):
        SummaryRepository(env[1]).read(env[9], 0, frozenset())


def test_v12_upgrade_keeps_1_to_11_checksums_and_rolls_back_failure(tmp_path, monkeypatch):
    old = tuple(m for m in migrations.MIGRATIONS if m[0] <= 11)
    migration = next(m for m in migrations.MIGRATIONS if m[0] == 12)
    monkeypatch.setattr(migrations, "MIGRATIONS", old)
    registry = SQLiteCompanyRepository(tmp_path / "documents.db")
    with closing(registry._connect()) as conn:
        before = conn.execute("SELECT * FROM analyst_schema_migrations").fetchall()
    monkeypatch.setattr(migrations, "MIGRATIONS", (*old,
        (12, migration[1], (*migration[2], "INSERT INTO missing_summary_table VALUES(1)"))))
    with pytest.raises(sqlite3.OperationalError):
        SQLiteCompanyRepository(tmp_path / "documents.db")
    with closing(registry._connect()) as conn:
        assert conn.execute("SELECT * FROM analyst_schema_migrations").fetchall() == before
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='conversation_summaries'").fetchone() is None
    monkeypatch.setattr(migrations, "MIGRATIONS", (*old, migration))
    SQLiteCompanyRepository(tmp_path / "documents.db")
    with closing(registry._connect()) as conn:
        assert conn.execute("SELECT * FROM analyst_schema_migrations").fetchall()[:11] == before
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_summary_cascade_delete_leaves_no_derived_thread(graph_env):
    env = graph_env
    for _ in range(10):
        ask(env, "2025年营业收入原文")
    assert count(env)
    response = env[8].request("DELETE", f"/conversations/{env[9]}", json={"operation_id": uid()})
    assert response.status_code == 200 and count(env) == []


def test_token_omission_never_jumps_over_recent_unknown_subject_barrier(graph_env, monkeypatch):
    from app.conversations import context as module
    env = graph_env
    for _ in range(12):
        ask(env, "2025年营业收入原文")
    ask(env, "BLOCKER苹果2025年营业收入")
    original = module.tokens
    monkeypatch.setattr(module, "tokens", lambda text: 5000 if "BLOCKER" in text else original(text))
    ex, context = prepare(env)
    assert context.turns == () and context.summary is None
    resolved, reason = resolve(ex, context)
    assert reason is not None and resolved.context_turn_ids == []
