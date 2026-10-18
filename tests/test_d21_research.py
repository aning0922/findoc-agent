"""Controlled D21 boundary tests. Actual receipts always isolated simulated_test."""

import copy
import json
from unittest.mock import AsyncMock
from tests.test_document_sources import metadata
import uuid

import pytest
from pydantic import ValidationError

from app.agent.execution_budget import ExecutionBudget
from app.research.task_contracts import StartTaskV2, TASK_RECORD
from app.research.repository import HistoryError
from app.rag.retriever import SearchHit
from app.rag.openai_compatible_llm import ProviderCallError
from tests.test_d11_financial_analysis import saved as saved
from tests.test_d13_company_comparison import paired as paired
from tests.test_d18_templates import body, run, Scripted, final, service
from tests.test_d19_tasks import setup, resume


def response(numbers=(1,), **extra):
    return json.dumps(
        dict(
            decision="answer",
            quotes=[dict(number=n) for n in numbers],
            interpretations=[
                dict(text="业务结构可能存在差异，尚需人工核验。", citations=list(numbers))
            ],
            unresolved_questions=["这些经营披露是否足以解释变化？"],
            **extra,
        ),
        ensure_ascii=False,
    )


def configured(h, numbers=(1,)):
    svc, repo, graph = setup(h)

    async def search(selection, top_k):
        return tuple(
            SearchHit(
                chunk_id=f"business-{n}",
                text="公司主营家电业务。原文不是因果证明。",
                page=1,
                score=1.0,
                source_file="controlled.pdf",
                type="paragraph",
                workspace_id=d.workspace_id,
                document_id=d.document_id,
                source_revision=d.source_revision,
            )
            for n, d in enumerate(selection.documents, 1)
        )

    svc.scope.search = search
    svc.model = Scripted(final(response(numbers)))
    return svc, repo, graph


def request(g, b=None, confirmed=True):
    return StartTaskV2.model_validate(
        dict(
            operation_id=str(uuid.uuid4()),
            input=body(g, b, confirmed),
            run_version="d21-operating-graph-v2",
        )
    )


@pytest.mark.parametrize("template", ["A", "B"])
def test_completed_result_joins_original_financial_truth_and_pending_semantics(
    saved, paired, template
):
    h, g, _ = saved
    b = None
    if template == "B":
        h, g, b, _ = paired
    svc, repo, graph = configured(h, (1, 2) if b else (1,))
    req = request(g, b)
    record = run(graph.start(req))
    assert record["status"] == "completed", record
    TASK_RECORD.validate_python(record)
    content = record["final_research_content"]
    assert len(content["financial_facts"]) == 6 and len(content["deterministic_analysis"]) == 3
    assert content["human_review_status"] == "pending"
    assert all(
        i["validation_status"] == "pending_semantic_review"
        for i in content["model_interpretations"]
    )
    assert not content["verified_operating_attribution"]
    assert content["test_mode"] == "simulated_test"
    assert all(not f["production_calculable"] for f in content["financial_facts"])
    assert record["budget"]["used"]["model_calls"] == svc.model.calls == 1
    assert run(graph.start(req)) == record
    assert repo.public(record)["publication_eligibility"]["status"] == "current_at_read"
    corrupt = copy.deepcopy(record)
    corrupt["final_research_content"]["model_interpretations"][0][
        "verified_operating_attribution"
    ] = True
    with pytest.raises(ValidationError):
        TASK_RECORD.validate_python(corrupt)


def test_real_interrupt_then_v2_resume_cumulative(saved):
    h, g, _ = saved
    svc, repo, graph = configured(h)
    wait = run(graph.start(request(g, confirmed=False)))
    assert wait["waiting_checkpoint"] and wait["budget"]["used"]["tool_calls"] == 14
    restored = run(graph.resume(wait["task_id"], resume(g, wait)))
    assert restored["status"] == "completed", restored
    assert restored["budget"]["used"] == dict(
        steps=34, tool_calls=25, retrieval_total=12, model_calls=1
    )
    assert svc.model.calls == 1


@pytest.mark.parametrize(
    "failure",
    [
        "no_model",
        "empty",
        "bad_citation",
        "protocol",
        "financial_number",
        "foreign",
        "budget",
        "unknown",
    ],
)
def test_failure_never_publishes_result_or_retries_unknown(saved, failure):
    h, g, _ = saved
    svc, repo, graph = configured(h)
    req = request(g)
    if failure == "no_model":
        svc.model = None
    elif failure == "empty":
        svc.scope.search = AsyncMock(return_value=())
    elif failure == "bad_citation":
        svc.model = Scripted(final(response((12,))), final(response((12,))))
    elif failure == "protocol":
        svc.model = Scripted(final('{"decision":"answer","amount":"123"}'), final("bad json"))
    elif failure == "financial_number":
        raw = json.loads(response())
        raw["interpretations"][0]["text"] = "营业收入增加123亿元，利润增长20%"
        svc.model = Scripted(final(json.dumps(raw)), final(json.dumps(raw)))
    elif failure == "foreign":
        svc.scope.search = AsyncMock(
            return_value=(
                SearchHit(
                    chunk_id="evil",
                    text="外部证据",
                    page=1,
                    score=1.0,
                    source_file="fake.pdf",
                    type="paragraph",
                    workspace_id="demo",
                    document_id="foreign",
                    source_revision="0" * 64,
                ),
            )
        )
    elif failure == "budget":
        original = repo.start

        def exhausted(req):
            record, claim = original(req)
            b = ExecutionBudget.restore(
                record["budget"], checkpoint=lambda v: repo.reserve(record["task_id"], claim, v)
            )
            b.model_calls = 2
            b.checkpoint()
            return repo.get(record["task_id"]), claim

        repo.start = exhausted
    elif failure == "unknown":
        svc.model = Scripted(ProviderCallError(retryable=True), final(response()))
    record = run(graph.start(req))
    assert record["status"] in ("failed", "refused"), record
    assert record["final_research_content"] is None
    assert record["snapshot"]["analysis_results"] == []
    assert record["snapshot"]["operating_evidence"] is None
    if failure == "unknown":
        assert svc.model.calls == record["budget"]["used"]["model_calls"] == 1
        assert run(graph.start(req)) == record
    if failure == "budget":
        assert record["error_code"] == "budget_model_calls_exhausted" and svc.model.calls == 0


def test_single_bounded_protocol_repair_succeeds(saved):
    h, g, _ = saved
    svc, repo, graph = configured(h)
    svc.model = Scripted(final("bad json"), final(response()))
    record = run(graph.start(request(g)))
    assert record["status"] == "completed", record
    assert record["budget"]["used"]["model_calls"] == svc.model.calls == 2
    assert [m["validation"] for m in record["final_research_content"]["model_attempts"]] == [
        "invalid_protocol_or_citation",
        "accepted_protocol_and_provenance",
    ]


@pytest.mark.parametrize("when", ["before_release", "after_release"])
@pytest.mark.parametrize("change", ["receipt", "source"])
def test_revocation_joint_transaction_and_current_read_qualification(saved, monkeypatch, when, change):
    h, g, _ = saved
    svc, repo, graph = configured(h)
    original = repo.release

    def revoke():
        if change == "source":
            changed = h.client.post(f"/documents/{h.id}/binding-corrections", json=dict(
                expected_attempt=1, metadata={**metadata(h.company.company_id,2031), "basis":"unknown"},
                reason="D21 controlled final source correction race"))
            assert changed.status_code == 200
            return
        h.receipts.revoke_financial_receipt(
            workspace_id="demo",
            receipt_id=g.receipt.receipt_id,
            confirmation_kind="simulated_test",
            reason="D21 controlled final commit race",
        )

    if when == "before_release":

        def race(*args, **kwargs):
            revoke()
            return original(*args, **kwargs)

        monkeypatch.setattr(repo, "release", race)
    record = run(graph.start(request(g)))
    if when == "before_release":
        assert record["status"] == "refused" and record["final_research_content"] is None
    else:
        assert record["status"] == "completed"
        revoke()
        assert (
            repo.public(repo.get(record["task_id"]))["publication_eligibility"]["status"]
            == "invalidated"
        )
        assert repo.get(record["task_id"]) == record  # Historical snapshot unchanged.


def test_unknown_save_withholds_completion_and_startup_no_replay(saved, monkeypatch):
    h, g, _ = saved
    svc, repo, graph = configured(h)
    req = request(g)
    monkeypatch.setattr(
        repo, "release", lambda *a, **k: (_ for _ in ()).throw(HistoryError("injected"))
    )
    with pytest.raises(HistoryError):
        run(graph.start(req))
    raw = repo.by_operation(req.operation_id)
    public = repo.public(raw)
    assert public["execution_status"] == "running"
    assert public["status"] != "completed" and public["final_research_content"] is None
    assert run(graph.start(req)) == raw and svc.model.calls == 1
    repo.recover_interrupted()
    failed = repo.by_operation(req.operation_id)
    assert (
        failed["error_code"] == "interrupted_unknown_execution"
        and failed["final_research_content"] is None
    )
    assert svc.model.calls == 1


def test_production_rejects_simulated_fact_ids_before_model(saved):
    h, g, _ = saved
    svc, repo, graph = configured(h)
    graph.templates = service(h, simulated=False)
    graph.templates.model = svc.model
    record = run(graph.start(request(g)))
    assert record["status"] == "awaiting_human_confirmation" and svc.model.calls == 0
    refused = run(graph.resume(record["task_id"], resume(g, record)))
    assert refused["status"] == "refused" and svc.model.calls == 0


@pytest.mark.parametrize("text", ["营业收入增长七个百分点", "归母净利润增长百分之三", "现金流量为一百亿元", "营业收入翻番", "营业收入增加⑦亿元"])
def test_generated_chinese_or_unicode_financial_numbers_are_rejected(saved, text):
    h, g, _ = saved
    svc, repo, graph = configured(h)
    raw = json.loads(response())
    raw["interpretations"][0]["text"] = text
    svc.model = Scripted(final(json.dumps(raw)), final(json.dumps(raw)))
    record = run(graph.start(request(g)))
    assert record["status"] == "failed" and record["error_code"] == "operating_output_invalid"
    assert record["final_research_content"] is None and svc.model.calls == 2


def test_budget_only_stage_a_v2_plan_v1_reads_and_resumes_without_upgrade_or_refund(saved):
    from contextlib import closing
    h,g,_ = saved
    svc,repo,graph = configured(h)
    waiting = run(graph.start(request(g, confirmed=False)))
    # Exact previous-stage shape: v2 task/budget with the original NULL-only PlanResult.
    legacy = copy.deepcopy(waiting)
    legacy["snapshot"]["schema_version"] = "operating-research-plan-v1"
    legacy["snapshot"].pop("model_attempts")
    legacy["snapshot"].pop("evidence_appendix")
    with closing(repo.registry._connect()) as conn, conn:
        repo.write(conn,legacy,None)
    restored = repo.get(legacy["task_id"])
    assert restored == legacy and svc.model.calls == 0
    assert restored["budget"] == waiting["budget"]
    assert restored["snapshot"]["final_research_content"] is None
    completed = run(graph.resume(restored["task_id"], resume(g, restored)))
    assert completed["status"] == "completed" and svc.model.calls == 1
    assert completed["budget"]["used"]["tool_calls"] == 25
    assert completed["snapshot"]["schema_version"] == "operating-research-plan-v2"
