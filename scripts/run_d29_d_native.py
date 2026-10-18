"""D29 actual React/HTTP/SQLite/fixed-SHA PDF acceptance in a fresh guarded root.

--before runs selected D29 assertions against BOTH fixed D28 frontend/backend.
Evidence directories are exclusive. No credentials, foreign DB or live services.
"""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
import httpx

BASE = "f5a13f308a0fd80458ef1cf753bc0312b170bcfe"


def fingerprint(db):
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as connection:
        tables = [
            r[0]
            for r in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
        return {
            t: hashlib.sha256(
                json.dumps(
                    sorted(
                        connection.execute(f'SELECT * FROM "{t}"').fetchall(), key=str
                    ),
                    default=str,
                ).encode()
            ).hexdigest()
            for t in tables
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--before", action="store_true")
    parser.add_argument("--grep", default="")
    args = parser.parse_args()
    product = Path(__file__).resolve().parents[1]
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    runtime = Path(tempfile.mkdtemp(prefix="findoc-d11-d29-d-native-"))
    source = product
    if args.before:
        source = Path(tempfile.mkdtemp(prefix="d29-fixed-d28-"))
        raw = subprocess.check_output(
            ["git", "archive", BASE, "app", "tests", "frontend", "pyproject.toml"],
            cwd=product,
        )
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
            archive.extractall(source, filter="data")
        (source / "scripts").mkdir()
        for path in ("tests/support/d29_app.py", "scripts/run_d26_legacy_browser.py"):
            shutil.copyfile(product / path, source / path)
        (source / "frontend/node_modules").symlink_to(
            product / "frontend/node_modules", target_is_directory=True
        )
        (source / "frontend/public/pdf-assets").symlink_to(
            product / "frontend/public/pdf-assets", target_is_directory=True
        )
    ports = []
    for _ in range(2):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            ports.append(sock.getsockname()[1])
    api, web = [f"http://127.0.0.1:{p}" for p in ports]
    node = os.environ.get(
        "FINDOC_NODE", "/Users/aipuli/.nvm/versions/node/v24.19.0/bin/node"
    )
    generated = product / "frontend/test-results" / out.name
    generated.mkdir(parents=True, exist_ok=False)
    spec_provenance = []
    for name in ("d29-d-native-journey.spec.ts", "financial-review-helpers.ts"):
        raw = (product / "frontend/e2e" / name).read_bytes()
        executed = raw.replace(b"../tests/support/", b"../../tests/support/")
        (generated / name).write_bytes(executed)
        spec_provenance.append(
            {"file": name, "source_sha256": hashlib.sha256(raw).hexdigest(), "executed_sha256": hashlib.sha256(executed).hexdigest()}
        )
    config = generated / "config.mjs"
    config.write_text(
        'import {defineConfig} from "@playwright/test";export default defineConfig('
        + json.dumps(
            dict(
                testDir=str(generated),
                testMatch="d29-d-native-journey.spec.ts",
                workers=1,
                retries=0,
                timeout=90000,
                outputDir=str(out / "traces"),
                reporter=[
                    ["line"],
                    ["json", dict(outputFile=str(out / "results.json"))],
                ],
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
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("LLM_", "OPENAI_", "DEEPSEEK_"))
    }
    env.update(
        FINDOC_UX_RUNTIME_ROOT=str(runtime),
        FINDOC_UX_LIVE="0",
        FINDOC_E2E_DISABLE_ENV_FILES="1",
        FINDOC_API_ORIGIN=api,
        D29_ALLOWED_WORKTREE=str(product),
        D29_ARTIFACT_DIR=str(out),
        D29_BEFORE="1" if args.before else "0",
        PYTHONDONTWRITEBYTECODE="1",
        HF_HUB_OFFLINE="1",
    )
    record = dict(
        base_sha=BASE,
        before=args.before,
        runtime_root=str(runtime),
        source_root=str(source),
        api=api,
        web=web,
        actual_react=True,
        actual_http=True,
        actual_sqlite=True,
        actual_pdf=True,
        simulated_test=True,
        human_acceptances=0,
        real_model=False,
        real_embedding=False,
        credentials_read=False,
        d28_runtime_accessed=False,
        outgoing_sockets_blocked=True,
        foreign_sqlite_blocked=True,
        protected_worktrees_blocked=True,
        specs=spec_provenance,
        exit_code=1,
    )
    processes, handles = [], []
    try:
        commands = [
            (
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "tests.support.d29_app:create_d29_app",
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
        for i, (command, cwd) in enumerate(commands):
            handle = (out / f"server-{i}.log").open("w")
            handles.append(handle)
            processes.append(
                subprocess.Popen(
                    command, cwd=cwd, env=env, stdout=handle, stderr=subprocess.STDOUT
                )
            )
        with httpx.Client(timeout=120) as client:
            for url in [api + "/companies", web]:
                deadline = time.monotonic() + 120
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
            reports = []
            for r in json.loads(
                (product / "product/validation/sources.json").read_text()
            ):
                code = "000333" if r["id"].startswith("midea") else "000651"
                company = next(c for c in companies if c["security_code"] == code)
                year = int(r["id"][-4:])
                raw = (product / r["path"]).read_bytes()
                assert hashlib.sha256(raw).hexdigest() == r["sha256"]
                meta = dict(
                    company_id=company["company_id"],
                    report_year=year,
                    report_type="annual",
                    basis="PRC_GAAP",
                    period_start=f"{year}-01-01",
                    period_end=f"{year}-12-31",
                    source_url=r["url"],
                )
                uploaded = client.post(
                    api + "/report-documents",
                    files={"file": (r["id"] + ".pdf", raw, "application/pdf")},
                    data={"metadata": json.dumps(meta)},
                )
                assert uploaded.status_code == 202, uploaded.text
                document = uploaded.json()["document_id"]
                deadline = time.monotonic() + 120
                while True:
                    ready = client.get(api + "/documents/" + document).json()
                    if ready["status"] == "ready":
                        break
                    assert ready["status"] != "failed", ready
                    assert time.monotonic() < deadline
                    time.sleep(0.3)
                s = client.get(api + "/documents/" + document + "/source").json()
                reports.append(
                    dict(report_id=r["id"], source=s, pdf_sha256=r["sha256"])
                )
            # One explicitly simulated saved group proves history reentry before/after.
            s = next(r["source"] for r in reports if r["report_id"] == "midea-2024")
            selection = dict(
                review_schema="financial-review-v1",
                company_id=s["company_id"],
                document_id=s["document_id"],
                source_revision=s["source_revision"],
                periods=[2024],
                metric_keys=["revenue", "net_profit_parent", "operating_cash_flow"],
            )
            review = client.post(
                api + "/financial-facts/reviews", json=selection
            ).json()
            acceptance = client.post(
                api + "/financial-facts/confirmations",
                json={
                    **selection,
                    "snapshot_id": review["snapshot_id"],
                    "request_id": "d29-simulated-history",
                    "accepted": True,
                },
            ).json()
            saved = client.post(
                api + "/financial-facts/persisted",
                json={"receipt_id": acceptance["receipt_id"]},
            )
            assert saved.status_code == 200, saved.text
            group = saved.json()
            assert (
                group["confirmation_kind"] == "simulated_test"
                and not group["production_calculable"]
            )
        manifest = dict(
            reports=reports, companies=companies, saved=group, receipt=acceptance
        )
        (out / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2)
        )
        record["seed_tables"] = fingerprint(runtime / "documents.db")
        command = [
            node,
            str(product / "frontend/node_modules/@playwright/test/cli.js"),
            "test",
            "--config",
            str(config),
        ]
        if args.grep:
            command += ["--grep", args.grep]
        if args.before:
            command += ["--grep", "baseline"]
        record["executed_source_sha256"] = {
            str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
            for d in ("app", "frontend/src") for p in sorted((source / d).rglob("*"))
            if p.is_file() and p.suffix in (".py", ".ts", ".tsx", ".css")
        }
        with (out / "browser.log").open("w") as log:
            record["exit_code"] = subprocess.run(
                command,
                cwd=product / "frontend",
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
        if (runtime / "documents.db").exists():
            record["final_tables"] = fingerprint(runtime / "documents.db")
        record["servers_stopped"] = all(p.poll() is not None for p in processes)
        record["diff_sha256"] = hashlib.sha256(
            subprocess.check_output(["git", "diff", "HEAD"], cwd=product)
        ).hexdigest()
        (out / "record.json").write_text(json.dumps(record, indent=2) + "\n")
    print((out / "browser.log").read_text()[-7500:])
    return record["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
