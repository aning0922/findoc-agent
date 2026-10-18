"""Agent HTTP 合同集成：复用受控正式装配，真实业务链和临时文件 SQLite。

模型/embedding/Milvus/文档存储是替身；不是纯预设 HTTP 响应，也不证明真实模型质量。
"""

import asyncio
from contextvars import ContextVar
import sqlite3
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import HTTPException
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
import pytest

from app.agent.run_models import AgentTerminalStatus
from app.agent.run_service import AgentRunService
from app.agent.runtime import RUNTIME_AGENT_CONFIG_VERSION
from app.agent.sqlite_run_repository import SQLiteAgentRunRepository
from app.api.app import create_app
from app.documents.models import DocumentStatus
from app.rag.openai_compatible_llm import ModelCompletion
from tests.test_agent_runtime import _final, _record, _tool_call, runtime as runtime


QUERY = {"document_id": "lookup-A", "query": "查询2025年度营业收入"}
SECRET = "private-test-token /private/runtime.db SELECT secret raw-model-output"


def _refusal() -> ModelCompletion:
    """受控模型候选，须经真实业务验证才能形成产品拒答。"""
    return ModelCompletion(
        message={"role": "assistant", "content": '{"decision":"refuse"}'},
        finish_reason="stop",
    )


def _created(runtime: SimpleNamespace) -> dict:
    """执行一次真实 HTTP→runtime→SQLite，返回已提交的公开结果。"""
    with TestClient(runtime.app) as client:
        response = client.post("/agent/runs", json=QUERY)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("product_status", ["answered", "refusal", "system_error"])
def test_post_three_states_equal_get_after_repository_and_app_reopen(
    runtime: SimpleNamespace, product_status: str,
) -> None:
    """三态经过真实内核/验证/提交，重建仓储和 app 后 GET 原样读回且零生成。"""
    if product_status != "answered":
        runtime.milvus.search.return_value = [[]]
        runtime.model.complete.side_effect = [
            _tool_call(), _refusal() if product_status == "refusal" else _final(),
        ]
    created = _created(runtime)
    assert set(created) == {"run_id", "document_id", "user_result"}
    assert created["document_id"] == "server-doc-A"  # 来自核准记录，非 lookup-A。
    assert created["user_result"]["status"] == product_status
    expected_fields = {
        "answered": {"status", "content", "citations"},
        "refusal": {"status", "reason", "message"},
        "system_error": {"status", "error_code", "message"},
    }
    assert set(created["user_result"]) == expected_fields[product_status]
    calls = (runtime.model.complete.call_count, runtime.retrieve_spy.call_count)
    runtime.service._run_service = AgentRunService(
        repository=SQLiteAgentRunRepository(runtime.run_path),
        execution_config_version=RUNTIME_AGENT_CONFIG_VERSION,
    )
    reopened_app = create_app(
        runtime.module.app.state.agent_service._document_preparer._document_service,
        agent_service=runtime.service, agent_workspace_id="demo",
    )
    with TestClient(reopened_app) as client:
        response = client.get(f"/agent/runs/{created['run_id']}")
        events = client.get(f"/agent/runs/{created['run_id']}/events")
    assert response.status_code == 200
    assert response.json() == created
    assert events.status_code == 200
    assert (runtime.model.complete.call_count, runtime.retrieve_spy.call_count) == calls
    # 引用校验 system_error 也能对应执行层 success；API 不把它改成 answered。
    stored_run = runtime.run_repository.get_run(workspace_id="demo", run_id=created["run_id"])
    assert stored_run.terminal_status is AgentTerminalStatus.SUCCESS


@pytest.mark.parametrize("extra", [
    "workspace", "workspace_id", "role", "context", "messages", "filters",
    "tools", "max_steps", "step_budget",
])
def test_extra_control_fields_are_rejected_without_input_echo(
    runtime: SimpleNamespace, extra: str,
) -> None:
    """额外控制字段拒绝而非忽略，错误正文不回显其值，且零文档查询/模型/Run。"""
    with TestClient(runtime.app) as client:
        response = client.post("/agent/runs", json={**QUERY, extra: SECRET})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_agent_request"
    assert SECRET not in response.text
    runtime.document_repository.get.assert_not_called()
    runtime.model.complete.assert_not_called()
    runtime.run_repository.start_run.assert_not_called()


@pytest.mark.parametrize("field,value", [
    (field, value) for field in ("document_id", "query")
    for value in (None, 12, True, [], {}, "", " \n\t")
])
def test_input_requires_nonempty_strict_strings(
    runtime: SimpleNamespace, field: str, value: object,
) -> None:
    with TestClient(runtime.app) as client:
        response = client.post("/agent/runs", json={**QUERY, field: value})
    assert response.status_code == 422
    runtime.document_repository.get.assert_not_called()
    runtime.run_repository.start_run.assert_not_called()


def test_malformed_json_and_missing_fields_have_safe_validation_response(
    runtime: SimpleNamespace,
) -> None:
    with TestClient(runtime.app) as client:
        malformed = client.post(
            "/agent/runs", content='{"query": "' + SECRET,
            headers={"Content-Type": "application/json"},
        )
        missing = client.post("/agent/runs", json={"document_id": "A"})
    assert malformed.status_code == missing.status_code == 422
    assert malformed.json() == missing.json()
    assert SECRET not in malformed.text
    runtime.model.complete.assert_not_called()
    runtime.run_repository.start_run.assert_not_called()


def test_unsupported_query_is_persisted_capability_refusal_not_422(
    runtime: SimpleNamespace,
) -> None:
    runtime.model.complete.side_effect = [_refusal()]
    with TestClient(runtime.app) as client:
        response = client.post("/agent/runs", json={
            **QUERY, "query": "计算2025年度营业收入增长率",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["user_result"]["reason"] == "capability_limit"
        assert client.get(f"/agent/runs/{data['run_id']}").json() == data
    runtime.retrieve_spy.assert_not_called()
    assert runtime.model.complete.call_count == 1


@pytest.mark.parametrize("record,status_code", [
    (None, 404), (_record(workspace="other"), 404),
    *[(_record(status=status), 409) for status in DocumentStatus
      if status is not DocumentStatus.READY],
])
def test_document_preconditions_fail_before_execution(
    runtime: SimpleNamespace, record: object, status_code: int,
) -> None:
    runtime.document_repository.get.return_value = record
    with TestClient(runtime.app) as client:
        response = client.post("/agent/runs", json=QUERY)
    assert response.status_code == status_code
    runtime.model.complete.assert_not_called()
    runtime.retrieve_spy.assert_not_called()
    runtime.run_repository.start_run.assert_not_called()


@pytest.mark.parametrize("suffix", ["", "/events"])
def test_scope_and_absence_are_identical_and_client_cannot_select_workspace(
    runtime: SimpleNamespace, suffix: str,
) -> None:
    other = runtime.run_repository.start_run(
        workspace_id="other", execution_config_version="offline",
    )
    with TestClient(runtime.app) as client:
        missing = client.get(f"/agent/runs/missing{suffix}")
        outside = client.get(f"/agent/runs/{other.run_id}{suffix}")
        injected = client.request(
            "GET", f"/agent/runs/{other.run_id}{suffix}",
            params={"workspace_id": "other", "workspace": "other"},
            headers={"X-Workspace-ID": "other", "workspace": "other"},
            json={"workspace_id": "other"},
        )
    assert missing.status_code == outside.status_code == injected.status_code == 404
    assert missing.json() == outside.json() == injected.json()
    runtime.model.complete.assert_not_called()
    runtime.retrieve_spy.assert_not_called()


@pytest.mark.parametrize("state,expected_status,code", [
    ("running", 409, "agent_result_not_ready"),
    ("legacy", 409, "agent_result_not_stored"),
    ("missing_result", 500, "agent_result_integrity_error"),
    ("corrupt", 500, "agent_result_integrity_error"),
    ("version", 500, "agent_result_integrity_error"),
])
def test_persisted_read_states_have_distinct_safe_http_mapping(
    runtime: SimpleNamespace, state: str, expected_status: int, code: str,
) -> None:
    if state == "running":
        run_id = runtime.run_repository.start_run(
            workspace_id="demo", execution_config_version=RUNTIME_AGENT_CONFIG_VERSION,
            document_id="server-doc-A", user_result_version="agent-user-result-v1",
        ).run_id
    else:
        run_id = _created(runtime)["run_id"]
        with sqlite3.connect(runtime.run_path) as connection:
            if state in {"legacy", "missing_result"}:
                connection.execute("DELETE FROM agent_user_results WHERE run_id = ?", (run_id,))
            if state == "legacy":
                connection.execute(
                    "UPDATE agent_runs SET document_id = NULL, user_result_version = NULL "
                    "WHERE run_id = ?", (run_id,),
                )
            elif state == "corrupt":
                connection.execute(
                    "UPDATE agent_user_results SET payload_json = ? WHERE run_id = ?",
                    (SECRET, run_id),
                )
            elif state == "version":
                connection.execute(
                    "UPDATE agent_runs SET user_result_version = ? WHERE run_id = ?",
                    ("unsupported-version", run_id),
                )
    calls = (runtime.model.complete.call_count, runtime.retrieve_spy.call_count)
    with TestClient(runtime.app) as client:
        response = client.get(f"/agent/runs/{run_id}")
    assert response.status_code == expected_status
    assert response.json()["detail"]["code"] == code
    assert SECRET not in response.text
    assert (runtime.model.complete.call_count, runtime.retrieve_spy.call_count) == calls


def test_real_commit_failure_is_http_error_and_never_claims_saved(
    runtime: SimpleNamespace,
) -> None:
    """真实 SQLite 触发器拒绝写结果，HTTP 不发布内存答案且终结事务回滚。"""
    with sqlite3.connect(runtime.run_path) as connection:
        connection.execute("""CREATE TRIGGER deny_result BEFORE INSERT ON agent_user_results
            BEGIN SELECT RAISE(ABORT, 'private-test-token'); END""")
    with TestClient(runtime.app) as client:
        response = client.post("/agent/runs", json=QUERY)
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "agent_storage_error"
    assert "private-test-token" not in response.text
    assert "user_result" not in response.json()
    with sqlite3.connect(runtime.run_path) as connection:
        assert connection.execute("SELECT status FROM agent_runs").fetchall() == [("running",)]
        assert connection.execute("SELECT COUNT(*) FROM agent_user_results").fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM run_events WHERE event_type IN ('run_succeeded', 'run_failed')"
        ).fetchone()[0] == 0


@pytest.mark.parametrize("error", [RuntimeError(SECRET), HTTPException(500, SECRET)])
def test_unexpected_exception_does_not_echo_internal_details(
    runtime: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, error: Exception,
) -> None:
    """纯异常适配补充测试；不代替真实业务与数据库集成。"""
    monkeypatch.setattr(runtime.service, "run", AsyncMock(side_effect=error))
    with TestClient(runtime.app) as client:
        response = client.post("/agent/runs", json=QUERY)
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "agent_internal_error"
    assert SECRET not in response.text


def test_events_are_ordered_allowlisted_history_without_payload(
    runtime: SimpleNamespace,
) -> None:
    data = _created(runtime)
    with sqlite3.connect(runtime.run_path) as connection:
        connection.execute(
            "UPDATE run_events SET payload_json = ? WHERE run_id = ? AND sequence = 1",
            ('{"messages":"private-test-token","workspace_id":"other"}', data["run_id"]),
        )
    calls = (runtime.model.complete.call_count, runtime.retrieve_spy.call_count)
    with TestClient(runtime.app) as client:
        response = client.get(f"/agent/runs/{data['run_id']}/events")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"run_id", "projection", "events"}
    assert body["projection"] == "history"
    assert [event["sequence"] for event in body["events"]] == [1, 2, 3]
    assert [event["execution_event_type"] for event in body["events"]] == [
        "tool_requested", "tool_succeeded", "run_succeeded",
    ]
    assert all(set(event) == {"sequence", "execution_event_type", "summary"}
               for event in body["events"])
    assert "用户结果以结果接口为准" in body["events"][-1]["summary"]
    assert "private-test-token" not in response.text
    assert (runtime.model.complete.call_count, runtime.retrieve_spy.call_count) == calls


@pytest.mark.parametrize("operation", ["model", "finalize", "result", "events"])
def test_blocking_execution_commit_and_reads_leave_health_responsive(
    runtime: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, operation: str,
) -> None:
    """真实 Agent API 的受控屏障：health 必须在放行前响应，POST/GET 则仍等待。

    独立观察线程最终无条件释放，超时仅防止测试永久挂起，不依赖真实耗时或 sleep。
    与 test_event_loop_boundary 的正反对照共同构成调度证据。
    """
    run_id = _created(runtime)["run_id"] if operation in {"result", "events"} else None
    started, release, health_done = threading.Event(), threading.Event(), threading.Event()
    request_done = threading.Event()
    context_marker: ContextVar[str] = ContextVar("agent_api_test_marker", default="missing")
    observations: list[tuple[bool, bool, bool]] = []
    thread_contexts: list[str] = []
    owner, method = {
        "model": (runtime.model, "complete"),
        "finalize": (runtime.run_repository, "finalize_run"),
        "result": (runtime.run_repository, "get_user_result"),
        "events": (runtime.run_repository, "list_events"),
    }[operation]
    original = getattr(owner, method)

    def blocked(*args: object, **kwargs: object) -> object:
        thread_contexts.append(context_marker.get())
        started.set()
        if not release.wait(timeout=3):
            raise TimeoutError("测试控制器未释放工作线程")
        return original(*args, **kwargs)

    monkeypatch.setattr(owner, method, blocked)

    def observe_then_release() -> None:
        try:
            did_start = started.wait(timeout=2)
            healthy = health_done.wait(timeout=0.5)
            observations.append((did_start, healthy, request_done.is_set()))
        finally:
            release.set()

    async def scenario() -> None:
        token = context_marker.set("request-context")
        controller = threading.Thread(target=observe_then_release, daemon=True)
        controller.start()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=runtime.app), base_url="http://test",
            ) as client:
                async def request_work() -> None:
                    if operation in {"model", "finalize"}:
                        response = await client.post("/agent/runs", json=QUERY)
                        assert response.status_code == 201
                    else:
                        suffix = "/events" if operation == "events" else ""
                        response = await client.get(f"/agent/runs/{run_id}{suffix}")
                        assert response.status_code == 200
                    request_done.set()

                async def probe_health() -> None:
                    assert await asyncio.to_thread(started.wait, 2)
                    response = await client.get("/health")
                    assert response.status_code == 200
                    health_done.set()

                await asyncio.gather(request_work(), probe_health())
        finally:
            release.set()
            controller.join(timeout=2)
            context_marker.reset(token)

    asyncio.run(scenario())
    assert observations == [(True, True, False)]
    assert thread_contexts and set(thread_contexts) == {"request-context"}


def test_repeating_post_creates_distinct_runs(runtime: SimpleNamespace) -> None:
    """重复 finalize 冲突不是请求幂等；客户端重发确实会再次执行并创建 Run。"""
    runtime.model.complete.side_effect = [_tool_call(), _final(), _tool_call(), _final()]
    first, second = _created(runtime), _created(runtime)
    assert first["run_id"] != second["run_id"]
    assert first["user_result"] == second["user_result"]
    assert runtime.model.complete.call_count == 4


def test_optional_agent_dependency_and_required_server_scope(runtime: SimpleNamespace) -> None:
    """旧应用工厂不需要装配 Agent；启用 Agent 时必须由服务器显式配置查询范围。"""
    documents = runtime.service._document_preparer._document_service
    with TestClient(create_app(documents)) as client:
        assert client.get("/health").status_code == 200
        assert client.post("/agent/runs", json=QUERY).status_code == 503
        assert client.get("/agent/runs/any").status_code == 503
        assert client.get("/agent/runs/any/events").status_code == 503
    with pytest.raises(ValueError, match="服务端 workspace"):
        create_app(documents, agent_service=runtime.service)


@pytest.mark.parametrize("suffix", ["", "/events"])
def test_real_sqlite_read_failure_is_safe_and_does_not_execute(
    runtime: SimpleNamespace, suffix: str,
) -> None:
    """移除临时库的查询表制造真实数据库读错误，不调用模型进行补救。"""
    created = _created(runtime)
    calls = (runtime.model.complete.call_count, runtime.retrieve_spy.call_count)
    with sqlite3.connect(runtime.run_path) as connection:
        connection.execute("DROP TABLE agent_runs")
    with TestClient(runtime.app) as client:
        response = client.get(f"/agent/runs/{created['run_id']}{suffix}")
    assert response.status_code == 500
    assert response.json() == {"detail": {
        "code": "agent_storage_error", "message": "运行数据读写失败，无法确认本次操作完成",
    }}
    assert (runtime.model.complete.call_count, runtime.retrieve_spy.call_count) == calls
