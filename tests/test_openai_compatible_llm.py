from unittest.mock import MagicMock, patch

import httpx
import pytest
from openai import APIConnectionError, APITimeoutError

from app.rag.openai_compatible_llm import OpenAICompatibleLLMClient, ProviderCallError


def test_generate_uses_injected_sync_client_and_returns_raw_content() -> None:
    """输入为注入的同步 OpenAI 兼容 SDK client、固定模型名和完整 prompt；
    预期 generate 只发起一次非流式 Chat Completions 调用，并原样返回
    首个 choice 的 message.content；
    若读取真实环境、访问网络、修改模型正文或调用错误的模型与 prompt，
    说明真实模型适配器的依赖注入或透明传输合同被破坏。
    """
    model = "test-model"
    prompt = "请只依据编号证据回答问题。"
    raw_content = '{"decision":"answer","content":"营业收入为100亿元 [1]"}'
    sdk_client = MagicMock()
    sdk_response = MagicMock()
    sdk_response.choices = [MagicMock()]
    sdk_response.choices[0].message.content = raw_content
    sdk_client.chat.completions.create.return_value = sdk_response
    llm_client = OpenAICompatibleLLMClient(
        model=model,
        client=sdk_client,
    )
    result = llm_client.generate(prompt)
    assert result == raw_content

    sdk_client.chat.completions.create.assert_called_once_with(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        stream=False,
    )


def test_generate_normalizes_sdk_timeout_to_builtin_timeout_error() -> None:
    """输入为在 Chat Completions 调用时抛出 APITimeoutError 的注入 SDK client；
    预期 generate 将其规范化为内置 TimeoutError，并保留原异常为 cause；
    若原始 SDK 异常直接逃逸或被转换成普通返回值，
    RAGService 将无法稳定映射 llm_timeout 系统终态。
    """
    prompt = "请依据证据回答问题。"
    request = httpx.Request(
        "POST",
        "https://example.invalid/v1/chat/completions",
    )
    sdk_timeout = APITimeoutError(request=request)
    sdk_client = MagicMock()
    sdk_client.chat.completions.create.side_effect = sdk_timeout
    llm_client = OpenAICompatibleLLMClient(
        model="test-model",
        client=sdk_client,
    )
    with pytest.raises(TimeoutError) as exc_info:
        llm_client.generate(prompt)
    assert exc_info.value.__cause__ is sdk_timeout
    sdk_client.chat.completions.create.assert_called_once_with(
        model="test-model",
        messages=[{"role": "user", "content": prompt}],
        stream=False,
    )
    assert str(exc_info.value) == "模型调用超时"


def test_from_env_builds_configured_sync_client_without_network() -> None:
    """输入为包含模型、base_url、测试 API key 和超时的内存环境配置；
    预期 from_env 使用这些值构造同步 SDK client，并返回持有该 client
    和模型名的 OpenAICompatibleLLMClient，构造期间不调用模型接口；
    若读取真实环境、忽略配置、泄露密钥或发起模型调用，
    说明真实配置入口与离线测试边界被破坏。
    """
    env: dict[str, str] = {
        "LLM_MODEL": "test-model",
        "LLM_BASE_URL": "https://example.invalid/v1",
        "LLM_API_KEY": "test-api-key",
        "LLM_TIMEOUT_SECONDS": "12.5",
    }
    with patch("app.rag.openai_compatible_llm.Client") as client_class:
        sdk_client = client_class.return_value
        llm_client = OpenAICompatibleLLMClient.from_env(env)
        client_class.assert_called_once_with(
            api_key="test-api-key",
            base_url="https://example.invalid/v1",
            timeout=12.5,
        )
        assert llm_client.model == "test-model"
        assert llm_client.client is sdk_client
        sdk_client.chat.completions.create.assert_not_called()


def test_complete_sends_tools_and_preserves_structured_model_completion() -> None:
    """输入为消息历史、工具定义和返回单个工具请求的fake SDK client；
    预期工具调用路径关闭SDK自动重试，发送完整非流式Chat Completions参数，
    并把finish_reason和嵌套tool_calls规范化为项目内部结果；
    若请求字段缺失、调用了错误的client、丢失关联ID或展开错function字段，
    说明真实工具调用适配合同被破坏。
    """
    model = "test-model"
    messages: list[dict[str, object]] = [
        {
            "role": "user",
            "content": "请搜索营业收入。",
        }
    ]
    tools: list[dict[str, object]] = [
        {
            "type": "function",
            "function": {
                "name": "search_finance_docs",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "top_k": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 5,
                        },
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        }
    ]

    expected_tool_call: dict[str, object] = {
        "id": "call_001",
        "type": "function",
        "function": {
            "name": "search_finance_docs",
            "arguments": '{"query":"营业收入","top_k":3}',
        },
    }

    # 原始client只负责生成一个关闭SDK重试的请求client。
    sdk_client = MagicMock()
    request_client = MagicMock()
    sdk_client.with_options.return_value = request_client

    # tool_call是SDK响应对象；complete通过model_dump保留其嵌套结构。
    sdk_tool_call = MagicMock()
    sdk_tool_call.model_dump.return_value = expected_tool_call

    sdk_message = MagicMock()
    sdk_message.content = None
    sdk_message.tool_calls = [sdk_tool_call]

    choice = MagicMock()
    choice.finish_reason = "tool_calls"
    choice.message = sdk_message

    sdk_response = MagicMock()
    sdk_response.choices = [choice]
    request_client.chat.completions.create.return_value = sdk_response

    llm_client = OpenAICompatibleLLMClient(
        model=model,
        client=sdk_client,
    )

    result = llm_client.complete(
        messages=messages,
        tools=tools,
    )

    # 第一道证据：SDK自己的重试被关闭。
    sdk_client.with_options.assert_called_once_with(max_retries=0)

    # 第二道证据：真正发送请求的是with_options返回的request_client。
    request_client.chat.completions.create.assert_called_once_with(
        model=model,
        messages=messages,
        tools=tools,
        stream=False,
        parallel_tool_calls=False,
    )

    # 防止实现绕过request_client，误用原始client直接发请求。
    sdk_client.chat.completions.create.assert_not_called()

    # 第三道证据：SDK工具调用对象确实经过规范化。
    sdk_tool_call.model_dump.assert_called_once_with()

    # 第四道证据：供应商停止原因被独立保留。
    assert result.finish_reason == "tool_calls"

    # 第五道证据：内部assistant消息完整保留关联ID和function嵌套结构。
    assert result.message == {
        "role": "assistant",
        "content": None,
        "tool_calls": [expected_tool_call],
    }


def test_complete_maps_connection_error_to_retryable_provider_error() -> None:
    """验证工具调用适配器将连接错误映射为可重试的安全异常。

    输入：
        注入一个在Chat Completions请求时抛出APIConnectionError的fake SDK client。
    输出：
        complete抛出retryable为True的ProviderCallError，并保留原异常为cause。
    失败：
        若异常未映射、被标记为不可重试，或SDK请求次数不为一次，则测试失败。
    责任边界：
        本测试只验证一次provider attempt的异常分类；
        实际有限重试次数由run_tool_loop的测试负责。
    """
    # 用 httpx.Request 构造请求
    request = httpx.Request(
        "POST",
        "https://example.invalid/v1/chat/completions",
    )
    # 用它构造 APIConnectionError(request=request)
    sdk_error = APIConnectionError(request=request)
    # 创建 sdk_client 和 request_client 两个 MagicMock
    sdk_client = MagicMock()
    request_client = MagicMock()
    sdk_client.with_options.return_value = request_client
    request_client.chat.completions.create.side_effect = sdk_error
    llm_client = OpenAICompatibleLLMClient(
        model="test-model",
        client=sdk_client,
    )
    with pytest.raises(ProviderCallError) as exc_info:
        llm_client.complete(
            messages=[{"role": "user", "content": "请搜索营业收入。"}],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "search_finance_docs",
                        "parameters": {
                            "query": "营业收入",
                        },
                    },
                }
            ],
        )
    assert exc_info.value.retryable is True
    assert str(exc_info.value) == "模型服务调用失败"
    assert exc_info.value.__cause__ is sdk_error
    sdk_client.with_options.assert_called_once_with(max_retries=0)
    assert request_client.chat.completions.create.call_count == 1
