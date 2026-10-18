from dataclasses import dataclass
from collections.abc import Callable
import json
from datetime import UTC, datetime
from app.agent.run_models import AgentRun, AgentTerminalStatus, RunEvent, RunEventType
from app.agent.sqlite_run_repository import SQLiteAgentRunRepository
from app.agent.result_storage import USER_RESULT_VERSION, StoredAgentUserResult
from app.agent.user_result import AgentUserResult
from app.agent.tool_loop import (
    DEFAULT_MAX_STEPS,
    LoopFailure,
    LoopFailureType,
    LoopOutcome,
    LoopSuccess,
    Message,
    ToolCallingModel,
    ToolExecutionContext,
    ToolRegistry,
    run_tool_loop,
)


def terminal_status_for(outcome: LoopOutcome) -> AgentTerminalStatus:
    """把现有 LoopOutcome 映射为唯一 Agent 精确终态。"""
    if isinstance(outcome, LoopSuccess):
        return AgentTerminalStatus.SUCCESS
    if isinstance(outcome, LoopFailure):
        if outcome.failure_type == LoopFailureType.PROTOCOL_ERROR:
            return AgentTerminalStatus.PROTOCOL_ERROR
        if outcome.failure_type == LoopFailureType.TOOL_ERROR:
            return AgentTerminalStatus.TOOL_ERROR
        if outcome.failure_type == LoopFailureType.PROVIDER_ERROR:
            return AgentTerminalStatus.PROVIDER_ERROR
        if outcome.failure_type == LoopFailureType.MAX_STEPS_REACHED:
            return AgentTerminalStatus.MAX_STEPS_REACHED
    raise TypeError("不支持的 LoopOutcome 类型")


def safe_arguments_summary(*, tool_name: str, arguments_json: str) -> dict[str, object]:
    """从模型工具参数中提取不含原文和可信上下文的安全摘要。"""
    if not isinstance(tool_name, str):
        raise TypeError("tool_name 必须是字符串")
    if not tool_name.strip():
        raise ValueError("tool_name 不能为空")

    if not isinstance(arguments_json, str):
        raise TypeError("arguments_json 必须是字符串")
    if not arguments_json.strip():
        return {"validation_status": "invalid"}

    try:
        arguments = json.loads(arguments_json)
    except json.JSONDecodeError:
        return {"validation_status": "invalid"}
    if arguments is None:
        return {"validation_status": "invalid"}
    if not isinstance(arguments, dict):
        return {"validation_status": "invalid"}
    if tool_name == "search_finance_docs":
        query = arguments.get("query")
        top_k = arguments.get("top_k", 5)
        if not isinstance(query, str) or isinstance(top_k, bool) or not isinstance(top_k, int):
            return {"validation_status": "invalid"}
        return {"query_length": len(query.strip()), "top_k": top_k}

    if tool_name == "calculate_financial_metric":
        metric_id = arguments.get("metric_id")
        current_ref = arguments.get("current_period_source_ref")
        previous_ref = arguments.get("previous_period_source_ref")
        if not all(
            isinstance(value, str) and bool(value.strip())
            for value in (metric_id, current_ref, previous_ref)
        ):
            return {"validation_status": "invalid"}
        return {
            "metric_id": metric_id,
            "has_current_period_source_ref": True,
            "has_previous_period_source_ref": True,
        }
    return {"validation_status": "not_projected"}


def safe_result_summary(
    *,
    tool_name: str,
    output: dict[str, object],
) -> dict[str, object]:
    """从可信工具结果中提取不含检索全文的确定性摘要。"""
    if not isinstance(tool_name, str):
        raise TypeError("tool_name 必须是字符串")
    if not tool_name.strip():
        raise ValueError("tool_name 不能为空")
    if not isinstance(output, dict):
        return {"result_status": "invalid"}

    if tool_name == "search_finance_docs":
        requested_top_k = output.get("requested_top_k")
        result_count = output.get("result_count")
        empty = output.get("empty")
        hits = output.get("hits")

        if (
            isinstance(requested_top_k, bool)
            or not isinstance(requested_top_k, int)
            or isinstance(result_count, bool)
            or not isinstance(result_count, int)
            or not isinstance(empty, bool)
            or not isinstance(hits, list)
        ):
            return {"result_status": "invalid"}

        chunk_ids: list[str] = []
        for hit in hits:
            if not isinstance(hit, dict):
                return {"result_status": "invalid"}
            chunk_id = hit.get("chunk_id")
            if not isinstance(chunk_id, str) or not chunk_id.strip():
                return {"result_status": "invalid"}
            chunk_ids.append(chunk_id)

        return {
            "requested_top_k": requested_top_k,
            "result_count": result_count,
            "empty": empty,
            "chunk_ids": chunk_ids,
        }

    if tool_name == "calculate_financial_metric":
        metric_id = output.get("metric_id")
        value = output.get("value")
        unit = output.get("unit")
        formula_id = output.get("formula_id")
        sources = output.get("sources")

        if not all(
            isinstance(item, str) and bool(item.strip())
            for item in (metric_id, value, unit, formula_id)
        ) or not isinstance(sources, list):
            return {"result_status": "invalid"}

        return {
            "metric_id": metric_id,
            "value": value,
            "unit": unit,
            "formula_id": formula_id,
            "source_count": len(sources),
        }

    return {"result_status": "not_projected"}


def _project_tool_events(*, run_id: str, outcome: LoopOutcome) -> list[RunEvent]:
    """按消息顺序投影工具请求、成功和失败事件。"""
    events: list[RunEvent] = []
    tool_names_by_call_id: dict[str, str] = {}

    trusted_results_by_call_id = {
        result.tool_call_id: result for result in outcome.trusted_tool_results
    }
    for message in outcome.messages:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role == "assistant":
            tool_calls = message.get("tool_calls")
            if not isinstance(tool_calls, list):
                continue

            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    continue
                if tool_call.get("type") != "function":
                    continue

                tool_call_id = tool_call.get("id")
                function = tool_call.get("function")

                if not isinstance(tool_call_id, str) or not tool_call_id.strip():
                    continue
                if not isinstance(function, dict):
                    continue

                tool_name = function.get("name")
                arguments_json = function.get("arguments")

                if not isinstance(tool_name, str) or not tool_name.strip():
                    continue
                if not isinstance(arguments_json, str):
                    continue

                tool_names_by_call_id[tool_call_id] = tool_name

                events.append(
                    RunEvent(
                        run_id=run_id,
                        sequence=len(events) + 1,
                        event_type=RunEventType.TOOL_REQUESTED,
                        payload={
                            "tool_name": tool_name,
                            "tool_call_id": tool_call_id,
                            "arguments_summary": safe_arguments_summary(
                                tool_name=tool_name,
                                arguments_json=arguments_json,
                            ),
                        },
                        occurred_at=datetime.now(UTC),
                    )
                )
        elif role == "tool":
            tool_call_id = message.get("tool_call_id")
            if not isinstance(tool_call_id, str) or not tool_call_id.strip():
                continue

            tool_name = tool_names_by_call_id.get(tool_call_id)
            if tool_name is None:
                continue

            trusted_result = trusted_results_by_call_id.pop(
                tool_call_id,
                None,
            )

            if trusted_result is not None:
                events.append(
                    RunEvent(
                        run_id=run_id,
                        sequence=len(events) + 1,
                        event_type=RunEventType.TOOL_SUCCEEDED,
                        payload={
                            "tool_name": tool_name,
                            "tool_call_id": tool_call_id,
                            "result_summary": safe_result_summary(
                                tool_name=tool_name,
                                output=trusted_result.output,
                            ),
                        },
                        occurred_at=datetime.now(UTC),
                    )
                )
                continue

            if (
                isinstance(outcome, LoopFailure)
                and outcome.tool_error is not None
                and outcome.tool_error.tool_call_id == tool_call_id
            ):
                events.append(
                    RunEvent(
                        run_id=run_id,
                        sequence=len(events) + 1,
                        event_type=RunEventType.TOOL_FAILED,
                        payload={
                            "tool_name": tool_name,
                            "tool_call_id": tool_call_id,
                            "error_code": outcome.tool_error.error_type.value,
                        },
                        occurred_at=datetime.now(UTC),
                    )
                )
    return events


def _project_terminal(
    *,
    run_id: str,
    outcome: LoopOutcome,
    tool_events: list[RunEvent],
) -> tuple[dict[str, object] | None, RunEvent]:
    """生成安全 Run 结果摘要和唯一终态事件。"""
    terminal_status = terminal_status_for(outcome)
    occurred_at = datetime.now(UTC)

    if isinstance(outcome, LoopSuccess):
        trusted_result_summaries: list[dict[str, object]] = []

        for event in tool_events:
            if event.event_type is not RunEventType.TOOL_SUCCEEDED:
                continue

            result_summary = event.payload.get("result_summary")
            if isinstance(result_summary, dict):
                trusted_result_summaries.append(dict(result_summary))

        safe_result: dict[str, object] = {
            "final_answer_available": True,
            "trusted_result_summaries": trusted_result_summaries,
        }

        terminal_event = RunEvent(
            run_id=run_id,
            sequence=len(tool_events) + 1,
            event_type=RunEventType.RUN_SUCCEEDED,
            payload={
                "terminal_status": terminal_status.value,
            },
            occurred_at=occurred_at,
        )
        return safe_result, terminal_event

    if not isinstance(outcome, LoopFailure):
        raise TypeError("不支持的 LoopOutcome 类型")

    error_code = (
        outcome.tool_error.error_type.value
        if outcome.tool_error is not None
        else outcome.failure_type.value
    )

    terminal_event = RunEvent(
        run_id=run_id,
        sequence=len(tool_events) + 1,
        event_type=RunEventType.RUN_FAILED,
        payload={
            "terminal_status": terminal_status.value,
            "error_code": error_code,
        },
        occurred_at=occurred_at,
    )
    return None, terminal_event


@dataclass(frozen=True)
class RecordedRunOutcome:
    """一次已经完成持久化的 Agent 执行结果。"""

    run: AgentRun
    outcome: LoopOutcome


@dataclass(frozen=True)
class ValidatedRunOutcome(RecordedRunOutcome):
    """已原子提交的运行与产品结果；只有 user_result.to_public() 可对外公开。

    outcome 仍含内部候选、消息与证据，不可直接序列化整个对象。
    """

    user_result: AgentUserResult


class AgentRunService:
    """在现有受控 loop 外创建、投影并终结 Agent Run。

    事件是 loop 结束后的安全业务投影，不是实时流或完整 trace。
    进程被杀或 SQLite 故障仍可能留下 running；本服务不提供
    崩溃恢复、事件回放、实时订阅或多用户认证。
    """

    def __init__(
        self, *, repository: SQLiteAgentRunRepository, execution_config_version: str
    ) -> None:
        """保存独立 Run/Event repository 和执行配置版本。"""
        self._repository = repository
        self._execution_config_version = execution_config_version

        if not isinstance(execution_config_version, str):
            raise TypeError("execution_config_version 必须是字符串")
        if not execution_config_version.strip():
            raise ValueError("execution_config_version 不能为空")

    def execute(
        self,
        *,
        model: ToolCallingModel,
        messages: list[Message],
        registry: ToolRegistry,
        execution_context: ToolExecutionContext,
        max_steps: int = DEFAULT_MAX_STEPS,
        result_validator: Callable[[LoopOutcome], AgentUserResult] | None = None,
    ) -> RecordedRunOutcome:
        """执行唯一 loop；可注入本次证据验证器，在最终写事务前产生产品结果。

        无验证器的旧离线调用保持 Run/Event 合同；有验证器时要求可信单文档，
        返回 ValidatedRunOutcome。验证或存储异常传播，不能报告已保存。
        模型、检索及产品验证均在 SQLite 终结写事务之外执行。
        """
        if isinstance(max_steps, bool) or not isinstance(max_steps, int):
            raise TypeError("max_steps 只能是整数")
        if max_steps < 1:
            raise ValueError("max_steps 必须大于 0")

        workspace_id = execution_context.trusted_context.workspace_id
        if not isinstance(workspace_id, str) or not workspace_id.strip():
            raise ValueError("可信 workspace_id 不能为空")

        document_id = None
        if result_validator is not None:
            if not callable(result_validator):
                raise TypeError("结果验证器必须可调用")
            filters = execution_context.filters
            if (
                filters is None
                or not isinstance(filters.document_id, str)
                or not filters.document_id.strip()
            ):
                raise ValueError("产品结果要求服务端核准的单文档范围")
            document_id = filters.document_id

        started_run = self._repository.start_run(
            workspace_id=workspace_id,
            execution_config_version=self._execution_config_version,
            document_id=document_id,
            user_result_version=USER_RESULT_VERSION if result_validator is not None else None,
        )

        outcome = run_tool_loop(
            model=model,
            messages=messages,
            registry=registry,
            execution_context=execution_context,
            max_steps=max_steps,
        )

        # 使用刚完成的唯一 loop 与本次证据会话；不补跑生成或检索。
        user_result = result_validator(outcome) if result_validator is not None else None

        tool_events = _project_tool_events(
            run_id=started_run.run_id,
            outcome=outcome,
        )

        for event in tool_events:
            self._repository.append_event(
                workspace_id=workspace_id,
                event=event,
            )

        safe_result, terminal_event = _project_terminal(
            run_id=started_run.run_id,
            outcome=outcome,
            tool_events=tool_events,
        )

        terminal_status = terminal_status_for(outcome)
        if user_result is not None:
            # 新产品路径不用旧候选可用 flag 表示答案成功；旧离线路径保持原摘要。
            safe_result = {
                "user_result_status": user_result.status,
                "trusted_result_summaries": (safe_result or {}).get("trusted_result_summaries", []),
            }
            terminal_event = RunEvent(
                run_id=terminal_event.run_id,
                sequence=terminal_event.sequence,
                event_type=terminal_event.event_type,
                payload={**terminal_event.payload, "user_result_status": user_result.status},
                occurred_at=terminal_event.occurred_at,
            )

        final_run = self._repository.finalize_run(
            workspace_id=workspace_id,
            terminal_status=terminal_status,
            safe_result=safe_result,
            terminal_event=terminal_event,
            user_result=user_result,
        )

        if user_result is not None:
            return ValidatedRunOutcome(
                run=final_run, outcome=outcome, user_result=user_result,
            )
        return RecordedRunOutcome(
            run=final_run,
            outcome=outcome,
        )

    def get_user_result(self, *, workspace_id: str, run_id: str) -> StoredAgentUserResult:
        """用调用方已核准的 workspace 读取持久结果；原样传播安全读取异常。"""
        return self._repository.get_user_result(workspace_id=workspace_id, run_id=run_id)

    def list_events(self, *, workspace_id: str, run_id: str) -> list[RunEvent]:
        """仅委托按可信范围的历史读取；保留 not-found，调用方投影公开字段。"""
        return self._repository.list_events(workspace_id=workspace_id, run_id=run_id)
