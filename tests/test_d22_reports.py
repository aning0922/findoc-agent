"""D22 uses actual frozen D21 results and original PDFs; no model assembly."""

import asyncio
import os
import copy
import json
from pathlib import Path
import shutil
import tempfile
from contextlib import closing
from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.api.report_drafts import create_report_router
from app.agent.financial_analysis import IsolatedAnalysisTestConfig
from app.reports.contracts import GenerateDraft, ReportDraft
from app.reports.service import ReportService
from app.research.repository import HistoryError
from app.research.task_repository import TaskRepository
from tests.support.d19_runtime import reopen


@pytest.fixture
def reports():
    proof = json.loads(Path(os.environ.get("FINDOC_REPORT_TEST_PROOF", "product/validation/d21-real-research.json")).read_text())
    root = Path(tempfile.mkdtemp(prefix="findoc-d11-d22-"))
    source = Path(proof["runtime_root"])
    shutil.copy2(source / "documents.db", root / "documents.db")
    shutil.copytree(source / "objects", root / "objects")
    h = reopen(root)
    repo = TaskRepository(h.registry, "demo")
    service = ReportService(repo, h.service, isolated_test=IsolatedAnalysisTestConfig(root))
    task = repo.get(proof["cases"][0]["result"]["task_id"])
    yield h, repo, service, task
    shutil.rmtree(root)


def run(awaitable):
    return asyncio.run(awaitable)


def request(t):
    return GenerateDraft(task_id=t["task_id"], expected_revision=t["revision"])


def rewrite(repo, task):
    with closing(repo.registry._connect()) as conn, conn:
        repo.write(conn, task, None)


def test_production_rejects_simulation_even_without_marker(reports):
    h, repo, _, t = reports
    service = ReportService(repo, h.service)
    with pytest.raises(HistoryError, match="report_production_confirmation_required"):
        run(service.generate(request(t)))
    t["final_research_content"]["test_mode"] = None
    t["snapshot"]["final_research_content"]["test_mode"] = None
    t["snapshot"]["test_mode"] = None
    rewrite(repo, t)
    with pytest.raises(HistoryError):
        run(service.generate(request(t)))


def test_no_execution_no_writes_and_strict_schema(reports, monkeypatch):
    h, repo, service, t = reports
    from app.agent.financial_analysis import FinancialAnalysisService
    from app.rag.retriever import Retriever
    from app.rag.openai_compatible_llm import OpenAICompatibleLLMClient
    from app.agent.operating_research_graph import PersistentTemplateService

    bombs = []
    for cls, key in [
        (FinancialAnalysisService, "analyze"),
        (FinancialAnalysisService, "compare"),
        (Retriever, "retrieve"),
        (OpenAICompatibleLLMClient, "complete"),
        (PersistentTemplateService, "start"),
    ]:
        bomb = AsyncMock(side_effect=AssertionError("D22 must not execute"))
        monkeypatch.setattr(cls, key, bomb)
        bombs.append(bomb)
    before = (h.root / "documents.db").read_bytes()
    a = run(service.generate(request(t)))
    b = run(service.generate(request(t)))
    assert (
        a.business_content_sha256 == b.business_content_sha256 and a.watermark and not a.persisted
    )
    assert (
        all(v.call_count == 0 for v in bombs) and before == (h.root / "documents.db").read_bytes()
    )
    assert len(a.field_verification) > 180
    with pytest.raises(ValidationError):
        ReportDraft.model_validate(dict(a.model_dump(), export_url="bad"))
    with pytest.raises(ValidationError):
        GenerateDraft.model_validate(dict(request(t).model_dump(), amount="1"))
    value = a.model_dump()
    value["financial_facts"][0]["value_cny_yuan"] = 123
    with pytest.raises(ValidationError):
        ReportDraft.model_validate(value)


@pytest.mark.parametrize(
    "state", ["awaiting_human_confirmation", "refused", "failed", "running", "v1", "unknown"]
)
def test_unqualified_task_never_generates(reports, monkeypatch, state):
    _, repo, service, t = reports
    value = copy.deepcopy(t)
    if state == "running":
        value["execution_status"] = "running"
    elif state == "v1":
        value["graph_version"] = "d19-operating-graph-v1"
    elif state == "unknown":
        value["error_code"] = "task_save_or_execution_unknown"
    else:
        value["status"] = state
    monkeypatch.setattr(repo, "decode", lambda _: value)
    with pytest.raises(HistoryError, match="report_research_not_completed"):
        run(service.generate(request(t)))


@pytest.mark.parametrize(
    "change",
    [
        "fact",
        "company",
        "period",
        "disclosure",
        "formula",
        "operand",
        "duplicate_metric",
        "quote",
        "chunk",
        "quote_page",
        "wrong_report_year",
    ],
)
def test_structural_identity_rejects_wrong_fields(reports, change):
    _, repo, service, t = reports
    c = t["final_research_content"]
    f = c["financial_facts"][0]
    if change == "fact":
        f["fact"]["raw_value"] = "1"
    elif change == "company":
        f["fact"]["company_id"] = c["input"]["second"]["company_id"] + "x"
    elif change == "period":
        f["fact"]["period"] -= 1
    elif change == "disclosure":
        f["disclosure_version"] += "x"
    elif change == "formula":
        c["deterministic_analysis"][0]["formula"]["percentage_change_id"] = "wrong"
    elif change == "operand":
        c["deterministic_analysis"][0]["current"]["value_cny_yuan"] = "1"
    elif change == "duplicate_metric":
        c["deterministic_analysis"][1] = copy.deepcopy(c["deterministic_analysis"][0])
    elif change == "quote":
        c["operating_descriptions"][0]["text"] = "没有来源的经营事实"
        c["operating_descriptions"][0]["citation"]["text"] = "没有来源的经营事实"
    elif change == "chunk":
        c["operating_descriptions"][0]["citation"]["chunk_id"] = "wrong"
    elif change == "quote_page":
        c["operating_descriptions"][0]["citation"]["physical_page"] = 1
    else:
        c["operating_descriptions"][0]["citation"]["report_year"] = 2031
    t["snapshot"]["final_research_content"] = copy.deepcopy(c)
    t["snapshot"]["analysis_results"] = copy.deepcopy(c["deterministic_analysis"])
    try:
        rewrite(repo, t)
    except (ValidationError, HistoryError):
        return
    with pytest.raises(HistoryError):
        run(service.generate(request(t)))


def test_stale_revision_unknown_task_and_api_errors(reports):
    h, _, service, t = reports
    h.client.app.include_router(create_report_router(service))
    client = TestClient(h.client.app)
    body = request(t).model_dump()
    assert client.get("/reports/drafts").status_code == 405
    assert (
        client.post(
            "/reports/drafts", json=dict(body, expected_revision=t["revision"] + 1)
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/reports/drafts", json=dict(body, task_id="00000000-0000-0000-0000-000000000000")
        ).status_code
        == 404
    )
    assert client.post("/reports/drafts", json=dict(body, foo="bar")).status_code == 422
    result = client.post("/reports/drafts", json=body)
    assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
    assert result.json()["persisted"] is False


@pytest.mark.parametrize("when", [1, 2])
def test_receipt_revocation_during_generation_rejects_and_invalidates(reports, when):
    h, repo, service, t = reports
    original = service.pdf_evidence
    calls = 0

    async def race(task):
        nonlocal calls
        await original(task)
        calls += 1
        if calls == when:
            h.receipts.revoke_financial_receipt(
                workspace_id="demo",
                receipt_id=t["final_research_content"]["financial_facts"][0]["receipt_id"],
                confirmation_kind="simulated_test",
                reason="D22 race",
            )

    service.pdf_evidence = race
    with pytest.raises(HistoryError):
        run(service.generate(request(t)))
    assert repo.public(repo.get(t["task_id"]))["publication_eligibility"]["status"] == "invalidated"


def test_pdf_bytes_changed_rejects(reports):
    h, _, service, t = reports
    doc = run(
        h.documents.get_document(t["final_research_content"]["selected_reports"][0]["document_id"])
    )
    path = h.root / "objects" / doc.object_key
    path.write_bytes(b"corrupted PDF")
    with pytest.raises(HistoryError):
        run(service.generate(request(t)))


def test_source_correction_during_generation_invalidates(reports):
    h, repo, service, t = reports
    original = service.pdf_evidence

    async def invalidate(task):
        await original(task)
        report = t["final_research_content"]["selected_reports"][0]
        metadata = {
            k: report[k]
            for k in (
                "company_id",
                "report_year",
                "report_type",
                "period_start",
                "period_end",
                "basis",
            )
        }
        changed = h.client.post(
            f"/documents/{report['document_id']}/binding-corrections",
            json=dict(
                expected_attempt=report["attempt"],
                metadata={**metadata, "basis": "unknown"},
                reason="D22 actual source correction race",
            ),
        )
        assert changed.status_code == 200

    service.pdf_evidence = invalidate
    with pytest.raises(HistoryError):
        run(service.generate(request(t)))
    assert repo.public(repo.get(t["task_id"]))["publication_eligibility"]["status"] == "invalidated"


def test_company_display_rename_does_not_change_frozen_draft(reports):
    h, _, service, task = reports
    first = run(service.generate(request(task)))
    from app.companies.models import CompanyPatch

    h.companies.update(
        task["active_input"]["first"]["company_id"], CompanyPatch(name="后续目录显示名")
    )
    second = service.builder.build(task)
    assert first.business_content_sha256 == second.business_content_sha256
    with pytest.raises(HistoryError):
        run(service.generate(request(task)))


def test_report_contract_refuses_promoted_simulation(reports):
    _, _, service, task = reports
    draft = run(service.generate(request(task)))
    body = draft.model_dump()
    body.update(test_mode=None, watermark=None, status="qualified_draft")
    with pytest.raises(ValidationError):
        ReportDraft.model_validate(body)


def test_current_task_publication_eligibility_is_required_even_with_valid_content(reports):
    _, repo, service, task = reports
    task["snapshot"]["facts"][0]["receipt_id"] = "00000000-0000-0000-0000-000000000000"
    rewrite(repo, task)
    assert repo.public(task)["publication_eligibility"]["status"] == "invalidated"
    with pytest.raises(HistoryError, match="report_publication_eligibility_invalidated"):
        run(service.generate(request(task)))
