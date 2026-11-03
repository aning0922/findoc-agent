"""Real OS children + synthetic SQLite seed, FAKE engine; no original data/providers."""
import asyncio
from dataclasses import replace
import json
import os
import sqlite3

import httpx
import pytest

from app.demo.app import create_demo_app
from app.demo.process import ProcessRuntimeManager, group_alive
from app.demo.seed import build_synthetic_seed, materialize, verify_seed
from tests.test_demo_auth import HEADERS, configuration, op
from tests.test_demo_gateway import OWNER_HASH, async_login


def seed_for(tmp_path):
    root = tmp_path / "seed"
    manifest, digest = build_synthetic_seed(root)
    return root, manifest, digest


def test_seed_is_readonly_checked_fresh_and_not_full_product_seed(tmp_path):
    seed, manifest, digest = seed_for(tmp_path)
    assert manifest["complete_product_seed"] is False
    assert manifest["sqlite"][0]["tables"]["companies"] == 1
    active = tmp_path / "active"
    active.mkdir()
    materialize(seed, active / "1", digest)
    assert (active / "1" / "documents.db").stat().st_nlink == 1
    with pytest.raises(FileExistsError):
        materialize(seed, active / "1", digest)
    obj = seed / "objects" / "mechanism-note.txt"
    obj.chmod(0o600)
    obj.write_text("tampered")
    obj.chmod(0o400)
    with pytest.raises(ValueError, match="checksum"):
        verify_seed(seed, digest)
    # A manifest entry pointing outside or via symlink is never accepted.
    obj.parent.chmod(0o700)
    obj.unlink()
    obj.symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError):
        verify_seed(seed, digest)


def test_group_permission_probe_requires_independent_exit_evidence(monkeypatch):
    from types import SimpleNamespace
    from app.demo import process

    def denied(*_):
        raise PermissionError("transient OS probe refusal")

    monkeypatch.setattr(process.os, "killpg", denied)
    monkeypatch.setattr(process.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout="123\n456\n"))
    assert process.group_alive(123)
    assert not process.group_alive(789)
    monkeypatch.setattr(process.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=1, stdout=""))
    assert process.group_alive(789)  # Unverifiable is not a proof of termination.


def test_real_process_fake_engine_secret_readiness_and_fresh_generation(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_PASSWORD_HASH", "test-only-placeholder-not-used-for-config")
    seed, manifest, _ = seed_for(tmp_path)
    async def run():
        config = replace(configuration(tmp_path), seed_root=seed, owner_password_hash=OWNER_HASH)
        manager = ProcessRuntimeManager(config, child_mode="fake", startup_timeout=15)
        app = create_demo_app(config, manager)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
                await async_login(client)
                first = manager.handle
                record = json.loads(manager.registry.read_text())
                assert manager.last_readiness["engine"] == "fake"
                assert manager.last_readiness["sqlite_counts"]["documents.db"]["companies"] == 1
                async with httpx.AsyncClient(base_url=first.client.base_url, trust_env=False) as direct:
                    for path in ("/companies", "/health", "/internal/demo-readiness", "/documents/x/file"):
                        assert (await direct.get(path)).status_code == 403
                    headers = {"X-Findoc-Internal-Secret": first.secret, "X-Findoc-Generation": "999", "X-Findoc-Instance": first.instance_id}
                    assert (await direct.get("/companies", headers=headers)).status_code == 403
                wrong_identity = {**record, "birth": "different-process-birth"}
                manager.registry.write_text(json.dumps(wrong_identity))
                with pytest.raises(RuntimeError, match="PID reused"):
                    await ProcessRuntimeManager(config, child_mode="fake").recover()
                assert manager.process.poll() is None  # Reused/unverified PID was never signalled.
                manager.registry.write_text(json.dumps(record))
                with sqlite3.connect(first.root / "documents.db") as db:
                    db.execute("UPDATE companies SET name='DIRTY VISITOR CHANGE'")
                second = await manager.reset(2)
                assert not group_alive(record["pgid"])
                assert first.root != second.root and first.root.exists()
                with sqlite3.connect(second.root / "documents.db") as db:
                    assert db.execute("SELECT name FROM companies").fetchone()[0] != "DIRTY VISITOR CHANGE"
                assert (seed / "documents.db").stat().st_mode & 0o222 == 0
        assert manager.handle is None and not manager.registry.exists()
    asyncio.run(run())


def test_failed_reset_and_restart_retire_old_group_fail_closed(tmp_path):
    seed, _, _ = seed_for(tmp_path)
    async def run():
        config = replace(configuration(tmp_path), seed_root=seed)
        manager = ProcessRuntimeManager(config, child_mode="fake", startup_timeout=15)
        app = create_demo_app(config, manager)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
                await async_login(client)
                old = manager.handle
                record = json.loads(manager.registry.read_text())
                # Simulate controller process lost ownership; a replacement manager must verify PID birth before retiring it.
                recovering = ProcessRuntimeManager(config, child_mode="fake", startup_timeout=15)
                reaper = asyncio.create_task(asyncio.to_thread(manager.process.wait))
                await recovering.recover()
                # Original controller is in-process in this test; reap as init would after a real crash.
                await reaper
                assert not group_alive(record["pgid"])
                manager.handle = None
                await old.client.aclose()
                # Source corruption after initial pin must fail and never activate a new lease.
                obj = seed / "objects" / "mechanism-note.txt"
                obj.chmod(0o600)
                obj.write_text("broken")
                obj.chmod(0o400)
                controller = app.state.demo_controller
                controller._begin_cleanup()
                await controller.reset_task
                assert controller.status()["service_state"] == "degraded"
                assert (await client.get("/companies")).status_code != 200
                with controller.store.tx() as db:
                    assert db.execute("SELECT state FROM slot").fetchone()[0] == "degraded"
        assert not os.path.exists(config.control_root / "child.json")
        # A corrupt seed at controller startup keeps a reachable degraded status API.
        broken = create_demo_app(config, ProcessRuntimeManager(config, child_mode="fake"))
        async with broken.router.lifespan_context(broken):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=broken), base_url="http://testserver") as client:
                assert (await client.get("/demo/status")).json()["service_state"] == "degraded"
                failed = await client.post("/demo/login", json=op(username="demo", password="unit-password"), headers=HEADERS)
                assert failed.status_code == 503
    asyncio.run(run())
