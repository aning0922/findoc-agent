"""One real browser path, using the existing isolated real-model runtime; no response fixtures."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
from dotenv import dotenv_values

root = Path(__file__).resolve().parent.parent
os.chdir(root)
frontend = root / "frontend"
output = root / "product/validation"
index = json.loads((output / "d16-real-index.json").read_text())
config = frontend / "test-results/d16-product-harness/live.config.mjs"
config.parent.mkdir(exist_ok=True, parents=True)
config.write_text(
    'import { defineConfig } from "@playwright/test"; export default defineConfig('
    + json.dumps(
        dict(
            testDir=str(frontend / "e2e"),
            testMatch=["d16-qa-live.spec.ts"],
            workers=1,
            retries=0,
            timeout=240000,
            reporter=[
                ["line"],
                ["json", dict(outputFile=str(output / "d16-live-browser-results.json"))],
            ],
            outputDir=str(frontend / "test-results/d16-live"),
            use=dict(baseURL="http://127.0.0.1:14190", trace="retain-on-failure", channel="chromium"),
        )
    )
    + ");\n"
)
for port in [18090, 14190]:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))
base = {k: v for k, v in os.environ.items() if not k.startswith("LLM_") and k != "OPENAI_API_KEY"}
base.update(
    PYTHONDONTWRITEBYTECODE="1",
    OMP_NUM_THREADS="1",
    MKL_NUM_THREADS="1",
    VECLIB_MAXIMUM_THREADS="1",
    HF_HUB_OFFLINE="1",
    FINDOC_E2E_DISABLE_ENV_FILES="1",
)
api_env = {
    **base,
    **{
        k: v
        for k, v in dotenv_values(root.parent / "findoc-rag/.env").items()
        if k.startswith("LLM_") and v is not None
    },
    "LLM_TIMEOUT_SECONDS": "120",
    "FINDOC_RUNTIME_ROOT": index["runtime_root"],
}
web_env = {**base, "FINDOC_API_ORIGIN": "http://127.0.0.1:18090"}
processes = []
started = time.monotonic()
command = [str(frontend / "node_modules/.bin/playwright"), "test", "--config", str(config)]
with (
    (output / "test-logs/d16-live-api.log").open("w") as api_log,
    (output / "test-logs/d16-live-vite.log").open("w") as web_log,
    (output / "test-logs/d16-live-browser.log").open("w") as log,
):
    try:
        processes.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.api.runtime_factory:create_isolated_runtime_app_from_env",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "18090",
                ],
                env=api_env,
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
                    "14190",
                    "--strictPort",
                ],
                cwd=frontend,
                env=web_env,
                stdout=web_log,
                stderr=subprocess.STDOUT,
            )
        )
        for url in ["http://127.0.0.1:18090/companies", "http://127.0.0.1:14190"]:
            until = time.monotonic() + 120
            while True:
                try:
                    with urlopen(url, timeout=2) as response:
                        assert response.status == 200
                    break
                except Exception:
                    if time.monotonic() > until:
                        raise RuntimeError("server startup failed")
                    time.sleep(0.5)
        code = subprocess.run(
            command, cwd=frontend, env=web_env, stdout=log, stderr=subprocess.STDOUT
        ).returncode
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
record = dict(
    command=command,
    exit_code=code,
    seconds=time.monotonic() - started,
    runtime_root=index["runtime_root"],
    actual_bge=True,
    actual_milvus=True,
    actual_llm=True,
    server_teardown_exit_codes=[p.returncode for p in processes],
)
(output / "d16-live-browser-record.json").write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps(record, indent=2))
sys.exit(code)
