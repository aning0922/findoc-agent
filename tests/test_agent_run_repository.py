import sqlite3
import json
from datetime import timedelta
from pathlib import Path

import pytest

from app.agent.run_models import (
    AgentRun,
    AgentRunNotFoundError,
    AgentRunStateConflictError,
    AgentTerminalStatus,
    RunEvent,
    RunEventSequenceError,
    RunEventType,
    RunStatus,
)
from app.agent.sqlite_run_repository import SQLiteAgentRunRepository
from app.agent.result_storage import (
    USER_RESULT_VERSION, AgentResultIntegrityError, AgentResultNotReadyError,
    AgentResultNotStoredError,
)
from app.agent.user_result import (
    AgentAnswer, AgentRefusal, AgentRefusalReason, AgentResultError, AgentSystemError,
)
from app.rag.service import Citation


def _event(
    run: AgentRun,
    *,
    sequence: int,
    event_type: RunEventType = RunEventType.TOOL_REQUESTED,
) -> RunEvent:
    """构造带安全白名单 payload 的测试事件。"""
    return RunEvent(
        run_id=run.run_id,
        sequence=sequence,
        event_type=event_type,
        payload={"tool_name": "search_finance_docs", "tool_call_id": f"call-{sequence}"},
        occurred_at=run.started_at + timedelta(seconds=sequence),
    )


def _terminal_event(
    run: AgentRun,
    *,
    sequence: int,
    terminal_status: AgentTerminalStatus,
) -> RunEvent:
    """构造与精确终态一致的测试终态事件。"""
    succeeded = terminal_status is AgentTerminalStatus.SUCCESS
    return RunEvent(
        run_id=run.run_id,
        sequence=sequence,
        event_type=(RunEventType.RUN_SUCCEEDED if succeeded else RunEventType.RUN_FAILED),
        payload={"terminal_status": terminal_status.value},
        occurred_at=run.started_at + timedelta(seconds=sequence),
    )


def test_repository_reopen_preserves_run_and_ordered_events(tmp_path: Path) -> None:
    """验证 repository 重开后 Run 与有序事件仍可查询。"""
    database_path = tmp_path / "agent-runs.db"
    repository = SQLiteAgentRunRepository(database_path)
    started = repository.start_run(
        workspace_id="WS-A",
        execution_config_version="agent-run-v1",
    )
    repository.append_event(
        workspace_id="WS-A",
        event=_event(started, sequence=1),
    )
    finalized = repository.finalize_run(
        workspace_id="WS-A",
        terminal_status=AgentTerminalStatus.SUCCESS,
        safe_result={"final_answer_available": True},
        terminal_event=_terminal_event(
            started,
            sequence=2,
            terminal_status=AgentTerminalStatus.SUCCESS,
        ),
    )

    reopened = SQLiteAgentRunRepository(database_path)

    assert reopened.get_run(workspace_id="WS-A", run_id=started.run_id) == finalized
    events = reopened.list_events(workspace_id="WS-A", run_id=started.run_id)
    assert [event.sequence for event in events] == [1, 2]
    assert [event.event_type for event in events] == [
        RunEventType.TOOL_REQUESTED,
        RunEventType.RUN_SUCCEEDED,
    ]


def test_repository_rejects_non_contiguous_and_duplicate_sequences(
    tmp_path: Path,
) -> None:
    """验证 sequence 必须从 1 开始严格连续，且复合主键拒绝重复。"""
    database_path = tmp_path / "agent-runs.db"
    repository = SQLiteAgentRunRepository(database_path)
    started = repository.start_run(
        workspace_id="WS-A",
        execution_config_version="agent-run-v1",
    )

    with pytest.raises(RunEventSequenceError):
        repository.append_event(
            workspace_id="WS-A",
            event=_event(started, sequence=2),
        )

    first_event = _event(started, sequence=1)
    repository.append_event(workspace_id="WS-A", event=first_event)
    with pytest.raises(RunEventSequenceError):
        repository.append_event(workspace_id="WS-A", event=first_event)
    with pytest.raises(RunEventSequenceError):
        repository.append_event(
            workspace_id="WS-A",
            event=_event(started, sequence=3),
        )

    with sqlite3.connect(database_path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO run_events (
                    run_id, sequence, event_type, payload_json, occurred_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    first_event.run_id,
                    first_event.sequence,
                    first_event.event_type.value,
                    "{}",
                    first_event.occurred_at.isoformat(),
                ),
            )

    assert [
        event.sequence
        for event in repository.list_events(
            workspace_id="WS-A",
            run_id=started.run_id,
        )
    ] == [1]


def test_repository_hides_run_existence_across_workspaces(tmp_path: Path) -> None:
    """验证错误 workspace 与不存在 Run 共用 not-found 语义。"""
    repository = SQLiteAgentRunRepository(tmp_path / "agent-runs.db")
    started = repository.start_run(
        workspace_id="WS-A",
        execution_config_version="agent-run-v1",
    )

    assert repository.get_run(workspace_id="WS-B", run_id=started.run_id) is None
    assert repository.get_run(workspace_id="WS-B", run_id="missing-run") is None

    for run_id in (started.run_id, "missing-run"):
        with pytest.raises(AgentRunNotFoundError, match="Agent Run 不存在"):
            repository.list_events(workspace_id="WS-B", run_id=run_id)


def test_repository_rejects_terminal_append_and_post_terminal_changes(
    tmp_path: Path,
) -> None:
    """验证终态只能原子写入一次，终态后不得再追加。"""
    repository = SQLiteAgentRunRepository(tmp_path / "agent-runs.db")
    started = repository.start_run(
        workspace_id="WS-A",
        execution_config_version="agent-run-v1",
    )
    terminal_event = _terminal_event(
        started,
        sequence=1,
        terminal_status=AgentTerminalStatus.SUCCESS,
    )

    with pytest.raises(AgentRunStateConflictError, match="finalize_run"):
        repository.append_event(workspace_id="WS-A", event=terminal_event)

    repository.finalize_run(
        workspace_id="WS-A",
        terminal_status=AgentTerminalStatus.SUCCESS,
        safe_result={"final_answer_available": True},
        terminal_event=terminal_event,
    )

    with pytest.raises(AgentRunStateConflictError, match="已经终结"):
        repository.finalize_run(
            workspace_id="WS-A",
            terminal_status=AgentTerminalStatus.SUCCESS,
            safe_result={"final_answer_available": True},
            terminal_event=terminal_event,
        )
    with pytest.raises(AgentRunStateConflictError, match="不是运行中"):
        repository.append_event(
            workspace_id="WS-A",
            event=_event(started, sequence=2),
        )


def test_finalize_rolls_back_terminal_event_when_run_update_fails(tmp_path: Path) -> None:
    """验证 Run 更新失败时，同事务的终态事件也回滚。"""
    database_path = tmp_path / "agent-runs.db"
    repository = SQLiteAgentRunRepository(database_path)
    started = repository.start_run(
        workspace_id="WS-A",
        execution_config_version="agent-run-v1",
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER reject_agent_run_update
            BEFORE UPDATE ON agent_runs
            BEGIN
                SELECT RAISE(ABORT, 'forced update failure');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="forced update failure"):
        repository.finalize_run(
            workspace_id="WS-A",
            terminal_status=AgentTerminalStatus.SUCCESS,
            safe_result={"final_answer_available": True},
            terminal_event=_terminal_event(
                started,
                sequence=1,
                terminal_status=AgentTerminalStatus.SUCCESS,
            ),
        )

    reopened = SQLiteAgentRunRepository(database_path)
    persisted = reopened.get_run(workspace_id="WS-A", run_id=started.run_id)
    assert persisted is not None
    assert persisted.status is RunStatus.RUNNING
    assert persisted.terminal_status is None
    assert reopened.list_events(workspace_id="WS-A", run_id=started.run_id) == []


def _product_run(repository):
    """创建明确要求产品结果的新 Run，并预存一条工具事件。"""
    run = repository.start_run(
        workspace_id="WS-A", execution_config_version="runtime-search-result-v2",
        document_id="server-doc", user_result_version=USER_RESULT_VERSION,
    )
    repository.append_event(workspace_id="WS-A", event=_event(run, sequence=1))
    return run


def _answer():
    """代表已由可信证据会话验证的受限结果，不包含原始候选。"""
    return AgentAnswer("营业收入100万元[1]", (Citation(1, "demo.pdf", 2, "chunk-1"),))


def _save_product(repository, run, result, terminal_status=AgentTerminalStatus.SUCCESS):
    """构造执行与产品双层摘要，调用真实终结事务。"""
    event = _terminal_event(run, sequence=2, terminal_status=terminal_status)
    event.payload["user_result_status"] = result.status
    return repository.finalize_run(
        workspace_id="WS-A", terminal_status=terminal_status,
        safe_result={"user_result_status": result.status}, terminal_event=event,
        user_result=result,
    )


@pytest.mark.parametrize(("result", "terminal_status"), [
    (_answer(), AgentTerminalStatus.SUCCESS),
    (AgentRefusal(AgentRefusalReason.EMPTY_RETRIEVAL), AgentTerminalStatus.SUCCESS),
    (AgentSystemError(AgentResultError.CITATION_VALIDATION_ERROR), AgentTerminalStatus.SUCCESS),
    (AgentSystemError(AgentResultError.PROVIDER_ERROR), AgentTerminalStatus.PROVIDER_ERROR),
])
def test_product_reopens_with_scope_metadata_and_unique_terminal(tmp_path, result, terminal_status):
    """三态在关闭连接后可重开读取；错误 scope、不存在、重复提交均不泄露或覆盖。"""
    path = tmp_path / "results.db"
    repository = SQLiteAgentRunRepository(path)
    run = _product_run(repository)
    final = _save_product(repository, run, result, terminal_status)
    del repository
    reopened = SQLiteAgentRunRepository(path)
    stored = reopened.get_user_result(workspace_id="WS-A", run_id=run.run_id)
    assert stored.user_result == result
    assert stored.user_result.to_public() == result.to_public()
    assert stored.document_id == "server-doc"
    assert stored.workspace_id == "WS-A" and stored.run_id == run.run_id
    assert stored.result_version == USER_RESULT_VERSION
    assert stored.execution_config_version == final.execution_config_version
    for missing in (run.run_id, "missing"):
        with pytest.raises(AgentRunNotFoundError, match="^Agent Run 不存在$"):
            reopened.get_user_result(workspace_id="WS-B", run_id=missing)
    for repeated in (result, AgentRefusal(AgentRefusalReason.CAPABILITY_LIMIT)):
        with pytest.raises(AgentRunStateConflictError, match="已经终结"):
            _save_product(reopened, run, repeated, terminal_status)
    assert reopened.get_user_result(workspace_id="WS-A", run_id=run.run_id) == stored
    assert [e.sequence for e in reopened.list_events(workspace_id="WS-A", run_id=run.run_id)] == [1, 2]
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM agent_user_results").fetchone()[0] == 1
        payload = json.loads(connection.execute("SELECT payload_json FROM agent_user_results").fetchone()[0])
    expected = {"status", "content", "citations"} if result.status == "answered" else {
        "status", "reason" if result.status == "refusal" else "error_code"
    }
    assert set(payload) == expected


@pytest.mark.parametrize(("table", "operation"), [
    ("agent_user_results", "INSERT"), ("run_events", "INSERT"), ("agent_runs", "UPDATE"),
])
def test_three_final_products_rollback_on_database_failure(tmp_path, table, operation):
    """真实 SQLite 触发器阻止任一写入；重开后仅保留原 running 和更早工具事件。"""
    path = tmp_path / "atomic.db"
    repository = SQLiteAgentRunRepository(path)
    run = _product_run(repository)
    with sqlite3.connect(path) as connection:
        connection.execute(f"""CREATE TRIGGER reject_final_write BEFORE {operation} ON {table}
            BEGIN SELECT RAISE(ABORT, 'forced final failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="forced final failure"):
        _save_product(repository, run, _answer())
    reopened = SQLiteAgentRunRepository(path)
    assert reopened.get_run(workspace_id="WS-A", run_id=run.run_id) == run
    assert [e.sequence for e in reopened.list_events(workspace_id="WS-A", run_id=run.run_id)] == [1]
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM agent_user_results").fetchone()[0] == 0
    with pytest.raises(AgentResultNotReadyError):
        reopened.get_user_result(workspace_id="WS-A", run_id=run.run_id)


def test_serialization_failure_after_result_insert_rolls_back(tmp_path, monkeypatch):
    """在结果已真实插入后令终态事件序列化失败，验证该结果也回滚。"""
    path = tmp_path / "serialize.db"
    repository = SQLiteAgentRunRepository(path)
    run = _product_run(repository)
    real_dumps = json.dumps
    def fail_terminal(value, **kwargs):
        if isinstance(value, dict) and "terminal_status" in value:
            raise TypeError("forced serialization failure")
        return real_dumps(value, **kwargs)
    event = _terminal_event(run, sequence=2, terminal_status=AgentTerminalStatus.SUCCESS)
    event.payload["user_result_status"] = "answered"
    monkeypatch.setattr(json, "dumps", fail_terminal)
    with pytest.raises(TypeError, match="forced serialization failure"):
        repository.finalize_run(
            workspace_id="WS-A", terminal_status=AgentTerminalStatus.SUCCESS,
            safe_result={"user_result_status": "answered"}, terminal_event=event,
            user_result=_answer(),
        )
    reopened = SQLiteAgentRunRepository(path)
    assert reopened.get_run(workspace_id="WS-A", run_id=run.run_id) == run
    assert len(reopened.list_events(workspace_id="WS-A", run_id=run.run_id)) == 1
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM agent_user_results").fetchone()[0] == 0


@pytest.mark.parametrize("bad_payload", [
    "not-json", "[]", '{"status":"refusal","reason":"invented"}',
    '{"status":"system_error","error_code":"provider_error","content":"SECRET"}',
    '{"status":"refusal","reason":"empty_retrieval","messages":["SECRET"]}',
    '{"status":"refusal","reason":"empty_retrieval","reason":"capability_limit"}',
    '{"status":"answered","content":"正文[1]","citations":[{"number":true,"page":1,"source_file":"f","chunk_id":"c"}]}',
    '{"status":"answered","content":"正文[2]","citations":[{"number":1,"page":1,"source_file":"f","chunk_id":"c"}]}',
])
def test_corrupt_result_is_rejected_after_scope_check(tmp_path, bad_payload):
    """数据库 JSON 不自动成为可信结果；损坏和越界均不回显正文。"""
    path = tmp_path / "corrupt.db"
    repository = SQLiteAgentRunRepository(path)
    run = _product_run(repository)
    _save_product(repository, run, _answer())
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE agent_user_results SET payload_json = ?", (bad_payload,))
    reopened = SQLiteAgentRunRepository(path)
    with pytest.raises(AgentRunNotFoundError):
        reopened.get_user_result(workspace_id="WS-B", run_id=run.run_id)
    with pytest.raises(AgentResultIntegrityError) as error:
        reopened.get_user_result(workspace_id="WS-A", run_id=run.run_id)
    assert "SECRET" not in str(error.value)


@pytest.mark.parametrize("corruption", ["missing_result", "version", "summary", "event"])
def test_new_product_missing_or_inconsistent_metadata_is_not_legacy(tmp_path, corruption):
    """新 Run 的缺结果、未知版本或双层摘要冲突均按一致性错误处理。"""
    path = tmp_path / "inconsistent.db"
    repository = SQLiteAgentRunRepository(path)
    run = _product_run(repository)
    _save_product(repository, run, _answer())
    statements = {
        "missing_result": "DELETE FROM agent_user_results",
        "version": "UPDATE agent_runs SET user_result_version = 'unknown-v9'",
        "summary": "UPDATE agent_runs SET safe_result_json = '{}'",
        "event": "DELETE FROM run_events WHERE sequence = 2",
    }
    with sqlite3.connect(path) as connection:
        connection.execute(statements[corruption])
    with pytest.raises(AgentResultIntegrityError):
        SQLiteAgentRunRepository(path).get_user_result(workspace_id="WS-A", run_id=run.run_id)


def test_existing_database_is_extended_without_backfill(tmp_path):
    """用原 Run/Event 表结构和旧终态重开；原记录保留，缺产品结果明确说明。"""
    path = tmp_path / "legacy.db"
    repository = SQLiteAgentRunRepository(path)
    run = repository.start_run(workspace_id="WS-A", execution_config_version="old-v1")
    final = repository.finalize_run(
        workspace_id="WS-A", terminal_status=AgentTerminalStatus.SUCCESS,
        safe_result={"final_answer_available": True},
        terminal_event=_terminal_event(run, sequence=1, terminal_status=AgentTerminalStatus.SUCCESS),
    )
    with sqlite3.connect(path) as connection:
        # 仅临时测试库退回原两表结构；不接触用户 runtime 数据库。
        connection.execute("DROP TABLE agent_user_results")
        connection.execute("ALTER TABLE agent_runs DROP COLUMN document_id")
        connection.execute("ALTER TABLE agent_runs DROP COLUMN user_result_version")
    reopened = SQLiteAgentRunRepository(path)
    assert reopened.get_run(workspace_id="WS-A", run_id=run.run_id) == final
    with pytest.raises(AgentResultNotStoredError, match="未保存产品结果"):
        reopened.get_user_result(workspace_id="WS-A", run_id=run.run_id)
    new = _product_run(reopened)
    _save_product(reopened, new, _answer())
    assert reopened.get_user_result(workspace_id="WS-A", run_id=new.run_id).user_result == _answer()


def test_product_requires_result_and_consistent_execution_layer(tmp_path):
    """新 Run 不允许缺结果、非连续序号或执行失败却持久 answered。"""
    repository = SQLiteAgentRunRepository(tmp_path / "required.db")
    run = _product_run(repository)
    with pytest.raises(AgentResultIntegrityError):
        repository.finalize_run(
            workspace_id="WS-A", terminal_status=AgentTerminalStatus.SUCCESS,
            safe_result=None,
            terminal_event=_terminal_event(run, sequence=2, terminal_status=AgentTerminalStatus.SUCCESS),
        )
    with pytest.raises(AgentResultIntegrityError):
        _save_product(repository, run, _answer(), AgentTerminalStatus.PROVIDER_ERROR)
    event = _terminal_event(run, sequence=3, terminal_status=AgentTerminalStatus.SUCCESS)
    event.payload["user_result_status"] = "answered"
    with pytest.raises(RunEventSequenceError):
        repository.finalize_run(
            workspace_id="WS-A", terminal_status=AgentTerminalStatus.SUCCESS,
            safe_result={"user_result_status": "answered"}, terminal_event=event, user_result=_answer(),
        )
    assert repository.get_run(workspace_id="WS-A", run_id=run.run_id) == run


def test_result_serialization_ignores_hidden_attributes_and_rejects_bad_types(tmp_path):
    """显式白名单不会夹带对象附加属性；非法引用字段也不能落盘。"""
    path = tmp_path / "whitelist.db"
    repository = SQLiteAgentRunRepository(path)
    run = _product_run(repository)
    result = _answer()
    for key in ("messages", "prompt", "final_answer", "tool_output", "raw_error", "hidden_reasoning"):
        object.__setattr__(result, key, "FORBIDDEN_INTERNAL_PAYLOAD")
    _save_product(repository, run, result)
    assert b"FORBIDDEN_INTERNAL_PAYLOAD" not in path.read_bytes()
    second = _product_run(repository)
    malformed = AgentAnswer("正文[1]", (Citation(True, "demo.pdf", 1, "chunk-1"),))
    with pytest.raises(AgentResultIntegrityError):
        _save_product(repository, second, malformed)
    assert repository.get_run(workspace_id="WS-A", run_id=second.run_id) == second
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM agent_user_results WHERE run_id = ?", (second.run_id,),
        ).fetchone()[0] == 0
