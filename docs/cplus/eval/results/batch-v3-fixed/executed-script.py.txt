"""Owned real OS/controller/socket HTTP 2x2 tool batch; model disabled, no ledger.

A fresh controller receives generated login credentials in its minimal environment.
Only its own active SQLite files are inspected read-only to prove no GET dispatch.
All original seed/config/active runtime/provider budget files remain untouched.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

import httpx
import pymupdf

from app.demo.config import password_hash
from app.demo.process import group_alive, process_birth
from app.demo.seed import verify_seed
from app.documents.source_repository import evidence_digest

PROJECT = Path(__file__).resolve().parents[2]
SEED_SHA = "d96b9340838c1d22619308d5d4492996f99ae03c52bf8a8a17eb6594ca139c3d"


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_read(path):
    return json.loads(path.read_text())


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def db_snapshot(root):
    result = {}
    for name, tables in {
        "cplus-research.db": ["operations", "objects"],
        "annual-diff.db": ["operations", "results"],
        "batch-research.db": ["operations", "snapshots", "batches", "cells"],
    }.items():
        with closing(sqlite3.connect((root / name).as_uri() + "?mode=ro", uri=True)) as db:
            result[name] = {}
            for table in tables:
                rows = db.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall()
                result[name][table] = {"rows": len(rows), "rows_sha256": sha(rows)}
    return result


def child_operation(root, operation, domain):
    database = root / ("annual-diff.db" if domain == "annual_changes" else "cplus-research.db")
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
        row = db.execute("SELECT state FROM operations WHERE id=?", (operation,)).fetchone()
    return row[0] if row else None


def verify_quote(root, evidence, allowed, pdfs):
    ref = evidence["source_ref"]
    assert ref in allowed and ref["kind"] == "fast", "citation outside exact frozen source"
    raw = pdfs[ref["document_id"]]
    assert hashlib.sha256(raw).hexdigest() == ref["content_sha256"]
    with closing(sqlite3.connect((root / "documents.db").as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        source = db.execute(
            "SELECT * FROM document_sources WHERE source_revision=?", (ref["source_revision"],)
        ).fetchone()
        assert source and source["invalidated_at"] is None
        for key in ("document_id", "content_sha256", "parser_version", "workspace_id", "attempt"):
            assert source[key] == ref[key]
        record = db.execute(
            "SELECT * FROM document_evidence WHERE source_revision=? AND evidence_id=?",
            (ref["source_revision"], evidence["evidence_id"]),
        ).fetchone()
        assert record and record["physical_page"] == evidence["physical_page"]
        assert record["payload_sha256"] == evidence_digest(
            record["physical_page"], record["text"], record["kind"]
        )
        assert evidence["text"] and evidence["text"] in record["text"], (
            "complete exact excerpt mismatch"
        )
    with pymupdf.open(stream=raw, filetype="pdf") as pdf:
        assert 1 <= evidence["physical_page"] <= len(pdf)
        page = pdf[evidence["physical_page"] - 1].get_text()
    return dict(
        document_id=ref["document_id"],
        source_revision=ref["source_revision"],
        content_sha256=ref["content_sha256"],
        report_year=ref["report_year"],
        basis=ref["basis"],
        physical_page=evidence["physical_page"],
        evidence_id=evidence["evidence_id"],
        text=evidence["text"],
        source_record_exact_verified=True,
        http_pdf_sha_verified=True,
        raw_pdf_text_exact=evidence["text"] in page,
        whitespace_only_pdf_match="".join(evidence["text"].split()) in "".join(page.split()),
    )


def failure_snapshot(root):
    """Read only the owned runtime before cleanup; never replay or repair a cell."""
    captured = {}
    if not root or not root.is_dir():
        return {"unavailable": "owned runtime absent"}
    try:
        with closing(
            sqlite3.connect((root / "batch-research.db").as_uri() + "?mode=ro", uri=True)
        ) as db:
            db.row_factory = sqlite3.Row
            captured["batches"] = [
                dict(r) for r in db.execute("SELECT id,plan_id,revision FROM batches")
            ]
            captured["cells"] = [
                dict(r)
                for r in db.execute(
                    "SELECT batch_id,key,state,operation_id,result_id,error FROM cells ORDER BY rowid"
                )
            ]
            captured["completed_cell_payloads"] = [
                json.loads(
                    db.execute(
                        "SELECT payload FROM snapshots WHERE id=?", (r["result_id"],)
                    ).fetchone()[0]
                )
                for r in captured["cells"]
                if r["result_id"]
            ]
        captured["domain_fingerprints"] = db_snapshot(root)
    except Exception as exc:
        captured["capture_error"] = type(exc).__name__
    return captured


def update_fixed24(output, receipt):
    fixed = json_read(PROJECT / "docs/cplus/eval/fixed-cases.json")
    previous = json_read(PROJECT / "docs/cplus/eval/results/v1/fixed24-execution-tiers.json")
    prior_by_id = {e["id"]: e for e in previous["entries"]}
    entries = []
    for case in fixed["cases"]:
        key = case["id"]
        value = dict(
            id=key,
            exact_question=case["question"],
            required_tier=case["evidence_tier_required"],
            previous_v1_execution=prior_by_id[key]["this_run_execution"],
            this_run_execution="NOT_RUN_BY_BATCH_SUITE",
            full_model_answer_pass=False,
            human_semantic_review="pending",
            human_financial_review="pending",
            remaining_gap=prior_by_id[key]["remaining_gap"],
        )
        if key in ("E01-02", "E01-09"):
            probe = receipt.get("midea_fixed_probes", {}).get(key)
            value.update(
                this_run_execution="REAL_OS_SOCKET_HTTP_EXCERPT_TOOL_ONLY"
                if probe
                else (
                    "REAL_SOCKET_HTTP_SOURCE_PREREQUISITE_ONLY_QUESTION_NOT_RUN"
                    if "000333-2024" in receipt.get("sources", {})
                    else "NOT_COMPLETED"
                ),
                remaining_gap="Midea 2024/2025 text source availability now verified; requested model planning/refusal/answer semantics remain unverified, provider disabled.",
                evidence_pointer=f"result.json#midea_fixed_probes.{key}"
                if probe
                else "result.json#sources",
            )
        elif key == "E01-03":
            value["remaining_gap"] = (
                "Both Midea text annual sources now exist; preceding turn/pronoun resolution and model conversation were not executed."
            )
        elif key == "E01-05":
            value["remaining_gap"] = (
                "All four text annual sources exist, but Midea 2024 basis is unknown; no financial hard comparison, human-confirmed ratio, or deep model cause is accepted."
            )
        elif key == "CP-19":
            has_annual = (
                len([c for c in receipt.get("cell_verification", []) if "topics" in c]) == 2
            )
            value.update(
                this_run_execution="REAL_OS_SOCKET_HTTP_TWO_COMPANIES_THREE_TOPICS_BILATERAL_EXCERPTS"
                if has_annual
                else "NOT_VERIFIED_BATCH_START_FAILED_BEFORE_RESULT_READ",
                evidence_pointer="result.json#cell_verification"
                if has_annual
                else "result.json#start_effect,last_live_readonly_observation",
                remaining_gap=(
                    "Program bilateral three-topic excerpts only; semantic change explanation requires real model and human review."
                    if has_annual
                    else "Batch start failed before annual payloads were read; bilateral completeness is not verified, and real-model/human review remains pending."
                ),
            )
        elif key == "CP-21":
            value.update(
                this_run_execution=receipt.get(
                    "batch_result", "NOT_COMPLETED_START_EFFECT_UNKNOWN_NO_REPLAY"
                ),
                evidence_pointer="result.json#matrix"
                if receipt.get("matrix")
                else "result.json#start_effect,last_live_readonly_observation",
                remaining_gap=(
                    "2x2 serial pure-tool batch and GET no-dispatch checked; partial-failure/UNKNOWN recovery and REAL_LLM remain unverified."
                    if receipt.get("matrix_get_zero_dispatch")
                    else "Start returned 503 at 260 seconds, effect UNKNOWN. Final matrix, matrix GET no-dispatch, per-cell result verification, and recovery were not completed. No retry or fault injection."
                ),
            )
        entries.append(value)
    assert len(entries) == 24
    dump(
        output / "fixed24-supplement.json",
        dict(
            schema_version="cplus-fixed24-batch-supplement-v1",
            fixed_cases_sha256=file_sha(PROJECT / "docs/cplus/eval/fixed-cases.json"),
            previous_v1_inventory_sha256=file_sha(
                PROJECT / "docs/cplus/eval/results/v1/fixed24-execution-tiers.json"
            ),
            entries=entries,
            full_model_answer_pass_count=0,
            provider_calls=0,
            financial_approvals=0,
        ),
    )


def diagnostic_hooks():
    # Timing only, in the owned child. Each wrapped function keeps its original
    # arguments/result/errors and no hook changes guards, budgets or source scope.
    return r"""import os
if os.environ.get("DEMO_INTERNAL_GENERATION") and os.environ.get("BATCH_TIMING_LOG"):
    import functools, json, threading, time, sys
    lock = threading.Lock()
    def event(name, elapsed, fields=None):
        row = {"name":name,"seconds":elapsed,"pid":os.getpid(),**(fields or {})}
        with lock, open(os.environ["BATCH_TIMING_LOG"],"a") as out:
            out.write(json.dumps(row,ensure_ascii=False)+"\n")
    event("child_python",0,{"executable":sys.executable,"prefix":sys.prefix,"base_prefix":sys.base_prefix})
    def sync(obj,name,label=None):
        original=getattr(obj,name)
        @functools.wraps(original)
        def wrapped(*args,**kwargs):
            begin=time.perf_counter()
            try:return original(*args,**kwargs)
            finally:event(label or name,time.perf_counter()-begin)
        setattr(obj,name,wrapped)
    def asynchronous(obj,name,label=None):
        original=getattr(obj,name)
        @functools.wraps(original)
        async def wrapped(*args,**kwargs):
            begin=time.perf_counter()
            try:return await original(*args,**kwargs)
            finally:event(label or name,time.perf_counter()-begin,{"cell_key":args[1]["cell_key"]} if label=="batch.cell" else None)
        setattr(obj,name,wrapped)
    from FlagEmbedding import BGEM3FlagModel
    sync(BGEM3FlagModel,"__init__","BGE.model_init")
    import app.rag.embed as embedding
    sync(embedding,"embed","BGE.embed")
    import app.documents.source_service as sources
    sync(sources,"inspect_pdf","source.inspect_pdf")
    asynchronous(sources.DocumentSourceService,"_checked","source.checked")
    from app.retrieval_v2.service import HybridRetrievalService
    for name in ("records","verify","search"):
        asynchronous(HybridRetrievalService,name,"hybrid."+name)
    from app.rag.selected_scope import SelectedScopeSearch
    asynchronous(SelectedScopeSearch,"search","dense.search")
    from app.batch_research.tools import ExistingToolAdapter
    asynchronous(ExistingToolAdapter,"execute_cell","batch.cell")
    from app.annual_diff.service import AnnualDiffService
    for name in ("side","create"):
        asynchronous(AnnualDiffService,name,"annual."+name)
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--diagnose-one-annual",
        action="store_true",
        help="New owned controller: timing-only hooks, one Gree annual comparison, no batch start",
    )
    parser.add_argument(
        "--timing", action="store_true", help="Timing-only child wrappers for the full real batch"
    )
    args = parser.parse_args()
    output = args.output.resolve()
    assert output.is_relative_to(PROJECT / "docs/cplus/eval/results") and output.name.startswith(
        "batch"
    )
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise FileExistsError("Use a new empty batch output directory; never replace a run")
    manifest, seed_sha = verify_seed(args.seed.resolve(), SEED_SHA)
    scratch = Path(tempfile.mkdtemp(prefix="findoc-cplus-real-batch-")).resolve()
    control = scratch / "control"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    assert port != 14540
    origin = f"http://127.0.0.1:{port}"
    username, password = "batch-" + secrets.token_hex(8), secrets.token_urlsafe(32)
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(Path.home()),
        "PYTHONPATH": str(PROJECT),
        "DEMO_CONTROL_ROOT": str(control),
        "DEMO_SEED_ROOT": str(args.seed.resolve()),
        "DEMO_USERNAME": username,
        "DEMO_PASSWORD_HASH": password_hash(password),
        "DEMO_ALLOWED_ORIGINS": origin,
        "DEMO_COOKIE_SECURE": "false",
        "DEMO_CONFLICT_POLICY": "wait_only",
        "DEMO_TTL_MINUTES": "30",
        "DEMO_CHILD_MODE": "real",
        "DEMO_CHILD_STARTUP_TIMEOUT": "150",
        "DEMO_CHILD_PYTHON": sys.executable,
        "FINDOC_CPLUS_ENABLED": "1",
        "LLM_API_KEY": "disabled-owned-batch-only",
        "LLM_MODEL": "disabled-no-calls",
        "LLM_BASE_URL": "http://127.0.0.1:9/v1",
        "LLM_TIMEOUT_SECONDS": "1",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "TOKENIZERS_PARALLELISM": "false",
    }
    if args.diagnose_one_annual or args.timing:
        hooks = scratch / "timing-hooks"
        hooks.mkdir()
        hook_text = diagnostic_hooks()
        (hooks / "sitecustomize.py").write_text(hook_text)
        (output / "timing-hooks.py.txt").write_text(hook_text)
        env["PYTHONPATH"] = str(hooks) + os.pathsep + str(PROJECT)
        env["BATCH_TIMING_LOG"] = str(scratch / "child-timing.jsonl")
    proof = dict(
        schema_version="cplus-real-batch-v1",
        generated_at=datetime.now(UTC).isoformat(),
        baseline=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True
        ).strip(),
        script_sha256=file_sha(Path(__file__)),
        implementation_sha256={
            "app/retrieval_v2/service.py": file_sha(PROJECT / "app/retrieval_v2/service.py")
        },
        timing_enabled=args.diagnose_one_annual or args.timing,
        tier="REAL_OS_CONTROLLER_CHILD_SOCKET_HTTP_PDF_BGE_MILVUS",
        origin=origin,
        seed_manifest_sha256=seed_sha,
        seed_version=manifest["seed_version"],
        seed_vector_indexes=manifest["vector_indexes"],
        owned_scratch=str(scratch),
        provider_calls=0,
        financial_approvals=0,
        paid_multi_agent=False,
        model="disabled-no-calls",
        login_config="generated per run, credentials not persisted",
        steps=[],
        operations=[],
        child_processes=[],
        execution="STARTED",
    )
    target = output / "result.json"

    def save():
        dump(target, proof)

    def remember_child():
        registry = control / "child.json"
        if registry.exists():
            record = json_read(registry)
            safe = {k: record[k] for k in ("pid", "pgid", "birth", "generation")}
            if safe not in proof["child_processes"]:
                proof["child_processes"].append(safe)
                save()

    save()
    controller = None
    root = None
    try:
        with (output / "controller.log").open("wb") as log:
            controller = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.demo.entrypoint:create_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--no-access-log",
                    "--log-level",
                    "warning",
                ],
                cwd=PROJECT,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
        proof["controller"] = {
            "pid": controller.pid,
            "pgid": controller.pid,
            "birth": process_birth(controller.pid),
        }
        save()
        with httpx.Client(
            base_url=origin, trust_env=False, timeout=300, headers={"Origin": origin}
        ) as client:

            def request(method, path, body=None, auth=False):
                started = time.monotonic()
                intent = None
                if method == "POST":
                    body = {"operation_id": str(uuid4()), **(body or {})}
                    intent = {
                        "operation_id": body["operation_id"],
                        "method": method,
                        "path": path,
                        "state": "INTENT_PERSISTED_NO_REPLAY",
                    }
                    if not auth:
                        intent["request_body"] = body
                    proof["operations"].append(intent)
                    save()
                try:
                    response = client.request(method, path, json=body if body is not None else None)
                    step = {
                        "method": method,
                        "path": path,
                        "status": response.status_code,
                        "elapsed_seconds": round(time.monotonic() - started, 3),
                    }
                    proof["steps"].append(step)
                    if intent is not None:
                        intent.update(state="HTTP_RESPONSE_RECEIVED", status=response.status_code)
                    save()
                    print(method, path, response.status_code, flush=True)
                    if response.status_code >= 400:
                        step["safe_business_error"] = response.json()
                        save()
                        raise RuntimeError(f"{method} {path}: HTTP {response.status_code}")
                    return response.json()
                except httpx.HTTPError as exc:
                    if intent is not None:
                        intent.update(state="UNKNOWN_NO_REPLAY", error_type=type(exc).__name__)
                        save()
                    raise

            deadline = time.monotonic() + 30
            while True:
                if controller.poll() is not None:
                    raise RuntimeError("owned controller exited")
                try:
                    status = client.get("/demo/status", timeout=2)
                    if status.status_code == 200 and status.json()["service_state"] == "ready":
                        break
                except httpx.HTTPError:
                    pass
                if time.monotonic() > deadline:
                    raise TimeoutError("owned controller startup")
                time.sleep(0.2)
            login = request(
                "POST", "/demo/login", {"username": username, "password": password}, auth=True
            )
            deadline = time.monotonic() + 180
            while True:
                remember_child()
                progress = client.get("/demo/operations/" + login["operation_id"]).json()
                if progress.get("claimable"):
                    break
                if progress.get("state") == "failed" or time.monotonic() > deadline:
                    proof["login_reset_failure"] = progress
                    raise RuntimeError("owned real child readiness failed")
                time.sleep(0.3)
            request(
                "POST", "/demo/claim", {"attempt_operation_id": login["operation_id"]}, auth=True
            )
            proof["session"] = request("GET", "/demo/session")
            remember_child()
            root = control / "active" / str(proof["session"]["lease_generation"])
            assert root.is_relative_to(scratch) and root.is_dir()
            proof["owned_active_root"] = str(root)
            companies = request("GET", "/companies")
            ids = {c["company_id"]: c["security_code"] for c in companies}
            documents = request("GET", "/documents")
            proof["document_status_counts"] = {
                state: sum(d["status"] == state for d in documents)
                for state in {d["status"] for d in documents}
            }
            sources = {}
            for document in documents:
                if document["status"] != "ready":
                    continue
                metadata = request("GET", f"/documents/{document['document_id']}/metadata")
                code = ids.get(metadata["company_id"])
                if code not in ("000651", "000333") or metadata["report_year"] not in (2024, 2025):
                    continue
                ref = request("GET", f"/cplus/documents/{document['document_id']}/research-source")
                assert (
                    ref["document_id"] == document["document_id"]
                    and ref["report_year"] == metadata["report_year"]
                )
                sources[(code, ref["report_year"])] = ref
            assert set(sources) == {(c, y) for c in ("000651", "000333") for y in (2024, 2025)}
            assert sources[("000333", 2024)]["basis"] == "unknown"
            proof["sources"] = {f"{c}-{y}": ref for (c, y), ref in sources.items()}
            pdfs = {}
            for ref in sources.values():
                response = client.get(
                    f"/documents/{ref['document_id']}/file",
                    params={
                        "source_revision": ref["source_revision"],
                        "company_id": ref["company_id"],
                    },
                )
                assert response.status_code == 200
                assert hashlib.sha256(response.content).hexdigest() == ref["content_sha256"]
                pdfs[ref["document_id"]] = response.content
            proof["http_pdf_sha_verified_documents"] = list(pdfs)
            proof["build"] = request(
                "POST", "/cplus/retrieval/builds", {"sources": list(sources.values())}
            )
            if args.diagnose_one_annual:
                begin = time.monotonic()
                proof["diagnostic_annual"] = request(
                    "POST",
                    "/cplus/annual-diffs",
                    {
                        "left_source": sources[("000651", 2024)],
                        "right_source": sources[("000651", 2025)],
                        "topics": ["经营风险", "主要业务", "研发"],
                        "generate_explanation": False,
                    },
                )
                proof["diagnostic_seconds"] = round(time.monotonic() - begin, 3)
                proof["execution"] = "COMPLETED_BOUNDED_DIAGNOSTIC_ONE_ANNUAL"
                proof["batch_result"] = "DIAGNOSTIC_ONLY_NO_BATCH_START"
                save()
                return
            before_plan = db_snapshot(root)
            cells = [
                {
                    "cell_key": f"{code}:{template}",
                    "company_id": sources[(code, 2025)]["company_id"],
                    "template": template,
                    "sources": [sources[(code, 2024)], sources[(code, 2025)]],
                }
                for code in ("000651", "000333")
                for template in ("risk_excerpt", "annual_changes")
            ]
            prepared = request(
                "POST", "/cplus/batch-plans", {"cells": cells, "preparation_confirmed": True}
            )
            plan = prepared["result"]
            assert prepared["state"] == "completed" and plan["approval_required"] is True
            assert len({c["child_operation_id"] for c in plan["cells"]}) == 4
            for cell in plan["cells"]:
                assert child_operation(root, cell["child_operation_id"], cell["template"]) is None
            after_plan = db_snapshot(root)
            assert before_plan["cplus-research.db"] == after_plan["cplus-research.db"]
            assert before_plan["annual-diff.db"] == after_plan["annual-diff.db"]
            recovered_plan = request("GET", "/cplus/batch-plans/" + plan["batch_plan_id"])
            assert recovered_plan == plan and db_snapshot(root) == after_plan
            proof["plan"] = plan
            proof["plan_no_child_dispatch"] = True
            proof["explicit_start_approval"] = {
                "confirmed": True,
                "batch_plan_id": plan["batch_plan_id"],
                "batch_plan_revision": plan["revision"],
                "batch_plan_sha256": plan["batch_plan_sha256"],
            }
            save()
            try:
                started = request("POST", "/cplus/batches", proof["explicit_start_approval"])
            except Exception:
                proof["start_effect"] = "UNKNOWN_NO_REPLAY"
                proof["failure_owned_state_before_cleanup"] = failure_snapshot(root)
                for batch in proof["failure_owned_state_before_cleanup"].get("batches", []):
                    try:
                        proof["failure_matrix_http_read"] = request(
                            "GET", "/cplus/batches/" + batch["id"]
                        )
                    except Exception as exc:
                        proof["failure_matrix_http_read_error"] = type(exc).__name__
                save()
                raise
            matrix = started["result"]
            proof["start_receipt"] = started
            proof["matrix"] = matrix
            save()
            before_get = db_snapshot(root)
            recovered = request("GET", "/cplus/batches/" + matrix["batch_id"])
            recovered_again = request("GET", "/cplus/batches/" + matrix["batch_id"])
            assert recovered == recovered_again == matrix
            after_get = db_snapshot(root)
            assert after_get == before_get
            proof["matrix_get_zero_dispatch"] = {
                "equal_matrices": True,
                "before": before_get,
                "after": after_get,
            }
            checks = []
            by_key = {c["cell_key"]: c for c in plan["cells"]}
            for cell in matrix["cells"]:
                planned = by_key[cell["cell_key"]]
                assert cell["operation_id"] == planned["child_operation_id"]
                check = {
                    "cell_key": cell["cell_key"],
                    "state": cell["state"],
                    "error_code": cell["error_code"],
                    "child_operation_id": cell["operation_id"],
                    "stored_child_state": child_operation(
                        root, cell["operation_id"], planned["template"]
                    ),
                }
                if cell["state"] == "completed":
                    wrapper = cell["result"]
                    assert wrapper["child_operation_id"] == cell["operation_id"]
                    result = wrapper["result"]
                    payload = result["payload"]
                    refs = planned["prepared"]["selected_sources"]
                    if planned["template"] == "risk_excerpt":
                        check["quotes"] = [
                            verify_quote(root, i["evidence_ref"], refs, pdfs)
                            for i in payload["items"]
                        ]
                        check["cited_report_years"] = sorted(
                            {q["report_year"] for q in check["quotes"]}
                        )
                        assert check["quotes"]
                    else:
                        assert [t["topic"] for t in payload["topics"]] == [
                            "经营风险",
                            "主要业务",
                            "研发",
                        ]
                        assert (
                            payload["financial_authority"] is False
                            and payload["provider_outcome"] == "not_requested"
                        )
                        topics = []
                        for topic in payload["topics"]:
                            sides = {}
                            for side, source in (("left", refs[0]), ("right", refs[1])):
                                sides[side] = {
                                    "state": topic[side]["state"],
                                    "quotes": [
                                        verify_quote(root, e, [source], pdfs)
                                        for e in topic[side]["evidence_refs"]
                                    ],
                                }
                            topics.append(
                                {
                                    "topic": topic["topic"],
                                    "program_label": topic["program_label"],
                                    **sides,
                                }
                            )
                        check["topics"] = topics
                        check["all_three_dimensions_bilateral"] = all(
                            t[s]["state"] == "available" and t[s]["quotes"]
                            for t in topics
                            for s in ("left", "right")
                        )
                        annual = request("GET", "/cplus/annual-diffs/" + payload["result_id"])
                        assert annual["current_source_status"] == "current"
                checks.append(check)
                proof["cell_verification"] = checks
                save()
            proof["batch_result"] = (
                "PASS_REAL_TOOL_MATRIX"
                if matrix["state"] == "completed" and all(c["state"] == "completed" for c in checks)
                else "PARTIAL_RETAINED_NO_REPLAY"
            )
            proof["all_annual_dimensions_bilateral"] = all(
                c.get("all_three_dimensions_bilateral", True) for c in checks
            )
            fixed = {
                c["id"]: c for c in json_read(PROJECT / "docs/cplus/eval/fixed-cases.json")["cases"]
            }
            proof["midea_fixed_probes"] = {}
            for case_id, years in (("E01-02", (2024, 2025)), ("E01-09", (2024,))):
                refs = [sources[("000333", year)] for year in years]
                context = request(
                    "POST",
                    "/cplus/research/contexts",
                    {"title": "Midea fixed question tool-only probe", "selected_sources": refs},
                )["result"]
                answer = request(
                    "POST",
                    "/cplus/research/answers",
                    dict(
                        context_id=context["context_id"],
                        context_revision=context["revision"],
                        context_sha256=context["context_sha256"],
                        question=fixed[case_id]["question"],
                    ),
                )["result"]
                assert answer["interpretation"] is None and answer["financial_authority"] is False
                verified = [
                    verify_quote(root, f["evidence_ref"], refs, pdfs) for f in answer["findings"]
                ]
                proof["midea_fixed_probes"][case_id] = {
                    "exact_question": fixed[case_id]["question"],
                    "context": context,
                    "answer": answer,
                    "verified_quotes": verified,
                    "tier": "REAL_OS_SOCKET_HTTP_TOOL_ONLY_MODEL_DISABLED",
                    "full_model_answer_pass": False,
                }
                save()
            proof["execution"] = "COMPLETED_REAL_BACKEND_TOOL_EVIDENCE"
            update_fixed24(output, proof)
            save()
    except Exception as exc:
        proof["execution"] = "FAILED_RETAINED_NO_REPLAY"
        proof["error"] = {"type": type(exc).__name__, "message": str(exc)[:1000]}
        update_fixed24(output, proof)
        save()
        raise
    finally:
        remember_child()
        if controller and controller.poll() is None:
            os.killpg(controller.pid, signal.SIGTERM)
            try:
                controller.wait(timeout=45)
            except subprocess.TimeoutExpired:
                os.killpg(controller.pid, signal.SIGKILL)
                controller.wait(timeout=10)
        child_cleanup = []
        for record in proof["child_processes"]:
            if group_alive(record["pgid"]):
                current = process_birth(record["pid"])
                if current == record["birth"]:
                    os.killpg(record["pgid"], signal.SIGTERM)
                    deadline = time.monotonic() + 10
                    while group_alive(record["pgid"]) and time.monotonic() < deadline:
                        time.sleep(0.1)
                else:
                    proof["cleanup_identity_mismatch"] = True
            child_cleanup.append(
                {**record, "group_alive_after_cleanup": group_alive(record["pgid"])}
            )
        for child_log in (control / "active").glob("*/child.log"):
            shutil.copyfile(child_log, output / f"child-generation-{child_log.parent.name}.log")
        timing_log = scratch / "child-timing.jsonl"
        if timing_log.exists():
            shutil.copyfile(timing_log, output / "child-timing.jsonl")
        proof["cleanup"] = {
            "controller_exited": controller is None or controller.poll() is not None,
            "children": child_cleanup,
        }
        verify_seed(args.seed.resolve(), seed_sha)
        proof["seed_unchanged"] = True
        if proof["cleanup"]["controller_exited"] and all(
            not p["group_alive_after_cleanup"] for p in child_cleanup
        ):
            shutil.rmtree(scratch)
        proof["owned_scratch_removed"] = not scratch.exists()
        save()
    print(proof["batch_result"], str(target), flush=True)


if __name__ == "__main__":
    main()
