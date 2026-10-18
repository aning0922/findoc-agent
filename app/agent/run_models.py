from dataclasses import dataclass
from enum import StrEnum
from datetime import datetime
import json


class AgentRunNotFoundError(LookupError):
    """Run 不存在或不属于当前可信 workspace。"""


class AgentRunStateConflictError(RuntimeError):
    """Run 当前状态不允许执行请求的操作。"""


class RunEventSequenceError(ValueError):
    """Event sequence 不是当前 Run 的下一连续序号。"""


class RunStatus(StrEnum):
    """执行层粗状态；succeeded 不代表产品 answered。"""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AgentTerminalStatus(StrEnum):
    """loop 执行终态；用户读取以独立产品三态为准。"""

    SUCCESS = "success"
    """成功"""
    PROTOCOL_ERROR = "protocol_error"
    """协议错误"""
    TOOL_ERROR = "tool_error"
    """工具错误"""
    PROVIDER_ERROR = "provider_error"
    """提供者错误"""
    MAX_STEPS_REACHED = "max_steps_reached"
    """最大步骤到达"""


class RunEventType(StrEnum):
    """Run事件类型"""

    TOOL_REQUESTED = "tool_requested"
    """工具请求"""
    TOOL_SUCCEEDED = "tool_succeeded"
    """工具成功"""
    TOOL_FAILED = "tool_failed"
    """工具失败"""
    RUN_SUCCEEDED = "run_succeeded"
    """运行成功"""
    RUN_FAILED = "run_failed"
    """运行失败"""


@dataclass(frozen=True)
class AgentRun:
    """一次 Agent 执行的不可变汇总事实。

    保存服务端生成的执行身份、可信 workspace、粗状态、精确终态、
    带时区的起止时间、安全结果摘要和执行配置版本。
    status/terminal_status 表示执行层；产品状态在独立结果与安全摘要中明确标识。
    不保存 prompt、完整消息、原始异常或隐藏推理。
    """

    run_id: str
    """执行身份"""
    workspace_id: str
    """可信 workspace"""
    status: RunStatus
    """执行粗状态，不表示用户回答成功。"""
    terminal_status: AgentTerminalStatus | None
    """执行精确终态，不替代产品三态。"""
    started_at: datetime
    """带时区的起始时间"""
    ended_at: datetime | None
    """带时区的结束时间"""
    safe_result: dict[str, object] | None
    """安全结果摘要"""
    execution_config_version: str
    """执行配置版本"""
    document_id: str | None = None
    """创建 Run 前服务端核准的文档身份；旧版或离线 Run 可为空。"""
    user_result_version: str | None = None
    """非空时要求终结事务同时保存此版本产品结果，不从执行状态推导结果。"""

    def __post_init__(self) -> None:
        """校验 Run 字段类型、时间和状态组合不变量。

        运行中不能包含终态、结束时间或结果；成功必须对应 success；
        失败必须对应现有四种失败终态。非法字段类型抛出 TypeError，
        非法值或互相冲突的状态组合抛出 ValueError。
        """
        if not isinstance(self.run_id, str):
            raise TypeError("run_id 必须是非空字符串")
        if not self.run_id.strip():
            raise ValueError("run_id 只能是非空字符串")

        if not isinstance(self.workspace_id, str):
            raise TypeError("workspace_id 必须是非空字符串")
        if not self.workspace_id.strip():
            raise ValueError("workspace_id 只能是非空字符串")

        if not isinstance(self.execution_config_version, str):
            raise TypeError("execution_config_version 必须是非空字符串")
        if not self.execution_config_version.strip():
            raise ValueError("execution_config_version 只能是非空字符串")

        if (self.document_id is None) != (self.user_result_version is None):
            raise ValueError("文档身份和产品结果版本必须同时提供")
        for value in (self.document_id, self.user_result_version):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError("文档身份和产品结果版本必须是非空字符串")

        if self.status is None or not isinstance(self.status, RunStatus):
            raise TypeError("status 只能是非空 RunStatus 枚举值")
        if not isinstance(self.terminal_status, AgentTerminalStatus | None):
            raise TypeError("terminal_status 只能是非空 AgentTerminalStatus 枚举值或 None")

        # started_at 必须是 datetime 并且带时区
        if (
            not isinstance(self.started_at, datetime)
            or self.started_at.tzinfo is None
            or self.started_at.utcoffset() is None
        ):
            raise ValueError("started_at 必须是 datetime 并且带时区")

        if self.status == RunStatus.RUNNING:
            if self.terminal_status is not None:
                raise ValueError("status 为 RUNNING 时，terminal_status 必须为 None")
            if self.ended_at is not None:
                raise ValueError("status 为 RUNNING 时，ended_at 必须为 None")
            if self.safe_result is not None:
                raise ValueError("status 为 RUNNING 时，safe_result 必须为 None")
        elif self.status == RunStatus.SUCCEEDED:
            if self.terminal_status is not AgentTerminalStatus.SUCCESS:
                raise ValueError(
                    "status 为 SUCCEEDED 时，terminal_status 必须为 AgentTerminalStatus.SUCCESS"
                )
            if self.ended_at is None:
                raise ValueError("status 为 SUCCEEDED 时，ended_at 必须不为 None")
            else:
                if (
                    not isinstance(self.ended_at, datetime)
                    or self.ended_at.tzinfo is None
                    or self.ended_at.utcoffset() is None
                ):
                    raise ValueError("ended_at 必须是 datetime 并且带时区")
                if self.ended_at <= self.started_at:
                    raise ValueError("ended_at 必须大于 started_at")
        elif self.status == RunStatus.FAILED:
            if self.terminal_status is None or self.terminal_status is AgentTerminalStatus.SUCCESS:
                raise ValueError(
                    "status 为 FAILED 时，terminal_status 必须不为 None 且不为 AgentTerminalStatus.SUCCESS"
                )
            if self.ended_at is None:
                raise ValueError("status 为 FAILED 时，ended_at 必须不为 None")
            else:
                if (
                    not isinstance(self.ended_at, datetime)
                    or self.ended_at.tzinfo is None
                    or self.ended_at.utcoffset() is None
                ):
                    raise ValueError("ended_at 必须是 datetime 并且带时区")
                if self.ended_at <= self.started_at:
                    raise ValueError("ended_at 必须大于 started_at")


@dataclass(frozen=True)
class RunEvent:
    """一次 Run 内不可变且有顺序的安全业务事件。

    使用 run_id 关联所属执行，sequence 表示 Run 内顺序，
    event_type 表示业务动作，payload 只保存白名单安全摘要。
    不保存完整消息、检索全文、原始供应商响应、异常或隐藏推理。
    """

    run_id: str
    sequence: int
    event_type: RunEventType
    payload: dict[str, object]
    occurred_at: datetime

    def __post_init__(self) -> None:
        """校验事件身份、顺序、类型、payload 和带时区时间。"""
        if not isinstance(self.run_id, str):
            raise TypeError("run_id 必须是非空字符串")
        if not self.run_id.strip():
            raise ValueError("run_id 只能是非空字符串")

        if isinstance(self.sequence, bool):
            raise TypeError("sequence 必须是非空 int")

        if not isinstance(self.sequence, int):
            raise TypeError("sequence 必须是非空 int")
        if self.sequence <= 0:
            raise ValueError("sequence 必须大于 0 的整数")

        if not isinstance(self.event_type, RunEventType):
            raise TypeError("event_type 必须是非空 RunEventType 枚举值")

        if not isinstance(self.payload, dict):
            raise TypeError("payload 必须是非空 dict")
        try:
            json.dumps(self.payload, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("payload 必须能 json 序列化") from exc

        if not isinstance(self.occurred_at, datetime):
            raise TypeError("occurred_at 必须是非空 datetime")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at 必须带时区")
