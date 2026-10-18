"""Independent processes: four real PDFs -> durable interrupt -> D9/D10 simulated receipts -> resume.

No model or human acceptance claims. This runner launches each phase as a fresh
interpreter, using one new isolated DB and copied bytes, with audited SQLite paths.
"""

import asyncio
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import uuid

product = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(product))


def compact(value):
    """Publish binding/numeric proof without duplicating megabytes of original PDF excerpts."""
    if isinstance(value, dict):
        if 'fact_id' in value and 'metric_key' in value:
            keys = ('fact_id','fact_set_id','metric_key','company_id','document_id','source_revision',
                    'content_sha256','disclosure_version','period','period_start','period_end',
                    'value_cny_yuan','raw_value','raw_unit','unit','currency','scope','accounting_basis',
                    'confirmation_kind','production_calculable','physical_page','evidence_id')
            return {k:value[k] for k in keys if k in value}
        return {k:compact(v) for k,v in value.items()}
    if isinstance(value,list):
        return [compact(v) for v in value]
    return value


def phase(name: str, root: Path) -> None:
    os.environ["FINDOC_RUNTIME_ROOT"] = str(root)
    for key in list(os.environ):
        if key.startswith("LLM_") or key == "OPENAI_API_KEY":
            del os.environ[key]

    def audit(event, args):
        if event == "sqlite3.connect" and args[0] != ":memory:":
            if not Path(args[0]).resolve().is_relative_to(root.resolve()):
                raise AssertionError("sqlite_outside_d19_root")

    sys.addaudithook(audit)
    from app.research.repository import ResearchOwner
    from app.research.task_contracts import StartTask, ResumeTask
    from app.research.template_contracts import TemplateRequest
    from tests.support.d19_runtime import reopen, persistent
    from tests.test_d18_templates import period, METRICS, run

    owner = ResearchOwner(root)
    context_path = root / "context.json"
    context = json.loads(context_path.read_text()) if context_path.exists() else {}
    result = dict(phase=name, pid=os.getpid(), human_acceptance_created=False, model_calls=0)
    try:
        if name == "wait":
            from tests.test_document_sources import Harness, metadata
            from tests.test_financial_reviews import assemble
            from app.companies.models import CompanyCreate
            from app.documents.models import DocumentStatus

            h = assemble(Harness(root))
            companies = {
                key: h.companies.create(
                    CompanyCreate(name=name, security_code=code, exchange="SZSE")
                )
                for key, name, code in [
                    ("midea", "美的集团股份有限公司", "000333"),
                    ("gree", "珠海格力电器股份有限公司", "000651"),
                ]
            }
            sources = {}
            for original in json.loads((product / "product/validation/sources.json").read_text()):
                key, year = original["id"].split("-")
                raw = (product / original["path"]).read_bytes()
                assert hashlib.sha256(raw).hexdigest() == original["sha256"]
                document = h.upload(raw, metadata(companies[key].company_id, int(year))).json()[
                    "document_id"
                ]
                assert h.processor.process(document).status == DocumentStatus.READY
                source = run(h.service.source(document))
                source["original_sha256"] = original["sha256"]
                sources[original["id"]] = source

            def side(key, year):
                source = sources[f"{key}-{year}"]
                version = (
                    "disclosure-v1:"
                    + hashlib.sha256(
                        json.dumps(
                            {
                                k: source[k]
                                for k in (
                                    "company_id",
                                    "document_id",
                                    "report_year",
                                    "report_type",
                                    "source_revision",
                                )
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode()
                    ).hexdigest()
                )
                return dict(
                    company_id=source["company_id"],
                    period=period(year),
                    choices=[
                        dict(
                            metric_key=m,
                            document_id=source["document_id"],
                            disclosure_version=version,
                            fact_set_id=None,
                            fact_id=None,
                        )
                        for m in METRICS
                    ],
                )

            pairs = [
                ("company_period_change", side(k, 2025), side(k, 2024)) for k in ("midea", "gree")
            ]
            pairs += [
                ("company_same_period_comparison", side("midea", y), side("gree", y))
                for y in (2024, 2025)
            ]
            repo, svc = persistent(h)
            records = []
            with closing(sqlite3.connect(h.db)) as conn:
                assert (
                    conn.execute("SELECT count(*) FROM financial_acceptance_receipts").fetchone()[0]
                    == 0
                )
            for template, first, second in pairs:
                ids = {c["document_id"] for s in (first, second) for c in s["choices"]}
                req = TemplateRequest.model_validate(
                    dict(
                        schema_version="operating-research-input-v1",
                        template=template,
                        first=first,
                        second=second,
                        direction="business_overview",
                        reports=[
                            dict(
                                document_id=s["document_id"],
                                expected_source_revision=s["source_revision"],
                            )
                            for s in sources.values()
                            if s["document_id"] in ids
                        ],
                    )
                )
                rec = run(svc.start(StartTask(operation_id=str(uuid.uuid4()), input=req)))
                assert (
                    rec["waiting_checkpoint"] and rec["status"] == "awaiting_human_confirmation"
                ), rec
                assert not rec["snapshot"]["analysis_results"]
                records.append(rec)
            context = dict(sources=sources, waiting=records)
            result.update(
                four_pdfs=[dict(report=k, sha256=s["original_sha256"]) for k, s in sources.items()],
                waiting=[
                    dict(
                        task_id=r["task_id"],
                        template=r["input"]["template"],
                        budget=r["budget"],
                        revision=r["revision"],
                        status=r["status"],
                    )
                    for r in records
                ],
                actual_pdf_parser_sqlite=True,
                simulated_facts=False,
            )
        elif name == "read":
            owner.close()
            # Only documents.db is copied. No source PDFs, vector store or model config.
            dbroot = root / "database-only"
            dbroot.mkdir()
            shutil.copy2(root / "documents.db", dbroot / "documents.db")
            os.environ["FINDOC_RUNTIME_ROOT"] = str(dbroot)
            from unittest.mock import Mock, AsyncMock
            from app.agent.financial_analysis import FinancialAnalysisService
            from app.research.templates import TemplateService
            from app.agent.revenue_confirmation import RevenueConfirmationService
            from app.rag.retriever import Retriever
            from app.rag.openai_compatible_llm import OpenAICompatibleLLMClient
            from app.agent.revenue_extraction import RevenueCandidateService
            import app.documents.fast_pdf_parser as parser
            from app.api.research_history_app import create_history_app_from_env
            from fastapi.testclient import TestClient

            bombs = {}
            for cls, method in [
                (FinancialAnalysisService, "analyze"),
                (FinancialAnalysisService, "compare"),
                (TemplateService, "prepare"),
                (RevenueConfirmationService, "confirm_financial"),
                (RevenueConfirmationService, "persist_financial"),
                (RevenueCandidateService, "collect_metrics"),
                (OpenAICompatibleLLMClient, "generate_once"),
                (Retriever, "retrieve"),
            ]:
                key = cls.__name__ + "." + method
                bomb = (
                    AsyncMock(side_effect=AssertionError(key))
                    if asyncio.iscoroutinefunction(getattr(cls, method))
                    else Mock(side_effect=AssertionError(key))
                )
                bombs[key] = bomb
                setattr(cls, method, bomb)
            parser.parse_fast_pdf_bytes = Mock(side_effect=AssertionError("parse"))
            with TestClient(create_history_app_from_env()) as client:
                for rec in context["waiting"]:
                    assert client.get("/research/tasks/" + rec["task_id"]).json() == rec
                    assert (
                        client.get("/research/tasks/by-operation/" + rec["operation_id"]).json()
                        == rec
                    )
                assert len(client.get("/research/tasks").json()["items"]) == 4
                assert client.post("/research/tasks", json={}).status_code == 405
            assert (
                not any(b.call_count for b in bombs.values())
                and not parser.parse_fast_pdf_bytes.call_count
            )
            result.update(
                database_only=True,
                restored_tasks=4,
                execution_calls={k: b.call_count for k, b in bombs.items()},
                parser_calls=0,
                budgets_and_waits_exact=True,
            )
        elif name == "confirm":
            h = reopen(root)
            groups = {}
            for key, source in context["sources"].items():
                selection = dict(
                    document_id=source["document_id"],
                    company_id=source["company_id"],
                    source_revision=source["source_revision"],
                    metric_keys=list(METRICS),
                    periods=[source["report_year"]],
                    review_schema="financial-review-v1",
                )
                review = h.client.post("/financial-facts/reviews", json=selection).json()
                assert review["review_status"] == "ready_for_acceptance"
                acceptance = h.client.post(
                    "/financial-facts/confirmations",
                    json=dict(
                        **selection,
                        accepted=True,
                        snapshot_id=review["snapshot_id"],
                        request_id="d19-simulated-" + key,
                    ),
                )
                assert acceptance.status_code == 200, acceptance.text
                stored = h.client.post(
                    "/financial-facts/persisted",
                    json={"receipt_id": acceptance.json()["receipt_id"]},
                )
                assert stored.status_code == 200, stored.text
                assert stored.json()["confirmation_kind"] == "simulated_test"
                groups[source["document_id"]] = stored.json()
            requests = []
            for record in context["waiting"]:
                facts = []
                for side in ("first", "second"):
                    for choice in record["input"][side]["choices"]:
                        group = groups[choice["document_id"]]
                        fact = next(
                            f for f in group["facts"] if f["metric_key"] == choice["metric_key"]
                        )
                        facts.append(
                            dict(
                                side=side,
                                metric_key=choice["metric_key"],
                                fact_set_id=group["fact_set_id"],
                                fact_id=fact["fact_id"],
                            )
                        )
                requests.append(
                    dict(
                        task_id=record["task_id"],
                        request=dict(
                            operation_id=str(uuid.uuid4()),
                            expected_revision=record["revision"],
                            facts=facts,
                        ),
                    )
                )
            context["resumes"] = requests
            result.update(
                confirmation_path="existing_D9_D10_HTTP",
                confirmation_kind="simulated_test",
                actual_persisted_fact_count=12,
                simulated_only=True,
            )
        elif name == "resume":
            h = reopen(root)
            repo, svc = persistent(h, simulated=True)
            assert repo.recover_interrupted() == 0
            results = []
            for waiting, item in zip(context["waiting"], context["resumes"], strict=True):
                req = ResumeTask.model_validate(item["request"])
                record = run(svc.resume(item["task_id"], req))
                assert record["status"] == "collecting_explanation", record
                assert len(record["snapshot"]["analysis_results"]) == 3
                assert record["budget"]["used"]["steps"] > waiting["budget"]["used"]["steps"]
                assert record["budget"]["used"]["tool_calls"] == 24
                assert run(svc.resume(item["task_id"], req)) == record
                results.append(record)
            context["continued"] = results
            result.update(
                continued=[
                    dict(
                        task_id=r["task_id"],
                        status=r["status"],
                        budget=r["budget"],
                        analysis_results=r["snapshot"]["analysis_results"],
                    )
                    for r in results
                ],
                actual_bge=False,
                actual_model=False,
                retrieval="controlled_empty",
                duplicate_no_reexecution=True,
            )
        elif name == "interrupt":
            h = reopen(root)
            repo, svc = persistent(h)
            req = StartTask(
                operation_id=str(uuid.uuid4()),
                input=TemplateRequest.model_validate(context["waiting"][0]["input"]),
            )
            # Persist a claim and nonzero physical model reservation, then kill process.
            rec, claim = repo.start(req)
            rec["budget"]["used"]["model_calls"] = 1
            repo.reserve(rec["task_id"], claim, rec["budget"])
            context["crashed_task_id"] = rec["task_id"]
            context_path.write_text(json.dumps(context, ensure_ascii=False))
            (root / "interrupt.json").write_text(
                json.dumps(
                    dict(
                        **result,
                        reserved_model_calls=1,
                        actual_model_calls=0,
                        killed_after_claim=True,
                        task_id=rec["task_id"],
                    )
                )
            )
            import signal

            os.kill(os.getpid(), signal.SIGKILL)
        elif name == "recover":
            h = reopen(root)
            repo, svc = persistent(h)
            assert repo.recover_interrupted() == 1
            rec = repo.get(context["crashed_task_id"])
            assert (
                rec["status"] == "failed" and rec["error_code"] == "interrupted_unknown_execution"
            )
            assert rec["budget"]["used"]["model_calls"] == 1
            for prior in context["continued"]:
                assert repo.get(prior["task_id"]) == prior
            result.update(
                crashed_task=rec, unknown_model_not_replayed=True, completed_snapshots_exact=True
            )
        context_path.write_text(json.dumps(context, ensure_ascii=False))
        (root / f"{name}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    finally:
        owner.close()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        phase(sys.argv[1], Path(sys.argv[2]))
    else:
        root = Path(tempfile.mkdtemp(prefix="findoc-d11-d19-real-restart-")).resolve()
        results = []
        for name in ("wait", "read", "confirm", "resume", "interrupt", "recover"):
            command = [sys.executable, __file__, name, str(root)]
            with (root / f"{name}.log").open("w") as log:
                code = subprocess.run(
                    command,
                    cwd=product,
                    env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                ).returncode
            results.append(
                dict(
                    phase=name,
                    exit_code=code,
                    expected_exit_code=-9 if name == "interrupt" else 0,
                    log_sha256=hashlib.sha256((root / f"{name}.log").read_bytes()).hexdigest(),
                )
            )
            print(name, code, flush=True)
            if code != results[-1]["expected_exit_code"]:
                print((root / f"{name}.log").read_text()[-4000:])
                break
        proof = dict(
            runtime_root=str(root),
            fresh_interpreter_per_phase=True,
            commands=results,
            phases=[
                json.loads((root / f"{r['phase']}.json").read_text())
                for r in results
                if (root / f"{r['phase']}.json").exists()
            ],
            all_passed=len(results) == 6
            and all(r["exit_code"] == r["expected_exit_code"] for r in results),
        )
        raw = json.dumps(proof,indent=2,ensure_ascii=False)+'\n'
        (root/'proof-full.json').write_text(raw)
        proof = compact(proof)
        proof['full_local_proof_sha256'] = hashlib.sha256(raw.encode()).hexdigest()
        proof['full_local_proof'] = str(root/'proof-full.json')
        (product / "product/validation/d19-persistent-recovery-proof.json").write_text(
            json.dumps(proof, indent=2, ensure_ascii=False) + "\n"
        )
        sys.exit(0 if proof["all_passed"] else 1)
