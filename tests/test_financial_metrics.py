from decimal import Decimal
from unittest.mock import Mock

from pydantic import ValidationError
import pytest
from app.agent.finance_tools import (
    CalculateFinancialMetricArguments,
    CalculateFinancialMetricTool,
    FinancialMetricError,
    FinancialMetricErrorCode,
)
from app.agent.financial_facts import (
    FinancialFact,
    FinancialFactKey,
    FinancialFactRepository,
    FinancialUnit,
    InMemoryFinancialFactRepository,
)
from app.agent.tool_loop import ToolExecutionContext
from app.rag.retriever import SearchFilters, TrustedContext


def test_financial_fact_accepts_traceable_decimal_value() -> None:
    """验证可追踪十进制数值。"""
    fact = FinancialFact(
        workspace_id="WS-A",
        document_id="DOC-1",
        source_ref="source-1",
        fact_key=FinancialFactKey.REVENUE,
        period=2025,
        value=Decimal("100"),
        unit=FinancialUnit.CNY_100_MILLION,
    )
    assert (
        fact.workspace_id,
        fact.document_id,
        fact.source_ref,
        fact.fact_key,
        fact.period,
        fact.value,
        fact.unit,
    ) == (
        "WS-A",
        "DOC-1",
        "source-1",
        FinancialFactKey.REVENUE,
        2025,
        Decimal("100"),
        FinancialUnit.CNY_100_MILLION,
    )


def test_financial_fact_rejects_bool_as_numeric_value() -> None:
    """验证布尔值被拒绝作为数值。"""
    with pytest.raises(TypeError):
        FinancialFact(
            workspace_id="WS-A",
            document_id="DOC-1",
            source_ref="source-1",
            fact_key=FinancialFactKey.REVENUE,
            period=2025,
            value=True,  # type: ignore[arg-type]
            unit=FinancialUnit.CNY_100_MILLION,
        )


def test_in_memory_repository_scopes_fact_lookup_to_trusted_context() -> None:
    """验证repository只返回当前workspace/document范围内的可信事实。"""
    allowed_fact = FinancialFact(
        workspace_id="WS-A",
        document_id="DOC-7",
        source_ref="chunk-current",
        fact_key=FinancialFactKey.REVENUE,
        period=2025,
        value=Decimal("100"),
        unit=FinancialUnit.CNY_100_MILLION,
    )

    foreign_fact = FinancialFact(
        workspace_id="WS-B",
        document_id="DOC-9",
        source_ref="chunk-secret",
        fact_key=FinancialFactKey.REVENUE,
        period=2025,
        value=Decimal("999"),
        unit=FinancialUnit.CNY_100_MILLION,
    )

    repository = InMemoryFinancialFactRepository([allowed_fact, foreign_fact])

    execution_context = ToolExecutionContext(
        trusted_context=TrustedContext(workspace_id="WS-A"),
        filters=SearchFilters(document_id="DOC-7"),
    )

    actual_allowed = repository.find_fact(
        execution_context=execution_context,
        source_ref="chunk-current",
        fact_key=FinancialFactKey.REVENUE,
    )

    assert actual_allowed is allowed_fact
    actual_foreign = repository.find_fact(
        execution_context=execution_context,
        source_ref="chunk-secret",
        fact_key=FinancialFactKey.REVENUE,
    )

    assert actual_foreign is None


def test_calculate_arguments_accepts_metric_and_source_refs() -> None:
    """验证合法参数和 source ref 去空格"""
    arguments = CalculateFinancialMetricArguments.model_validate(
        {
            "metric_id": "revenue_growth_rate",
            "current_period_source_ref": "  chunk-current  ",
            "previous_period_source_ref": "  chunk-previous  ",
        }
    )

    assert (
        arguments.metric_id,
        arguments.current_period_source_ref,
        arguments.previous_period_source_ref,
    ) == (
        "revenue_growth_rate",
        "chunk-current",
        "chunk-previous",
    )


def test_calculate_arguments_rejects_model_supplied_numeric_values() -> None:
    """验证模型提交裸数值时被严格schema拒绝。"""
    with pytest.raises(ValidationError):
        CalculateFinancialMetricArguments.model_validate(
            {
                "metric_id": "revenue_growth_rate",
                "current_period_source_ref": "chunk-current",
                "previous_period_source_ref": "chunk-previous",
                "current_value": 100,
            }
        )


def test_calculate_financial_metric_returns_deterministic_traceable_result() -> None:
    """验证工具返回确定性、可追溯的结果。"""
    current = FinancialFact(
        workspace_id="WS-A",
        document_id="DOC-7",
        source_ref="chunk-current",
        fact_key=FinancialFactKey.REVENUE,
        period=2025,
        value=Decimal("100"),
        unit=FinancialUnit.CNY_100_MILLION,
    )
    previous = FinancialFact(
        workspace_id="WS-A",
        document_id="DOC-7",
        source_ref="chunk-previous",
        fact_key=FinancialFactKey.REVENUE,
        period=2024,
        value=Decimal("80"),
        unit=FinancialUnit.CNY_100_MILLION,
    )
    tool_execution_context = ToolExecutionContext(
        trusted_context=TrustedContext(workspace_id="WS-A"),
        filters=SearchFilters(document_id="DOC-7"),
    )
    repository = Mock(spec=FinancialFactRepository)
    repository.find_fact.side_effect = [current, previous]
    tool = CalculateFinancialMetricTool(repository)
    result = tool(
        tool_execution_context,
        metric_id="revenue_growth_rate",
        current_period_source_ref="chunk-current",
        previous_period_source_ref="chunk-previous",
    )
    assert result == {
        "metric_id": "revenue_growth_rate",
        "value": "25.00",
        "unit": "PERCENT",
        "formula_id": "revenue_growth_rate_v1",
        "sources": [
            {
                "role": "current_period",
                "source_ref": "chunk-current",
                "fact_key": "revenue",
                "period": 2025,
                "value": "100",
                "unit": "CNY_100_MILLION",
            },
            {
                "role": "previous_period",
                "source_ref": "chunk-previous",
                "fact_key": "revenue",
                "period": 2024,
                "value": "80",
                "unit": "CNY_100_MILLION",
            },
        ],
    }


def test_calculate_financial_metric_rejects_source_outside_trusted_context() -> None:
    """验证工具拒绝来自非可信workspace/document的来源引用。"""
    current = FinancialFact(
        workspace_id="WS-B",
        document_id="DOC-9",
        source_ref="chunk-current",
        fact_key=FinancialFactKey.REVENUE,
        period=2025,
        value=Decimal("100"),
        unit=FinancialUnit.CNY_100_MILLION,
    )

    repository = InMemoryFinancialFactRepository([current])
    tool = CalculateFinancialMetricTool(repository)
    tool_execution_context = ToolExecutionContext(
        trusted_context=TrustedContext(workspace_id="WS-A"),
        filters=SearchFilters(document_id="DOC-7"),
    )
    with pytest.raises(FinancialMetricError) as exc_info:
        tool(
            tool_execution_context,
            metric_id="revenue_growth_rate",
            current_period_source_ref="chunk-current",
            previous_period_source_ref="chunk-previous",
        )
    assert exc_info.value.code is FinancialMetricErrorCode.SOURCE_NOT_AVAILABLE
    assert exc_info.value.message == "财务数值来源不可用"
    assert "chunk-current" not in str(exc_info.value)
    assert "WS-B" not in str(exc_info.value)


def test_calculate_financial_metric_rejects_conflicting_units() -> None:
    """验证不同货币单位不能直接进入固定增长率公式。"""
    current = FinancialFact(
        workspace_id="WS-A",
        document_id="DOC-7",
        source_ref="chunk-current",
        fact_key=FinancialFactKey.REVENUE,
        period=2025,
        value=Decimal("100"),
        unit=FinancialUnit.CNY_100_MILLION,
    )
    previous = FinancialFact(
        workspace_id="WS-A",
        document_id="DOC-7",
        source_ref="chunk-previous",
        fact_key=FinancialFactKey.REVENUE,
        period=2024,
        value=Decimal("100"),
        unit=FinancialUnit.CNY_YUAN,
    )
    repository = InMemoryFinancialFactRepository([current, previous])
    tool_execution_context = ToolExecutionContext(
        trusted_context=TrustedContext(workspace_id="WS-A"),
        filters=SearchFilters(document_id="DOC-7"),
    )
    tool = CalculateFinancialMetricTool(repository)
    with pytest.raises(FinancialMetricError) as exc_info:
        tool(
            tool_execution_context,
            metric_id="revenue_growth_rate",
            current_period_source_ref="chunk-current",
            previous_period_source_ref="chunk-previous",
        )

    assert exc_info.value.code is FinancialMetricErrorCode.UNIT_CONFLICT
    assert exc_info.value.message == "财务事实单位不兼容"
    assert "CNY_100_MILLION" not in str(exc_info.value)
    assert "CNY_YUAN" not in str(exc_info.value)


def test_calculate_financial_metric_rejects_zero_denominator() -> None:
    """验证上期可信数值为零时拒绝执行增长率公式。"""
    current = FinancialFact(
        workspace_id="WS-A",
        document_id="DOC-7",
        source_ref="chunk-current",
        fact_key=FinancialFactKey.REVENUE,
        period=2025,
        value=Decimal("100"),
        unit=FinancialUnit.CNY_100_MILLION,
    )
    previous = FinancialFact(
        workspace_id="WS-A",
        document_id="DOC-7",
        source_ref="chunk-previous",
        fact_key=FinancialFactKey.REVENUE,
        period=2024,
        value=Decimal("0"),
        unit=FinancialUnit.CNY_100_MILLION,
    )
    repository = InMemoryFinancialFactRepository([current, previous])
    tool_execution_context = ToolExecutionContext(
        trusted_context=TrustedContext(workspace_id="WS-A"),
        filters=SearchFilters(document_id="DOC-7"),
    )
    tool = CalculateFinancialMetricTool(repository)
    with pytest.raises(FinancialMetricError) as exc_info:
        tool(
            tool_execution_context,
            metric_id="revenue_growth_rate",
            current_period_source_ref="chunk-current",
            previous_period_source_ref="chunk-previous",
        )
    assert exc_info.value.code is FinancialMetricErrorCode.DIVISION_BY_ZERO
    assert exc_info.value.message == "财务指标分母不能为零"
    assert "chunk-previous" not in str(exc_info.value)
