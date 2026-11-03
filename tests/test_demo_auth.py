"""UNIT_FAKE: real control SQLite/HTTP boundary, no runtime/models/PDFs."""
import asyncio
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from app.demo.app import COOKIE, create_demo_app
from app.demo.config import DemoConfig, password_hash

ORIGIN = "http://testserver"
HEADERS = {"Origin": ORIGIN}
PASSWORD_HASH = password_hash("unit-password", iterations=100_000)


class FakeManager:
    handle = None
    def __init__(self):
        self.resets = []
    async def recover(self):
        pass
    async def reset(self, generation):
        await asyncio.sleep(0)
        self.resets.append(generation)
        self.handle = SimpleNamespace(generation=generation, seed_version="synthetic-unit-v1")
        return self.handle
    async def close(self):
        pass


def configuration(tmp_path, **kw):
    return DemoConfig(tmp_path / "control", tmp_path / "seed", "demo", PASSWORD_HASH,
                      (ORIGIN,), secure_cookie=False, **kw)


def op(**fields):
    return {"operation_id": str(uuid4()), **fields}


def attempt(client):
    payload = op(username="demo", password="unit-password")
    result = client.post("/demo/login", json=payload, headers=HEADERS)
    assert result.status_code == 202, result.text
    for _ in range(50):
        progress = client.get("/demo/operations/" + payload["operation_id"])
        if progress.json()["claimable"]:
            break
    result = client.post("/demo/claim", json=op(attempt_operation_id=payload["operation_id"]), headers=HEADERS)
    assert result.status_code == 200, result.text
    return result


def test_credentials_cookie_pending_claim_and_absolute_expiry(tmp_path):
    manager = FakeManager()
    app = create_demo_app(configuration(tmp_path), manager)
    with TestClient(app) as client:
        controller = app.state.demo_controller
        now = [1_800_000_000.0]
        controller.clock = lambda: now[0]
        bad = client.post("/demo/login", json=op(username="demo", password="wrong"), headers=HEADERS)
        assert bad.status_code == 401 and set(bad.json()["detail"]) == {"code", "message"}
        first = attempt(client)
        cookie = first.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=strict" in cookie
        assert first.json()["can_review"] is False
        now[0] += 30
        repeat = client.post("/demo/login", json=op(username="demo", password="unit-password"), headers=HEADERS)
        assert repeat.status_code == 200
        assert repeat.json()["expires_at"] == first.json()["expires_at"]
        assert "set-cookie" not in repeat.headers
        now[0] += 1200
        assert client.get("/demo/session").json()["detail"]["code"] == "expired"
        assert client.post("/documents", json={}, headers=HEADERS).status_code == 401
        assert len(manager.resets) >= 1


def test_operation_uuid_does_not_authorize_and_claim_is_single_use(tmp_path):
    app = create_demo_app(configuration(tmp_path), FakeManager())
    with TestClient(app) as client:
        login = op(username="demo", password="unit-password")
        assert client.post("/demo/login", json=login, headers=HEADERS).status_code == 202
        pending = client.cookies.get("findoc_demo_pending")
        for _ in range(50):
            state = client.get("/demo/operations/" + login["operation_id"]).json()
            if state["claimable"]:
                break
        client.cookies.clear()
        assert client.get("/demo/operations/" + login["operation_id"]).status_code == 401
        assert client.post("/demo/login", json=login, headers=HEADERS).status_code == 409
        client.cookies.set("findoc_demo_pending", pending, path="/demo")
        claim = op(attempt_operation_id=login["operation_id"])
        first = client.post("/demo/claim", json=claim, headers=HEADERS)
        assert first.status_code == 200
        assert client.post("/demo/claim", json=claim, headers=HEADERS).json()["expires_at"] == first.json()["expires_at"]
        client.cookies.delete(COOKIE)
        assert client.post("/demo/claim", json=claim, headers=HEADERS).status_code == 409
        assert client.post("/demo/claim", json=op(attempt_operation_id=login["operation_id"]), headers=HEADERS).status_code == 409


def test_boundary_strict_config_and_restart_fail_closed(tmp_path):
    config = configuration(tmp_path)
    with pytest.raises(ValueError):
        replace(config, ttl_minutes=21)
    app = create_demo_app(config, FakeManager())
    with TestClient(app) as client:
        assert client.post("/demo/login", json=op(username="demo", password="unit-password")).status_code == 403
        result = client.post("/demo/login", json=op(username="demo", password="secret-echo", ttl=30), headers=HEADERS)
        assert result.status_code == 422 and "secret-echo" not in result.text
        assert client.post("/demo/login", json=op(username="demo", password="x" * 17000), headers=HEADERS).status_code == 413
        now = [1_800_000_000.0]
        app.state.demo_controller.clock = lambda: now[0]
        abandoned = op(username="demo", password="unit-password")
        assert client.post("/demo/login", json=abandoned, headers=HEADERS).status_code == 202
        for _ in range(50):
            progress = client.get("/demo/operations/" + abandoned["operation_id"]).json()
            if progress["claimable"]:
                break
        now[0] += 301
        assert client.get("/demo/status").json()["service_state"] == "ready"
        assert client.post("/demo/claim", json=op(attempt_operation_id=abandoned["operation_id"]), headers=HEADERS).status_code == 409
        first = attempt(client)
        saved = client.cookies.get(COOKIE)
        assert set(client.get("/demo/status").json()) == {"schema_version", "service_state", "ttl_minutes", "conflict_policy"}
    with TestClient(create_demo_app(config, FakeManager())) as client:
        client.cookies.set(COOKIE, saved)
        assert client.get("/demo/session").status_code == 401
        assert first.json()["lease_generation"] == 2
