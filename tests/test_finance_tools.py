from decimal import Decimal
import json
from pydantic import ValidationError
from unittest.mock import Mock
import pytest

from app.agent.finance_tools import (
    CalculateFinancialMetricArguments,
    CalculateFinancialMetricTool,
    SearchFinanceDocsArguments,
    SearchFinanceDocsTool,
    build_finance_tool_registry,
    build_search_finance_tool_registry,
)

from app.agent.financial_facts import (
    FinancialFact,
    FinancialFactKey,
    FinancialFactRepository,
    FinancialUnit,
    InMemoryFinancialFactRepository,
)
from app.agent.tool_loop import (
    LoopFailure,
    LoopFailureType,
    LoopSuccess,
    ToolErrorType,
    ToolExecutionContext,
    ToolSpec,
    run_tool_loop,
)
from app.rag.openai_compatible_llm import ModelCompletion
from app.rag.retriever import (
    Retriever,
    SearchFilters,
    SearchHit,
    TrustedContext,
)


def test_search_arguments_normalizes_query_and_uses_default_top_k() -> None:
    """验证合法搜索参数会规范化query并使用默认top_k。"""
    arguments = SearchFinanceDocsArguments.model_validate({"query": "  营业收入  "})

    assert arguments.query == "营业收入"
    assert arguments.top_k == 5


def test_search_arguments_rejects_model_workspace_override() -> None:
    """验证模型提交workspace_id时被严格schema拒绝。"""
    with pytest.raises(ValidationError) as _:
        SearchFinanceDocsArguments.model_validate(
            {
                "query": "营业收入",
                "workspace_id": "WS-B",
            }
        )


def test_search_finance_docs_uses_trusted_context_and_returns_structured_hits() -> None:
    """验证工具使用可信上下文和返回结构化命中。"""
    execution_context = ToolExecutionContext(
        trusted_context=TrustedContext(workspace_id="WS-A"),
        filters=SearchFilters(document_id="DOC-7"),
    )
    hit = SearchHit(
        score=0.95,
        chunk_id="chunk-18",
        text="2025年营业收入为100亿元。",
        page=18,
        source_file="annual-report.pdf",
        type="paragraph",
        section="主要会计数据",
        table_md=None,
    )

    retriever = Mock(spec=Retriever)
    retriever.retrieve.return_value = [hit]

    tool = SearchFinanceDocsTool(retriever)
    result = tool(execution_context, query="营业收入", top_k=3)

    retriever.retrieve.assert_called_once_with(
        "营业收入",
        context=execution_context.trusted_context,
        top_k=3,
        filters=execution_context.filters,
    )

    assert result == {
        "query": "营业收入",
        "requested_top_k": 3,
        "result_count": 1,
        "empty": False,
        "hits": [
            {
                "score": 0.95,
                "chunk_id": "chunk-18",
                "text": "2025年营业收入为100亿元。",
                "page": 18,
                "source_file": "annual-report.pdf",
                "type": "paragraph",
                "section": "主要会计数据",
                "table_md": None,
            }
        ],
    }


def test_search_finance_docs_returns_explicit_empty_result() -> None:
    """验证空检索返回empty为True和空hits。"""
    retriever = Mock(spec=Retriever)
    retriever.retrieve.return_value = []
    tool = SearchFinanceDocsTool(retriever)
    execution_context = ToolExecutionContext(
        trusted_context=TrustedContext(workspace_id="WS-A"),
        filters=SearchFilters(source_file="demo.pdf"),
    )
    query = "不存在的指标"
    top_k = 5
    result = tool(execution_context, query, top_k)
    assert result == {
        "query": "不存在的指标",
        "requested_top_k": 5,
        "result_count": 0,
        "empty": True,
        "hits": [],
    }


def test_search_finance_docs_maps_retriever_exception_to_safe_tool_error() -> None:
    """验证Retriever异常被安全映射为ToolError。"""
    retriever = Mock(spec=Retriever)
    retriever.retrieve.side_effect = RuntimeError("sensitive store connection details")
    execution_context = ToolExecutionContext(
        trusted_context=TrustedContext(workspace_id="WS-A"),
        filters=SearchFilters(source_file="demo.pdf"),
    )
    query = "不存在的指标"
    top_k = 5

    registry = {
        "search_finance_docs": ToolSpec(
            arguments_schema=SearchFinanceDocsArguments,
            handler=SearchFinanceDocsTool(retriever),
            description="在当前服务端可信财报范围内检索与问题相关的文档片段。",
        )
    }

    model = Mock()
    model.complete.return_value = ModelCompletion(
        message={
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_search_failure",
                    "type": "function",
                    "function": {
                        "name": "search_finance_docs",
                        "arguments": json.dumps(
                            {
                                "query": query,
                                "top_k": top_k,
                            },
                            ensure_ascii=False,
                        ),
                    },
                }
            ],
        },
        finish_reason="tool_calls",
    )

    messages: list[dict[str, object]] = [{"role": "user", "content": "搜索营业收入"}]
    outcome = run_tool_loop(
        model=model,
        messages=messages,
        registry=registry,
        execution_context=execution_context,
    )
    assert isinstance(outcome, LoopFailure)
    assert outcome.failure_type is LoopFailureType.TOOL_ERROR
    assert outcome.tool_error is not None
    assert outcome.tool_error.error_type is ToolErrorType.TOOL_EXECUTION_ERROR
    assert outcome.tool_error.tool_call_id == "call_search_failure"
    assert outcome.tool_error.message == "工具执行异常"
    tool_message = outcome.messages[-1]

    assert tool_message["role"] == "tool"
    assert tool_message["tool_call_id"] == "call_search_failure"

    tool_content = tool_message["content"]
    assert isinstance(tool_content, str)
    assert "sensitive store connection details" not in tool_content
    assert "工具执行异常" in tool_content
    retriever.retrieve.assert_called_once_with(
        query,
        context=execution_context.trusted_context,
        top_k=top_k,
        filters=execution_context.filters,
    )
    assert model.complete.call_count == 1


def test_build_finance_tool_registry_registers_only_allowed_business_tools() -> None:
    """验证财报工具registry只注册冻结的搜索与确定性计算工具。"""
    retriever = Mock(spec=Retriever)
    repository = Mock(spec=FinancialFactRepository)

    registry = build_finance_tool_registry(
        retriever=retriever,
        financial_fact_repository=repository,
    )
    assert set(registry) == {
        "search_finance_docs",
        "calculate_financial_metric",
    }

    assert registry["search_finance_docs"].arguments_schema is SearchFinanceDocsArguments
    assert (
        registry["calculate_financial_metric"].arguments_schema is CalculateFinancialMetricArguments
    )

    assert isinstance(
        registry["search_finance_docs"].handler,
        SearchFinanceDocsTool,
    )
    assert isinstance(
        registry["calculate_financial_metric"].handler,
        CalculateFinancialMetricTool,
    )


def test_search_registry_instances_are_isolated_from_two_tool_factory() -> None:
    """修改一个局部表不改变其他实例或旧双工具表，搜索仍复用同一 schema/handler 类型。"""
    retriever = Mock(spec=Retriever)
    runtime_registry = build_search_finance_tool_registry(retriever=retriever)
    local_registry = build_search_finance_tool_registry(retriever=retriever)
    offline_registry = build_finance_tool_registry(
        retriever=retriever, financial_fact_repository=Mock(spec=FinancialFactRepository)
    )
    local_registry.clear()
    assert set(runtime_registry) == {"search_finance_docs"}
    assert set(offline_registry) == {"search_finance_docs", "calculate_financial_metric"}
    assert runtime_registry["search_finance_docs"].arguments_schema is SearchFinanceDocsArguments
    assert isinstance(runtime_registry["search_finance_docs"].handler, SearchFinanceDocsTool)


def test_run_tool_loop_executes_calculation_from_shared_finance_registry() -> None:
    """验证模型只能选择计算工具和来源键，真值由可信repository计算并回填。"""
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

    retriever = Mock(spec=Retriever)
    repository = InMemoryFinancialFactRepository([current, previous])

    registry = build_finance_tool_registry(
        retriever=retriever,
        financial_fact_repository=repository,
    )

    tool_request = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_metric_1",
                "type": "function",
                "function": {
                    "name": "calculate_financial_metric",
                    "arguments": json.dumps(
                        {
                            "metric_id": "revenue_growth_rate",
                            "current_period_source_ref": "chunk-current",
                            "previous_period_source_ref": "chunk-previous",
                        }
                    ),
                },
            }
        ],
    }
    final_response: dict[str, object] = {
        "role": "assistant",
        "content": "营业收入增长率为25.00%。",
    }
    model = Mock()
    model.complete.side_effect = [
        ModelCompletion(
            message=tool_request,
            finish_reason="tool_calls",
        ),
        ModelCompletion(
            message=final_response,
            finish_reason="stop",
        ),
    ]
    execution_context = ToolExecutionContext(
        trusted_context=TrustedContext(workspace_id="WS-A"),
        filters=SearchFilters(document_id="DOC-7"),
    )
    messages: list[dict[str, object]] = [{"role": "user", "content": "计算营业收入增长率"}]
    outcome = run_tool_loop(
        model=model,
        messages=messages,
        registry=registry,
        execution_context=execution_context,
    )
    assert isinstance(outcome, LoopSuccess)

    (trusted_result,) = outcome.trusted_tool_results
    assert trusted_result.tool_call_id == "call_metric_1"
    assert trusted_result.output["value"] == "25.00"
    assert trusted_result.output["unit"] == "PERCENT"
    assert trusted_result.output["formula_id"] == "revenue_growth_rate_v1"

    assert outcome.final_answer == "营业收入增长率为25.00%。"
    assert [message["role"] for message in outcome.messages] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ]
    assert model.complete.call_count == 2
    retriever.retrieve.assert_not_called()

    tool_message = outcome.messages[2]

    assert tool_message["tool_call_id"] == "call_metric_1"

    content = tool_message["content"]
    assert isinstance(content, str)

    payload = json.loads(content)
    assert payload["ok"] is True
    assert payload["output"]["value"] == "25.00"
    assert payload["output"]["formula_id"] == "revenue_growth_rate_v1"


def test_run_tool_loop_maps_untrusted_financial_source_to_safe_tool_error() -> None:
    """验证越界财务来源经loop统一映射且不泄露内部信息。"""
    foreign_fact = FinancialFact(
        workspace_id="WS-B",
        document_id="DOC-9",
        source_ref="chunk-secret",
        fact_key=FinancialFactKey.REVENUE,
        period=2025,
        value=Decimal("999"),
        unit=FinancialUnit.CNY_100_MILLION,
    )
    retriever = Mock(spec=Retriever)
    repository = InMemoryFinancialFactRepository([foreign_fact])

    registry = build_finance_tool_registry(
        retriever=retriever,
        financial_fact_repository=repository,
    )

    tool_request = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_metric_failure",
                "type": "function",
                "function": {
                    "name": "calculate_financial_metric",
                    "arguments": json.dumps(
                        {
                            "metric_id": "revenue_growth_rate",
                            "current_period_source_ref": "chunk-secret",
                            "previous_period_source_ref": "chunk-previous",
                        }
                    ),
                },
            }
        ],
    }

    model = Mock()
    model.complete.return_value = ModelCompletion(
        message=tool_request,
        finish_reason="tool_calls",
    )
    execution_context = ToolExecutionContext(
        trusted_context=TrustedContext(workspace_id="WS-A"),
        filters=SearchFilters(document_id="DOC-7"),
    )
    messages: list[dict[str, object]] = [{"role": "user", "content": "计算营业收入增长率"}]
    outcome = run_tool_loop(
        model=model,
        messages=messages,
        registry=registry,
        execution_context=execution_context,
    )

    assert isinstance(outcome, LoopFailure)
    assert outcome.failure_type is LoopFailureType.TOOL_ERROR
    assert outcome.tool_error is not None
    assert outcome.tool_error.error_type is ToolErrorType.TOOL_EXECUTION_ERROR
    assert outcome.tool_error.tool_call_id == "call_metric_failure"
    assert outcome.tool_error.message == "工具执行异常"

    tool_message = outcome.messages[-1]

    assert tool_message["role"] == "tool"
    assert tool_message["tool_call_id"] == "call_metric_failure"

    content = tool_message["content"]
    assert isinstance(content, str)
    assert "工具执行异常" in content
    assert "chunk-secret" not in content
    assert "WS-B" not in content
    assert "999" not in content

    assert model.complete.call_count == 1
    retriever.retrieve.assert_not_called()
