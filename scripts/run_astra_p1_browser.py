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
parser.add_argument("--d26", action="store_true")
parser.add_argument("--d26-reports", action="store_true")
parser.add_argument("--d27", action="store_true")
parser.add_argument("--foundation-reports", action="store_true")
parser.add_argument("--foundation", action="store_true")
parser.add_argument("--foundation-baseline", action="store_true")
parser.add_argument("--production-build", action="store_true")
parser.add_argument("--manual-session", action="store_true")
parser.add_argument("--compiled-harness", action="store_true")
parser.add_argument("--s4", action="store_true")
parser.add_argument("--s5", action="store_true")
parser.add_argument("--polish", action="store_true")
parser.add_argument("--legacy-reports", choices=["d22", "d23", "d24"])
parser.add_argument("--seed-artifact-dir", type=Path)
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
seed_artifacts = (args.seed_artifact_dir or root / "product/d26/evidence/seed").resolve()
if args.d26_reports or args.d27 or args.foundation_reports or args.foundation or args.s5 or args.polish or args.legacy_reports:
    seed_record = json.loads((seed_artifacts / "record.json").read_text())
    assert seed_record["servers_stopped"] and seed_record["exit_code"] == 0 and seed_record["simulated_test"]
    seed_root = Path(seed_record["runtime_root"]).resolve()
    assert seed_root.name.startswith("findoc-d11-d21-ux-p1-") and seed_root.is_relative_to(Path(tempfile.gettempdir()).resolve())
    shutil.copy2(seed_root / "documents.db", runtime / "documents.db")
    shutil.copytree(seed_root / "objects", runtime / "objects")
    with __import__("sqlite3").connect(runtime / "documents.db") as conn:
        assert conn.execute("SELECT count(*) FROM reports").fetchone()[0] == 0
        assert all("simulated_test" in str(r) for r in conn.execute("SELECT * FROM financial_acceptance_receipts"))
out = (
    args.artifact_dir.resolve()
    if args.artifact_dir
    else (root / "product/ux-p1-astra-p1/evidence" / time.strftime("run-%Y%m%d-%H%M%S"))
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
    if args.s5:
        (frontend / "e2e/report-workspace.spec.ts").write_bytes((root / "frontend/e2e/report-workspace.spec.ts").read_bytes())
    if args.polish:
        (frontend / "e2e/polish-helpers.ts").write_bytes((root / "frontend/e2e/polish-helpers.ts").read_bytes())
        for spec in (root / "frontend/e2e").glob("*-polish.spec.ts"):
            (frontend / "e2e" / spec.name).write_bytes(spec.read_bytes())
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
    D26_REPORT_SEED_DIR=str(seed_artifacts),
    PYTHONDONTWRITEBYTECODE="1",
    OMP_NUM_THREADS="1",
    MKL_NUM_THREADS="1",
    VECLIB_MAXIMUM_THREADS="1",
    HF_HUB_OFFLINE="1",
    FOUNDATION_BASELINE="1" if args.foundation_baseline else "0",
    S5_COMPILED_REPORT_TEST="1" if args.s5 and args.production_build else "0",
)
api_env = env.copy()
config = root / f"frontend/test-results/astra-p1-{runtime.name}.config.mjs"
config.parent.mkdir(exist_ok=True)
config.write_text(
    'import {defineConfig} from "@playwright/test";export default defineConfig('
    + json.dumps(
        dict(
            testDir=str(frontend / "e2e"),
            testMatch="ux-v21.spec.ts"
            if args.baseline
            else [f"{args.legacy_reports}-reports.spec.ts" if args.legacy_reports != "d24" else "d24-exports.spec.ts"] if args.legacy_reports else ["*-polish.spec.ts"] if args.polish else ["report-workspace.spec.ts"] if args.s5 else ["qa-workspace.spec.ts"] if args.s4 else ["foundation-reports.spec.ts"] if args.foundation_reports else ["foundation-navigation.spec.ts"] if args.foundation else ["d27-waiting.spec.ts"] if args.d27 else ["d26-reports.spec.ts"] if args.d26_reports else ["d26-recovery.spec.ts"] if args.d26 else ["ux-p1.spec.ts", "d25-company-setup.spec.ts"],
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
if args.compiled_harness:
    assert args.production_build and args.integration and not args.manual_session
    assert not args.source_ref and not args.before and not args.baseline
    # Compile the existing explicit test entry with the exact formal source.
    # The production dist and productionAccess remain unchanged; no runtime
    # URL/flag in the delivered application enables simulated facts.
    compiled_frontend = Path(tempfile.mkdtemp(prefix="findoc-s6-compiled-")) / "frontend"
    shutil.copytree(frontend, compiled_frontend,
                    ignore=shutil.ignore_patterns("node_modules", "dist", "test-results", "playwright-report"))
    (compiled_frontend / "node_modules").symlink_to(frontend / "node_modules", target_is_directory=True)
    index = compiled_frontend / "index.html"
    index.write_text(index.read_text().replace('/src/main.tsx', '/tests/support/d20-entry.tsx'))
    assert all((compiled_frontend / p.relative_to(frontend)).read_bytes() == p.read_bytes()
               for p in (frontend / "src").rglob("*") if p.is_file())
    with (out / "compiled-build.log").open("w") as log:
        subprocess.run([str(node), str(frontend / "node_modules/vite/bin/vite.js"), "build"],
                       cwd=compiled_frontend, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    (out / "compiled-build-manifest.json").write_text(json.dumps({
        "entry": "existing d20-entry; compiled formal components; explicit simulated_test DataAccess",
        "production_access_modified": False,
        "source_sha256": {str(p.relative_to(frontend)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in (frontend / "src").rglob("*") if p.is_file()},
        "dist_sha256": {str(p.relative_to(compiled_frontend / "dist")): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in (compiled_frontend / "dist").rglob("*") if p.is_file()},
    }, indent=2))
    frontend = compiled_frontend
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
    compiled_harness=args.compiled_harness,
    frontend_entry="compiled explicit simulated test entry" if args.compiled_harness else "compiled production" if args.production_build else "formal components in Vite",
    human_acceptances=0,
    actual_llm=False,
    actual_bge=False,
    actual_milvus=False,
    zoom_method="CSS viewport; selected legacy checks additionally use CDP/DPR2; neither is native Chrome zoom",
)
try:
    for i, (command, cwd, server_env) in enumerate(
        [
            (
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "tests.support.foundation_app:create_app" if args.foundation_reports or args.foundation or args.s5 or args.polish or args.legacy_reports else "tests.support.d27_wait_app:create_app" if args.d27 else "tests.support.d26_report_app:create_app" if args.d26_reports or args.foundation_reports else "tests.support.d26_app:create_app" if args.d26 or args.s4 or args.integration else "tests.support.ux_p1_app:create_ux_p1_app",
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
                    *(["preview"] if args.production_build else []),
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
    if args.legacy_reports:
        from urllib.request import Request
        from uuid import uuid4
        def api(path, body=None):
            request = Request(api_origin + path, data=json.dumps(body).encode() if body else None,
                              headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        task_a = api("/research/tasks/" + json.loads((seed_artifacts / "journey-proof.json").read_text())["result"]["task_id"])
        task_input = json.loads(json.dumps(task_a["input"]))
        for side in ["first", "second"]:
            for choice in task_input[side]["choices"]:
                choice["fact_id"] = choice["fact_set_id"] = None
        task_b = api("/research/tasks", {"operation_id": str(uuid4()), "input": task_input, "run_version": "d21-operating-graph-v2"})
        facts = [dict(side=side, metric_key=c["metric_key"], fact_id=c["fact_id"], fact_set_id=c["fact_set_id"]) for side in ["first", "second"] for c in task_a["active_input"][side]["choices"]]
        task_b = api(f"/research/tasks/{task_b['task_id']}/resume", {"operation_id": str(uuid4()), "expected_revision": task_b["revision"], "facts": facts})
        assert task_b["status"] == "completed"
        cases = []
        for task in [task_a, task_b]:
            draft = api("/reports/drafts", {"task_id": task["task_id"], "expected_revision": task["revision"]})
            case = dict(task_id=task["task_id"], revision=task["revision"], title=draft["title"], template=draft["report_type"], facts=draft["financial_facts"], analysis=draft["financial_analysis"])
            if args.legacy_reports == "d24":
                request = dict(operation_id=str(uuid4()), task_id=task["task_id"], expected_task_revision=task["revision"], edits={"title": None, "conclusions": []})
                v1 = api("/reports", request)
                request.update(operation_id=str(uuid4()), expected_report_revision=1, edits={"title": None, "conclusions": ["用户结论仅作为待审断言"]})
                v2 = api(f"/reports/{v1['report']['report_id']}/revisions", request)
                case.update(report_id=v1["report"]["report_id"], versions=[v1, v2])
            cases.append(case)
        proof = out / "legacy-proof.json"
        proof.write_text(json.dumps(dict(runtime_root=str(runtime), cases=cases), ensure_ascii=False, indent=2))
        for prefix in ["D22", "D23", "D24"]:
            env[prefix + "_REPORT_PROOF"] = str(proof)
            env[prefix + "_ARTIFACT_DIR"] = str(out)
            env[prefix + "_PHASE"] = "live"
        env.update(D22_PYTHON=sys.executable, D22_PRODUCT_ROOT=str(root))
        record["legacy_fixture_origin"] = "this round's stopped simulated seed and explicit controlled B task"
    command = [
        str(node),
        str(root / "frontend/node_modules/@playwright/test/cli.js"),
        "test",
        "--config",
        str(config),
    ]
    if args.grep:
        command.extend(["--grep", args.grep])
    if args.manual_session:
        record["tests_executed"] = False
        record["browser_started_by_runner"] = False
        (out / "session.json").write_text(json.dumps(dict(record, api_origin=api_origin, web_origin=web_origin), indent=2))
        print(json.dumps(dict(api_origin=api_origin, web_origin=web_origin, runtime_root=str(runtime))), flush=True)
        try:
            while all(p.poll() is None for p in processes):
                time.sleep(0.3)
        except KeyboardInterrupt:
            pass
        code = 0 if all(p.poll() is None for p in processes) else 1
    else:
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
    record["baseline_commit"] = "cb55b8a72a5f9de1caa45c21534acb006710e5da"
    record["api_origin"] = api_origin
    record["web_origin"] = web_origin
    record["before"] = args.before
    record["source_ref"] = tested_ref
    record["source_mode"] = "git-archive" if args.source_ref else "working-tree"
    record["production_build"] = args.production_build
    record["worktree_diff_sha256"] = hashlib.sha256(subprocess.check_output(["git", "diff", "HEAD", "--", "frontend", "scripts/run_astra_p1_browser.py"], cwd=root)).hexdigest()
    record["servers_stopped"] = all(p.poll() is not None for p in processes)
    record["d25_runtime_accessed"] = False
    (out / "record.json").write_text(json.dumps(record, indent=2) + "\n")
if not args.manual_session:
    print((out / "browser.log").read_text()[-6500:])
sys.exit(code)
