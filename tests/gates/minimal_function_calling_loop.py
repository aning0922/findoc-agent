from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
import json


class ErrorType(StrEnum):
    """表示最小loop的受控失败类型。

    输入：无；输出：稳定错误码；正常路径：由失败终态引用；
    失败路径：未知值由枚举拒绝；责任边界：不保存原始异常或内部细节。
    """

    TOOL_ERROR = "tool_error"
    PROTOCOL_ERROR = "protocol_error"
    MAX_STEPS = "max_steps"


@dataclass(frozen=True)
class LoopResult:
    """保存最小loop的终态与消息证据。

    输入：成功标记、内容、错误与消息；输出：单一受控终态；
    正常路径：成功携带最终回答；失败路径：携带安全错误；
    责任边界：只投影协议轨迹，不执行模型或工具。
    """

    success: bool
    content: str
    error_type: ErrorType | None
    error_message: str | None
    messages: list[dict[str, object]]


def add_number(number_value: int, workspace_id: str) -> int:
    """执行测试专用的确定性加倍工具。

    输入：已校验整数和应用注入的workspace；输出：加倍结果；
    正常路径：返回整数结果；失败路径：保留值7触发业务失败；
    责任边界：不解析模型参数，workspace仅用于证明可信注入通道。
    """

    if number_value == 7:
        raise ValueError("number_value 不能为 7")
    return number_value * 2


@dataclass(frozen=True)
class TrustedContext:
    """保存不允许由模型提供的服务端可信上下文。

    输入：已认证workspace；输出：供应用调用handler时读取的上下文；
    正常路径：原样携带workspace；失败路径：本Gate不负责认证失败；
    责任边界：不进入模型可见arguments。
    """

    workspace_id: str


class Registry:
    """维护测试工具名到本地callable的应用侧allowlist。

    输入：应用预注册工具；输出：按名称返回callable或None；
    正常路径：命中唯一测试工具；失败路径：未知名称不返回函数；
    责任边界：模型只能提议名称，不能注入可执行实现。
    """

    def __init__(self) -> None:
        self.tools = {
            "add": add_number,
        }

    def get_tool(self, name: str) -> Callable[[int, str], int] | None:
        """按模型提议名称查询应用allowlist，不执行工具。"""
        if name not in self.tools:
            return None
        return self.tools[name]


class FakeModel:
    """按顺序生成有限的assistant响应。

    输入：应用维护的messages；输出：下一条assistant消息；
    正常路径：先请求工具再给最终回答；失败路径：角色非法时拒绝；
    责任边界：不生成user/tool消息，也不执行工具。
    """

    index = 0
    messages: list[dict[str, object]] = []

    def __init__(self) -> None:
        self.messages = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "123",
                        "type": "function",
                        "function_name": "add",
                        "arguments": '{"number_value": 6}',
                    }
                ],
            },
            {"role": "assistant", "content": "12"},
        ]

    def chat(self, messages: list[dict[str, object]]) -> dict[str, object]:
        """读取应用消息入口并返回下一条预设assistant响应。"""
        message = self.messages[self.index]
        self.index += 1
        role = message.get("role")
        if not isinstance(role, str):
            raise TypeError("角色必须是字符串")
        if not role.strip():
            raise ValueError("角色不能为空")
        if role != "assistant":
            raise ValueError("角色必须是 assistant")
        return message


def loop(
    query: str, registry: Registry, model: FakeModel, context: TrustedContext, max_steps: int = 5
) -> LoopResult:
    """运行测试专用的最小单工具Function Calling循环。

    输入：用户问题、allowlist、fake模型、可信上下文与步数上限；
    输出：包含消息轨迹的成功或受控失败终态；
    正常路径：模型请求工具、应用校验执行并回填、模型最终回答；
    失败路径：协议、工具或步数上限均返回稳定错误；
    责任边界：应用独占消息维护、工具执行、可信注入与终止决策。
    """

    messages: list[dict[str, object]] = [{"role": "user", "content": query}]
    for index_number in range(max_steps):
        try:
            message = model.chat(messages)
        except (ValueError, TypeError):
            return LoopResult(
                success=False,
                content="",
                error_type=ErrorType.PROTOCOL_ERROR,
                error_message="协议错误",
                messages=messages,
            )
        messages.append(message)
        role = message["role"]
        if role == "assistant":
            tool_calls = message.get("tool_calls")
            content = message.get("content")
            if not tool_calls and not content:
                return LoopResult(
                    success=False,
                    content="",
                    error_type=ErrorType.PROTOCOL_ERROR,
                    error_message="必须有内容或工具调用",
                    messages=messages,
                )
            if not tool_calls and isinstance(content, str) and content.strip():
                return LoopResult(
                    success=True,
                    content=content,
                    error_type=None,
                    error_message=None,
                    messages=messages,
                )

            if not isinstance(tool_calls, list) or not tool_calls or len(tool_calls) != 1:
                return LoopResult(
                    success=False,
                    content="",
                    error_type=ErrorType.PROTOCOL_ERROR,
                    error_message="必须有且只有一个工具调用",
                    messages=messages,
                )
            tool_call = tool_calls[0]
            if not isinstance(tool_call, dict):
                return LoopResult(
                    success=False,
                    content="",
                    error_type=ErrorType.PROTOCOL_ERROR,
                    error_message="工具调用必须是字典",
                    messages=messages,
                )
            tool_name = tool_call.get("function_name")
            if not isinstance(tool_name, str) or not tool_name.strip():
                return LoopResult(
                    success=False,
                    content="",
                    error_type=ErrorType.PROTOCOL_ERROR,
                    error_message="工具名称必须是字符串",
                    messages=messages,
                )

            tool_call_id = tool_call.get("id")
            if not isinstance(tool_call_id, str) or not tool_call_id.strip():
                return LoopResult(
                    success=False,
                    content="",
                    error_type=ErrorType.PROTOCOL_ERROR,
                    error_message="工具调用 ID 必须是字符串",
                    messages=messages,
                )

            tool = registry.get_tool(tool_name)
            if not tool:
                messages.append(
                    {
                        "role": "tool",
                        "content": json.dumps(
                            {
                                "error_type": "tool_not_found",
                                "error_message": "请求的工具不可用",
                            }
                        ),
                        "tool_call_id": tool_call_id,
                    }
                )
                return LoopResult(
                    success=False,
                    content="",
                    error_type=ErrorType.TOOL_ERROR,
                    error_message="请求的工具不可用",
                    messages=messages,
                )

            try:
                arguments_str = tool_call.get("arguments")
                if not isinstance(arguments_str, str):
                    raise ValueError("参数必须是字符串")
                if not arguments_str.strip():
                    raise ValueError("参数不能为空")
                arguments = json.loads(arguments_str)
                if not isinstance(arguments, dict):
                    raise ValueError("参数必须是字典")
                if set(arguments.keys()) != {"number_value"}:
                    raise ValueError("参数必须是 number_value")
                number_value = arguments["number_value"]
                if isinstance(number_value, bool):
                    raise ValueError("number_value 必须是整数")
                if not isinstance(number_value, int):
                    raise ValueError("number_value 必须是整数")
                if number_value < 1 or number_value > 10:
                    raise ValueError("number_value 必须在 1 到 10 之间")
            except (ValueError, TypeError, json.JSONDecodeError):
                messages.append(
                    {
                        "role": "tool",
                        "content": json.dumps(
                            {
                                "error_type": "tool_argument_invalid",
                                "error_message": "工具参数无效",
                            }
                        ),
                        "tool_call_id": tool_call_id,
                    }
                )
                return LoopResult(
                    success=False,
                    content="",
                    error_type=ErrorType.TOOL_ERROR,
                    error_message="工具参数无效",
                    messages=messages,
                )
            try:
                result = tool(number_value, context.workspace_id)
            except ValueError:
                messages.append(
                    {
                        "role": "tool",
                        "content": json.dumps(
                            {
                                "error_type": "tool_execution_failed",
                                "error_message": "工具无法处理该输入",
                            }
                        ),
                        "tool_call_id": tool_call_id,
                    }
                )
                return LoopResult(
                    success=False,
                    content="",
                    error_type=ErrorType.TOOL_ERROR,
                    error_message="工具无法处理该输入",
                    messages=messages,
                )
            messages.append({"role": "tool", "content": str(result), "tool_call_id": tool_call_id})
            continue
    return LoopResult(
        success=False,
        content="",
        error_type=ErrorType.MAX_STEPS,
        error_message="达到最大步数",
        messages=messages,
    )


def main() -> None:
    """运行一个本地成功样本并打印终态，不调用真实模型。"""
    query = "把 6 加倍"
    registry = Registry()
    model = FakeModel()
    context = TrustedContext(workspace_id="123")
    result = loop(query, registry, model, context, max_steps=5)
    print(result)
    if result.success:
        print(result.content)
    else:
        print(result.error_type)
        print(result.error_message)
        print(result.messages)


if __name__ == "__main__":
    main()
