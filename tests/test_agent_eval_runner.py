import json
from dataclasses import replace
from pathlib import Path

from app.agent.eval_runner import AgentEvalRunner, extract_observed_tool_calls
from app.agent.evaluation import (
    AgentEvalSuite,
    Score,
    load_agent_eval_suite,
    score_parameters,
    score_terminal_status,
    score_tool_selection,
)
from app.agent.run_models import AgentTerminalStatus
from app.agent.run_service import AgentRunService
from app.agent.sqlite_run_repository import SQLiteAgentRunRepository
from app.agent.tool_loop import LoopSuccess, Message
from app.rag.openai_compatible_llm import ModelCompletion
from app.rag.retriever import SearchFilters, TrustedContext
from app.agent.tool_loop import ToolExecutionContext


PROJECT_ROOT = Path(__file__).parents[1]
AGENT_EVAL_CONFIG_PATH = PROJECT_ROOT / "eval/agent_eval_config_v1.json"


class _FinalOnlyModel:
    """为 runner 合同测试返回固定最终回答。"""

    def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, object]],
    ) -> ModelCompletion:
        """不调用工具，直接结束当前 scripted 案例。"""
        return ModelCompletion(
            message={"role": "assistant", "content": "这是固定合同结果。"},
            finish_reason="stop",
        )


def test_extract_observed_tool_calls_preserves_order_and_marks_bad_arguments() -> None:
    """验证工具顺序保留，非法 JSON 只使参数无法得分。"""
    outcome = LoopSuccess(
        final_answer="已完成。",
        messages=(
            {"role": "user", "content": "prompt-marker"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-search",
                        "type": "function",
                        "function": {
                            "name": "search_finance_docs",
                            "arguments": json.dumps({"query": "2025 营业收入", "top_k": 2}),
                        },
                    },
                    {
                        "id": "call-calculate",
                        "type": "function",
                        "function": {
                            "name": "calculate_financial_metric",
                            "arguments": "{",
                        },
                    },
                ],
            },
            {"role": "assistant", "content": "已完成。"},
        ),
    )

    observed = extract_observed_tool_calls(outcome)

    assert [call.tool_name for call in observed] == [
        "search_finance_docs",
        "calculate_financial_metric",
    ]
    assert observed[0].arguments == {"query": "2025 营业收入", "top_k": 2}
    assert observed[1].arguments == {}


def test_runner_persists_run_and_produces_independent_scores(tmp_path: Path) -> None:
    """验证 scripted runner 串联持久化与 scorer 合同，不声称模型准确率。"""
    full_suite = load_agent_eval_suite(AGENT_EVAL_CONFIG_PATH)
    first_case = full_suite.cases[0]
    suite = AgentEvalSuite(
        config=replace(full_suite.config, case_count=1),
        dataset_path=full_suite.dataset_path,
        cases=(first_case,),
    )
    database_path = tmp_path / "agent-runs.db"
    repository = SQLiteAgentRunRepository(database_path)
    runner = AgentEvalRunner(
        run_service=AgentRunService(
            repository=repository,
            execution_config_version=suite.config.runner_config_version,
        ),
        model=_FinalOnlyModel(),
        registry={},
        execution_context=ToolExecutionContext(
            trusted_context=TrustedContext(workspace_id="WS-EVAL"),
            filters=SearchFilters(document_id="DOC-EVAL"),
        ),
    )

    results = runner.run(suite)

    assert len(results) == 1
    assert results[0].case_id == first_case.case_id
    assert results[0].observed_terminal_status is AgentTerminalStatus.SUCCESS
    assert score_tool_selection(suite.cases, results) == Score(1, 1)
    assert score_parameters(suite.cases, results) == Score(0, 0)
    assert score_terminal_status(suite.cases, results) == Score(1, 1)

    reopened = SQLiteAgentRunRepository(database_path)
    stored_run = reopened.get_run(
        workspace_id="WS-EVAL",
        run_id=results[0].run_id,
    )
    stored_events = reopened.list_events(
        workspace_id="WS-EVAL",
        run_id=results[0].run_id,
    )
    assert stored_run is not None
    assert stored_run.terminal_status is AgentTerminalStatus.SUCCESS
    assert [event.sequence for event in stored_events] == [1]

    safe_storage = json.dumps(
        {
            "safe_result": stored_run.safe_result,
            "events": [event.payload for event in stored_events],
        },
        ensure_ascii=False,
    )
    assert first_case.prompt not in safe_storage
    assert "prompt-marker" not in safe_storage
