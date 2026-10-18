from collections.abc import Sequence
from typing import Protocol

from langchain_core.tools import BaseTool, StructuredTool

from app.agent.tool_loop import (
    ToolExecutionContext,
    ToolRegistry,
    ToolSpec,
)


class _SupportsBindTools(Protocol):
    """描述工具薄适配所需的最小bind_tools调用合同。"""

    def bind_tools(self, tools: Sequence[BaseTool]) -> object:
        """绑定工具说明并返回绑定后的模型对象"""
        ...


def _build_langchain_tool(
    *, tool_name: str, tool_spec: ToolSpec, execution_context: ToolExecutionContext
) -> StructuredTool:
    """把一个现有ToolSpec投影为LangChain结构化工具。

    模型只能提交arguments_schema中的业务参数；
    execution_context由服务端闭包注入，不进入模型schema。
    参数校验交给同一个Pydantic schema，业务执行委托给原handler。
    校验或业务异常不在此吞掉，由外层应用统一映射。
    """

    def invoke_handler(**arguments: object) -> dict[str, object]:
        """使用服务端可信上下文调用原业务handler。"""
        return tool_spec.handler(execution_context, **arguments)

    return StructuredTool.from_function(
        func=invoke_handler,
        name=tool_name,
        description=tool_spec.description,
        args_schema=tool_spec.arguments_schema,
        infer_schema=False,
    )


def build_langchain_tools(
    tool_registry: ToolRegistry,
    *,
    execution_context: ToolExecutionContext,
) -> list[BaseTool]:
    """从唯一ToolRegistry构造LangChain工具列表。

    每个工具复用现有名称、描述、参数schema和handler；
    服务端可信上下文由闭包注入，不暴露给模型。
    本函数只创建工具，不执行工具、不绑定模型，也不创建tool loop。
    """
    langchain_tools: list[BaseTool] = []

    for tool_name, tool_spec in tool_registry.items():
        langchain_tools.append(
            _build_langchain_tool(
                tool_name=tool_name,
                tool_spec=tool_spec,
                execution_context=execution_context,
            )
        )
    return langchain_tools


def bind_langchain_tools(
    *,
    model: _SupportsBindTools,
    tool_registry: ToolRegistry,
    execution_context: ToolExecutionContext,
) -> object:
    """构造LangChain工具并调用模型的bind_tools。

    本函数只绑定工具说明，不执行工具、不调用模型、
    不创建客户端、配置或tool loop。
    """
    tools = build_langchain_tools(tool_registry=tool_registry, execution_context=execution_context)
    return model.bind_tools(tools)
