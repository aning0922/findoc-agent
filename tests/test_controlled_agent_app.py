"""验证浏览器可启动的受控装配确实经过真实业务与临时 SQLite。"""

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from tests.support.controlled_agent_app import (
    CONTROLLED_DOCUMENT_ID,
    CONTROLLED_RUNTIME_ROOT_ENV,
    create_controlled_agent_app,
    create_controlled_agent_app_from_env,
)


def test_controlled_three_states_persist_and_reopen(tmp_path: Path) -> None:
    """三态经 POST 提交后可由新 app GET 读回，隔离目录包含四类资源。"""
    runtime_root = tmp_path / "controlled-runtime"
    app = create_controlled_agent_app(runtime_root)
    scenarios = (
        ("查询2025年度营业收入", "answered"),
        ("查询2025年度员工平均年龄", "refusal"),
        ("查询2025年度净利润", "system_error"),
    )
    created: list[dict[str, object]] = []
    with TestClient(app) as client:
        documents = client.get("/documents")
        assert documents.status_code == 200
        assert documents.json()[0]["document_id"] == CONTROLLED_DOCUMENT_ID
        for query, expected_status in scenarios:
            response = client.post(
                "/agent/runs",
                json={"document_id": CONTROLLED_DOCUMENT_ID, "query": query},
            )
            assert response.status_code == 201
            payload = response.json()
            assert payload["user_result"]["status"] == expected_status
            created.append(payload)

    reopened = create_controlled_agent_app(runtime_root)
    with TestClient(reopened) as client:
        for payload in created:
            run_id = payload["run_id"]
            assert client.get(f"/agent/runs/{run_id}").json() == payload
            events = client.get(f"/agent/runs/{run_id}/events")
            assert events.status_code == 200
            sequences = [event["sequence"] for event in events.json()["events"]]
            assert sequences == sorted(sequences)

    assert {path.name for path in runtime_root.iterdir()} == {
        "agent-runs.db", "documents.db", "milvus.db", "objects"
    }


def test_controlled_events_failure_does_not_break_saved_result(tmp_path: Path) -> None:
    """Events 读故障返回安全错误，同一 Run 的结果 GET 仍来自已提交记录。"""
    runtime_root = tmp_path / "controlled-runtime"
    with TestClient(create_controlled_agent_app(runtime_root)) as client:
        created = client.post(
            "/agent/runs",
            json={
                "document_id": CONTROLLED_DOCUMENT_ID,
                "query": "查询2025年度营业收入",
            },
        ).json()

    with TestClient(create_controlled_agent_app(runtime_root, fail_events=True)) as client:
        run_id = created["run_id"]
        assert client.get(f"/agent/runs/{run_id}").json() == created
        events = client.get(f"/agent/runs/{run_id}/events")
        assert events.status_code == 500
        assert events.json()["detail"]["code"] == "agent_storage_error"


def test_controlled_env_factory_requires_explicit_safe_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """uvicorn factory 没有显式隔离目录时立即失败，不回退用户 runtime。"""
    monkeypatch.delenv(CONTROLLED_RUNTIME_ROOT_ENV, raising=False)
    with pytest.raises(RuntimeError, match=CONTROLLED_RUNTIME_ROOT_ENV):
        create_controlled_agent_app_from_env()
