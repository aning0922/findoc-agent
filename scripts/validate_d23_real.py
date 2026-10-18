"""Separate save and GET-only processes over four real D21 frozen scenarios."""

import asyncio
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid
from unittest.mock import AsyncMock, Mock

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from app.agent.financial_analysis import FinancialAnalysisService, IsolatedAnalysisTestConfig  # noqa: E402
from app.rag.retriever import Retriever  # noqa: E402
from app.rag.openai_compatible_llm import OpenAICompatibleLLMClient  # noqa: E402
from app.reports.service import ReportService  # noqa: E402
from app.reports.builder import ReportBuilder  # noqa: E402
from app.reports.persistence_contracts import SaveReport, CreateRevision  # noqa: E402
from app.research.task_repository import TaskRepository  # noqa: E402
from app.documents.source_service import DocumentSourceService  # noqa: E402
from app.api.report_history import create_report_history_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def bombs(history=False):
    blocked = [
        (FinancialAnalysisService, "analyze"),
        (FinancialAnalysisService, "compare"),
        (Retriever, "retrieve"),
        (OpenAICompatibleLLMClient, "complete"),
        (OpenAICompatibleLLMClient, "generate_once"),
    ]
    if history:
        blocked += [(DocumentSourceService, "parsed_evidence"), (ReportBuilder, "build")]
    result = {}
    for cls, method in blocked:
        value = (AsyncMock if asyncio.iscoroutinefunction(getattr(cls, method)) else Mock)(
            side_effect=AssertionError("D23 forbidden execution")
        )
        setattr(cls, method, value)
        result[cls.__name__ + "." + method] = value
    return result


def save_worker(runtime):
    from tests.support.d19_runtime import reopen
    from app.api.report_drafts import create_report_router

    blocked = bombs()
    h = reopen(runtime)
    tasks = TaskRepository(h.registry, "demo")
    drafts = ReportService(tasks, h.service, isolated_test=IsolatedAnalysisTestConfig(runtime))
    h.client.app.include_router(create_report_router(drafts))
    proof = json.loads((root / "product/validation/d21-real-research.json").read_text())
    cases = []
    with closing(h.registry._connect()) as conn:
        before = [tuple(r) for r in conn.execute("SELECT * FROM template_tasks ORDER BY sequence")]
    for case in proof["cases"]:
        task = tasks.get(case["result"]["task_id"])
        body = SaveReport(
            operation_id=str(uuid.uuid4()),
            task_id=task["task_id"],
            expected_task_revision=task["revision"],
        )
        first = h.client.post("/reports", json=body.model_dump(mode="json"))
        assert first.status_code == 200, first.text
        a = first.json()
        rid = a["report"]["report_id"]
        second = CreateRevision(
            **body.model_dump(exclude={"operation_id"}),
            operation_id=str(uuid.uuid4()),
            expected_report_revision=1,
        )
        second = second.model_copy(
            update={
                "edits": body.edits.model_copy(
                    update={
                        "title": "用户编辑 · " + a["report"]["trusted_snapshot"]["title"],
                        "conclusions": ["用户结论仅作为待审断言，未验证经营归因。"],
                    }
                )
            }
        )
        response = h.client.post(f"/reports/{rid}/revisions", json=second.model_dump(mode="json"))
        assert response.status_code == 200, response.text
        b = response.json()
        assert (
            h.client.post("/reports", json=body.model_dump(mode="json")).json()["report"]
            == a["report"]
        )
        frozen = task["final_research_content"]
        s = a["report"]["trusted_snapshot"]
        assert s["evidence_appendix"]["financial_facts"] == frozen["financial_facts"]
        assert s["evidence_appendix"]["deterministic_analysis"] == frozen["deterministic_analysis"]
        assert s["operating_information"] == frozen["operating_descriptions"]
        assert s["model_interpretations"] == frozen["model_interpretations"]
        assert (
            b["report"]["trusted_snapshot"]["business_content_sha256"]
            == s["business_content_sha256"]
        )
        assert s["test_mode"] == "simulated_test" and s["watermark"]
        cases.append(
            dict(
                task_id=task["task_id"],
                task_revision=task["revision"],
                report_id=rid,
                title=s["title"],
                template=s["report_type"],
                versions=[a, b],
                facts=s["financial_facts"],
                analysis=s["financial_analysis"],
            )
        )
    with closing(h.registry._connect()) as conn:
        assert before == [
            tuple(r) for r in conn.execute("SELECT * FROM template_tasks ORDER BY sequence")
        ]
    assert len(cases) == 4 and all(v.call_count == 0 for v in blocked.values())
    (runtime / "saved-proof.json").write_text(
        json.dumps(
            dict(
                cases=cases,
                execution_calls={k: v.call_count for k, v in blocked.items()},
                task_rows_unchanged=True,
            ),
            ensure_ascii=False,
        )
    )


def history_worker(runtime, invalidated=False):
    blocked = bombs(history=True)
    before = (runtime / "documents.db").read_bytes()
    client = TestClient(create_report_history_app(runtime / "documents.db"))
    proof = json.loads((runtime / "saved-proof.json").read_text())
    results = []
    for case in proof["cases"]:
        for version in case["versions"]:
            r = version["report"]
            detail = client.get(f"/reports/{r['report_id']}/revisions/{r['revision']}")
            assert detail.status_code == 200, detail.text
            value = detail.json()
            assert value["report"] == r and value["payload_sha256"] == version["payload_sha256"]
            assert value["current_eligibility"]["status"] == (
                "invalidated" if invalidated else "current_at_read"
            )
            assert client.get(f"/reports/by-operation/{r['operation_id']}").json() == value
            results.append(
                dict(
                    report_id=r["report_id"],
                    revision=r["revision"],
                    payload_sha256=value["payload_sha256"],
                    eligibility=value["current_eligibility"],
                )
            )
    assert len(client.get("/reports").json()["items"]) == 4
    assert all(v.call_count == 0 for v in blocked.values())
    assert before == (runtime / "documents.db").read_bytes()
    (runtime / ("invalidated-history.json" if invalidated else "restart-history.json")).write_text(
        json.dumps(
            dict(
                results=results,
                db_unchanged=True,
                no_pdf_directory=not (runtime / "objects").exists(),
                execution_calls={k: v.call_count for k, v in blocked.items()},
            )
        )
    )


if __name__ == "__main__":
    if len(sys.argv) > 1:
        runtime = Path(sys.argv[2])
        if sys.argv[1] == "save":
            save_worker(runtime)
        else:
            history_worker(runtime, sys.argv[1] == "invalidated")
    else:
        original = Path(
            json.loads((root / "product/validation/d21-real-research.json").read_text())[
                "runtime_root"
            ]
        )
        runtime = Path(tempfile.mkdtemp(prefix="findoc-d11-d23-real-"))
        shutil.copy2(original / "documents.db", runtime / "documents.db")
        shutil.copytree(original / "objects", runtime / "objects")
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        subprocess.run([sys.executable, __file__, "save", str(runtime)], check=True, env=env)
        (runtime / "objects").rename(runtime / "objects-offline")
        subprocess.run([sys.executable, __file__, "history", str(runtime)], check=True, env=env)
        # Independently invalidate D6 sources, without revoking acceptances, on a DB-only copy.
        source_audit = Path(tempfile.mkdtemp(prefix="findoc-d11-d23-source-audit-"))
        shutil.copy2(runtime / "documents.db", source_audit / "documents.db")
        shutil.copy2(runtime / "saved-proof.json", source_audit / "saved-proof.json")
        from app.companies.sqlite_repository import SQLiteCompanyRepository
        from app.documents.source_repository import SQLiteSourceRepository

        source_repo = SQLiteSourceRepository(SQLiteCompanyRepository(source_audit / "documents.db"))
        saved_for_sources = json.loads((source_audit / "saved-proof.json").read_text())
        affected = {}
        for case in saved_for_sources["cases"]:
            selected = case["versions"][0]["report"]["trusted_snapshot"]["evidence_appendix"][
                "selected_reports"
            ]
            affected[selected[0]["document_id"]] = selected[0]["attempt"]
        for document_id, attempt in affected.items():
            source_repo.request_reindex("demo", document_id, attempt)
        subprocess.run(
            [sys.executable, __file__, "invalidated", str(source_audit)], check=True, env=env
        )
        # Explicit D10 revocation in the isolated database; each case has a selected affected receipt.
        from app.agent.sqlite_financial_facts import SQLiteRevenueConfirmationRepository

        reader = SQLiteRevenueConfirmationRepository(runtime / "documents.db", initialize=False)
        saved = json.loads((runtime / "saved-proof.json").read_text())
        for receipt in {c["facts"][0]["receipt_id"] for c in saved["cases"]}:
            reader.revoke_financial_receipt(
                workspace_id="demo",
                receipt_id=receipt,
                confirmation_kind="simulated_test",
                reason="D23 saved-history audit",
            )
        subprocess.run([sys.executable, __file__, "invalidated", str(runtime)], check=True, env=env)
        proof = dict(
            runtime_root=str(runtime),
            original_d21_runtime=str(original),
            cases=[
                {k: v for k, v in c.items() if k != "versions"}
                | dict(
                    versions=[
                        dict(
                            revision=v["report"]["revision"],
                            operation_id=v["report"]["operation_id"],
                            payload_sha256=v["payload_sha256"],
                        )
                        for v in c["versions"]
                    ]
                )
                for c in saved["cases"]
            ],
            save_execution_calls=saved["execution_calls"],
            task_rows_unchanged=saved["task_rows_unchanged"],
            restart=json.loads((runtime / "restart-history.json").read_text()),
            invalidated=json.loads((runtime / "invalidated-history.json").read_text()),
            source_invalidated=json.loads((source_audit / "invalidated-history.json").read_text()),
            source_audit_runtime=str(source_audit),
            human_acceptances=0,
            simulated_test=True,
        )
        (root / "product/validation/d23-real-reports.json").write_text(
            json.dumps(proof, ensure_ascii=False, indent=2) + "\n"
        )
        print(
            json.dumps(
                dict(
                    runtime_root=str(runtime),
                    cases=4,
                    revisions=8,
                    restart_readonly=True,
                    invalidated_history=True,
                )
            )
        )
