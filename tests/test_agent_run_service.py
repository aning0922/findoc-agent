import json
from pathlib import Path

import pytest

from app.agent.eval_fixtures import build_agent_eval_dependencies
from app.agent.run_models import AgentTerminalStatus, RunEventType
from app.agent.run_service import AgentRunService, terminal_status_for
from app.agent.sqlite_run_repository import SQLiteAgentRunRepository
from app.agent.tool_loop import (
    LoopFailure,
    LoopFailureType,
    LoopOutcome,
    LoopSuccess,
    Message,
    ToolError,
    ToolErrorType,
)
from app.rag.openai_compatible_llm import ModelCompletion


class _SearchThenFinalModel:
    """为安全投影测试返回一次检索请求和最终回答。"""

    def __init__(self) -> None:
        """初始化当前 scripted 生成步数。"""
        self._step = 0

    def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, object]],
    ) -> ModelCompletion:
        """首轮返回工具调用，次轮返回带敏感标记的最终文本。"""
        self._step += 1
        if self._step == 1:
            return ModelCompletion(
                message={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-safe-projection",
                            "type": "function",
                            "function": {
                                "name": "search_finance_docs",
                                "arguments": json.dumps(
                                    {
                                        "query": "prompt-secret sk-secret hidden-cot",
                                        "top_k": 2,
                                    }
                                ),
                            },
                        }
                    ],
                },
                finish_reason="tool_calls",
            )
        return ModelCompletion(
            message={
                "role": "assistant",
                "content": "RAW_EXCEPTION traceback hidden-cot",
            },
            finish_reason="stop",
        )


def _failure_outcome(failure_type: LoopFailureType) -> LoopFailure:
    """构造与现有四种 loop 失败合同一致的测试终态。"""
    tool_error = (
        ToolError(
            tool_call_id="call-failed",
            error_type=ToolErrorType.TOOL_EXECUTION_ERROR,
            message="工具执行异常",
        )
        if failure_type is LoopFailureType.TOOL_ERROR
        else None
    )
    return LoopFailure(
        failure_type=failure_type,
        message=failure_type.value,
        messages=(),
        tool_error=tool_error,
    )


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (
            LoopSuccess(final_answer="完成", messages=()),
            AgentTerminalStatus.SUCCESS,
        ),
        (
            _failure_outcome(LoopFailureType.PROTOCOL_ERROR),
            AgentTerminalStatus.PROTOCOL_ERROR,
        ),
        (
            _failure_outcome(LoopFailureType.TOOL_ERROR),
            AgentTerminalStatus.TOOL_ERROR,
        ),
        (
            _failure_outcome(LoopFailureType.PROVIDER_ERROR),
            AgentTerminalStatus.PROVIDER_ERROR,
        ),
        (
            _failure_outcome(LoopFailureType.MAX_STEPS_REACHED),
            AgentTerminalStatus.MAX_STEPS_REACHED,
        ),
    ],
)
def test_terminal_status_for_maps_existing_loop_outcomes(
    outcome: LoopOutcome,
    expected: AgentTerminalStatus,
) -> None:
    """验证 success 和四种 LoopFailure 只映射到现有精确终态。"""
    assert terminal_status_for(outcome) is expected


def test_service_persists_only_safe_projection(tmp_path: Path) -> None:
    """验证服务不持久化 prompt、密钥、全文、原始异常或 CoT。"""
    database_path = tmp_path / "agent-runs.db"
    repository = SQLiteAgentRunRepository(database_path)
    registry, execution_context = build_agent_eval_dependencies()
    service = AgentRunService(
        repository=repository,
        execution_config_version="agent-run-v1",
    )
    prompt = "prompt-secret sk-secret RAW_EXCEPTION traceback hidden-cot https://secret.invalid/v1"

    recorded = service.execute(
        model=_SearchThenFinalModel(),
        messages=[{"role": "user", "content": prompt}],
        registry=registry,
        execution_context=execution_context,
    )

    assert recorded.run.terminal_status is AgentTerminalStatus.SUCCESS
    reopened = SQLiteAgentRunRepository(database_path)
    stored_run = reopened.get_run(
        workspace_id=execution_context.trusted_context.workspace_id,
        run_id=recorded.run.run_id,
    )
    stored_events = reopened.list_events(
        workspace_id=execution_context.trusted_context.workspace_id,
        run_id=recorded.run.run_id,
    )
    assert stored_run is not None
    assert [event.event_type for event in stored_events] == [
        RunEventType.TOOL_REQUESTED,
        RunEventType.TOOL_SUCCEEDED,
        RunEventType.RUN_SUCCEEDED,
    ]

    persisted_json = json.dumps(
        {
            "safe_result": stored_run.safe_result,
            "events": [event.payload for event in stored_events],
        },
        ensure_ascii=False,
    )
    forbidden_values = (
        prompt,
        "prompt-secret",
        "sk-secret",
        "2025 年营业收入为 100 亿元。",
        "RAW_EXCEPTION",
        "traceback",
        "hidden-cot",
        "https://secret.invalid/v1",
    )
    assert all(value not in persisted_json for value in forbidden_values)
