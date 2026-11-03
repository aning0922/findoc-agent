"""Bounded OS-process retirement and private readiness before generation publication."""
import asyncio
from dataclasses import dataclass
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import time
from uuid import uuid4

import httpx

from app.demo.seed import materialize, verify_seed, verify_materialized


@dataclass(frozen=True)
class RuntimeHandle:
    generation: int
    seed_version: str
    root: Path
    instance_id: str
    secret: str
    client: httpx.AsyncClient


def process_birth(pid: int) -> str | None:
    """OS start identity; never decide ownership from a live PID alone."""
    result = subprocess.run(["ps", "-p", str(pid), "-o", "lstart="], capture_output=True, text=True, check=False)
    return result.stdout.strip() or None


def group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # macOS can transiently answer EPERM while an owned, terminating group
        # disappears. Do not infer death from EPERM: independently inspect the
        # OS group inventory. An unreadable inventory remains alive/fail-closed.
        result = subprocess.run(["ps", "-axo", "pgid="], capture_output=True, text=True, check=False)
        if result.returncode:
            return True
        return str(pgid) in result.stdout.split()
    return True


class ProcessRuntimeManager:
    def __init__(self, config, *, child_mode="real", python=sys.executable, startup_timeout=90, stop_timeout=4,
                 retired_gc=False):
        if child_mode not in ("real", "fake"):
            raise ValueError("Invalid child mode")
        self.config, self.child_mode, self.python = config, child_mode, python
        self.startup_timeout, self.stop_timeout = startup_timeout, stop_timeout
        self.active = config.control_root / "active"
        self.active.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.active.is_symlink():
            raise ValueError("Active root cannot be a symlink")
        self.registry = config.control_root / "child.json"
        self.handle, self.process = None, None
        self.seed_error = None
        try:
            self.manifest, self.manifest_sha = verify_seed(config.seed_root)
        except Exception as exc:
            self.manifest, self.manifest_sha, self.seed_error = None, None, exc
        self._reset_lock = asyncio.Lock()
        self.last_readiness = None
        self.retired_gc = retired_gc
        self.last_gc_report = None

    def _remember_retired(self, record):
        if self.retired_gc:
            from app.demo.retired_gc import remember_retired
            remember_retired(self.config.control_root, record, self.manifest_sha)

    async def gc_retired_generations(self, *, dry_run=True, keep=1):
        async with self._reset_lock:
            return await self._gc_retired(dry_run=dry_run, keep=keep)

    async def _gc_retired(self, *, dry_run=True, keep=1):
        from app.demo.retired_gc import collect_retired
        current = self.handle.root if self.handle else None
        report = await asyncio.to_thread(
            collect_retired, self.config.control_root, self.config.seed_root, current,
            process_birth=process_birth, group_alive=group_alive, dry_run=dry_run, keep=keep,
        )
        self.last_gc_report = report
        return report

    async def recover(self):
        # Registry stores PID + birth identity, no reusable auth secret; old endpoint is not reused.
        if self.registry.exists():
            record = json.loads(self.registry.read_text())
            await self._retire_record(record)
            self._remember_retired(record)
            self.registry.unlink()
        if self.seed_error:
            raise RuntimeError("Invalid seed; remain degraded until repaired and restarted") from self.seed_error

    async def _retire_record(self, record):
        pid, pgid, birth = record["pid"], record["pgid"], record["birth"]
        if pid != pgid or not isinstance(pid, int) or pid <= 1 or not birth:
            raise RuntimeError("Invalid child process identity")
        if self.process and self.process.pid == pid:
            self.process.poll()
        current_birth = await asyncio.to_thread(process_birth, pid)
        if current_birth is not None and current_birth != birth:
            # PID reused: never signal this unrelated process or its group.
            raise RuntimeError("Child PID reused; operator must resolve orphan state")
        if current_birth is None and not group_alive(pgid):
            return
        if current_birth is None:
            # Leader gone with members left: cannot re-establish group identity safely after restart.
            raise RuntimeError("Unverified orphan process group")
        try:
            current_group = os.getpgid(pid)
        except ProcessLookupError:
            if not group_alive(pgid):
                return
            raise RuntimeError("Unverified orphan process group") from None
        if current_group != pgid:
            raise RuntimeError("Child process group identity changed")
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + self.stop_timeout
        while time.monotonic() < deadline:
            if self.process and self.process.pid == pid:
                self.process.poll()  # reap the leader while waiting for the whole group.
            if not group_alive(pgid):
                return
            await asyncio.sleep(0.05)
        # Recheck leader identity; allow absent leader only while we own this live Popen object.
        current_birth = await asyncio.to_thread(process_birth, pid)
        if current_birth != birth and not (current_birth is None and self.process and self.process.pid == pid):
            raise RuntimeError("Cannot verify child identity before SIGKILL")
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + self.stop_timeout
        while time.monotonic() < deadline:
            if self.process and self.process.pid == pid:
                self.process.poll()
            if not group_alive(pgid):
                return
            await asyncio.sleep(0.05)
        raise RuntimeError("Old child group did not exit")

    async def _stop(self):
        old_handle = self.handle
        self.handle = None
        try:
            if self.registry.exists():
                record = json.loads(self.registry.read_text())
                await self._retire_record(record)
                self._remember_retired(record)
                self.registry.unlink()
            if self.process:
                self.process.poll()
                self.process = None
        finally:
            if old_handle:
                await old_handle.client.aclose()

    async def reset(self, generation):
        async with self._reset_lock:
            await self._stop()
            if self.seed_error:
                raise RuntimeError("Invalid seed") from self.seed_error
            root = self.active / str(generation)
            # Copy/hash can take time, and must not monopolize the controller event loop.
            await asyncio.to_thread(materialize, self.config.seed_root, root, self.manifest_sha)
            instance, secret = str(uuid4()), secrets.token_urlsafe(48)
            # Bind socket in parent, inherit it: no free-port race or external binding.
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.bind(("127.0.0.1", 0))
            listener.listen(128)
            port = listener.getsockname()[1]
            env = os.environ.copy()
            # Owner/shared credentials never reach the business runtime, fake or real.
            for key in list(env):
                if key.startswith("DEMO_"):
                    env.pop(key, None)
                if self.child_mode == "fake" and any(word in key.upper() for word in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
                    env.pop(key, None)
            env.update({"FINDOC_RUNTIME_ROOT": str(root), "DEMO_INTERNAL_GENERATION": str(generation),
                        "DEMO_INTERNAL_INSTANCE": instance, "DEMO_INTERNAL_SECRET": secret,
                        "DEMO_INTERNAL_MANIFEST_SHA": self.manifest_sha, "DEMO_CHILD_MODE": self.child_mode})
            project_root = Path(__file__).resolve().parents[2]
            # No .env loading, no shell, no key/secret in command line or access log.
            command = [str(self.python), "-m", "uvicorn", "app.demo.child:create_child_app", "--factory",
                       "--fd", str(listener.fileno()), "--no-access-log", "--log-level", "warning"]
            log_path = root / "child.log"
            try:
                with log_path.open("wb") as log:
                    log_path.chmod(0o600)
                    self.process = subprocess.Popen(command, cwd=project_root, env=env, stdin=subprocess.DEVNULL,
                                                    stdout=log, stderr=log, start_new_session=True,
                                                    pass_fds=(listener.fileno(),))
                birth = process_birth(self.process.pid)
                if not birth:
                    raise RuntimeError("Child exited before process identity capture")
                record = {"pid": self.process.pid, "pgid": self.process.pid, "birth": birth,
                          "instance_id": instance, "generation": generation}
                temporary = self.registry.with_suffix(".tmp")
                temporary.write_text(json.dumps(record))
                temporary.chmod(0o600)
                temporary.replace(self.registry)
            finally:
                listener.close()
            client = httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", trust_env=False,
                                       follow_redirects=False, timeout=httpx.Timeout(260, connect=3))
            handle = RuntimeHandle(generation, self.manifest["seed_version"], root, instance, secret, client)
            try:
                deadline = time.monotonic() + self.startup_timeout
                headers = {"X-Findoc-Internal-Secret": secret, "X-Findoc-Generation": str(generation),
                           "X-Findoc-Instance": instance}
                while time.monotonic() < deadline:
                    if self.process.poll() is not None:
                        raise RuntimeError("Child startup failed")
                    try:
                        response = await client.get("/internal/demo-readiness", headers=headers, timeout=2)
                        if response.status_code == 200:
                            ready = response.json()
                            expected_probe = await asyncio.to_thread(verify_materialized, root, self.manifest)
                            if (ready.get("ready") is not True or ready.get("instance_id") != instance or
                                    ready.get("generation") != generation or ready.get("manifest_sha256") != self.manifest_sha or
                                    ready.get("seed_version") != self.manifest["seed_version"] or ready.get("engine") != self.child_mode or
                                    any(ready.get(k) != v for k, v in expected_probe.items())):
                                raise RuntimeError("Child readiness identity/probe mismatch")
                            self.last_readiness = ready
                            self.handle = handle
                            if self.retired_gc:
                                try:
                                    await self._gc_retired(dry_run=False, keep=1)
                                except (OSError, ValueError):
                                    # Cleanup may fail closed without invalidating a ready runtime.
                                    self.last_gc_report = {"dry_run": False, "deleted": [], "error": "gc_refused"}
                            return handle
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.1)
                raise RuntimeError("Child readiness timed out")
            except BaseException:
                await client.aclose()
                await self._stop()
                raise

    async def close(self):
        await self._stop()
