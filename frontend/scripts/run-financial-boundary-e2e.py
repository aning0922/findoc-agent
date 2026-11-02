"""Real-PDF boundary E2E in a fresh simulated_test-only runtime.

Run from any directory with FINDOC_NODE24_BIN=/absolute/node24/bin .venv/bin/python
frontend/scripts/run-financial-boundary-e2e.py. The four fixed-SHA PDFs from
product/validation/sources.json must already exist under repository data/.
Outputs stay under a unique repository data directory; API runtime is /tmp.
No model execution or human acceptance is claimed.
"""

import os
import sys
import time
import json
import tempfile
import socket
import subprocess
import urllib.request
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
node = Path(os.environ["FINDOC_NODE24_BIN"]).resolve()
if not subprocess.check_output([str(node / "node"), "--version"], text=True).startswith("v24."):
    raise RuntimeError("This harness requires Node 24")
out = repo / "data" / ("ux-financial-boundary-" + time.strftime("%Y%m%d-%H%M%S"))
out.mkdir(exist_ok=False)
runtime = Path(tempfile.mkdtemp(prefix="findoc-d10-ux-boundary-", dir="/tmp"))
(out / "runtime-path.txt").write_text(str(runtime))


def port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


api, web = port(), port()
env = {k: v for k, v in os.environ.items() if not k.startswith("LLM_") and k != "OPENAI_API_KEY"}
env.update(
    PATH=str(node) + ":" + env["PATH"],
    FINDOC_D10_RUNTIME_ROOT=str(runtime),
    FINDOC_API_ORIGIN=f"http://127.0.0.1:{api}",
    FINDOC_E2E_DISABLE_ENV_FILES="1",
    FINDOC_E2E_STAGE="ux-boundary",
    FINDOC_FINANCIAL_RUNTIME_PATH_FILE=str(out / "runtime-path.txt"),
    FINDOC_FINANCIAL_SCREENSHOTS=str(out / "screenshots"),
    FINDOC_FINANCIAL_REVIEW_MEASUREMENTS=str(out / "review-measurements.json"),
    FINDOC_D10_MEASUREMENTS_FILE=str(out / "facts-measurements.json"),
)
(out / "screenshots").mkdir(exist_ok=True)
config = runtime / "playwright.config.mjs"
config.write_text(
    "import {defineConfig,devices} from "
    + json.dumps(str(repo / "frontend/node_modules/@playwright/test/index.mjs"))
    + ";\nexport default defineConfig("
    + json.dumps(
        dict(
            testDir=str(repo / "frontend/e2e"),
            testMatch=["financial-persistence-real.spec.ts", "financial-review-real.spec.ts"],
            fullyParallel=False,
            workers=1,
            retries=0,
            timeout=90000,
            reporter=[["line"], ["json", {"outputFile": str(out / "results.json")}]],
            outputDir=str(out / "test-results"),
            use={
                "baseURL": f"http://127.0.0.1:{web}",
                "browserName": "chromium",
                "viewport": {"width": 1440, "height": 900},
                "trace": "retain-on-failure",
            },
        )
    )
    + ");\n"
)
(out / "run-manifest.json").write_text(
    json.dumps(
        {
            "runtime": str(runtime),
            "api": api,
            "web": web,
            "node": str(node),
            "config": str(config),
            "simulation": "simulated_test",
            "real": ["PDF", "parser", "SQLite", "HTTP"],
            "substitutions": ["embedding", "vector index", "chunk IDs"],
        },
        indent=2,
    )
)
procs = []


def start(args, cwd, log):
    p = subprocess.Popen(
        args, cwd=cwd, env=env, stdout=open(out / log, "w"), stderr=subprocess.STDOUT
    )
    procs.append(p)
    return p


def ready(url, p, deadline=240):
    end = time.time() + deadline
    while time.time() < end:
        if p.poll() is not None:
            raise RuntimeError("server exited; inspect logs")
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("server readiness timeout")


try:
    p = start(
        [
            str(repo / ".venv/bin/python"),
            "-m",
            "uvicorn",
            "tests.support.real_financial_facts_app:create_real_financial_facts_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(api),
        ],
        repo,
        "api.log",
    )
    ready(f"http://127.0.0.1:{api}/health", p)
    print("API seeded", runtime, flush=True)
    p = start(
        [
            str(node / "node"),
            "node_modules/vite/bin/vite.js",
            "--host",
            "127.0.0.1",
            "--port",
            str(web),
            "--strictPort",
        ],
        repo / "frontend",
        "vite.log",
    )
    ready(f"http://127.0.0.1:{web}", p)
    result = subprocess.run(
        [
            str(node / "node"),
            "node_modules/@playwright/test/cli.js",
            "test",
            "--config",
            str(config),
        ],
        cwd=repo / "frontend",
        env=env,
    )
    sys.exit(result.returncode)
finally:
    for p in procs:
        p.terminate()
    for p in procs:
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
