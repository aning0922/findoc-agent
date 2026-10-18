"""Run UX-P1 Chromium checks in a fresh, disposable runtime.

Actual HTTP/PDF/SQLite; controlled index/model; all consent simulated_test.
Never copies a running database or reads credentials. D25 is not accessed.
"""

import argparse
import hashlib
import json
import io
import tarfile
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import shutil
from urllib.request import urlopen

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument("--baseline", action="store_true")
parser.add_argument("--before", action="store_true")
parser.add_argument("--source-ref")
parser.add_argument("--download-public-sources", action="store_true")
parser.add_argument("--grep", default="")
parser.add_argument("--artifact-dir", type=Path)
parser.add_argument("--integration", action="store_true")
args = parser.parse_args()
def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
api_port, web_port = free_port(), free_port()
api_origin, web_origin = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{web_port}"
node = Path(os.environ.get("FINDOC_NODE") or shutil.which("node") or "node")
tested_ref = subprocess.check_output(["git", "rev-parse", args.source_ref or ("e4b56007a143a1dce72f9dd098e1c37039136eaa" if args.before else "HEAD")], cwd=root, text=True).strip()
runtime = Path(tempfile.mkdtemp(prefix="findoc-d11-d21-ux-p1-"))
out = (
    args.artifact_dir.resolve()
    if args.artifact_dir
    else (root / "product/ux-p1-astra-p0/evidence" / time.strftime("run-%Y%m%d-%H%M%S"))
)
out.mkdir(parents=True, exist_ok=True)
if any(out.iterdir()):
    raise RuntimeError("Use a new empty evidence directory for each isolated run")
frontend = root / "frontend"
if args.baseline or args.before or args.source_ref:
    # Recreate the submitted source in a temporary test directory, never in D25.
    snapshot = Path(tempfile.mkdtemp(prefix="findoc-ux-p1-baseline-"))
    archive = subprocess.check_output(
        ["git", "archive", args.source_ref or "e4b56007a143a1dce72f9dd098e1c37039136eaa" if args.before or args.source_ref else "c9a84c454130690fb7eae43ac17511b0f4e67f1a", "frontend"], cwd=root
    )
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(snapshot, filter="data")
    frontend = snapshot / "frontend"
    (frontend / "node_modules").symlink_to(root / "frontend/node_modules", target_is_directory=True)
    (frontend / "public/pdf-assets").symlink_to(
        root / "frontend/public/pdf-assets", target_is_directory=True
    )
if args.before or args.source_ref:
    (frontend / "e2e/ux-p1.spec.ts").write_text((root / "frontend/e2e/ux-p1.spec.ts").read_text().replace('name: "查看原PDF"', 'name: "展开证据"') if args.before else (root / "frontend/e2e/ux-p1.spec.ts").read_text())
source_dir = root
sources = json.loads((root / "product/validation/sources.json").read_text())
for r in sources:
    r["absolute_path"] = str(source_dir / r["path"])
    source_path = Path(r["absolute_path"])
    if args.download_public_sources and not source_path.exists():
        source_path.parent.mkdir(parents=True, exist_ok=True)
        with urlopen(r["url"], timeout=120) as response:
            source_path.write_bytes(response.read())
    assert hashlib.sha256(source_path.read_bytes()).hexdigest() == r["sha256"]
(out / "sources.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2))
env = {k: v for k, v in os.environ.items() if not k.startswith("LLM_") and k != "OPENAI_API_KEY"}
env.update(
    FINDOC_UX_RUNTIME_ROOT=str(runtime),
    FINDOC_D21_RUNTIME_ROOT=str(runtime),
    FINDOC_D22_RUNTIME_ROOT=str(runtime),
    FINDOC_RUNTIME_ROOT=str(runtime),
    FINDOC_UX_LIVE="0",
    ASTRA_P0_BEFORE="1" if args.before else "0",
    FINDOC_UX_INTEGRATION="1" if args.integration else "0",
    FINDOC_E2E_DISABLE_ENV_FILES="1",
    FINDOC_API_ORIGIN=api_origin,
    UX_ARTIFACT_DIR=str(out),
    UX_SOURCE_FILE=str(out / "sources.json"),
    PYTHONDONTWRITEBYTECODE="1",
    OMP_NUM_THREADS="1",
    MKL_NUM_THREADS="1",
    VECLIB_MAXIMUM_THREADS="1",
    HF_HUB_OFFLINE="1",
)
api_env = env.copy()
config = root / "frontend/test-results/astra-p0.config.mjs"
config.parent.mkdir(exist_ok=True)
config.write_text(
    'import {defineConfig} from "@playwright/test";export default defineConfig('
    + json.dumps(
        dict(
            testDir=str(frontend / "e2e"),
            testMatch="ux-v21.spec.ts"
            if args.baseline
            else ["ux-p1.spec.ts", "d25-company-setup.spec.ts"],
            workers=1,
            retries=0,
            timeout=360000,
            reporter=[["line"], ["json", dict(outputFile=str(out / "results.json"))]],
            outputDir=str(out / "traces"),
            use=dict(
                baseURL=web_origin,
                trace="retain-on-failure",
                viewport=dict(width=1440, height=900),
                actionTimeout=20000,
            ),
        )
    )
    + ");"
)
for port in (api_port, web_port):
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", port))
processes, logs = [], []
record = dict(
    runtime_root=str(runtime),
    actual_chromium=True,
    actual_pdf=True,
    actual_http=True,
    actual_sqlite=True,
    simulated_test=True,
    human_acceptances=0,
    actual_llm=False,
    actual_bge=False,
    actual_milvus=False,
    zoom_method="Chromium CDP layout viewport at half physical dimensions with deviceScaleFactor=2",
)
try:
    for i, (command, cwd, server_env) in enumerate(
        [
            (
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "tests.support.ux_p1_app:create_ux_p1_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(api_port),
                ],
                root,
                api_env,
            ),
            (
                [
                    str(node),
                    str(frontend / "node_modules/vite/bin/vite.js"),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(web_port),
                    "--strictPort",
                ],
                frontend,
                env,
            ),
        ]
    ):
        handle = (out / f"server-{i}.log").open("w")
        logs.append(handle)
        processes.append(
            subprocess.Popen(
                command, cwd=cwd, env=server_env, stdout=handle, stderr=subprocess.STDOUT
            )
        )
    for url in (f"{api_origin}/companies", web_origin):
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
                time.sleep(0.3)
    command = [
        str(node),
        str(root / "frontend/node_modules/@playwright/test/cli.js"),
        "test",
        "--config",
        str(config),
    ]
    if args.grep:
        command.extend(["--grep", args.grep])
    with (out / "browser.log").open("w") as log:
        code = subprocess.run(
            command, cwd=root / "frontend", env=env, stdout=log, stderr=subprocess.STDOUT
        ).returncode
    record["exit_code"] = code
finally:
    for p in processes:
        p.terminate()
    for p in processes:
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
    for f in logs:
        f.close()
    record["fresh_runtime_only"] = True
    record["isolated_server_socket_connect_blocked"] = True
    record["isolated_server_sqlite_guard"] = True
    record["baseline_commit"] = "e4b56007a143a1dce72f9dd098e1c37039136eaa"
    record["api_origin"] = api_origin
    record["web_origin"] = web_origin
    record["before"] = args.before
    record["source_ref"] = tested_ref
    record["servers_stopped"] = all(p.poll() is not None for p in processes)
    record["d25_runtime_accessed"] = False
    (out / "record.json").write_text(json.dumps(record, indent=2) + "\n")
print((out / "browser.log").read_text()[-6500:])
sys.exit(code)
