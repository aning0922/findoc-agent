"""Rerun predecessor browsers without overwriting D8/D9/D10 evidence.

Only paths/stage names in ignored spec copies change; assertions stay intact.
Each suite has a new retained runtime and managed server processes.
"""

import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

product = Path.cwd().resolve()
if product != Path(__file__).resolve().parent.parent:
    raise RuntimeError("Run from the Analyst cwd")
frontend = product / "frontend"
output = product / "product/validation"
logs = output / "test-logs"
generated = frontend / "test-results/d13-product-harness"
generated.mkdir(parents=True, exist_ok=True)
suites = (
    (
        "product",
        "findoc-d11-d12-d13-product-",
        "FINDOC_D12_RUNTIME_ROOT",
        18083,
        14176,
        "tests.support.real_product_app:create_real_product_app",
        ["comparison-real.spec.ts"],
        "d13-product",
    ),
    (
        "legacy-product",
        "findoc-d11-d12-d13-legacy-",
        "FINDOC_D12_RUNTIME_ROOT",
        18084,
        14177,
        "tests.support.real_product_app:create_real_product_app",
        ["product-real.spec.ts"],
        "d13-legacy-product",
    ),
)
record = output / "d13-product-browser-record.json"
results = json.loads(record.read_text()) if sys.argv[1:] and record.exists() else []
if sys.argv[1:]:
    suites = tuple(s for s in suites if s[0] in sys.argv[1:])
    if not suites:
        raise ValueError("Unknown browser suite")
for name, prefix, root_env, api_port, web_port, factory, specs, stage in suites:
    for port in (api_port, web_port):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))  # Occupied ports abort; no unrelated process is killed.
    root = Path(tempfile.mkdtemp(prefix=prefix)).resolve()
    (product / f"data/30d-foundation/{stage}-runtime-path.txt").write_text(str(root))
    (output / f"{stage}-screenshots").mkdir(exist_ok=True)
    spec_paths = [frontend / "e2e" / filename for filename in specs]
    copied = []  # Actual source specs run directly; no relative-import copies.
    config = generated / f"{name}.config.mjs"
    report = output / f"d13-{name}-browser-results.json"
    config.write_text(
        "import { defineConfig, devices } from '@playwright/test';\nexport default defineConfig("
        + json.dumps(
            dict(
                testDir=str(frontend / "e2e"),
                testMatch=specs,
                workers=1,
                retries=0,
                timeout=90000,
                reporter=[["line"], ["json", dict(outputFile=str(report))]],
                outputDir=str(generated / f"{name}-artifacts"),
                use=dict(baseURL=f"http://127.0.0.1:{web_port}", trace="retain-on-failure"),
            )
        )
        + ");\n"
    )
    env = dict(
        os.environ,
        PYTHONDONTWRITEBYTECODE="1",
        FINDOC_E2E_DISABLE_ENV_FILES="1",
        FINDOC_E2E_STAGE=stage,
        FINDOC_PRODUCT_STAGE="d13" if name == "product" else "d13-legacy",
        FINDOC_EVIDENCE_STAGE=stage,
        FINDOC_API_ORIGIN=f"http://127.0.0.1:{api_port}",
    )
    for key in list(env):
        if key.startswith("LLM_") or key == "OPENAI_API_KEY":
            del env[key]
    env[root_env] = str(root)
    processes = []
    start = time.monotonic()
    with (
        (logs / f"d13-{name}-api.log").open("w") as api_log,
        (logs / f"d13-{name}-vite.log").open("w") as web_log,
        (logs / f"d13-{name}-browser.log").open("w") as browser_log,
    ):
        try:
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        factory,
                        "--factory",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(api_port),
                    ],
                    env=env,
                    stdout=api_log,
                    stderr=subprocess.STDOUT,
                )
            )
            processes.append(
                subprocess.Popen(
                    [
                        str(frontend / "node_modules/.bin/vite"),
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(web_port),
                        "--strictPort",
                    ],
                    cwd=frontend,
                    env=env,
                    stdout=web_log,
                    stderr=subprocess.STDOUT,
                )
            )
            for url in (f"http://127.0.0.1:{api_port}/health", f"http://127.0.0.1:{web_port}"):
                deadline = time.monotonic() + 600
                while True:
                    if any(p.poll() is not None for p in processes):
                        raise RuntimeError(f"{name} server exited; inspect logs")
                    try:
                        with urlopen(url, timeout=1) as response:
                            assert response.status == 200
                        break
                    except Exception:
                        if time.monotonic() > deadline:
                            raise RuntimeError(f"startup timed out: {url}")
                        time.sleep(0.5)
            copied = [
                dict(
                    source=str(p),
                    executed_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                    copied=False,
                )
                for p in spec_paths
            ]
            command = [
                str(frontend / "node_modules/.bin/playwright"),
                "test",
                "--config",
                str(config),
            ]
            code = subprocess.run(
                command, cwd=frontend, env=env, stdout=browser_log, stderr=subprocess.STDOUT
            ).returncode
            results.append(
                dict(
                    suite=name,
                    exit_code=code,
                    seconds=time.monotonic() - start,
                    runtime_root=str(root),
                    command=command,
                    report=str(report),
                    specs=copied,
                    human_acceptance="pending",
                    controlled_dependencies=True,
                )
            )
            (output / "d13-product-browser-record.json").write_text(
                json.dumps(results, indent=2, ensure_ascii=False) + "\n"
            )
            print(f"D13 {name}: exit {code}; retained runtime {root}", flush=True)
            if code:
                sys.exit(code)
        finally:
            for process in reversed(processes):
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
