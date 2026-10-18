import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from app.agent.evaluation import (
    AgentEvalResult,
    AgentEvalSuite,
    Score,
    score_parameters,
    score_terminal_status,
    score_tool_selection,
)
from app.agent.run_models import AgentTerminalStatus


class AgentEvalExecutionKind(StrEnum):
    """区分真实模型评测与只验证代码合同的 scripted 运行。"""

    REAL_MODEL = "real_model"
    SCRIPTED_CONTRACT = "scripted_contract"


@dataclass(frozen=True)
class AgentEvalScores:
    """保存三个分母独立的 Agent 评测指标。"""

    tool_selection: Score
    parameters: Score
    terminal_status: Score


@dataclass(frozen=True)
class AgentEvalReport:
    """保存一次可追溯评测的冻结配置、安全结果和独立指标。"""

    evaluation_run_id: str
    execution_kind: AgentEvalExecutionKind
    created_at: datetime
    model_name: str | None
    dataset_sha256: str
    schema_version: str
    tool_schema_version: str
    runner_config_version: str
    expected_case_count: int
    scores: AgentEvalScores
    results: tuple[AgentEvalResult, ...]


def build_agent_eval_report(
    *,
    suite: AgentEvalSuite,
    results: tuple[AgentEvalResult, ...],
    execution_kind: AgentEvalExecutionKind,
    model_name: str | None,
) -> AgentEvalReport:
    """用唯一 ID 组装评测证据，并保持三个 scorer 独立。"""
    if not isinstance(execution_kind, AgentEvalExecutionKind):
        raise TypeError("execution_kind 必须是 AgentEvalExecutionKind")
    if execution_kind is AgentEvalExecutionKind.REAL_MODEL and (
        not isinstance(model_name, str) or not model_name.strip()
    ):
        raise ValueError("真实模型评测必须记录模型名称")

    case_ids = {case.case_id for case in suite.cases}
    result_ids = [result.case_id for result in results]
    if len(result_ids) != len(set(result_ids)):
        raise ValueError("评测结果不能包含重复 case_id")
    unknown_ids = set(result_ids) - case_ids
    if unknown_ids:
        raise ValueError(f"评测结果包含未知 case_id: {sorted(unknown_ids)}")

    scores = AgentEvalScores(
        tool_selection=score_tool_selection(suite.cases, results),
        parameters=score_parameters(suite.cases, results),
        terminal_status=score_terminal_status(suite.cases, results),
    )
    return AgentEvalReport(
        evaluation_run_id=str(uuid4()),
        execution_kind=execution_kind,
        created_at=datetime.now(UTC),
        model_name=model_name,
        dataset_sha256=suite.config.dataset_sha256,
        schema_version=suite.config.schema_version,
        tool_schema_version=suite.config.tool_schema_version,
        runner_config_version=suite.config.runner_config_version,
        expected_case_count=suite.config.case_count,
        scores=scores,
        results=results,
    )


def _score_payload(score: Score) -> dict[str, object]:
    """把单个指标转为保留分子、分母的 JSON 结构。"""
    return {
        "correct": score.correct,
        "total": score.total,
        "rate": score.rate,
    }


def _report_payload(report: AgentEvalReport) -> dict[str, object]:
    """显式白名单化报告字段，避免自动扩大持久化边界。"""
    has_complete_results = len(report.results) == report.expected_case_count
    provider_available = all(
        result.observed_terminal_status is not AgentTerminalStatus.PROVIDER_ERROR
        for result in report.results
    )
    quality_claim_allowed = (
        report.execution_kind is AgentEvalExecutionKind.REAL_MODEL
        and has_complete_results
        and provider_available
    )
    if report.execution_kind is AgentEvalExecutionKind.SCRIPTED_CONTRACT:
        quality_status = "contract_only"
    elif not has_complete_results:
        quality_status = "incomplete"
    elif not provider_available:
        quality_status = "provider_unavailable"
    else:
        quality_status = "measured"

    return {
        "evaluation_run_id": report.evaluation_run_id,
        "execution_kind": report.execution_kind.value,
        "quality_status": quality_status,
        "quality_claim_allowed": quality_claim_allowed,
        "created_at": report.created_at.isoformat(),
        "model_name": report.model_name,
        "dataset_sha256": report.dataset_sha256,
        "schema_version": report.schema_version,
        "tool_schema_version": report.tool_schema_version,
        "runner_config_version": report.runner_config_version,
        "expected_case_count": report.expected_case_count,
        "scores": {
            "tool_selection": _score_payload(report.scores.tool_selection),
            "parameters": _score_payload(report.scores.parameters),
            "terminal_status": _score_payload(report.scores.terminal_status),
        },
        "results": [
            {
                "case_id": result.case_id,
                "run_id": result.run_id,
                "observed_tool_calls": [
                    {
                        "tool_name": call.tool_name,
                        "arguments": call.arguments,
                    }
                    for call in result.observed_tool_calls
                ],
                "observed_terminal_status": result.observed_terminal_status.value,
            }
            for result in report.results
        ],
    }


def write_agent_eval_report(*, report: AgentEvalReport, output_dir: Path) -> Path:
    """以唯一文件名写入评测报告，已存在时明确拒绝覆盖。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"agent_eval_{report.evaluation_run_id}.json"
    with output_path.open("x", encoding="utf-8") as output_file:
        json.dump(
            _report_payload(report),
            output_file,
            ensure_ascii=False,
            indent=2,
        )
        output_file.write("\n")
    return output_path
