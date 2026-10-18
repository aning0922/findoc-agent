import json

from app.agent.evaluation import AgentEvalResult, AgentEvalSuite, ObservedToolCall
from app.agent.run_service import AgentRunService, terminal_status_for
from app.agent.tool_loop import LoopOutcome, ToolCallingModel, ToolExecutionContext, ToolRegistry


def extract_observed_tool_calls(outcome: LoopOutcome) -> tuple[ObservedToolCall, ...]:
    """按消息顺序提取模型实际申请的工具名和参数"""
    observed_calls: list[ObservedToolCall] = []
    for message in outcome.messages:
        if message.get("role") != "assistant":
            continue

        raw_tool_calls = message.get("tool_calls")
        if not isinstance(raw_tool_calls, list):
            continue

        for raw_tool_call in raw_tool_calls:
            if not isinstance(raw_tool_call, dict):
                continue

            if raw_tool_call.get("type") != "function":
                continue

            function = raw_tool_call.get("function")
            if not isinstance(function, dict):
                continue

            tool_name = function.get("name")
            arguments_json = function.get("arguments")
            if not isinstance(tool_name, str) or not tool_name.strip():
                continue

            arguments: dict[str, object] = {}
            if isinstance(arguments_json, str):
                try:
                    parsed_arguments = json.loads(arguments_json)
                except json.JSONDecodeError:
                    pass
                else:
                    if isinstance(parsed_arguments, dict):
                        arguments = parsed_arguments

            observed_calls.append(
                ObservedToolCall(
                    tool_name=tool_name,
                    arguments=arguments,
                )
            )

    return tuple(observed_calls)


class AgentEvalRunner:
    """逐条执行冻结任务，并生成可追溯的评分输入"""

    def __init__(
        self,
        *,
        run_service: AgentRunService,
        model: ToolCallingModel,
        registry: ToolRegistry,
        execution_context: ToolExecutionContext,
    ) -> None:
        """保存执行每条评测任务所需的受控依赖"""
        self._run_service = run_service
        self._model = model
        self._registry = registry
        self._execution_context = execution_context

    def run(self, suite: AgentEvalSuite) -> tuple[AgentEvalResult, ...]:
        """按冻结顺序执行全部任务，并关联每条持久化 Run"""
        results: list[AgentEvalResult] = []
        for case in suite.cases:
            messages: list[dict[str, object]] = [
                {
                    "role": "user",
                    "content": case.prompt,
                }
            ]

            recorded = self._run_service.execute(
                model=self._model,
                messages=messages,
                registry=self._registry,
                execution_context=self._execution_context,
                max_steps=suite.config.max_steps,
            )

            agent_eval_result = AgentEvalResult(
                case_id=case.case_id,
                run_id=recorded.run.run_id,
                observed_tool_calls=extract_observed_tool_calls(recorded.outcome),
                observed_terminal_status=terminal_status_for(recorded.outcome),
            )
            results.append(agent_eval_result)

        return tuple(results)
