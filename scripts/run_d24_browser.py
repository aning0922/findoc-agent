"""Actual Chromium downloads of eight D23 revisions, restart, failures and revocation."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

root = Path(__file__).resolve().parent.parent
frontend = root / "frontend"
out = root / "data/30d-foundation" / f"d24-browser-{time.time_ns()}"
out.mkdir()
original = json.loads((root / "product/validation/d24-real-exports.json").read_text())[
    "runtime_root"
]
runtime = Path(tempfile.mkdtemp(prefix="findoc-d11-d22-d24-browser-"))
shutil.copy2(Path(original) / "documents.db", runtime / "documents.db")
shutil.copytree(Path(original) / "objects", runtime / "objects")
proof = json.loads((Path(original) / "saved-proof.json").read_text())
proof["runtime_root"] = str(runtime)
(out / "proof.json").write_text(json.dumps(proof))
base = {k: v for k, v in os.environ.items() if not k.startswith("LLM_") and k != "OPENAI_API_KEY"}
base.update(
    PYTHONDONTWRITEBYTECODE="1",
    OMP_NUM_THREADS="1",
    MKL_NUM_THREADS="1",
    VECLIB_MAXIMUM_THREADS="1",
    HF_HUB_OFFLINE="1",
    FINDOC_E2E_DISABLE_ENV_FILES="1",
    FINDOC_D22_RUNTIME_ROOT=str(runtime),
    FINDOC_API_ORIGIN="http://127.0.0.1:18124",
    D24_REPORT_PROOF=str(out / "proof.json"),
    D24_ARTIFACT_DIR=str(out),
)
records = []
for phase, factory, spec in [
    ("live", "tests.support.d23_app:create_d23_app", "d24-exports.spec.ts"),
    ("restart", "tests.support.d23_app:create_d23_app", "d24-exports.spec.ts"),
    ("revoked", "tests.support.d23_app:create_d23_app", "d24-exports.spec.ts"),
]:
    if phase == "restart":
        pass  # restart reopens the original PDFs; export must recheck their bytes
    if phase == "revoked":
        sys.path.insert(0, str(root))
        from app.agent.sqlite_financial_facts import SQLiteRevenueConfirmationRepository

        repo = SQLiteRevenueConfirmationRepository(runtime / "documents.db", initialize=False)
        for receipt in {c["facts"][0]["receipt_id"] for c in proof["cases"]}:
            repo.revoke_financial_receipt(
                workspace_id="demo",
                receipt_id=receipt,
                confirmation_kind="simulated_test",
                reason="D24 browser historical audit",
            )
    before = hashlib.sha256((runtime / "documents.db").read_bytes()).hexdigest()
    env = dict(base, D24_PHASE=phase)
    config = frontend / "test-results" / f"d24-{phase}.config.mjs"
    config.parent.mkdir(exist_ok=True)
    config.write_text(
        'import {defineConfig} from "@playwright/test";export default defineConfig('
        + json.dumps(
            dict(
                testDir=str(frontend / "e2e"),
                testMatch=[spec],
                workers=1,
                retries=0,
                timeout=120000,
                reporter=[["line"], ["json", dict(outputFile=str(out / f"{phase}-results.json"))]],
                outputDir=str(out / f"{phase}-traces"),
                use=dict(
                    baseURL="http://127.0.0.1:14224",
                    channel="chromium",
                    trace="retain-on-failure",
                    viewport=dict(width=1280, height=900),
                    actionTimeout=15000,
                ),
            )
        )
        + ");"
    )
    for port in (18124, 14224):
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", port))
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
                "18124",
            ],
            root,
        ),
        (
            [
                str(frontend / "node_modules/.bin/vite"),
                "--host",
                "127.0.0.1",
                "--port",
                "14224",
                "--strictPort",
            ],
            frontend,
        ),
    ]
    processes = []
    handles = []
    record = dict(
        phase=phase, runtime_root=str(runtime), no_pdf_directory=not (runtime / "objects").exists()
    )
    records.append(record)
    try:
        for i, (command, cwd) in enumerate(commands):
            log = (out / f"{phase}-server-{i}.log").open("x")
            handles.append(log)
            processes.append(
                subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
            )
        for url in ("http://127.0.0.1:18124/companies", "http://127.0.0.1:14224"):
            deadline = time.monotonic() + 60
            while True:
                if any(p.poll() is not None for p in processes):
                    raise RuntimeError("server_exited")
                try:
                    with urlopen(url, timeout=2) as response:
                        assert response.status == 200
                    break
                except Exception:
                    if time.monotonic() > deadline:
                        raise RuntimeError("startup_timeout")
                    time.sleep(0.3)
        command = [str(frontend / "node_modules/.bin/playwright"), "test", "--config", str(config)]
        with (out / f"{phase}-browser.log").open("x") as log:
            code = subprocess.run(
                command, cwd=frontend, env=env, stdout=log, stderr=subprocess.STDOUT
            ).returncode
        record.update(command=command, exit_code=code)
    finally:
        for p in processes:
            p.terminate()
        for p in processes:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        for f in handles:
            f.close()
        record["server_exit_codes"] = [p.returncode for p in processes]
        record["db_unchanged"] = (
            before == hashlib.sha256((runtime / "documents.db").read_bytes()).hexdigest()
        )
        (root / "product/validation/d24-browser-record.json").write_text(
            json.dumps(
                dict(
                    artifacts=str(out),
                    runtime_root=str(runtime),
                    actual_chromium=True,
                    records=records,
                    file_checks=[json.loads(p.read_text()) for p in sorted(out.glob("*-?.json"))],
                ),
                indent=2,
            )
            + "\n"
        )
    print((out / f"{phase}-browser.log").read_text()[-2500:])
    if code:
        sys.exit(code)
    if phase != "live":
        assert record["db_unchanged"]
print(json.dumps(dict(artifacts=str(out), phases=len(records), passed=True)))
