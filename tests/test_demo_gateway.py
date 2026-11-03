"""UNIT_FAKE: auth/CAS + fixed-generation proxy, no real model/runtime."""
import asyncio
from dataclasses import replace
from types import SimpleNamespace

from fastapi import HTTPException
from fastapi.testclient import TestClient
import httpx

from app.demo.app import COOKIE, create_demo_app
from app.demo.config import password_hash
from app.demo.gateway import stream_events
from tests.test_demo_auth import HEADERS, ORIGIN, attempt, configuration, op

OWNER_HASH = password_hash("unit-owner", iterations=100_000)


class HTTPManager:
    def __init__(self, root, handler=None):
        self.root, self.handler, self.handle = root, handler, None
        self.calls, self.clients = [], []
    async def recover(self):
        pass
    async def reset(self, generation):
        root = self.root / str(generation)
        root.mkdir(parents=True)
        async def handle(request):
            self.calls.append((generation, request))
            assert request.headers["X-Findoc-Internal-Secret"] == "server-secret"
            assert "cookie" not in request.headers and "authorization" not in request.headers
            if self.handler:
                return await self.handler(generation, root, request)
            return httpx.Response(200, json={"generation": generation, "calls": len(self.calls)})
        client = httpx.AsyncClient(base_url="http://127.0.0.1:12345", transport=httpx.MockTransport(handle), trust_env=False)
        self.clients.append(client)
        self.handle = SimpleNamespace(root=root, client=client, generation=generation,
                                      instance_id=str(generation), secret="server-secret", seed_version="synthetic-unit-v1")
        return self.handle
    async def close(self):
        for client in self.clients:
            await client.aclose()


async def async_login(client):
    payload = op(username="demo", password="unit-password")
    result = await client.post("/demo/login", json=payload, headers=HEADERS)
    assert result.status_code == 202, result.text
    for _ in range(500):
        state = (await client.get("/demo/operations/" + payload["operation_id"])).json()
        if state["claimable"]:
            break
        await asyncio.sleep(0.02)
    result = await client.post("/demo/claim", json=op(attempt_operation_id=payload["operation_id"]), headers=HEADERS)
    assert result.status_code == 200, result.text
    return result


def test_conflict_wait_only_and_concurrent_owner_takeover_cas(tmp_path):
    async def run():
        config = replace(configuration(tmp_path), owner_password_hash=OWNER_HASH, conflict_policy="takeover_enabled")
        manager = HTTPManager(tmp_path / "generations")
        app = create_demo_app(config, manager)
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with (httpx.AsyncClient(transport=transport, base_url=ORIGIN) as a,
                        httpx.AsyncClient(transport=transport, base_url=ORIGIN) as b,
                        httpx.AsyncClient(transport=transport, base_url=ORIGIN) as c):
                original = await async_login(a)
                wrong = await b.post("/demo/login", json=op(username="demo", password="bad"), headers=HEADERS)
                assert wrong.status_code == 401 and "generation" not in wrong.text
                conflict = await b.post("/demo/login", json=op(username="demo", password="unit-password"), headers=HEADERS)
                assert conflict.status_code == 423 and conflict.json()["detail"]["lease_generation"] == 1
                payload = op(username="demo", password="unit-password", owner_password="wrong", confirm=True, expected_generation=1)
                assert (await b.post("/demo/takeover", json=payload, headers=HEADERS)).status_code == 403
                payload["owner_password"] = "unit-owner"
                no_confirm = {**payload, "operation_id": op()["operation_id"], "confirm": False}
                assert (await b.post("/demo/takeover", json=no_confirm, headers=HEADERS)).status_code == 422
                outcomes = await asyncio.gather(
                    b.post("/demo/takeover", json=payload, headers=HEADERS),
                    c.post("/demo/takeover", json={**payload, "operation_id": op()["operation_id"]}, headers=HEADERS))
                assert sorted(r.status_code for r in outcomes) == [202, 409]
                assert (await a.get("/demo/session")).json()["detail"]["code"] == "taken_over"
                assert original.json()["lease_generation"] == 1
    asyncio.run(run())
    with TestClient(create_demo_app(configuration(tmp_path / "wait"), HTTPManager(tmp_path / "wait-gens"))) as client:
        attempt(client)
        payload = op(username="demo", password="unit-password", owner_password="unit-owner", confirm=True, expected_generation=1)
        assert client.post("/demo/takeover", json=payload, headers=HEADERS).json()["detail"]["code"] == "takeover_disabled"
        assert client.get("/demo/session").status_code == 200


def test_all_business_gate_owner_five_routes_idempotency_and_fixed_headers(tmp_path):
    manager = HTTPManager(tmp_path / "generations")
    config = replace(configuration(tmp_path), owner_password_hash=OWNER_HASH)
    app = create_demo_app(config, manager)
    with TestClient(app) as client:
        for path in ("/companies", "/documents/a/file", "/deep-research/jobs/a/events", "/health", "/openapi.json"):
            assert client.get(path).status_code == 401
        assert not manager.calls
        attempt(client)
        routes = ["/financial-facts/confirmations", "/financial-facts/persisted",
                  "/financial-facts/acceptances/receipt/revoke", "/revenue-research/confirmations",
                  "/research/tasks/task/resume", "/financial/extended-confirmations",
                  "/financial/extended-confirmations/receipt/revoke"]
        for path in routes:
            assert client.post(path, json=op(), headers=HEADERS).status_code == 403
        for path in ("/evaluations/runs", "/unknown-new-write", "/financial-facts/confirmations/"):
            assert client.post(path, json=op(), headers=HEADERS).status_code == 403
        payload = op(name="test")
        forwarded = {**HEADERS, "X-Findoc-Internal-Secret": "browser-forged", "Authorization": "browser-forged",
                     "X-Findoc-Owner-Authorized": "1", "X-Findoc-Owner-Expires-At": "2099-01-01T00:00:00Z",
                     "X-Findoc-Lease-Expires-At": "2099-01-01T00:00:00Z"}
        first = client.post("/companies", json=payload, headers=forwarded)
        assert first.status_code == 200, first.text
        assert "operation_id" not in manager.calls[-1][1].content.decode()
        assert "X-Findoc-Owner-Authorized" not in manager.calls[-1][1].headers
        assert "X-Findoc-Owner-Expires-At" not in manager.calls[-1][1].headers
        assert manager.calls[-1][1].headers["X-Findoc-Lease-Expires-At"] != "2099-01-01T00:00:00Z"
        assert client.post("/companies", json=payload, headers=forwarded).json() == first.json()
        assert len(manager.calls) == 1
        assert client.post("/companies", json={**payload, "name": "changed"}, headers=HEADERS).status_code == 409
        assert client.get("/demo/operations/" + payload["operation_id"]).json()["state"] == "completed"
        now = [1_800_000_000.0]
        app.state.demo_controller.clock = lambda: now[0]
        # Grant issuance before the real test lease expiry (epoch chosen below expiry).
        with app.state.demo_controller.store.tx() as db:
            db.execute("UPDATE sessions SET expires=?", (now[0] + 1200,))
            db.execute("UPDATE slot SET expires=?", (now[0] + 1200,))
        grant = op(owner_password="unit-owner", confirm=True)
        accepted = client.post("/demo/owner-authorize", json=grant, headers=HEADERS)
        assert accepted.status_code == 200 and client.get("/demo/session").json()["can_review"]
        for path in routes:
            assert client.post(path, json=op(), headers=HEADERS).status_code == 200
        now[0] += 301
        assert client.post("/demo/owner-authorize", json=grant, headers=HEADERS).status_code == 403
        for path in routes:
            assert client.post(path, json=op(), headers=HEADERS).status_code == 403


def test_late_pdf_and_sse_discarded_old_write_only_old_root(tmp_path):
    async def run():
        started, release = asyncio.Event(), asyncio.Event()
        async def handler(generation, root, request):
            if request.url.path == "/companies":
                started.set()
                await release.wait()
                (root / "late-write.txt").write_text("old-generation-only")
                return httpx.Response(200, content=b"%PDF-OLD-SECRET", headers={"content-type": "application/pdf"})
            return httpx.Response(200, json={"generation": generation})
        manager = HTTPManager(tmp_path / "generations", handler)
        config = replace(configuration(tmp_path), owner_password_hash=OWNER_HASH, conflict_policy="takeover_enabled")
        app = create_demo_app(config, manager)
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with (httpx.AsyncClient(transport=transport, base_url=ORIGIN) as a,
                        httpx.AsyncClient(transport=transport, base_url=ORIGIN) as b):
                await async_login(a)
                old_token = a.cookies.get(COOKIE)
                late = asyncio.create_task(a.post("/companies", json=op(name="late"), headers=HEADERS))
                await started.wait()
                taken = await b.post("/demo/takeover", json=op(username="demo", password="unit-password",
                    owner_password="unit-owner", confirm=True, expected_generation=1), headers=HEADERS)
                assert taken.status_code == 202
                for _ in range(500):
                    state = (await b.get("/demo/operations/" + taken.json()["operation_id"])).json()
                    if state["claimable"]:
                        break
                    await asyncio.sleep(0)
                assert (await b.post("/demo/claim", json=op(attempt_operation_id=taken.json()["operation_id"]), headers=HEADERS)).status_code == 200
                release.set()
                response = await late
                assert response.status_code == 401 and b"OLD-SECRET" not in response.content
                assert (manager.root / "1" / "late-write.txt").exists()
                assert not (manager.root / "2" / "late-write.txt").exists()
                class OldEvents:
                    status_code = 200
                    closed = False
                    async def aiter_bytes(self):
                        yield b"data: OLD-SECRET\n\n"
                    async def aclose(self):
                        self.closed = True
                source = OldEvents()
                events = [chunk async for chunk in stream_events(source, app.state.demo_controller,
                    old_token, 1, None, None, {})]
                assert not events and source.closed
                try:
                    app.state.demo_controller.fence(old_token, 1)
                except HTTPException as exc:
                    assert exc.detail["code"] == "taken_over"
                else:
                    raise AssertionError("Old fence unexpectedly passed")
    asyncio.run(run())


def test_owner_grant_expiring_during_body_read_never_dispatches(tmp_path):
    async def run():
        manager = HTTPManager(tmp_path / "generations")
        app = create_demo_app(replace(configuration(tmp_path), owner_password_hash=OWNER_HASH), manager)
        async with app.router.lifespan_context(app):
            controller = app.state.demo_controller
            now = [1_800_000_000.0]
            controller.clock = lambda: now[0]
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
                await async_login(client)
                assert (await client.post("/demo/owner-authorize", json=op(owner_password="unit-owner", confirm=True), headers=HEADERS)).status_code == 200
                class SlowBody(httpx.AsyncByteStream):
                    async def __aiter__(self):
                        yield b'{"operation_id":"'
                        now[0] += 301
                        await asyncio.sleep(0)
                        yield (op()["operation_id"] + '"}').encode()
                result = await client.post("/financial-facts/confirmations", content=SlowBody(),
                    headers={**HEADERS, "Content-Type": "application/json"})
                assert result.status_code == 403, result.text
                assert result.json()["detail"]["code"] == "owner_authorization_required"
                assert not manager.calls
    asyncio.run(run())
