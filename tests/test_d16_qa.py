"""Multi-source evidence/API boundaries; model outputs here are controlled protocol tests."""

import asyncio
from dataclasses import replace
import json
from unittest.mock import AsyncMock, Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.research_qa import create_research_qa_router
from app.documents.source_models import SourceError
from app.rag.retriever import SearchHit
from app.rag.selected_evidence import build_selected_evidence, validate_selected_output
from app.rag.service import CitationValidationError, RAGService
from tests.test_d15_selection import scope as source_scope

scope = source_scope


def prepared(scope):
    return asyncio.run(
        scope[0].prepare_many(document_ids=["doc-0", "doc-1"], query="主营业务是什么")
    )


def hits():
    return tuple(
        SearchHit(
            score=0.9,
            chunk_id="same-chunk",
            text="原文收入2024年100元，2025年200元。",
            page=1,
            source_file="report.pdf",
            type="paragraph",
            workspace_id="demo",
            document_id=f"doc-{i}",
            source_revision=str(i) * 64,
        )
        for i in range(2)
    )


def answer(number=1, quote=None):
    item = dict(number=number)
    if quote is not None:
        item["quote"] = quote
    return json.dumps(dict(decision="answer", quotes=[item]))


def test_compound_identity_preserves_duplicate_text(scope):
    selection = prepared(scope)
    evidence = build_selected_evidence(hits(), selection)
    assert len(evidence.context.hits_by_number) == 2
    a = validate_selected_output(answer(1), evidence)["citations"][0]
    b = validate_selected_output(answer(2), evidence)["citations"][0]
    assert a["document_id"] != b["document_id"] and a["source_revision"] != b["source_revision"]
    assert a["chunk_id"] == b["chunk_id"]


@pytest.mark.parametrize(
    "bad",
    [
        '{"decision":"answer","quotes":[{"number":99,"quote":"x"}]}',
        '{"decision":"answer","quotes":[],"page":1}',
        '{"decision":"refuse","decision":"refuse"}',
        answer(1, "原文收入2024年200元，2025年100元。"),
        answer(1, "200元"),
        answer(1, "原文收入2024年100万元，2025年200万元。"),
    ],
)
def test_citation_numeric_year_unit_or_protocol_tamper_rejected(scope, bad):
    with pytest.raises((CitationValidationError, ValueError)):
        validate_selected_output(bad, build_selected_evidence(hits(), prepared(scope)))


@pytest.mark.parametrize(
    "field,value",
    [
        ("document_id", "foreign"),
        ("workspace_id", "other"),
        ("source_revision", None),
        ("document_id", None),
    ],
)
def test_foreign_or_missing_hit_identity_rejected(scope, field, value):
    with pytest.raises(CitationValidationError):
        build_selected_evidence((replace(hits()[0], **{field: value}),), prepared(scope))


def test_same_evidence_identity_cannot_change_contents(scope):
    with pytest.raises(CitationValidationError):
        build_selected_evidence((hits()[0], replace(hits()[0], text="tampered")), prepared(scope))


def test_table_requires_whole_table_and_original_page_context(scope):
    h = replace(hits()[0], type="table", table_md="|年份|2024|2025|\n|营业收入|100|200|")
    with pytest.raises(CitationValidationError):
        build_selected_evidence((h,), prepared(scope))
    ev = build_selected_evidence(
        (h,),
        prepared(scope),
        table_context={("doc-0", "0" * 64, 1): "合并利润表 单位：人民币元\n" + h.table_md},
    )
    with pytest.raises(CitationValidationError):
        validate_selected_output(answer(1, h.table_md), ev)
    result = validate_selected_output(answer(1), ev)
    assert "单位：人民币元" in result["content"]


def service(scope, model=None, found=None):
    adapter = Mock(
        search=AsyncMock(return_value=hits() if found is None else found),
        table_context=AsyncMock(return_value={}),
        revalidate=AsyncMock(),
    )
    model = model or Mock(generate=Mock(return_value=answer()))
    rag = RAGService(
        retriever=Mock(),
        llm_client=model,
        evidence_gate=Mock(allows=Mock(return_value=True)),
        max_evidence_chars=4000,
    )
    return rag, adapter, model


def test_generation_then_final_revalidation_and_no_publish_on_source_change(scope):
    rag, adapter, model = service(scope)

    def generate(prompt):
        adapter.revalidate.side_effect = SourceError("selection_changed")
        return answer()

    model.generate.side_effect = generate
    result = asyncio.run(rag.answer_selected(prepared(scope), adapter))
    assert result["outcome"] == "system_error" and result["error_code"] == "source_changed"
    assert result["content"] == "" and result["citations"] == []


@pytest.mark.parametrize(
    "failure", ["empty", "retrieval", "llm", "citation", "refuse", "calculation"]
)
def test_success_refusal_system_error_are_distinct(scope, failure):
    rag, adapter, model = service(scope)
    selection = prepared(scope)
    expected = "system_error"
    if failure == "empty":
        adapter.search.return_value = ()
        expected = "refused"
    elif failure == "retrieval":
        adapter.search.side_effect = OSError("index failed")
    elif failure == "llm":
        model.generate.side_effect = RuntimeError("private provider details")
    elif failure == "citation":
        model.generate.return_value = answer(99)
    elif failure == "refuse":
        model.generate.return_value = '{"decision":"refuse"}'
        expected = "refused"
    else:
        selection = replace(selection, query="计算营业收入同比")
        expected = "refused"
    result = asyncio.run(rag.answer_selected(selection, adapter))
    assert result["outcome"] == expected
    assert "private provider details" not in json.dumps(result)
    assert not result["content"] and not result["citations"]
    if failure in ("empty", "calculation"):
        model.generate.assert_not_called()


def test_api_reprepares_and_rejects_client_authority(scope):
    rag, adapter, _ = service(scope)
    app = FastAPI()
    app.include_router(create_research_qa_router(scope[0], adapter, rag))
    client = TestClient(app)
    body = dict(document_ids=["doc-0", "doc-1"], query="主营业务是什么")
    r = client.post("/research/questions", json=body)
    assert r.status_code == 200 and r.json()["outcome"] == "answered"
    assert r.json()["citations"][0]["document_id"] == "doc-0"
    for field in ["selection_id", "workspace_id", "source_revision", "filter_expression"]:
        assert client.post("/research/questions", json={**body, field: "x"}).status_code == 422
    assert (
        client.post("/research/questions", json={**body, "document_ids": ["foreign"]}).status_code
        == 404
    )
    assert (
        client.post(
            "/research/questions", json={**body, "document_ids": ["doc-0", "doc-0"]}
        ).status_code
        == 422
    )
    adapter.search.side_effect = RuntimeError("index failure")
    assert client.post("/research/questions", json=body).status_code == 503
