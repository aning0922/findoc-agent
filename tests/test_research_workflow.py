from decimal import Decimal

import pytest

from app.agent.financial_facts import FinancialUnit
from app.agent.research_workflow import (
    RevenueCandidate,
    RevenueWorkflowFailureCode,
    RevenueWorkflowStage,
    RevenueWorkflowTransitionError,
    begin_revenue_workflow,
    calculate_confirmed_revenue_growth,
    confirm_revenue_candidates,
    record_revenue_candidates,
)


def _candidate(
    *,
    period: int,
    value: str,
    source_ref: str,
    unit: FinancialUnit | None = FinancialUnit.CNY_YUAN,
) -> RevenueCandidate:
    """构造同一合成文档中已规范为人民币元的营业收入候选。"""
    return RevenueCandidate(
        workspace_id="demo",
        document_id="doc-A",
        source_ref=source_ref,
        chunk_id="chunk-page-1",
        source_file="synthetic_finance.pdf",
        page=1,
        period=period,
        value=Decimal(value),
        unit=unit,
    )


def test_confirmed_candidates_produce_traceable_deterministic_growth() -> None:
    """正常链必须经过候选检查和明确确认，再产生20.00%带来源结果。"""
    state = begin_revenue_workflow(workspace_id="demo", document_id="doc-A")
    state = record_revenue_candidates(
        state,
        (
            _candidate(period=2024, value="1000000", source_ref="revenue-2024"),
            _candidate(period=2025, value="1200000", source_ref="revenue-2025"),
        ),
    )

    assert state.stage is RevenueWorkflowStage.AWAITING_CONFIRMATION
    assert state.confirmed_facts == ()
    assert state.result is None

    with pytest.raises(RevenueWorkflowTransitionError):
        calculate_confirmed_revenue_growth(state)

    state = confirm_revenue_candidates(state)
    assert state.stage is RevenueWorkflowStage.READY_FOR_CALCULATION
    assert [item.fact.period for item in state.confirmed_facts] == [2024, 2025]

    state = calculate_confirmed_revenue_growth(state)

    assert state.stage is RevenueWorkflowStage.COMPLETED
    assert state.failure_code is None
    assert state.result is not None
    assert state.result.value == Decimal("20.00")
    assert state.result.unit == "PERCENT"
    assert state.result.formula_id == "revenue_growth_rate_v1"
    assert [item.fact.period for item in state.result.sources] == [2025, 2024]
    assert {item.chunk_id for item in state.result.sources} == {"chunk-page-1"}
    assert {item.page for item in state.result.sources} == {1}


def test_conflicting_candidate_is_terminal_and_cannot_be_confirmed() -> None:
    """同期出现两个候选时由程序终止，不允许模型自动选择。"""
    state = begin_revenue_workflow(workspace_id="demo", document_id="doc-A")
    state = record_revenue_candidates(
        state,
        (
            _candidate(period=2024, value="1000000", source_ref="revenue-2024"),
            _candidate(period=2025, value="1200000", source_ref="revenue-2025-a"),
            _candidate(period=2025, value="1180000", source_ref="revenue-2025-b"),
        ),
    )

    assert state.stage is RevenueWorkflowStage.FAILED
    assert state.failure_code is RevenueWorkflowFailureCode.CANDIDATE_CONFLICT
    assert state.confirmed_facts == ()
    assert state.result is None

    with pytest.raises(RevenueWorkflowTransitionError):
        confirm_revenue_candidates(state)


def test_unknown_unit_is_terminal_and_cannot_be_confirmed() -> None:
    """候选数量合法但任一单位不明时，进入独立失败终态。"""
    state = begin_revenue_workflow(workspace_id="demo", document_id="doc-A")
    state = record_revenue_candidates(
        state,
        (
            _candidate(period=2024, value="1000000", source_ref="revenue-2024"),
            _candidate(
                period=2025,
                value="120",
                source_ref="revenue-2025",
                unit=None,
            ),
        ),
    )

    assert state.stage is RevenueWorkflowStage.FAILED
    assert state.failure_code is RevenueWorkflowFailureCode.UNIT_UNKNOWN
    assert state.confirmed_facts == ()
    assert state.result is None

    with pytest.raises(RevenueWorkflowTransitionError):
        confirm_revenue_candidates(state)
