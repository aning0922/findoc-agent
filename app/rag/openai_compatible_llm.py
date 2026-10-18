from dataclasses import dataclass
import os
from collections.abc import Mapping
from typing import Self, cast

from openai import APIConnectionError, APIStatusError, APITimeoutError, Client, OpenAIError

from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolUnionParam


class ProviderCallError(RuntimeError):
    """表示一次已经安全归类的供应商调用失败。

    输入：
        retryable说明相同逻辑step是否允许再尝试一次。
    输出：
        为应用层有限重试提供不包含供应商敏感细节的稳定异常。
    失败：
        retryable不是bool时拒绝构造。
    责任边界：
        对外只暴露固定安全消息；
        原始SDK异常通过异常cause保留，不负责决定最终应用终态。
    """

    def __init__(self, *, retryable: bool) -> None:
        """保存供应商失败是否属于瞬时白名单。"""
        if not isinstance(retryable, bool):
            raise TypeError("retryable 只能是bool")

        super().__init__("模型服务调用失败")
        self.retryable = retryable


@dataclass(frozen=True)
class ModelCompletion:
    """保存一次供应商生成得到的规范化模型结果。

    输入：
        message是一条规范化但仍不可信的assistant消息；
        finish_reason是供应商返回的停止原因元数据。
    输出：
        为受控loop提供不可变的单轮模型结果。
    失败：
        本对象不执行消息深层协议校验；
        字段形状冲突由受控loop识别并形成明确失败终态。
    责任边界：
        不代表工具已获授权或应用已经成功终止；
        不执行工具，也不保证assistant文本是可信财务真值。
    """

    message: dict[str, object]
    finish_reason: str


class OpenAICompatibleLLMClient:
    """适配同步OpenAI兼容Chat Completions的两种现有调用合同。

    输入：
        generate接收W8既有的单个prompt；
        complete接收完整messages和从唯一registry生成的tools。
    输出：
        generate返回未经验证的模型正文；
        complete返回保留assistant消息和finish_reason的ModelCompletion。
    失败：
        generate保持既有TimeoutError合同；
        complete关闭SDK自动重试，并将SDK异常安全映射为ProviderCallError。
    责任边界：
        不验证工具名、参数schema、权限或最终财务真值；
        不执行工具，也不控制受控loop的继续与终止。
    """

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Self:
        """从显式映射或当前进程环境创建同步 OpenAI 兼容模型适配器。

        Args:
            env: 可选的字符串配置映射；为 None 时读取 os.environ。
                显式传入映射主要用于离线测试和受控配置构造。

        Returns:
            保存模型名并持有已配置同步 SDK client 的适配器。

        Raises:
            KeyError: 必填配置缺失。
            ValueError: 超时无法转换为数字。
            SDK 构造异常: API key、base_url 或 timeout 不被 SDK 接受。

        边界:
            本方法不加载 .env、不打印或返回 API key，也不调用模型接口。
        """
        if env is None:
            env = os.environ
        return cls(
            model=env["LLM_MODEL"],
            client=Client(
                api_key=env["LLM_API_KEY"],
                base_url=env["LLM_BASE_URL"],
                timeout=float(env["LLM_TIMEOUT_SECONDS"]),
            ),
        )

    def __init__(self, model: str, client: Client) -> None:
        """初始化同步模型适配器。

        Args:
            model: 每次 Chat Completions 调用使用的模型名称。
            client: 已配置认证信息、base_url 和超时的 OpenAI 兼容 SDK client。

        边界:
            本构造路径不读取环境变量，也不访问网络，便于普通 pytest 注入 fake。
        """
        self.model = model
        self.client = client

    def generate(self, prompt: str) -> str:
        """执行一次同步非流式生成并返回未经验证的原始模型正文。

        Args:
            prompt: RAGService 已构造完成的非空业务提示词。

        Returns:
            首个 choice 的 message.content；供应商返回 None 时转换为空字符串，
            由 RAGService 归类为 empty_model_output。

        Raises:
            TimeoutError:
                SDK 调用超时时抛出，并保留原始 APITimeoutError 为 cause。
            其他 SDK 异常:
                网络、鉴权、额度等异常原样传播，由 RAGService 统一映射。

        边界:
            不解析或修复 JSON、Markdown、拒答协议和引用编号。
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                stream=False,
            )
        except APITimeoutError as exc:
            raise TimeoutError("模型调用超时") from exc
        if response.choices[0].message.content is None:
            return ""
        return response.choices[0].message.content

    def for_operating_research(self) -> Self:
        """D21 per-request timeout; same adapter and single-attempt complete contract."""
        return type(self)(self.model, self.client.with_options(max_retries=0, timeout=90))

    def generate_once(self, prompt: str) -> str:
        """D17 model calls must not replay after an unknown provider outcome."""
        return OpenAICompatibleLLMClient(self.model, self.client.with_options(max_retries=0)).generate(prompt)

    def complete(
        self, messages: list[dict[str, object]], tools: list[dict[str, object]]
    ) -> ModelCompletion:
        """执行一次启用工具定义的同步非流式模型调用。

        输入：
            messages是应用维护的完整消息历史；
            tools是从唯一ToolRegistry生成的供应商安全投影。
        输出：
            返回保留assistant content、结构化tool_calls和finish_reason的
            ModelCompletion。
        失败：
            SDK调用异常或供应商响应无法规范化时向上抛出并保留原始cause，
            由上层执行有限白名单重试并映射为安全终态。
        责任边界：
            每次调用只执行一个provider attempt，并关闭SDK自动重试；
            不校验工具授权、参数schema或可信上下文，
            不执行工具，也不控制loop是否继续。
        """
        request_client = self.client.with_options(max_retries=0)
        try:
            response = request_client.chat.completions.create(
                model=self.model,
                messages=cast(list[ChatCompletionMessageParam], messages),
                tools=cast(list[ChatCompletionToolUnionParam], tools),
                stream=False,
                parallel_tool_calls=False,
            )
        except APIConnectionError as exc:
            raise ProviderCallError(retryable=True) from exc
        except APIStatusError as exc:
            retryable = exc.status_code in {408, 409, 429} or exc.status_code >= 500
            raise ProviderCallError(retryable=retryable) from exc
        except OpenAIError as exc:
            raise ProviderCallError(retryable=False) from exc

        choice = response.choices[0]
        sdk_message = choice.message

        normalized_message: dict[str, object] = {
            "role": "assistant",
            "content": sdk_message.content,
        }
        if sdk_message.tool_calls is not None:
            normalized_tool_calls: list[dict[str, object]] = []

            for tool_call in sdk_message.tool_calls:
                normalized_tool_calls.append(tool_call.model_dump())

            normalized_message["tool_calls"] = normalized_tool_calls
        return ModelCompletion(
            message=normalized_message,
            finish_reason=choice.finish_reason,
        )
