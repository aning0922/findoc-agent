"""Isolated real-HTTP smoke; optional Chromium/Vite check, no real provider fees.

--engine real initializes cached real BGE/Milvus with a disabled loopback LLM
endpoint; it does not claim real PDF/LLM/finance acceptance. --frontend-root adds
Chromium/Vite two-context protocol checks for the FAKE child only.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

import httpx

from app.demo.config import password_hash
from app.demo.seed import build_synthetic_seed, verify_seed


def launch(command, env, cwd, log):
    return subprocess.Popen(command, env=env, cwd=cwd, stdin=subprocess.DEVNULL,
                            stdout=log, stderr=log, start_new_session=True)


def wait_http(url, process, timeout=15):
    deadline = time.monotonic() + timeout
    with httpx.Client(trust_env=False, timeout=1) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("HTTP process exited")
            try:
                if client.get(url).status_code < 500:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.05)
    raise RuntimeError("HTTP startup timeout")


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("fake", "real"), default="fake")
    parser.add_argument("--frontend-root", type=Path)
    parser.add_argument("--restart-check", action="store_true", help="Abrupt controller crash/restart (fake engine only)")
    args = parser.parse_args()
    if args.restart_check and (args.engine != "fake" or args.frontend_root):
        parser.error("Restart check requires --engine fake and no frontend-root")
    if args.frontend_root and args.engine != "fake":
        parser.error("Browser fixture requires --engine fake")
    project = Path(__file__).resolve().parents[1]
    evidence = Path(tempfile.mkdtemp(prefix="findoc-showcase-demo-check-")).resolve()
    seed, control = evidence / "seed", evidence / "control"
    _, digest = build_synthetic_seed(seed)
    backend_port, vite_port = free_port(), free_port()
    origin = f"http://127.0.0.1:{vite_port if args.frontend_root else backend_port}"
    username, password, owner = "isolated-check", secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    env = os.environ.copy()
    env.update({"DEMO_CONTROL_ROOT": str(control), "DEMO_SEED_ROOT": str(seed), "DEMO_USERNAME": username,
                "DEMO_PASSWORD_HASH": password_hash(password), "DEMO_OWNER_PASSWORD_HASH": password_hash(owner),
                "DEMO_ALLOWED_ORIGINS": origin, "DEMO_COOKIE_SECURE": "false", "DEMO_CONFLICT_POLICY": "takeover_enabled",
                "DEMO_CHILD_MODE": args.engine, "DEMO_CHILD_STARTUP_TIMEOUT": "90",
                "LLM_API_KEY": "disabled-isolated-test-only", "LLM_MODEL": "disabled-no-provider-calls",
                "LLM_BASE_URL": "http://127.0.0.1:9/v1", "LLM_TIMEOUT_SECONDS": "1",
                "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "TOKENIZERS_PARALLELISM": "false"})
    processes, result = [], None
    with (evidence / "http.log").open("wb") as log:
        try:
            backend = launch([sys.executable, "-m", "uvicorn", "app.demo.entrypoint:create_app", "--factory",
                              "--host", "127.0.0.1", "--port", str(backend_port), "--no-access-log"], env, project, log)
            processes.append(backend)
            wait_http(f"http://127.0.0.1:{backend_port}/demo/status", backend)
            if args.frontend_root:
                frontend = args.frontend_root.resolve()
                vite_env = {**env, "FINDOC_API_ORIGIN": f"http://127.0.0.1:{backend_port}", "FINDOC_E2E_DISABLE_ENV_FILES": "1"}
                vite = launch(["node", str(frontend / "node_modules/vite/bin/vite.js"), "--host", "127.0.0.1",
                               "--port", str(vite_port), "--strictPort"], vite_env, frontend, log)
                processes.append(vite)
                wait_http(origin, vite)
                browser_env = {**env, "DEMO_CHECK_FRONTEND_ROOT": str(frontend), "DEMO_CHECK_ORIGIN": origin,
                               "DEMO_CHECK_USERNAME": username, "DEMO_CHECK_PASSWORD": password,
                               "DEMO_CHECK_OWNER_PASSWORD": owner}
                checked = subprocess.run(["node", str(project / "scripts/showcase_demo_browser.mjs")],
                                         env=browser_env, cwd=project, capture_output=True, text=True, timeout=90)
                if checked.returncode:
                    # Browser script asserts status/payload only, never prints passwords/cookies.
                    (evidence / "browser-failure.txt").write_text(checked.stderr)
                    raise RuntimeError("Browser protocol check failed; inspect browser-failure.txt")
                result = json.loads(checked.stdout.strip().splitlines()[-1])
            else:
                started = time.monotonic()
                with httpx.Client(base_url=origin, trust_env=False, timeout=5, headers={"Origin": origin}) as client:
                    attempt = str(uuid4())
                    response = client.post("/demo/login", json={"operation_id": attempt, "username": username, "password": password})
                    assert response.status_code == 202
                    for _ in range(1000):
                        operation = client.get(f"/demo/operations/{attempt}").json()
                        if operation["claimable"]:
                            break
                        assert operation["state"] != "failed"
                        time.sleep(0.1)
                    claim = client.post("/demo/claim", json={"operation_id": str(uuid4()), "attempt_operation_id": attempt})
                    assert claim.status_code == 200, claim.text
                    companies = client.get("/companies")
                    assert companies.status_code == 200 and len(companies.json()) == 1
                    result = {"engine": args.engine, "evidence": "REAL_CACHED_BGE_MILVUS_SYNTHETIC_SEED" if args.engine == "real" else "HTTP_FAKE",
                              "elapsed_to_claim_seconds": round(time.monotonic() - started, 3),
                              "generation": claim.json()["lease_generation"], "companies": len(companies.json()),
                              "llm_requests": 0, "real_pdfs": 0, "checks": ["PASS pending→readiness→claim→business GET"]}
                    if args.restart_check:
                        previous = json.loads((control / "child.json").read_text())
                        backend.kill()  # Controller only; deliberately leave the independent child orphaned.
                        backend.wait(timeout=5)
                        replacement = launch([sys.executable, "-m", "uvicorn", "app.demo.entrypoint:create_app", "--factory",
                            "--host", "127.0.0.1", "--port", str(backend_port), "--no-access-log"], env, project, log)
                        processes.append(replacement)
                        wait_http(origin + "/demo/status", replacement)
                        assert client.get("/demo/session").status_code == 401
                        for _ in range(300):
                            status = client.get("/demo/status").json()["service_state"]
                            if status == "ready":
                                break
                            assert status != "degraded"
                            time.sleep(0.05)
                        assert status == "ready"
                        from app.demo.process import group_alive
                        assert not group_alive(previous["pgid"])
                        attempt = str(uuid4())
                        assert client.post("/demo/login", json={"operation_id": attempt, "username": username, "password": password}).status_code == 202
                        for _ in range(300):
                            progress = client.get(f"/demo/operations/{attempt}").json()
                            if progress["claimable"]:
                                break
                            assert progress["state"] != "failed"
                            time.sleep(0.05)
                        claimed = client.post("/demo/claim", json={"operation_id": str(uuid4()), "attempt_operation_id": attempt})
                        assert claimed.status_code == 200 and claimed.json()["lease_generation"] > claim.json()["lease_generation"]
                        assert len(client.get("/companies").json()) == 1
                        result["checks"].append("PASS controller SIGKILL/restart → verified orphan exit → cleanup → old cookie rejected → fresh lease")
            verify_seed(seed, digest)
            (evidence / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=3)
    print(json.dumps({"result": result, "evidence_directory": str(evidence)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
