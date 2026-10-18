import argparse
from collections.abc import Sequence
from pathlib import Path

from dotenv import load_dotenv

from app.agent.eval_fixtures import build_agent_eval_dependencies
from app.agent.eval_reporting import (
    AgentEvalExecutionKind,
    build_agent_eval_report,
    write_agent_eval_report,
)
from app.agent.eval_runner import AgentEvalRunner
from app.agent.evaluation import load_agent_eval_suite
from app.agent.run_models import AgentTerminalStatus
from app.agent.run_service import AgentRunService
from app.agent.sqlite_run_repository import SQLiteAgentRunRepository
from app.rag.openai_compatible_llm import OpenAICompatibleLLMClient


PROJECT_ROOT = Path(__file__).parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "eval/agent_eval_config_v1.json"
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "eval/agent_results/agent_runs.sqlite3"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "eval/agent_results"


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """解析正式 Agent 评测的冻结配置、Run 库和输出目录。"""
    parser = argparse.ArgumentParser(description="执行一次冻结的真实模型 Agent 评测")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """执行一次真实模型 Agent 评测，并以唯一文件名保存证据。"""
    args = _parse_args(argv)
    suite = load_agent_eval_suite(args.config.resolve())
    registry, execution_context = build_agent_eval_dependencies()
    if tuple(registry) != suite.config.tool_names:
        raise RuntimeError("实际工具 registry 与冻结工具配置不一致")

    load_dotenv(PROJECT_ROOT / ".env")
    model = OpenAICompatibleLLMClient.from_env()
    repository = SQLiteAgentRunRepository(args.database.resolve())
    runner = AgentEvalRunner(
        run_service=AgentRunService(
            repository=repository,
            execution_config_version=suite.config.runner_config_version,
        ),
        model=model,
        registry=registry,
        execution_context=execution_context,
    )

    results = runner.run(suite)
    report = build_agent_eval_report(
        suite=suite,
        results=results,
        execution_kind=AgentEvalExecutionKind.REAL_MODEL,
        model_name=model.model,
    )
    output_path = write_agent_eval_report(
        report=report,
        output_dir=args.output_dir.resolve(),
    )

    provider_unavailable = any(
        result.observed_terminal_status is AgentTerminalStatus.PROVIDER_ERROR for result in results
    )
    if provider_unavailable:
        print("真实模型指标：未测（供应商调用不可用）")
    else:
        scores = report.scores
        print(
            "工具选择: "
            f"{scores.tool_selection.correct}/{scores.tool_selection.total}; "
            "参数: "
            f"{scores.parameters.correct}/{scores.parameters.total}; "
            "终态: "
            f"{scores.terminal_status.correct}/{scores.terminal_status.total}"
        )
    print(f"评测证据已保存: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
