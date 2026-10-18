import json
from pathlib import Path

import pytest

from app.agent.eval_reporting import (
    AgentEvalExecutionKind,
    build_agent_eval_report,
    write_agent_eval_report,
)
from app.agent.evaluation import (
    AgentEvalResult,
    load_agent_eval_suite,
)
from app.agent.run_models import AgentTerminalStatus


PROJECT_ROOT = Path(__file__).parents[1]
AGENT_EVAL_CONFIG_PATH = PROJECT_ROOT / "eval/agent_eval_config_v1.json"


def test_scripted_report_is_labeled_and_cannot_be_overwritten(tmp_path: Path) -> None:
    """验证 scripted 结果不得声称模型质量，且同一报告不得覆盖。"""
    suite = load_agent_eval_suite(AGENT_EVAL_CONFIG_PATH)
    first_case = suite.cases[0]
    result = AgentEvalResult(
        case_id=first_case.case_id,
        run_id="run-contract-001",
        observed_tool_calls=(),
        observed_terminal_status=AgentTerminalStatus.SUCCESS,
    )
    report = build_agent_eval_report(
        suite=suite,
        results=(result,),
        execution_kind=AgentEvalExecutionKind.SCRIPTED_CONTRACT,
        model_name=None,
    )

    output_path = write_agent_eval_report(report=report, output_dir=tmp_path)
    original_bytes = output_path.read_bytes()
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["execution_kind"] == "scripted_contract"
    assert payload["quality_status"] == "contract_only"
    assert payload["quality_claim_allowed"] is False
    assert payload["scores"]["tool_selection"] == {
        "correct": 1,
        "total": 12,
        "rate": pytest.approx(1 / 12),
    }

    with pytest.raises(FileExistsError):
        write_agent_eval_report(report=report, output_dir=tmp_path)
    assert output_path.read_bytes() == original_bytes


def test_real_model_report_requires_model_name() -> None:
    """验证真实模型评测必须保存非空模型名称。"""
    suite = load_agent_eval_suite(AGENT_EVAL_CONFIG_PATH)

    with pytest.raises(ValueError, match="模型名称"):
        build_agent_eval_report(
            suite=suite,
            results=(),
            execution_kind=AgentEvalExecutionKind.REAL_MODEL,
            model_name=None,
        )


def test_real_report_disallows_quality_claim_when_provider_is_unavailable(
    tmp_path: Path,
) -> None:
    """验证任一供应商失败都使正式报告标记为未测。"""
    suite = load_agent_eval_suite(AGENT_EVAL_CONFIG_PATH)
    results = tuple(
        AgentEvalResult(
            case_id=case.case_id,
            run_id=f"run-{case.case_id}",
            observed_tool_calls=(),
            observed_terminal_status=AgentTerminalStatus.PROVIDER_ERROR,
        )
        for case in suite.cases
    )
    report = build_agent_eval_report(
        suite=suite,
        results=results,
        execution_kind=AgentEvalExecutionKind.REAL_MODEL,
        model_name="real-model",
    )

    output_path = write_agent_eval_report(report=report, output_dir=tmp_path)
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["quality_status"] == "provider_unavailable"
    assert payload["quality_claim_allowed"] is False
