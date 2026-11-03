"""Synthetic root integration: strict nonnumeric template explanation, fake provider only."""

from uuid import uuid4

import pytest

from tests.test_cplus_g4_templates_drafts import rig as rig, run_template


@pytest.mark.parametrize(
    "text",
    [
        "2024年经营现金流为46383114754.02元，2025年为29369250570.66元。",
        "二〇二四年利润增长百分之十。",
        "现金流增长３％。",
        "经营现金流为壹佰万元。",
        "统一口径后进一步分析。",  # Intentional conservative false positive.
    ],
)
def test_numeric_explanation_withheld_without_retry_and_child_retained(rig, monkeypatch, text):
    _, client, service, _, refs, _ = rig
    calls = []

    async def fake_once(question, evidence):
        calls.append(question)
        return {"text": text}

    monkeypatch.setattr(service.hybrid, "provider", fake_once)
    body, result = run_template(rig, "cash", refs[:2], generate_explanation=True)
    assert len(calls) == 1 and len(result["financial_points"]) == 10
    assert result["question"] == body["question"]
    assert result["interpretation"] is None
    assert result["provider_outcome"] == "numeric_claim_requires_review"
    assert result["interpretation_policy"] == "non_numeric_review_v1"
    assert result["financial_authority"] is False
    child = next(c for c in result["child_operations"] if c["label"] == "explanation-once")
    assert child["state"] == "completed" and child["result_ref"]
    raw = client.get("/cplus/research/answers/" + child["result_ref"])
    assert raw.status_code == 200, raw.text
    assert raw.json()["interpretation"] == text  # Original immutable child is reviewable.
    assert "不得按摘录顺序拼接年份与金额" in calls[0]
    assert "不得将fast来源称为OCR" in calls[0]
    assert "不得输出金额、比率、年份" in calls[0]
    assert len(calls[0]) <= 2000
    # Completed original operation recovery only; no second provider attempt.
    assert client.post("/cplus/template-runs", json=body).json()["result"] == result
    assert (
        client.get("/cplus/template-runs/operations/" + body["operation_id"]).json()["result"]
        == result
    )
    history = client.get("/cplus/template-runs/" + result["run_id"]).json()
    assert (
        history["interpretation"] is None
        and history["financial_points"] == result["financial_points"]
    )
    assert len(calls) == 1


def test_nonnumeric_explanation_remains_unreviewed_once(rig, monkeypatch):
    calls = []

    async def fake_once(question, evidence):
        calls.append(question)
        return {"text": "仍需结合原文核查经营现金流与利润口径，原因待审。"}

    monkeypatch.setattr(rig[2].hybrid, "provider", fake_once)
    _, result = run_template(rig, "cash", rig[4][:2], generate_explanation=True)
    assert len(calls) == 1
    assert result["interpretation"] == "仍需结合原文核查经营现金流与利润口径，原因待审。"
    assert result["provider_outcome"] == "returned"
    assert result["interpretation_review_status"] == "ai_unreviewed"
    assert result["interpretation_policy"] == "non_numeric_review_v1"
    assert result["financial_authority"] is False


def test_child_question_bounded_full_original_question_preserved(rig, monkeypatch):
    question = "主要业务。" + "风险待核查。" * 332 + "原文。"  # Exactly 2000 characters.
    assert len(question) == 2000
    calls = []

    async def fake_once(question, evidence):
        calls.append(question)
        return {"text": "仍需回到完整原文核查。"}

    monkeypatch.setattr(rig[2].hybrid, "provider", fake_once)
    body = dict(
        operation_id=str(uuid4()),
        template_id="overview",
        template_version="cplus-template-v1",
        question=question,
        selected_sources=[rig[4][1]],
        generate_explanation=True,
    )
    response = rig[1].post("/cplus/template-runs", json=body)
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["question"] == question
    assert len(calls) == 1 and len(calls[0]) <= 2000
    assert "原问题已截尾" in calls[0]
    assert result["interpretation"] == "仍需回到完整原文核查。"
