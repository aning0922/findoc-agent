from collections.abc import Sequence
from unittest.mock import Mock
from langchain_core.messages.tool import ToolCall
from langchain_core.tools import BaseTool, tool
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from app.agent.finance_tools import SearchFinanceDocsArguments, build_finance_tool_registry

from pydantic import BaseModel, ValidationError

import pytest

from app.agent.financial_facts import FinancialFactRepository
from app.agent.langchain_adapter import bind_langchain_tools, build_langchain_tools
from app.agent.tool_loop import ToolExecutionContext
from app.rag.retriever import Retriever, SearchFilters, TrustedContext


@tool
def calculate_total(quantity: int, unit_price: int) -> int:
    """计算总价
    Args:
        quantity: 数量
        unit_price: 单价
    Returns:
        int: 总价
    """
    return quantity * unit_price


def test_langchain_toy_tool_executes_and_preserves_tool_call_id() -> None:
    """测试LangChain工具适配器是否能够正确执行工具并保留工具调用ID。"""
    tool_call_id = "call_toy_001"
    ai_message = AIMessage(
        content="",
        tool_calls=[
            ToolCall(
                id=tool_call_id, name="calculate_total", args={"quantity": 10, "unit_price": 100}
            )
        ],
    )

    tool_call = ai_message.tool_calls[0]
    result = calculate_total.invoke(tool_call["args"])
    assert result == 1000

    tool_message = ToolMessage(
        content=f"总价是{result}",
        tool_call_id=tool_call_id,
        name=tool_call["name"],
    )
    assert tool_message.tool_call_id == tool_call["id"]
    assert calculate_total.name == "calculate_total"
    assert "计算总价" in calculate_total.description
    assert tool_message.tool_call_id == tool_call_id
    assert ai_message.tool_calls[0]["id"] == tool_call_id
    assert calculate_total.args_schema is not None
    args_schema = calculate_total.args_schema
    assert isinstance(args_schema, type)
    assert issubclass(args_schema, BaseModel)

    schema = args_schema.model_json_schema()

    assert set(schema["properties"]) == {"quantity", "unit_price"}
    assert set(schema["required"]) == {"quantity", "unit_price"}


def test_langchain_toy_tool_rejects_invalid_arguments() -> None:
    """测试LangChain工具适配器是否能够正确拒绝无效的参数。"""
    tool_call_id = "call_toy_001"
    ai_message = AIMessage(
        content="",
        tool_calls=[
            ToolCall(
                id=tool_call_id,
                name="calculate_total",
                args={"quantity": 10, "unit_price": "not-a-number"},
            )
        ],
    )
    with pytest.raises(ValidationError):
        calculate_total.invoke(ai_message.tool_calls[0]["args"])


def test_search_arguments_schema_conversion_changes_strict_required_fields() -> None:
    """测试搜索参数模式转换是否改变了严格要求的字段。"""
    raw_schema = SearchFinanceDocsArguments.model_json_schema()
    default_tool = convert_to_openai_tool(SearchFinanceDocsArguments)
    strict_tool = convert_to_openai_tool(
        SearchFinanceDocsArguments,
        strict=True,
    )

    default_function = default_tool["function"]
    strict_function = strict_tool["function"]

    assert isinstance(default_function, dict)
    assert isinstance(strict_function, dict)

    default_parameters = default_function["parameters"]
    strict_parameters = strict_function["parameters"]
    assert isinstance(default_parameters, dict)
    assert isinstance(strict_parameters, dict)

    assert raw_schema["additionalProperties"] is False
    assert set(raw_schema["required"]) == {"query"}
    assert raw_schema["properties"]["top_k"]["default"] == 5

    assert default_parameters["additionalProperties"] is False
    assert set(default_parameters["required"]) == {"query"}
    assert default_parameters["properties"]["top_k"]["default"] == 5

    assert strict_function["strict"] is True
    assert strict_parameters["additionalProperties"] is False
    assert set(strict_parameters["required"]) == {"query", "top_k"}
    assert strict_parameters["properties"]["top_k"]["default"] == 5


def test_build_langchain_tools_reuses_registry_contract_without_trusted_fields() -> None:
    """测试构建LangChain工具时是否能够正确复用注册表的合同定义，而不暴露可信上下文字段。"""
    retriever = Mock(spec=Retriever)
    financial_fact_repository = Mock(spec=FinancialFactRepository)
    registry = build_finance_tool_registry(
        retriever=retriever, financial_fact_repository=financial_fact_repository
    )
    execution_context = ToolExecutionContext(
        trusted_context=TrustedContext(workspace_id="WS-A"),
        filters=SearchFilters(source_file="demo.pdf"),
    )
    langchain_tools = build_langchain_tools(
        tool_registry=registry, execution_context=execution_context
    )

    tools_by_name = {tool.name: tool for tool in langchain_tools}

    assert len(langchain_tools) == len(registry)
    assert set(tools_by_name) == set(registry)
    for tool_name, tool_spec in registry.items():
        langchain_tool = tools_by_name[tool_name]

        assert langchain_tool.description == tool_spec.description
        assert langchain_tool.args_schema is tool_spec.arguments_schema

        properties = tool_spec.arguments_schema.model_json_schema()["properties"]
        trusted_field_names = {
            "workspace_id",
            "user",
            "role",
            "authorization",
            "execution_context",
            "trusted_context",
            "filters",
        }

        assert trusted_field_names.isdisjoint(properties)


def test_langchain_search_tool_matches_native_handler_output_and_context() -> None:
    """测试LangChain搜索工具是否能够正确匹配原生处理器的输出和上下文。"""
    retriever = Mock(spec=Retriever)
    retriever.retrieve.return_value = []
    financial_fact_repository = Mock(spec=FinancialFactRepository)
    registry = build_finance_tool_registry(
        retriever=retriever, financial_fact_repository=financial_fact_repository
    )

    execution_context = ToolExecutionContext(
        trusted_context=TrustedContext(workspace_id="WS-A"),
        filters=SearchFilters(source_file="demo.pdf"),
    )
    langchain_tools = build_langchain_tools(
        tool_registry=registry, execution_context=execution_context
    )

    tools_by_name = {tool.name: tool for tool in langchain_tools}
    langchain_search_tool = tools_by_name["search_finance_docs"]
    native_search_handler = registry["search_finance_docs"].handler

    query = "营业收入"
    top_k = 2
    arguments = {"query": query, "top_k": top_k}

    native_output = native_search_handler(execution_context, query=query, top_k=top_k)
    langchain_output = langchain_search_tool.invoke(arguments)
    assert langchain_output == native_output
    assert retriever.retrieve.call_count == 2

    for retriever_call in retriever.retrieve.call_args_list:
        assert retriever_call.args == (query,)
        assert retriever_call.kwargs["top_k"] == top_k
        assert retriever_call.kwargs["context"] is execution_context.trusted_context
        assert retriever_call.kwargs["filters"] is execution_context.filters


def test_langchain_tool_rejects_model_workspace_before_handler() -> None:
    """测试LangChain工具是否能够正确拒绝模型提交的不可信workspace ID。"""
    retriever = Mock(spec=Retriever)
    financial_fact_repository = Mock(spec=FinancialFactRepository)

    registry = build_finance_tool_registry(
        retriever=retriever, financial_fact_repository=financial_fact_repository
    )
    execution_context = ToolExecutionContext(
        trusted_context=TrustedContext(workspace_id="WS-A"),
        filters=SearchFilters(source_file="demo.pdf"),
    )
    langchain_tools = build_langchain_tools(
        tool_registry=registry, execution_context=execution_context
    )
    tools_by_name = {tool.name: tool for tool in langchain_tools}
    search_tool = tools_by_name["search_finance_docs"]

    model_arguments = {
        "query": "营业收入",
        "top_k": 2,
        "workspace_id": "WS-B",
    }
    with pytest.raises(ValidationError):
        search_tool.invoke(model_arguments)

    retriever.retrieve.assert_not_called()


class RecordingBindToolsModel:
    """记录应用传给bind_tools的工具，不模拟真实供应商能力。"""

    def __init__(self) -> None:
        self.calls: list[list[BaseTool]] = []
        self.bound_model = object()

    def bind_tools(self, tools: Sequence[BaseTool]) -> object:
        self.calls.append(list(tools))
        return self.bound_model


def test_bind_langchain_tools_calls_recording_model_with_registry_tools() -> None:
    """验证适配器调用bind_tools；不证明真实provider或模型客户端已经接通。"""
    retriever = Mock(spec=Retriever)
    financial_fact_repository = Mock(spec=FinancialFactRepository)
    registry = build_finance_tool_registry(
        retriever=retriever, financial_fact_repository=financial_fact_repository
    )
    execution_context = ToolExecutionContext(
        trusted_context=TrustedContext(workspace_id="WS-A"),
        filters=SearchFilters(source_file="demo.pdf"),
    )
    model = RecordingBindToolsModel()
    result = bind_langchain_tools(
        model=model, tool_registry=registry, execution_context=execution_context
    )
    assert result is model.bound_model
    assert len(model.calls) == 1
    assert {tool.name for tool in model.calls[0]} == set(registry)
