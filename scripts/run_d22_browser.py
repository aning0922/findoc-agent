"""Chromium real v2 execution and independent history-only restart; no response substitutes."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

root = Path(__file__).resolve().parent.parent
frontend = root / "frontend"
proof = json.loads((root / "product/validation/d22-real-reports.json").read_text())
runtime = proof["runtime_root"]
out = root / "data/30d-foundation" / f"d22-browser-{time.time_ns()}"
out.mkdir(parents=True)
base = dict(
    os.environ,
    PYTHONDONTWRITEBYTECODE="1",
    OMP_NUM_THREADS="1",
    MKL_NUM_THREADS="1",
    VECLIB_MAXIMUM_THREADS="1",
    HF_HUB_OFFLINE="1",
    FINDOC_E2E_DISABLE_ENV_FILES="1",
    FINDOC_D22_RUNTIME_ROOT=runtime,
    FINDOC_RUNTIME_ROOT=runtime,
    D22_ARTIFACT_DIR=str(out),
    D22_PYTHON=sys.executable,
    D22_PRODUCT_ROOT=str(root),
    FINDOC_API_ORIGIN="http://127.0.0.1:18090",
)
base["D22_REPORT_PROOF"] = str(root / "product/validation/d22-real-reports.json")
api = dict(base)
for key in list(api):
    if key.startswith("LLM_") or key == "OPENAI_API_KEY":
        del api[key]
config = frontend / "test-results/d22-preview.config.mjs"
config.parent.mkdir(parents=True, exist_ok=True)
config.write_text(
    'import {defineConfig} from "@playwright/test";export default defineConfig('
    + json.dumps(
        dict(
            testDir=str(frontend / "e2e"),
            testMatch=["d22-reports.spec.ts"],
            workers=1,
            retries=0,
            timeout=180000,
            reporter=[["line"], ["json", dict(outputFile=str(out / "results.json"))]],
            outputDir=str(out / "trace"),
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
for port in (18090, 14190):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", port))
commands = [
    (
        [
            sys.executable,
            "-m",
            "uvicorn",
            "tests.support.d22_app:create_d22_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            "18090",
        ],
        root,
        api,
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
processes = []
logs = []
record = dict(
    runtime_root=runtime, artifacts=str(out), commands=[], actual_chromium=True, simulated_test=True
)
try:
    for n, (command, cwd, env) in enumerate(commands):
        log = (out / f"server-{n}.log").open("x")
        logs.append(log)
        processes.append(
            subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
        )
    for url in ("http://127.0.0.1:18090/companies", "http://127.0.0.1:14190"):
        deadline = time.monotonic() + 120
        while True:
            if any(p.poll() is not None for p in processes):
                raise RuntimeError("server_exited")
            try:
                with urlopen(url, timeout=2) as r:
                    assert r.status == 200
                break
            except Exception:
                if time.monotonic() > deadline:
                    raise RuntimeError("startup_timeout")
                time.sleep(0.5)
    command = [str(frontend / "node_modules/.bin/playwright"), "test", "--config", str(config)]
    with (out / "browser.log").open("x") as log:
        code = subprocess.run(
            command, cwd=frontend, env=base, stdout=log, stderr=subprocess.STDOUT
        ).returncode
    record["commands"].append(dict(command=command, exit_code=code))
finally:
    for p in processes:
        p.terminate()
    for p in processes:
        try:
            p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
    for log in logs:
        log.close()
    record["server_exit_codes"] = [p.returncode for p in processes]
    (root / "product/validation/d22-browser-record.json").write_text(
        json.dumps(record, indent=2) + "\n"
    )
print((out / "browser.log").read_text()[-7000:])
sys.exit(code)
