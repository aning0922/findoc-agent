"""规则/状态定向测试；手写 SearchHit 和检索替身不代表实际上传链证据。"""

import asyncio
from dataclasses import replace
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from app.agent.financial_facts import FinancialUnit
from app.agent.research_workflow import (
    RevenueCandidate,
    RevenueEvidence,
    RevenueWorkflowFailureCode as Failure,
    RevenueWorkflowStage as Stage,
    RevenueWorkflowTransitionError,
    calculate_confirmed_revenue_growth,
    confirm_revenue_candidates,
)
from app.agent.revenue_extraction import (
    REVENUE_QUERY,
    RevenueCandidateCollection,
    RevenueCandidateService,
    extract_revenue_candidates,
)
from app.documents.preparation import DocumentTaskPreparer, PreparedDocumentTask
from app.rag.retriever import Retriever, SearchFilters, SearchHit, TrustedContext


def _prepared() -> PreparedDocumentTask:
    return PreparedDocumentTask(
        query=REVENUE_QUERY,
        context=TrustedContext("demo"),
        filters=SearchFilters(document_id="doc-A"),
        source_file="synthetic.pdf",
    )


def _hit(text: str, *, chunk_id: str = "chunk-1", page: int = 1) -> SearchHit:
    """测试专用命中替身；生产验证另用真实 BGE/Milvus/上传 API。"""
    return SearchHit(
        score=0.8,
        chunk_id=chunk_id,
        text=text,
        page=page,
        source_file="synthetic.pdf",
        type="paragraph",
        workspace_id="demo",
        document_id="doc-A",
    )


def _collect(*hits: SearchHit) -> RevenueCandidateCollection:
    return extract_revenue_candidates(prepared=_prepared(), hits=hits)


def test_same_chunk_two_years_have_distinct_refs_and_reviewable_raw_evidence() -> None:
    """同片段两年不误合并，原数字/单位/位置可回看，收集不产生确认事实。"""
    text = "合成资料\n2024年度营业收入：81.25万元。\n2025年度营业收入：9,765,432.10元。"
    output = _collect(_hit(text))
    state = output.state
    assert state.stage is Stage.AWAITING_CONFIRMATION
    previous, current = state.candidates
    assert previous.value == Decimal("812500")
    assert current.value == Decimal("9765432.10")
    assert {item.unit for item in state.candidates} == {FinancialUnit.CNY_YUAN}
    assert previous.source_ref != current.source_ref
    assert previous.chunk_id == current.chunk_id
    for candidate in state.candidates:
        (evidence,) = candidate.evidence
        assert evidence.text == text
        assert evidence.text[evidence.start : evidence.end].startswith(str(candidate.period))
        assert candidate.extraction_method == "revenue_line_rule"
        assert candidate.extraction_version == "v1"
    assert previous.evidence[0].raw_value == "81.25"
    assert previous.evidence[0].raw_unit == "万元"
    assert current.evidence[0].raw_value == "9,765,432.10"
    assert state.confirmed_facts == () and state.result is None
    with pytest.raises(RevenueWorkflowTransitionError):
        calculate_confirmed_revenue_growth(state)


def test_repeat_search_only_deduplicates_identical_evidence_ignoring_score() -> None:
    hit = _hit("2024年度营业收入：81.25万元。\n2025年度营业收入：96万元。")
    single = _collect(hit).state
    repeated = _collect(hit, replace(hit, score=0.99)).state
    assert repeated == single
    assert all(len(item.evidence) == 1 for item in repeated.candidates)


def test_equal_values_merge_all_sources_after_unit_conversion_and_are_order_independent() -> None:
    a = _hit("2024年度营业收入：81万元。\n2025年度营业收入：96万元。")
    b = _hit("2025年度营业收入：0.0096亿元。", chunk_id="chunk-3", page=3)
    output = _collect(a, b)
    assert output.state == _collect(b, a).state
    assert output.state.stage is Stage.AWAITING_CONFIRMATION
    current = output.state.candidates[1]
    assert current.value == Decimal("960000")
    assert {item.page for item in current.evidence} == {1, 3}
    assert {item.raw_unit for item in current.evidence} == {"万元", "亿元"}
    assert len(current.evidence) == 2


def test_distinct_occurrences_in_one_chunk_remain_two_supporting_sources() -> None:
    output = _collect(
        _hit("2024年度营业收入：81万元。\n2025年度营业收入：96万元。\n2025年度营业收入：96万元。")
    )
    current = output.state.candidates[1]
    assert len(current.evidence) == 2
    assert len({item.start for item in current.evidence}) == 2


def test_conflicting_values_do_not_select_the_higher_score_or_confirm() -> None:
    a = _hit("2024年度营业收入：81万元。\n2025年度营业收入：96万元。")
    b = replace(_hit("2025年度营业收入：98万元。", chunk_id="chunk-2"), score=0.99)
    output = _collect(a, b)
    assert output.state.stage is Stage.FAILED
    assert output.state.failure_code is Failure.CANDIDATE_CONFLICT
    assert {c.value for c in output.state.candidates if c.period == 2025} == {
        Decimal("960000"),
        Decimal("980000"),
    }
    assert output.state.confirmed_facts == () and output.state.result is None
    with pytest.raises(RevenueWorkflowTransitionError):
        confirm_revenue_candidates(output.state)


@pytest.mark.parametrize("raw_unit", ["", "美元", "未知", "万元（未经审计）"])
def test_unknown_unit_reaches_existing_unit_unknown_gate(raw_unit: str) -> None:
    output = _collect(_hit(f"2024年度营业收入：81万元。\n2025年度营业收入：96{raw_unit}。"))
    assert output.state.failure_code is Failure.UNIT_UNKNOWN
    current = output.state.candidates[1]
    assert current.unit is None and current.value == Decimal("96")
    assert current.evidence[0].raw_unit == (raw_unit or None)
    with pytest.raises(RevenueWorkflowTransitionError):
        confirm_revenue_candidates(output.state)


def test_document_unit_note_is_not_guessed_as_a_missing_line_unit() -> None:
    output = _collect(_hit("2024年度营业收入：81万元。\n2025年度营业收入：96。\n金额单位：万元。"))
    assert output.state.failure_code is Failure.UNIT_UNKNOWN


@pytest.mark.parametrize(
    ("field", "value", "failure"),
    [
        ("workspace_id", None, Failure.SOURCE_INVALID),
        ("document_id", None, Failure.SOURCE_INVALID),
        ("workspace_id", "other", Failure.SCOPE_MISMATCH),
        ("document_id", "doc-B", Failure.SCOPE_MISMATCH),
        ("source_file", "other.pdf", Failure.SCOPE_MISMATCH),
        ("chunk_id", "", Failure.SOURCE_INVALID),
        ("page", 0, Failure.SOURCE_INVALID),
        ("page", True, Failure.SOURCE_INVALID),
    ],
)
def test_invalid_source_blocks_whole_batch_instead_of_fabricating_or_keeping_partial(
    field: str,
    value: object,
    failure: Failure,
) -> None:
    valid = _hit("2024年度营业收入：81万元。\n2025年度营业收入：96万元。")
    invalid = replace(_hit("2025年度营业收入：96万元。", chunk_id="chunk-2"), **{field: value})
    for hits in ((valid, invalid), (invalid, valid)):
        output = _collect(*hits)
        assert output.state.failure_code is failure
        assert output.state.candidates == ()
        assert output.hits == hits


def test_same_chunk_with_changed_text_is_source_invalid_even_when_amounts_match() -> None:
    a = _hit("2024年度营业收入：81万元。\n2025年度营业收入：96万元。")
    b = replace(a, text=a.text + "\n内容变化")
    assert _collect(a, b).state.failure_code is Failure.SOURCE_INVALID


@pytest.mark.parametrize(
    "hits", [(), (_hit("2024年度营业收入：81万元。"),), (_hit("2025年度净利润：96万元。"),)]
)
def test_empty_missing_or_other_metric_has_missing_candidate_exit(
    hits: tuple[SearchHit, ...],
) -> None:
    output = _collect(*hits)
    assert output.state.failure_code is Failure.MISSING_CANDIDATE


def test_wrong_period_is_retained_as_diagnostic_never_relabelled() -> None:
    output = _collect(_hit("2023年度营业收入：79万元。\n2024年度营业收入：81万元。"))
    assert output.state.failure_code is Failure.PERIOD_MISMATCH
    assert output.excluded_periods == (2023,)
    assert [c.period for c in output.state.candidates] == [2024]


def test_extra_period_does_not_block_complete_target_periods() -> None:
    output = _collect(
        _hit("2023年度营业收入：79万元。\n2024年度营业收入：81万元。\n2025年度营业收入：96万元。")
    )
    assert output.state.stage is Stage.AWAITING_CONFIRMATION
    assert output.excluded_periods == (2023,)


def test_table_format_is_explicitly_outside_line_rule_capability() -> None:
    hit = replace(_hit("| 年份 | 营业收入 |\n| 2024 | 81万元 |\n| 2025 | 96万元 |"), type="table")
    assert _collect(hit).state.failure_code is Failure.MISSING_CANDIDATE


@pytest.mark.parametrize("raw", ["12,34", "1.2.3", "1e6"])
def test_unsupported_number_syntax_is_not_partially_extracted(raw: str) -> None:
    output = _collect(_hit(f"2024年度营业收入：81万元。\n2025年度营业收入：{raw}元。"))
    assert output.state.failure_code is Failure.MISSING_CANDIDATE
    assert [candidate.period for candidate in output.state.candidates] == [2024]


def test_unknown_unit_is_not_merged_with_a_known_amount_of_the_same_digits() -> None:
    a = _hit("2024年度营业收入：81元。\n2025年度营业收入：96元。")
    b = _hit("2025年度营业收入：96。", chunk_id="chunk-2")
    output = _collect(a, b)
    assert output.state.failure_code is Failure.UNIT_UNKNOWN
    assert (
        len([candidate for candidate in output.state.candidates if candidate.period == 2025]) == 2
    )


def test_long_decimal_conversion_does_not_round_through_float_or_default_context() -> None:
    raw = "12345678901234567890123456789.123456789"
    output = _collect(_hit(f"2024年度营业收入：1元。\n2025年度营业收入：{raw}万元。"))
    assert output.state.candidates[1].value == Decimal("123456789012345678901234567891234.56789")


def test_service_uses_ready_preparation_and_actual_retriever_contract_with_labelled_doubles() -> (
    None
):
    """接线测试使用 fake embedding/store；不作为真实检索质量证据。"""
    preparer = Mock(spec=DocumentTaskPreparer)
    preparer.prepare = AsyncMock(return_value=_prepared())
    hit = _hit("2024年度营业收入：81万元。\n2025年度营业收入：96万元。")
    store = Mock()
    store.search.return_value = [vars(hit)]
    embedder = Mock(return_value=[[0.1, 0.2]])
    service = RevenueCandidateService(preparer=preparer, retriever=Retriever(embedder, store))
    result = asyncio.run(service.collect(document_id="requested-id"))
    preparer.prepare.assert_awaited_once_with(document_id="requested-id", query=REVENUE_QUERY)
    embedder.assert_called_once_with([REVENUE_QUERY])
    assert store.search.call_args.kwargs["filter_expression"] == (
        'workspace_id == "demo" and document_id == "doc-A"'
    )
    assert result.state.stage is Stage.AWAITING_CONFIRMATION


def test_evidence_span_and_candidate_numeric_type_are_validated() -> None:
    with pytest.raises(ValueError, match="原始数字"):
        RevenueEvidence("chunk", "file.pdf", 1, "原文81万元", 0, 6, "96", "万元")
    with pytest.raises(TypeError, match="Decimal"):
        RevenueCandidate("demo", "doc", "ref", "chunk", "file.pdf", 1, 2024, 1.2, None)  # type: ignore[arg-type]
