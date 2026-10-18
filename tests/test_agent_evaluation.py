import json
from pathlib import Path

import pytest

from app.agent.evaluation import (
    AgentEvalCase,
    AgentEvalResult,
    ObservedToolCall,
    Score,
    compute_dataset_sha256,
    load_agent_eval_suite,
    score_parameters,
    score_terminal_status,
    score_tool_selection,
)
from app.agent.run_models import AgentTerminalStatus


PROJECT_ROOT = Path(__file__).parents[1]
AGENT_EVAL_CONFIG_PATH = PROJECT_ROOT / "eval/agent_eval_config_v1.json"


@pytest.mark.parametrize(
    (
        "actual_arguments",
        "actual_terminal",
        "expected_tool_score",
        "expected_parameter_score",
        "expected_terminal_score",
    ),
    [
        # 工具正确、参数错误
        (
            {"query": "净利润"},
            AgentTerminalStatus.SUCCESS,
            Score(correct=1, total=1),
            Score(correct=0, total=1),
            Score(correct=1, total=1),
        ),
        # 工具正确、终态错误
        (
            {"query": "2023 年营业收入"},
            AgentTerminalStatus.TOOL_ERROR,
            Score(correct=1, total=1),
            Score(correct=1, total=1),
            Score(correct=0, total=1),
        ),
    ],
)
def test_scorers_are_independent(
    actual_arguments: dict[str, object],
    actual_terminal: AgentTerminalStatus,
    expected_tool_score: Score,
    expected_parameter_score: Score,
    expected_terminal_score: Score,
) -> None:
    """验证工具、参数和终态指标不会互相吞并。"""
    case = AgentEvalCase(
        case_id="scorer-boundary",
        prompt="检索 2023 年营业收入。",
        expected_tool_sequence=("search_finance_docs",),
        expected_argument_rules=(
            {
                "query": {
                    "operator": "contains_all",
                    "value": ["2023", "营业收入"],
                }
            },
        ),
        expected_terminal_status=AgentTerminalStatus.SUCCESS,
    )

    result = AgentEvalResult(
        case_id=case.case_id,
        run_id="run-scorer-boundary",
        observed_tool_calls=(
            ObservedToolCall(
                tool_name="search_finance_docs",
                arguments=actual_arguments,
            ),
        ),
        observed_terminal_status=actual_terminal,
    )
    tool_score = score_tool_selection([case], [result])
    parameter_score = score_parameters([case], [result])
    terminal_score = score_terminal_status([case], [result])

    assert tool_score == expected_tool_score
    assert parameter_score == expected_parameter_score
    assert terminal_score == expected_terminal_score


def test_agent_eval_suite_has_exactly_twelve_reproducible_cases() -> None:
    """验证 Agent 任务数、唯一 ID 和冻结数据集 hash。"""
    suite = load_agent_eval_suite(AGENT_EVAL_CONFIG_PATH)

    assert suite.config.case_count == 12
    assert len(suite.cases) == 12
    assert len({case.case_id for case in suite.cases}) == 12
    assert compute_dataset_sha256(suite.dataset_path) == suite.config.dataset_sha256


def test_agent_eval_suite_rejects_changed_dataset_hash(tmp_path: Path) -> None:
    """验证冻结数据集任何字节变化都会阻止评测。"""
    original_suite = load_agent_eval_suite(AGENT_EVAL_CONFIG_PATH)
    changed_dataset_path = tmp_path / original_suite.dataset_path.name
    changed_dataset_path.write_bytes(original_suite.dataset_path.read_bytes() + b"\n")

    raw_config = json.loads(AGENT_EVAL_CONFIG_PATH.read_text(encoding="utf-8"))
    raw_config["dataset_path"] = changed_dataset_path.name
    changed_config_path = tmp_path / AGENT_EVAL_CONFIG_PATH.name
    changed_config_path.write_text(
        json.dumps(raw_config, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="hash 不匹配"):
        load_agent_eval_suite(changed_config_path)
