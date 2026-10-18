"""Chromium real v2 execution and independent history-only restart; no response substitutes."""

import json
import os
from pathlib import Path
import socket
import shutil
import tempfile
import subprocess
import sys
import time
from urllib.request import urlopen
from dotenv import dotenv_values

root = Path(__file__).resolve().parent.parent
frontend = root / "frontend"
proof = json.loads((root / "product/validation/d21-real-research.json").read_text())
runtime = proof["runtime_root"]
readonly = sys.argv[1:] == ["readonly"]
if readonly:
    prior = json.loads((root / "product/validation/d21-browser-record.json").read_text())
    results = [json.loads((Path(prior["artifacts"]) / (name + "-proof.json")).read_text())["result"]
               for name in ("company_period_change", "company_same_period_comparison")]
    copied = Path(tempfile.mkdtemp(prefix="findoc-d11-d21-history-"))
    shutil.copy2(Path(runtime) / "documents.db", copied / "documents.db")
    shutil.copytree(Path(runtime) / "objects", copied / "objects")
    (copied / "results.json").write_text(json.dumps(results, ensure_ascii=False))
    runtime = str(copied)
out = root / "data/30d-foundation" / f"d21-browser-{time.time_ns()}"
out.mkdir(parents=True)
base = dict(
    os.environ,
    PYTHONDONTWRITEBYTECODE="1",
    OMP_NUM_THREADS="1",
    MKL_NUM_THREADS="1",
    VECLIB_MAXIMUM_THREADS="1",
    HF_HUB_OFFLINE="1",
    FINDOC_E2E_DISABLE_ENV_FILES="1",
    FINDOC_D21_RUNTIME_ROOT=runtime,
    FINDOC_RUNTIME_ROOT=runtime,
    D21_ARTIFACT_DIR=str(out),
    FINDOC_API_ORIGIN="http://127.0.0.1:18090",
)
if readonly:
    base["D21_READONLY_RESULTS"] = str(Path(runtime) / "results.json")
api = dict(base)
for k, v in ({} if readonly else dotenv_values(root.parent / "findoc-rag/.env")).items():
    if k.startswith("LLM_") and v is not None:
        api[k] = v
api["LLM_TIMEOUT_SECONDS"] = "90"
config = frontend / "test-results/d21-live.config.mjs"
config.parent.mkdir(parents=True, exist_ok=True)
config.write_text(
    'import {defineConfig} from "@playwright/test";export default defineConfig('
    + json.dumps(
        dict(
            testDir=str(frontend / "e2e"),
            testMatch=["d21-readonly.spec.ts" if readonly else "d21-real.spec.ts"],
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
            "tests.support.d21_history_app:create_d21_history_app" if readonly else "tests.support.d21_live_app:create_d21_app",
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
    (root / ("product/validation/d21-readonly-browser-record.json" if readonly else "product/validation/d21-browser-record.json")).write_text(
        json.dumps(record, indent=2) + "\n"
    )
print((out / "browser.log").read_text()[-7000:])
sys.exit(code)
