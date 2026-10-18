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
generated = frontend / "test-results/d14-harness"
generated.mkdir(parents=True, exist_ok=True)
suites = (
    (
        "financial",
        "findoc-d10-d14-regression-",
        "FINDOC_D10_RUNTIME_ROOT",
        18082,
        14175,
        "tests.support.real_financial_facts_app:create_real_financial_facts_app",
        ["financial-persistence-real.spec.ts", "financial-review-real.spec.ts"],
        "d14",
    ),
    (
        "evidence",
        "findoc-d8-d14-regression-",
        "FINDOC_D8_RUNTIME_ROOT",
        18081,
        14174,
        "tests.support.real_evidence_app:create_real_evidence_app",
        ["evidence-real.spec.ts", "evidence-races.spec.ts"],
        "d14-legacy-evidence",
    ),
    (
        "agent",
        "findoc-d14-agent-",
        "FINDOC_CONTROLLED_RUNTIME_ROOT",
        18080,
        14173,
        "tests.support.controlled_agent_app:create_controlled_agent_app_from_env",
        ["agent-create-refresh.spec.ts"],
        "d14-agent",
    ),
)
results = []
for name, prefix, root_env, api_port, web_port, factory, specs, stage in suites:
    for port in (api_port, web_port):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))  # Occupied ports abort; no unrelated process is killed.
    root = Path(tempfile.mkdtemp(prefix=prefix)).resolve()
    (product / f"data/30d-foundation/{stage}-runtime-path.txt").write_text(str(root))
    (output / f"{stage}-screenshots").mkdir(exist_ok=True)
    spec_dir = generated / name
    spec_dir.mkdir(exist_ok=True)
    copied = []
    for filename in specs:
        source = frontend / "e2e" / filename
        text = (
            source.read_text()
            .replace("d10-runtime-path.txt", "d14-runtime-path.txt")
            .replace("d10-screenshots", "d14-screenshots")
            .replace("d10-facts-browser-measurements.json", "d14-facts-browser-measurements.json")
            .replace("stage === 'd10'", "stage === 'd14'")
        )
        # Keep all predecessor assertions; their screenshots already exist at the D12 baseline.
        text = text.replace("await page.screenshot(", "await skipHistoricalScreenshot(")
        text += "\nasync function skipHistoricalScreenshot(_options: unknown) {}\n"
        destination = spec_dir / filename
        destination.write_text(text)
        copied.append(
            dict(
                source=str(source),
                original_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                copied_sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
            )
        )
    config = generated / f"{name}.config.mjs"
    report = output / f"d14-{name}-browser-results.json"
    config.write_text(
        "import { defineConfig, devices } from '@playwright/test';\nexport default defineConfig("
        + json.dumps(
            dict(
                testDir=str(spec_dir),
                testMatch="*.spec.ts",
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
        (logs / f"d14-{name}-api.log").open("w") as api_log,
        (logs / f"d14-{name}-vite.log").open("w") as web_log,
        (logs / f"d14-{name}-browser.log").open("w") as browser_log,
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
                deadline = time.monotonic() + 300
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
            (output / "d14-browser-regression-record.json").write_text(
                json.dumps(results, indent=2, ensure_ascii=False) + "\n"
            )
            print(f"D14 {name}: exit {code}; retained runtime {root}", flush=True)
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
