"""Actual model save, process stop, DB-only restart and browser history/PDF recovery."""

import json
import tempfile
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

root = Path(__file__).resolve().parent.parent
frontend = root / "frontend"
out = (
    Path(os.environ["D20_REUSE_ARTIFACTS"])
    if "D20_REUSE_ARTIFACTS" in os.environ
    else root / "data/30d-foundation" / f"d22-operating-browser-{time.time_ns()}"
)
out.mkdir(exist_ok=True)
runtime = os.environ.get("D20_REUSE_RUNTIME") or tempfile.mkdtemp(prefix="findoc-d11-d20-browser-")
base = {k: v for k, v in os.environ.items() if not k.startswith("LLM_") and k != "OPENAI_API_KEY"}
base.update(
    FINDOC_D20_RUNTIME_ROOT=runtime,
    FINDOC_E2E_DISABLE_ENV_FILES="1",
    OMP_NUM_THREADS="1",
    MKL_NUM_THREADS="1",
    VECLIB_MAXIMUM_THREADS="1",
    HF_HUB_OFFLINE="1",
    PYTHONDONTWRITEBYTECODE="1",
    FINDOC_API_ORIGIN="http://127.0.0.1:18090",
    D20_ARTIFACT_DIR=str(out),
)
previous = (
    json.loads((out / "commands.json").read_text()) if (out / "commands.json").exists() else []
)
failed = [r for r in previous if r.get("exit_code") != 0]
if failed:
    (out / f"failed-attempts-{time.time_ns()}.json").write_text(json.dumps(failed, indent=2))
records = [r for r in previous if r.get("exit_code") == 0]
phases = [
    ("wait", "tests.support.d20_workbench_app:create_d20_app", ["d20-wait.spec.ts"]),
    (
        "recovery-resume",
        "tests.support.d20_workbench_app:create_d20_app",
        ["d20-workbench.spec.ts"],
    ),
    (
        "production-proof",
        "tests.support.d20_workbench_app:create_d20_app",
        ["d20-workbench.spec.ts"],
    ),
    ("screenshots", "tests.support.d20_workbench_app:create_d20_app", ["d20-screenshots.spec.ts"]),
    (
        "screenshots-final",
        "tests.support.d20_workbench_app:create_d20_app",
        ["d20-screenshots.spec.ts"],
    ),
    (
        "invalid-reasons",
        "tests.support.d20_workbench_app:create_d20_app",
        ["d20-invalid-reasons.spec.ts"],
    ),
]
if not sys.argv[1:]:
    phases = [
        p
        for p in phases
        if p[0] not in ("production-proof", "screenshots-final", "invalid-reasons")
    ]
if sys.argv[1:]:
    phases = [p for p in phases if p[0] in sys.argv[1:]]
for name, factory, specs in phases:
    for port in (18090, 14190):
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", port))
    for old_log in out.glob(f"{name}-*.log"):
        old_log.rename(old_log.with_name(f"retained-{time.time_ns()}-{old_log.name}"))
    env = dict(base)
    config = frontend / "test-results" / f"d20-{name}.config.mjs"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        'import { defineConfig } from "@playwright/test"; export default defineConfig('
        + json.dumps(
            dict(
                testDir=str(frontend / "e2e"),
                testMatch=specs,
                workers=1,
                retries=0,
                timeout=180000,
                reporter=[["line"], ["json", {"outputFile": str(out / f"{name}-results.json")}]],
                outputDir=str(frontend / "test-results" / f"d20-{name}-{out.name}"),
                use=dict(
                    baseURL="http://127.0.0.1:14190",
                    channel="chromium",
                    trace="retain-on-failure",
                    viewport=dict(width=1440, height=900),
                    actionTimeout=20000,
                ),
            )
        )
        + ");"
    )
    commands = [
        (
            [
                sys.executable,
                "-m",
                "uvicorn",
                factory,
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                "18090",
            ],
            root,
            env,
        ),
        (
            [
                str(frontend / "node_modules/.bin/vite"),
                "--host",
                "127.0.0.1",
                "--port",
                "14190",
                "--strictPort",
            ],
            frontend,
            base,
        ),
    ]
    procs, handles = [], []
    record = dict(phase=name, runtime_root=runtime, models_configured=name == "live", commands=[])
    records.append(record)
    try:
        for i, (cmd, cwd, proc_env) in enumerate(commands):
            log = (out / f"{name}-server-{i}.log").open("x")
            handles.append(log)
            proc = subprocess.Popen(
                cmd, cwd=cwd, env=proc_env, stdout=log, stderr=subprocess.STDOUT
            )
            procs.append(proc)
            record["commands"].append(
                dict(command=cmd, kind="server", log=str(out / f"{name}-server-{i}.log"))
            )
        for url in ("http://127.0.0.1:18090/companies", "http://127.0.0.1:14190"):
            deadline = time.monotonic() + 120
            while True:
                if any(p.poll() is not None for p in procs):
                    raise RuntimeError("server_exited")
                try:
                    with urlopen(url, timeout=2) as response:
                        assert response.status == 200
                    break
                except Exception:
                    if time.monotonic() > deadline:
                        raise RuntimeError("server_start_timeout") from None
                    time.sleep(0.3)
        cmd = [str(frontend / "node_modules/.bin/playwright"), "test", "--config", str(config)]
        if name == "production-proof":
            cmd += ["--grep", "正式UI及正式D19|无财报空状态"]
        with (out / f"{name}-browser.log").open("x") as log:
            code = subprocess.run(
                cmd, cwd=frontend, env=base, stdout=log, stderr=subprocess.STDOUT
            ).returncode
        record["commands"].append(dict(command=cmd, exit_code=code, kind="browser"))
        record["exit_code"] = code
    finally:
        for p in procs:
            p.terminate()
        for i, p in enumerate(procs):
            try:
                p.wait(timeout=15)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
            record["commands"][i]["exit_code"] = p.returncode
        for handle in handles:
            handle.close()
        (out / "commands.json").write_text(json.dumps(records, indent=2) + "\n")
        (root / "data/30d-foundation/d22-operating-browser-latest.json").write_text(
            json.dumps({"artifact_dir": str(out), "records": records}, indent=2) + "\n"
        )
    print(name, code, out, flush=True)
    if code:
        sys.exit(code)
