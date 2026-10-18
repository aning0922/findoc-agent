"""Actual RAG guard, Chinese clause polarity; controlled evidence/model only."""

import asyncio
from dataclasses import replace
import pytest
from tests.test_d16_qa import scope, prepared, service  # noqa: F401

CASES = [
    ("请列营业收入原值，不计算同比", False),
    ("请列净利润原值，无需计算增长率", False),
    ("仅摘录原值，不要计算同比和差额", False),
    ("不要算同比，请列原值", False),
    ("请勿计算差额", False),
    ("营业收入原值，不求增幅", False),
    ("同比不要计算，只列原值", False),
    ("仅列原文，无需计算", False),
    ("不需要计算同比", False),
    ("不必计算同比", False),
    ("不用算相差", False),
    ("只取原值，别算同比", False),
    ("不要进行同比计算", False),
    ("不做同比计算", False),
    ("列原值，勿计算差额", False),
    ("不计算同比、增长率与差额", False),
    ("列营业收入原值", False),
    ("请计算营业收入同比", True),
    ("计算增幅", True),
    ("求增长率", True),
    ("两期相差多少", True),
    ("增长了多少", True),
    ("不要算同比但计算差额", True),
    ("不计算增长率，但求差额", True),
    ("不要计算差额，营业收入同比是多少", True),
    ("别不计算同比", True),
    ("不要不计算同比", True),
    ("不计算同比吗", True),
    ("是否不计算同比", True),
    ("不只计算同比", True),
    ("不是不计算同比", True),
    ("不计算同比，增幅呢", True),
    ("同比", True),
    ("不要算同比或算差额", True),
    ("不计算同比增长率", True),
    ("不要计算差额而是同比", True),
    ("请列原值；但净利润差额是多少", True),
]


@pytest.mark.parametrize("query,requires", CASES)
def test_chinese_calculation_polarity_preserves_deterministic_gate(scope, query, requires):  # noqa: F811
    rag, adapter, model = service(scope)
    selected = replace(prepared(scope), query=query)
    result = asyncio.run(rag.answer_selected(selected, adapter))
    assert result["outcome"] == ("refused" if requires else "answered"), result
    if requires:
        assert result["reason"] == "requires_confirmed_financial_analysis"
        assert not result["content"] and not result["citations"]
        assert model.generate.call_count == 0
    else:
        assert model.generate.call_count == 1
    # D27 denies calculation intent before expensive BGE/Milvus retrieval.
    assert adapter.search.call_count == (0 if requires else 1)


def test_unsupported_geometry_is_explicit_refusal_with_full_identity(scope):  # noqa: F811
    from unittest.mock import AsyncMock
    from app.documents.source_models import SourceError
    from app.research.models import Result

    rag, adapter, model = service(scope)
    adapter.table_context = AsyncMock(side_effect=SourceError("table_structure_unsupported"))
    selected = prepared(scope)
    result = asyncio.run(rag.answer_selected(selected, adapter))
    assert result["outcome"] == "refused" and result["reason"] == "unsupported_table_structure"
    assert not result["content"] and not result["citations"]
    assert model.generate.call_count == 0 and len(result["documents"]) == 2
    Result.model_validate(result)
