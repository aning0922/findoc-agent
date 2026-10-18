"""Migrate all 18 predecessor financial checks without touching old evidence.

Real formal React, HTTP, fixed-SHA PDFs and SQLite; simulated_test only.
--before executes the unmodified fixed-base specs with only path relocation.
"""

import argparse
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

BASE = "cb55b8a72a5f9de1caa45c21534acb006710e5da"


def main():
    product = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--before", action="store_true")
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    frontend = product / "frontend"
    generated = frontend / "test-results" / out.name
    generated.mkdir(parents=True, exist_ok=False)
    runtime = Path(tempfile.mkdtemp(prefix="findoc-d10-s6-financial-"))
    stage = f"s6-financial-{out.name}"
    (product / "data/30d-foundation").mkdir(parents=True, exist_ok=True)
    (product / f"data/30d-foundation/{stage}-runtime-path.txt").write_text(str(runtime))
    screenshots = out / "screenshots"
    screenshots.mkdir()
    specs = ["financial-persistence-real.spec.ts", "financial-review-real.spec.ts"]
    provenance = []
    for name in specs + ([] if args.before else ["financial-review-helpers.ts"]):
        source = frontend / "e2e" / name
        original = subprocess.check_output(["git", "show", f"{BASE}:frontend/e2e/{name}"], cwd=product) if args.before else source.read_bytes()
        content = original.decode().replace("d10-runtime-path.txt", f"{stage}-runtime-path.txt")
        content = content.replace("stage === 'd10'", f"stage === '{stage}'")
        content = content.replace("`../product/validation/${stage}-screenshots`", json.dumps(str(screenshots)))
        content = content.replace("../product/validation/d10-screenshots", str(screenshots))
        content = content.replace("`../product/validation/${stage}-review-browser-measurements.json`", json.dumps(str(out / "review-measurements.json")))
        (generated / name).write_text(content)
        provenance.append(dict(file=name, source_sha256=hashlib.sha256(original).hexdigest(), executed_sha256=hashlib.sha256(content.encode()).hexdigest()))
    ports = []
    for _ in range(2):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            ports.append(sock.getsockname()[1])
    api_origin, web_origin = [f"http://127.0.0.1:{p}" for p in ports]
    config = generated / "config.mjs"
    config.write_text('import {defineConfig} from "@playwright/test";export default defineConfig(' + json.dumps(dict(
        testDir=str(generated), testMatch=specs, workers=1, retries=0, timeout=90000,
        reporter=[["line"], ["json", dict(outputFile=str(out / "results.json"))]],
        outputDir=str(out / "traces"), use=dict(baseURL=web_origin, trace="retain-on-failure", actionTimeout=20000, viewport=dict(width=1440, height=900)),
    )) + ');')
    env = {k: v for k, v in os.environ.items() if not k.startswith("LLM_") and k != "OPENAI_API_KEY"}
    env.update(FINDOC_D10_RUNTIME_ROOT=str(runtime), FINDOC_E2E_STAGE=stage,
        FINDOC_E2E_DISABLE_ENV_FILES="1", FINDOC_API_ORIGIN=api_origin,
        FINDOC_D10_MEASUREMENTS_FILE=str(out / "facts-measurements.json"),
        D26_LEGACY_ROOT=str(runtime), D26_LEGACY_FACTORY="tests.support.real_financial_facts_app:create_real_financial_facts_app",
        PYTHONDONTWRITEBYTECODE="1", HF_HUB_OFFLINE="1")
    node = os.environ["FINDOC_NODE"]
    commands = [([sys.executable, "-m", "uvicorn", "scripts.run_d26_legacy_browser:guarded_factory", "--factory", "--host", "127.0.0.1", "--port", str(ports[0])], product),
        ([node, str(frontend / "node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", str(ports[1]), "--strictPort"], frontend)]
    processes, handles = [], []
    record = dict(base_sha=BASE, source_ref=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=product, text=True).strip(),
        before=args.before, runtime_root=str(runtime), api_origin=api_origin, web_origin=web_origin,
        actual_http=True, actual_pdf=True, actual_sqlite=True, actual_formal_react=True,
        simulated_test=True, human_acceptances=0, actual_llm=False, actual_bge=False, actual_milvus=False,
        d25_runtime_accessed=False, service_connections_blocked=True, foreign_sqlite_blocked=True, protected_worktrees_blocked=True,
        specs=provenance, exit_code=1)
    try:
        for index, (command, cwd) in enumerate(commands):
            handle = (out / f"server-{index}.log").open("w")
            handles.append(handle)
            processes.append(subprocess.Popen(command, cwd=cwd, env=env, stdout=handle, stderr=subprocess.STDOUT))
        for url in [api_origin + "/health", web_origin]:
            deadline = time.monotonic() + 180
            while True:
                if any(p.poll() is not None for p in processes):
                    raise RuntimeError("server exited; inspect preserved logs")
                try:
                    with urlopen(url, timeout=1) as response:
                        assert response.status == 200
                    break
                except Exception:
                    if time.monotonic() > deadline:
                        raise RuntimeError("server startup timeout")
                    time.sleep(0.3)
        command = [node, str(frontend / "node_modules/@playwright/test/cli.js"), "test", "--config", str(config)]
        record["command"] = command
        with (out / "browser.log").open("w") as log:
            record["exit_code"] = subprocess.run(command, cwd=frontend, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for handle in handles:
            handle.close()
        record["servers_stopped"] = all(p.poll() is not None for p in processes)
        record["worktree_diff_sha256"] = hashlib.sha256(subprocess.check_output(["git", "diff", "HEAD"], cwd=product)).hexdigest()
        (out / "record.json").write_text(json.dumps(record, indent=2) + "\n")
    print((out / "browser.log").read_text()[-7000:])
    return record["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
