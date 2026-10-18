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
import uuid

import httpx

BASE = "0cf97c376ca675815ae51e6af1408953bdee7f46"
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
    runtime = Path(tempfile.mkdtemp(prefix="findoc-d11-d29-c1-"))
    source = ROOT
    if a.before:
        source = Path(tempfile.mkdtemp(prefix="d29-c1-fixed-b-"))
        raw = subprocess.check_output(
            ["git", "archive", BASE, "app", "tests", "frontend", "pyproject.toml"], cwd=ROOT
        )
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
            archive.extractall(source, filter="data")
        shutil.copyfile(
            ROOT / "tests/support/d29_c1_app.py", source / "tests/support/d29_c1_app.py"
        )
        (source / "frontend/node_modules").symlink_to(
            ROOT / "frontend/node_modules", target_is_directory=True
        )
        (source / "frontend/public/pdf-assets").symlink_to(
            ROOT / "frontend/public/pdf-assets", target_is_directory=True
        )
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
        C1_BEFORE="1" if a.before else "0",
        C1_OUT=str(out),
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
                    "tests.support.d29_c1_app:create_d29_c1_app",
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
            # Explicitly synthetic questions over complete immutable public excerpts; not new real model answers.
            variants = [
                ("T01", "A01", "2024年度扣非净利润原值", "30,099,760,382.99", "元", 2024),
                ("T02", "A01", "2024年度营业总收入原值", None, None, None),
                ("T03", "A07", "2023年度营业收入原值", "372,037,280", "千元", 2023),
                ("T04", "A04", "2024年度营业收入原值", "189,163,654,064.64", "元", 2024),
                ("T05", "A10", "2025年度营业收入原值", "456,451,731", "千元", 2025),
                ("T06", "A07", "2024年度扣非净利润原值", "35,741,418", "千元", 2024),
                ("T07", "A01", "2024年度归母净利润原值", "32,184,570,372.28", "元", 2024),
                ("T08", "A07", "2024年度营业收入原值", "407,149,600", "千元", 2024),
                ("T09", "A01", "2024年度营业收入和归母净利润原值", None, None, None),
                ("T10", "A01", "2024年度毛利润原值", None, None, None),
                ("T11", "A01", "2024年度营业收入原值，不做同比", "189,163,654,064.64", "元", 2024),
                ("T12", "A01", "2024年度营业收入原值，不计算同比，但计算差额", None, None, None),
            ]
            distractors = []
            if not a.before:
                for case, parent, q, value, unit, year in variants:
                    base = next(x["run"] for x in runs if x["case"] == parent)
                    body = {k: base[k] for k in FIELDS}
                    body.update(query="请摘录" + base["documents"][0]["company_id"] + q)
                    body["query"] = (
                        "请摘录"
                        + next(
                            c["name"]
                            for c in companies
                            if c["company_id"] == base["documents"][0]["company_id"]
                        )
                        + q
                    )
                    body.update(run_id=str(uuid.uuid4()), operation_id=str(uuid.uuid4()))
                    r = client.post(api + "/__test__/seed-public-run", json=body)
                    assert r.status_code == 200, r.text
                    v = r.json()
                    projection = client.get(api + "/research/runs/" + v["run_id"] + "/focus").json()
                    distractors.append(
                        dict(
                            case=case,
                            synthetic_question=True,
                            run=v,
                            projection=projection,
                            expected_value=value,
                            expected_unit=unit,
                            expected_year=year,
                        )
                    )
            manifest = dict(
                runs=runs, distractors=distractors, sources=sources, companies=companies
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
        spec = "d29-c1-trusted-focus.spec.ts"
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
