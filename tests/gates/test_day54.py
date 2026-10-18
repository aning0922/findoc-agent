from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from copy import deepcopy

from app.agent.tool_loop import (
    LoopFailure,
    LoopFailureType,
    LoopSuccess,
    ToolErrorType,
    ToolExecutionContext,
    ToolResult,
    ToolSpec,
    run_tool_loop,
)
from app.rag.openai_compatible_llm import ModelCompletion
from app.rag.retriever import TrustedContext

# 测试专用服务端事实：模型看不到workspace与允许文档的对应关系。
DocumentMapping: dict[str, str] = {
    "workspace-gate": "DOC-2048",
    "workspace-gate-v2": "DOC-2049",
}


class ReviewWorkOrderArguments(BaseModel):
    """

    输入：
        模型提交的 document_name、urgency和processing_day
    输出：
        规范化后的严格工作订单参数
    失败：
        类型，范围或额外字段不合法时抛出 ValidationError
    正常路径：
        将模型提交的 document_name、urgency和processing_day 规范化后返回
    责任边界：
        不包含任意服务端可信字段
    """

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    document_name: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=4, max_length=16, pattern=r"^[A-Z0-9-]+$"
        ),
    ] = Field(
        description="文档名称",
    )

    urgency: Literal["normal", "urgent"] = Field(
        description="紧急程度",
    )

    processing_day: int = Field(
        ge=1,
        le=30,
        description="处理天数",
    )


def review_work_order(
    document_name: str, urgency: str, processing_day: int, workspace_id: str
) -> dict[str, object]:
    """
    输入：
        模型提交的 document_name、urgency和processing_day
    输出：
        归属检查后生成结果
    失败：
        文档不属于可信 workspace
    正常路径：
        归属匹配后返回文档、派生队列和处理天数
    责任边界：
        handler 不接受模型提供的 workspace
    """
    document_mapping_name = DocumentMapping.get(workspace_id)
    if not document_mapping_name:
        raise ValueError("文档不可用")
    if document_name != document_mapping_name:
        raise ValueError("文档不可用")
    return {
        "document_name": document_mapping_name,
        "queue": "expedited" if urgency == "urgent" else "standard",
        "processing_day": processing_day,
    }


def adaptation_function(
    execution_context: ToolExecutionContext,
    *,
    document_name: str,
    urgency: str,
    processing_day: int,
) -> dict[str, object]:
    """
    输入：
        模型提交的 document_name、urgency和processing_day
    输出：
        归属检查后生成结果
    失败：
        文档不属于可信 workspace
    正常路径：
        从可信上下文提取workspace并调用唯一业务handler
    责任边界：
        只连接校验后参数与可信上下文，不读取原始模型消息
    """
    return review_work_order(
        document_name,
        urgency,
        processing_day,
        execution_context.trusted_context.workspace_id,
    )


# 临时registry仅在本测试模块内存在，不进入正式finance registry。
temporary_registry = {
    "review_work_order": ToolSpec(
        arguments_schema=ReviewWorkOrderArguments,
        handler=adaptation_function,
        description="为当前工作区内的文档生成确定性的复核工单预览",
    )
}


class ScriptedToolCallingModel:
    """按顺序返回预设 assistant 响应，并记录生产 loop 传入的消息。

    输入：
        初始化时接收有限的 ModelCompletion 响应序列。
    输出：
        每次 complete 调用返回下一条预设模型响应。
    正常路径：
        记录当前 messages 和 tools，再依次返回响应。
    失败路径：
        响应耗尽时抛出 AssertionError，使测试立即失败。
    责任边界：
        只模拟模型供应商，不执行工具、不生成 tool 消息、
        不决定可信 workspace，也不调用真实模型。
    """

    def __init__(self, responses: list[ModelCompletion]) -> None:
        self._responses = responses
        self._index = 0
        self.calls: list[tuple[list[dict[str, object]], list[dict[str, object]]]] = []

    def complete(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> ModelCompletion:
        """记录一次模型调用并返回下一条预设响应。

        输入：
            应用维护的 messages 和由测试 registry 生成的 tools。
        输出：
            下一条 ModelCompletion。
        正常路径：
            深拷贝输入轨迹，递增索引并返回对应响应。
        失败路径：
            没有剩余响应时抛出 AssertionError。
        责任边界：
            不修改应用传入的数据，不伪造 user/tool 消息。
        """
        self.calls.append((deepcopy(messages), deepcopy(tools)))

        if self._index >= len(self._responses):
            raise AssertionError("scripted provider 响应已经耗尽")

        response = self._responses[self._index]
        self._index += 1
        return response


def test_temporary_review_tool_returns_result_with_trusted_context() -> None:
    """验证合法参数经过可信注入、工具执行、消息回填后成功终止。

    输入：合法工具请求和可信workspace；输出：LoopSuccess；
    正常路径：产生并回填ToolResult；失败路径：任一协议断言失败即测试失败；
    责任边界：不调用真实模型，不修改正式registry。
    """

    model = ScriptedToolCallingModel(
        [
            ModelCompletion(
                message={
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "gate-call-1",
                            "type": "function",
                            "function": {
                                "name": "review_work_order",
                                "arguments": (
                                    '{"document_name":"DOC-2048",'
                                    '"urgency":"urgent","processing_day":3}'
                                ),
                            },
                        }
                    ],
                },
                finish_reason="tool_calls",
            ),
            ModelCompletion(
                message={"role": "assistant", "content": "工单已生成"},
                finish_reason="stop",
            ),
        ]
    )

    result = run_tool_loop(
        model=model,
        messages=[{"role": "user", "content": "为 DOC-2048 创建紧急复核工单"}],
        registry=temporary_registry,
        execution_context=ToolExecutionContext(
            trusted_context=TrustedContext(workspace_id="workspace-gate"),
            filters=None,
        ),
        max_steps=3,
    )
    assert isinstance(result, LoopSuccess)
    assert result.final_answer == "工单已生成"
    assert [message["role"] for message in result.messages] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ]

    tool_message = result.messages[2]
    assert tool_message["tool_call_id"] == "gate-call-1"

    assert len(model.calls) == 2
    second_call_messages = model.calls[1][0]
    assert second_call_messages[-1] == tool_message

    assert result.trusted_tool_results == (
        ToolResult(
            tool_call_id="gate-call-1",
            output={
                "document_name": "DOC-2048",
                "queue": "expedited",
                "processing_day": 3,
            },
        ),
    )


def test_temporary_review_tool_rejects_invalid_schema_before_execution() -> None:
    """验证陌生enum值在handler执行前形成安全参数错误。

    输入：urgency为rush的请求；输出：INVALID_ARGUMENTS终态；
    正常路径：失败消息关联原调用ID；失败路径：handler结果出现即测试失败；
    责任边界：只证明schema与回填合同，不扩展生产工具。
    """

    model = ScriptedToolCallingModel(
        [
            ModelCompletion(
                message={
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "gate-call-1",
                            "type": "function",
                            "function": {
                                "name": "review_work_order",
                                "arguments": (
                                    '{"document_name":"DOC-2048",'
                                    '"urgency":"rush","processing_day":3}'
                                ),
                            },
                        }
                    ],
                },
                finish_reason="tool_calls",
            )
        ]
    )

    result = run_tool_loop(
        model=model,
        messages=[{"role": "user", "content": "为 DOC-2048 创建紧急复核工单"}],
        registry=temporary_registry,
        execution_context=ToolExecutionContext(
            trusted_context=TrustedContext(workspace_id="workspace-gate"),
            filters=None,
        ),
        max_steps=3,
    )
    assert isinstance(result, LoopFailure)
    assert result.failure_type is LoopFailureType.TOOL_ERROR
    assert result.tool_error is not None
    assert result.tool_error.error_type is ToolErrorType.INVALID_ARGUMENTS
    assert result.tool_error.tool_call_id == "gate-call-1"
    assert result.messages[-1]["role"] == "tool"
    assert result.messages[-1]["tool_call_id"] == "gate-call-1"
    assert result.trusted_tool_results == ()
    assert len(model.calls) == 1


def test_temporary_review_tool_maps_business_failure_to_safe_tool_error() -> None:
    """验证schema合法但文档越权时形成安全执行错误。

    输入：当前workspace不可用的DOC-9999；输出：TOOL_EXECUTION_ERROR；
    正常路径：原调用ID被回填；失败路径：内部业务文案泄露即测试失败；
    责任边界：不暴露允许文档集合，不调用真实模型。
    """

    model = ScriptedToolCallingModel(
        [
            ModelCompletion(
                message={
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "gate-call-1",
                            "type": "function",
                            "function": {
                                "name": "review_work_order",
                                "arguments": (
                                    '{"document_name":"DOC-9999",'
                                    '"urgency":"normal","processing_day":5}'
                                ),
                            },
                        }
                    ],
                },
                finish_reason="tool_calls",
            ),
            ModelCompletion(
                message={"role": "assistant", "content": "工单已生成"},
                finish_reason="stop",
            ),
        ]
    )

    result = run_tool_loop(
        model=model,
        messages=[{"role": "user", "content": "为 DOC-2048 创建紧急复核工单"}],
        registry=temporary_registry,
        execution_context=ToolExecutionContext(
            trusted_context=TrustedContext(workspace_id="workspace-gate"),
            filters=None,
        ),
        max_steps=3,
    )

    assert isinstance(result, LoopFailure)
    assert result.failure_type is LoopFailureType.TOOL_ERROR
    assert result.tool_error is not None
    assert result.tool_error.error_type is ToolErrorType.TOOL_EXECUTION_ERROR
    assert result.tool_error.tool_call_id == "gate-call-1"
    assert result.tool_error.message == "工具执行异常"
    assert result.messages[-1]["role"] == "tool"
    assert result.messages[-1]["tool_call_id"] == "gate-call-1"
    assert "文档不可用" not in str(result.messages[-1]["content"])
    assert result.trusted_tool_results == ()
    assert len(model.calls) == 1
