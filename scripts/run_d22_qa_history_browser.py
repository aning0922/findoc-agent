"""Actual model save, process stop, DB-only restart and browser history/PDF recovery."""

import json
import shutil
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
out = root / "data/30d-foundation" / f"d22-qa-history-browser-{time.time_ns()}"
out.mkdir()
original_runtime = json.loads((root / "product/validation/d17-real-runtime.json").read_text())[
    "runtime_root"
]
runtime = tempfile.mkdtemp(prefix="findoc-d22-qa-history-browser-")
shutil.copy2(Path(original_runtime) / "documents.db", Path(runtime) / "documents.db")
shutil.copytree(Path(original_runtime) / "objects", Path(runtime) / "objects")
base = {k: v for k, v in os.environ.items() if not k.startswith("LLM_") and k != "OPENAI_API_KEY"}
base.update(
    FINDOC_RUNTIME_ROOT=runtime,
    FINDOC_E2E_DISABLE_ENV_FILES="1",
    OMP_NUM_THREADS="1",
    MKL_NUM_THREADS="1",
    VECLIB_MAXIMUM_THREADS="1",
    HF_HUB_OFFLINE="1",
    PYTHONDONTWRITEBYTECODE="1",
    FINDOC_API_ORIGIN="http://127.0.0.1:18100",
    D17_ARTIFACT_DIR=str(out),
)
generated = frontend / "test-results/d22-qa-history-harness"
generated.mkdir(parents=True, exist_ok=True)
original = frontend / "e2e/d17-history.spec.ts"
text = original.read_text()
for receiver in ("page", "list", "detail", "popup"):
    text = text.replace(f"await {receiver}.screenshot(", "await skipHistoricalScreenshot(")
text += "\nasync function skipHistoricalScreenshot(_options: unknown) {}\n"
(generated / original.name).write_text(text)
records = []
phases = [
    (
        "recovery",
        "app.api.research_history_app:create_history_app_from_env",
        ["d17-history.spec.ts"],
    )
]
if sys.argv[1:]:
    phases = [p for p in phases if p[0] in sys.argv[1:]]
for name, factory, specs in phases:
    for port in (18100, 14200):
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", port))
    env = dict(base)
    config = frontend / "test-results" / f"d22-{name}.config.mjs"
    config.write_text(
        'import { defineConfig } from "@playwright/test"; export default defineConfig('
        + json.dumps(
            dict(
                testDir=str(generated),
                testMatch=specs,
                workers=1,
                retries=0,
                timeout=180000,
                reporter=[["line"], ["json", {"outputFile": str(out / f"{name}-results.json")}]],
                outputDir=str(frontend / "test-results" / f"d22-{name}-{out.name}"),
                use=dict(
                    baseURL="http://127.0.0.1:14200", channel="chromium", trace="retain-on-failure"
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
                "18100",
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
                "14200",
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
        for url in ("http://127.0.0.1:18100/companies", "http://127.0.0.1:14200"):
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
        (root / "data/30d-foundation/d22-qa-history-browser-latest.json").write_text(
            json.dumps({"artifact_dir": str(out), "records": records}, indent=2) + "\n"
        )
    print(name, code, out, flush=True)
    if code:
        sys.exit(code)
