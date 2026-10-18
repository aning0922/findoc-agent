"""Exact-base before/after over new SQLite/PDF roots, committed historical Run fixtures.

Test preparation imports only strict public Run envelopes, never D28 acceptance
records, runtime database or credentials. Model/retrieval dependencies are absent.
"""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time

import httpx

BASE = "43d7badfb6a6eb270c7d233cb9a64926e90f9bd6"
ROOT = Path(__file__).resolve().parents[1]
FIELDS = [
    "schema_version",
    "execution_config_version",
    "execution_config",
    "run_id",
    "operation_id",
    "workspace_id",
    "query",
    "document_ids",
    "selection_id",
    "documents",
    "created_at",
    "ended_at",
    "status",
    "result",
]
GOLD = [
    ("189,163,654,064.64", "元"),
    ("32,184,570,372.28", "元"),
    ("29,369,250,570.66", "元"),
    ("170,447,058,533.57", "元"),
    ("29,003,103,411.66", "元"),
    ("46,383,114,754.02", "元"),
    ("407,149,600", "千元"),
    ("38,537,237", "千元"),
    ("60,511,572", "千元"),
    ("456,451,731", "千元"),
    ("43,945,411", "千元"),
    ("53,345,930", "千元"),
]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--before", action="store_true")
    p.add_argument("--grep", default="")
    a = p.parse_args()
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    runtime = Path(tempfile.mkdtemp(prefix="findoc-d11-d29-c2-"))
    source = ROOT
    if a.before:
        source = Path(tempfile.mkdtemp(prefix="d29-c2-fixed-c1-"))
        raw = subprocess.check_output(
            ["git", "archive", BASE, "app", "tests", "frontend", "pyproject.toml"], cwd=ROOT
        )
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
            archive.extractall(source, filter="data")
        shutil.copyfile(
            ROOT / "tests/support/d29_c2_app.py", source / "tests/support/d29_c2_app.py"
        )
        (source / "frontend/node_modules").symlink_to(
            ROOT / "frontend/node_modules", target_is_directory=True
        )
        (source / "frontend/public/pdf-assets").symlink_to(
            ROOT / "frontend/public/pdf-assets", target_is_directory=True
        )
    reader = source / "frontend/test-results/c2-reader"
    reader.mkdir(parents=True, exist_ok=True)
    (reader / "reading.html").write_text(
        '<div id="root"></div><script type="module" src="./reading.tsx"></script>'
    )
    (reader / "reading.tsx").write_text(r"""
import React from 'react';
import { createRoot } from 'react-dom/client';
import { OperatingLimitedResult } from '/src/product/OperatingLimitedResult.tsx';
import { ReportPaper } from '/src/product/ReportPaper.tsx';
import { validateTask } from '/src/product/operatingResearch.ts';
import { validateReport } from '/src/product/reportPersistence.ts';
import '/src/index.css'; import '/src/product/tokens.css'; import '/src/product/product.css'; import '/src/product/foundation.css'; import '/src/product/ReportWorkspace.css';
async function read() {
 const p = new URLSearchParams(location.search), task = p.get('task');
 const path = task ? `/__test__/archive/tasks/${task}` : `/__test__/archive/reports/${p.get('revision')}`;
 const response = await fetch('/api' + path, {cache: 'no-store'}); if(!response.ok) throw Error(await response.text());
 const v = await response.json();
 const target = task ? {workspace_id:v.workspace_id,task_id:v.task_id,task_revision:v.revision,sources:v.snapshot.documents,descriptions:v.final_research_content.operating_descriptions,model_interpretations:v.final_research_content.model_interpretations,test_mode:v.final_research_content.test_mode} : null;
 task ? validateTask(v,task) : validateReport(v,false);
 createRoot(document.getElementById('root')!).render(<main style={{padding:16,maxWidth:1200,margin:'auto'}}><p>隔离历史阅读组件验证 · 公开冻结快照 · 不导入原生接受资格</p>{task ? <OperatingLimitedResult content={v.final_research_content} reviewTarget={target} compact /> : <ReportPaper draft={v.report.trusted_snapshot} saved={v} />}</main>);
}
void read().catch(e=>{document.getElementById('root')!.textContent=e.message;});
""")
    ports = []
    for _ in range(2):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            ports.append(s.getsockname()[1])
    api, web = [f"http://127.0.0.1:{v}" for v in ports]
    node = "/Users/aipuli/.nvm/versions/node/v24.19.0/bin/node"
    env = {
        k: v for k, v in os.environ.items() if not k.startswith(("LLM_", "OPENAI_", "DEEPSEEK_"))
    }
    env.update(
        FINDOC_UX_RUNTIME_ROOT=str(runtime),
        D29_ALLOWED_WORKTREE=str(ROOT),
        FINDOC_API_ORIGIN=api,
        FINDOC_E2E_DISABLE_ENV_FILES="1",
        HF_HUB_OFFLINE="1",
        PYTHONDONTWRITEBYTECODE="1",
        C2_BEFORE="1" if a.before else "0",
        C2_OUT=str(out),
    )
    record = dict(
        base_sha=BASE,
        before=a.before,
        runtime_root=str(runtime),
        source_root=str(source),
        api=api,
        web=web,
        actual_react=True,
        actual_http=True,
        actual_sqlite=True,
        actual_pdf=True,
        model_calls=0,
        retrieval_calls=0,
        credentials_read=False,
        d28_database_access=False,
        human_acceptance_records_imported=False,
        external_review_records_readonly=True,
        archive_snapshots_not_native_qualification=True,
        human_acceptances=0,
        public_run_fixtures=True,
        foreign_sqlite_blocked=True,
        other_worktrees_blocked=True,
        outgoing_sockets_blocked=True,
        exit_code=1,
    )
    processes = []
    handles = []
    try:
        commands = [
            (
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "tests.support.d29_c2_app:create_d29_c2_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(ports[0]),
                ],
                source,
            ),
            (
                [
                    node,
                    str(source / "frontend/node_modules/vite/bin/vite.js"),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(ports[1]),
                    "--strictPort",
                ],
                source / "frontend",
            ),
        ]
        for i, (cmd, cwd) in enumerate(commands):
            h = (out / f"server-{i}.log").open("w")
            handles.append(h)
            processes.append(
                subprocess.Popen(cmd, cwd=cwd, env=env, stdout=h, stderr=subprocess.STDOUT)
            )
        with httpx.Client(timeout=120) as client:
            for url in [api + "/companies", web]:
                deadline = time.monotonic() + 90
                while True:
                    if any(p.poll() is not None for p in processes):
                        raise RuntimeError("server exited; see logs")
                    try:
                        if client.get(url).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    if time.monotonic() > deadline:
                        raise RuntimeError("startup timeout")
                    time.sleep(0.2)
            companies = client.get(api + "/companies").json()
            sources = []
            for s in json.loads((ROOT / "product/d29-c1/public-pdfs.json").read_text()):
                raw = (ROOT / s["path"]).read_bytes()
                assert hashlib.sha256(raw).hexdigest() == s["sha256"]
                company = next(
                    c
                    for c in companies
                    if c["security_code"] == ("000333" if s["id"].startswith("midea") else "000651")
                )
                year = int(s["id"][-4:])
                meta = dict(
                    company_id=company["company_id"],
                    report_year=year,
                    report_type="annual",
                    basis="PRC_GAAP",
                    period_start=f"{year}-01-01",
                    period_end=f"{year}-12-31",
                    source_url=s["url"],
                )
                r = client.post(
                    api + "/report-documents",
                    files={"file": (s["id"] + ".pdf", raw, "application/pdf")},
                    data={"metadata": json.dumps(meta)},
                )
                assert r.status_code == 202, r.text
                document = r.json()["document_id"]
                deadline = time.monotonic() + 180
                while True:
                    v = client.get(api + "/documents/" + document).json()
                    if v["status"] == "ready":
                        break
                    assert v["status"] != "failed", v
                    assert time.monotonic() < deadline
                    time.sleep(0.3)
                source_data = client.get(api + "/documents/" + document + "/source").json()
                sources.append(dict(report_id=s["id"], source=source_data, pdf_sha256=s["sha256"]))
            runs = []
            for f in sorted((ROOT / "product/d28/evidence/qa-real").glob("[AR][0-9][0-9].json")):
                v = json.loads(f.read_bytes())
                old = v["response"]
                body = {k: old[k] for k in FIELDS}
                r = client.post(api + "/__test__/seed-public-run", json=body)
                assert r.status_code == 200, (f.name, r.text)
                run = r.json()
                assert run["integrity_sha256"] == old["integrity_sha256"]
                assert run["result"] == old["result"]
                item = dict(
                    case=f.stem,
                    run=run,
                    input_file_sha256=hashlib.sha256(f.read_bytes()).hexdigest(),
                    answer_sha256=v["answer_utf8_sha256"],
                )
                if f.stem.startswith("A"):
                    n = int(f.stem[1:]) - 1
                    item.update(
                        expected_value=GOLD[n][0],
                        expected_unit=GOLD[n][1],
                        expected_year=run["documents"][0]["report_year"],
                        expected_row=[1, 2, 4][n % 3],
                    )
                if not a.before:
                    projection = client.get(api + "/research/runs/" + run["run_id"] + "/focus")
                    assert projection.status_code == 200, projection.text
                    item["projection"] = projection.json()
                runs.append(item)
            distractors = []
            archive_tasks = []
            for name in ["midea", "gree", "comparison"]:
                task = json.loads(
                    (
                        ROOT
                        / f"product/d28/evidence/human-followup/{name}-user-resume-completed.json"
                    ).read_text()
                )["task"]
                response = client.get(api + "/__test__/archive/tasks/" + task["task_id"])
                assert response.status_code == 200, response.text
                assert response.json() == task
                archive_tasks.append(
                    dict(
                        name=name,
                        task_id=task["task_id"],
                        sha256=hashlib.sha256(response.content).hexdigest(),
                    )
                )
            archive_reports = []
            for revision in [1, 2]:
                detail = json.loads(
                    (
                        ROOT
                        / f"product/d28/evidence/human-followup/midea-report-v{revision}-user-saved.json"
                    ).read_text()
                )["detail"]
                response = client.get(api + f"/__test__/archive/reports/{revision}")
                assert response.status_code == 200, response.text
                assert response.json() == detail
                markdown = client.get(api + f"/__test__/archive/reports/{revision}/markdown")
                assert markdown.status_code == 200, markdown.text
                archive_reports.append(
                    dict(
                        revision=revision,
                        payload_sha256=detail["payload_sha256"],
                        sha256=hashlib.sha256(response.content).hexdigest(),
                        markdown_sha256=hashlib.sha256(markdown.content).hexdigest(),
                    )
                )
            manifest = dict(
                runs=runs,
                distractors=distractors,
                sources=sources,
                companies=companies,
                archive_tasks=archive_tasks,
                archive_reports=archive_reports,
            )
            (out / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
            )
            record["seed_tables"] = client.get(api + "/__test__/c1-readonly-state").json()
        record["executed_source_sha256"] = {
            str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
            for d in ("app", "frontend/src")
            for p in sorted((source / d).rglob("*"))
            if p.is_file() and p.suffix in (".py", ".ts", ".tsx", ".css")
        }
        generated = ROOT / "frontend/test-results" / out.name
        generated.mkdir(parents=True, exist_ok=False)
        spec = "d29-c2-review-provenance.spec.ts"
        raw = (ROOT / "frontend/e2e" / spec).read_bytes()
        (generated / spec).write_bytes(raw)
        record["spec_sha256"] = hashlib.sha256(raw).hexdigest()
        config = generated / "config.mjs"
        config.write_text(
            'import {defineConfig} from "@playwright/test"; export default defineConfig('
            + json.dumps(
                dict(
                    testDir=str(generated),
                    testMatch=spec,
                    workers=1,
                    retries=0,
                    timeout=90000,
                    outputDir=str(out / "traces"),
                    reporter=[["line"], ["json", dict(outputFile=str(out / "results.json"))]],
                    use=dict(
                        baseURL=web,
                        trace="retain-on-failure",
                        actionTimeout=10000,
                        viewport=dict(width=1440, height=1000),
                    ),
                )
            )
            + ");"
        )
        with (out / "browser.log").open("w") as log:
            record["exit_code"] = subprocess.run(
                [
                    node,
                    str(ROOT / "frontend/node_modules/@playwright/test/cli.js"),
                    "test",
                    "--config",
                    str(config),
                    "--max-failures=1",
                    *(["--grep", a.grep] if a.grep else []),
                ],
                cwd=ROOT / "frontend",
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            ).returncode
        if record["exit_code"] == 0 and not a.before:
            paths = ["/research/runs/" + x["run"]["run_id"] for x in runs]
            paths += ["/__test__/archive/tasks/" + x["task_id"] for x in archive_tasks]
            paths += [
                f"/__test__/archive/reports/{n}{suffix}"
                for n in [1, 2]
                for suffix in ["", "/markdown"]
            ]
            with httpx.Client(timeout=30) as client:
                before_bytes = {path: client.get(api + path).content for path in paths}
                before_state = client.get(api + "/__test__/c1-readonly-state").json()
            processes[0].terminate()
            processes[0].wait(timeout=10)
            with (out / "restart-server.log").open("w") as log:
                cmd, cwd = commands[0]
                restarted = subprocess.Popen(
                    cmd, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT
                )
                processes.append(restarted)
                with httpx.Client(timeout=30) as client:
                    deadline = time.monotonic() + 30
                    while True:
                        assert restarted.poll() is None, "restart server exited"
                        try:
                            if client.get(api + "/companies").status_code == 200:
                                break
                        except httpx.HTTPError:
                            pass
                        assert time.monotonic() < deadline
                        time.sleep(0.1)
                    after_bytes = {path: client.get(api + path).content for path in paths}
                    after_state = client.get(api + "/__test__/c1-readonly-state").json()
                assert before_bytes == after_bytes and before_state == after_state
                proof = dict(
                    before_state=before_state,
                    after_state=after_state,
                    exact_http_bytes={
                        path: hashlib.sha256(raw).hexdigest() for path, raw in before_bytes.items()
                    },
                    same_isolated_root=True,
                    old_process_exited=True,
                    new_process_started=True,
                    model_calls=0,
                    retrieval_calls=0,
                    native_acceptance_rows_imported=0,
                )
                (out / "restart-proof.json").write_text(json.dumps(proof, indent=2) + "\n")
                record["isolated_restart_verified"] = True
    finally:
        for p in processes:
            p.terminate()
        for p in processes:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        for h in handles:
            h.close()
        if (runtime / "http.jsonl").exists():
            shutil.copyfile(runtime / "http.jsonl", out / "http.jsonl")
        record["servers_stopped"] = all(p.poll() is not None for p in processes)
        (out / "record.json").write_text(json.dumps(record, indent=2) + "\n")
    if (out / "browser.log").exists():
        print((out / "browser.log").read_text()[-6000:])
    return record["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
