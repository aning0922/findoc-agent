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
output = product / "data/30d-foundation/d18-browser"
output.mkdir(parents=True, exist_ok=True)
logs = output / "test-logs"
logs.mkdir(parents=True, exist_ok=True)
generated = frontend / "test-results/d18-product-harness"
generated.mkdir(parents=True, exist_ok=True)
suites = (
    ("agent", "findoc-d18-agent-regression-", "FINDOC_CONTROLLED_RUNTIME_ROOT", 18088, 14181,
     "tests.support.controlled_agent_app:create_controlled_agent_app_from_env", ["agent-create-refresh.spec.ts"], "d18-agent"),
    ("comparison", "findoc-d11-d12-d18-comparison-", "FINDOC_D12_RUNTIME_ROOT", 18085, 14178,
     "tests.support.real_product_app:create_real_product_app", ["comparison-real.spec.ts"], "d18-comparison-product"),
    (
        "product",
        "findoc-d11-d12-d18-product-",
        "FINDOC_D12_RUNTIME_ROOT",
        18086,
        14179,
        "tests.support.real_product_app:create_real_product_app",
        ["charts-real.spec.ts"],
        "d18-product",
    ),
    (
        "legacy-product",
        "findoc-d11-d12-d18-legacy-",
        "FINDOC_D12_RUNTIME_ROOT",
        18084,
        14177,
        "tests.support.real_product_app:create_real_product_app",
        ["product-real.spec.ts"],
        "d18-legacy-product",
    ),
)
record = output / "d18-product-browser-record.json"
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
    spec_dir = generated / name
    spec_dir.mkdir(exist_ok=True)
    for source in spec_paths:
        text = source.read_text().replace("../src/", str(frontend / "src") + "/")
        text = text.replace("d14-product-runtime-path.txt", "d18-product-runtime-path.txt")
        text = text.replace("d14-chart-mappings.json", "d18-chart-mappings.json")
        text = text.replace("await page.screenshot(", "await skipHistoricalScreenshot(")
        text += "\nasync function skipHistoricalScreenshot(_options: unknown) {}\n"
        (spec_dir / source.name).write_text(text)
    copied = []
    config = generated / f"{name}.config.mjs"
    report = output / f"d18-{name}-browser-results.json"
    config.write_text(
        "import { defineConfig, devices } from '@playwright/test';\nexport default defineConfig("
        + json.dumps(
            dict(
                testDir=str(spec_dir),
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
        FINDOC_PRODUCT_STAGE="d18" if name == "product" else "d18-legacy",
        FINDOC_COMPARISON_STAGE="d18-comparison",
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
        (logs / f"d18-{name}-api.log").open("w") as api_log,
        (logs / f"d18-{name}-vite.log").open("w") as web_log,
        (logs / f"d18-{name}-browser.log").open("w") as browser_log,
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
                    original_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                    executed_sha256=hashlib.sha256((spec_dir / p.name).read_bytes()).hexdigest(),
                    copied=True,
                    changes="only import/output paths and skipped predecessor screenshots; assertions preserved",
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
            (output / f"d18-{name}-run-record.json").write_text(
                json.dumps(results[-1], indent=2, ensure_ascii=False) + "\n"
            )
            (output / "d18-product-browser-record.json").write_text(
                json.dumps(results, indent=2, ensure_ascii=False) + "\n"
            )
            print(f"D18 {name}: exit {code}; retained runtime {root}", flush=True)
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
            (output / f"d18-{name}-server-exits.json").write_text(json.dumps([p.returncode for p in processes]))
