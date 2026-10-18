from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Sequence

from app.agent.run_models import AgentTerminalStatus


@dataclass(frozen=True)
class ObservedToolCall:
    """记录模型实际发起的一次工具调用"""

    tool_name: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class AgentEvalCase:
    """保存一条冻结的 Agent 评测标准-"""

    case_id: str
    prompt: str
    expected_tool_sequence: tuple[str, ...]
    expected_argument_rules: tuple[dict[str, dict[str, object]], ...]
    expected_terminal_status: AgentTerminalStatus


@dataclass(frozen=True)
class AgentEvalResult:
    """某次运行的实际观察"""

    case_id: str
    run_id: str
    observed_tool_calls: tuple[ObservedToolCall, ...]
    observed_terminal_status: AgentTerminalStatus


@dataclass(frozen=True)
class AgentEvalConfig:
    """保存数据集 hash、工具 schema 和 runner 的冻结配置。"""

    schema_version: str
    dataset_path: str
    dataset_sha256: str
    case_count: int
    tool_schema_version: str
    tool_names: tuple[str, ...]
    runner_config_version: str
    parameter_rule_version: str
    allowed_rule_operators: tuple[str, ...]
    max_steps: int


@dataclass(frozen=True)
class AgentEvalSuite:
    """保存通过配置、hash 和数量校验的完整评测套件。"""

    config: AgentEvalConfig
    dataset_path: Path
    cases: tuple[AgentEvalCase, ...]


@dataclass(frozen=True)
class Score:
    """记录某项评测指标的正确数和分母。"""

    correct: int
    total: int

    @property
    def rate(self) -> float | None:
        """返回正确率；没有有效样本时返回 None。"""
        if self.total == 0:
            return None
        return self.correct / self.total


def score_tool_selection(
    cases: Sequence[AgentEvalCase], results: Sequence[AgentEvalResult]
) -> Score:
    """按案例比较完整的有序工具序列。"""
    result_by_case = {result.case_id: result for result in results}
    correct = 0
    for case in cases:
        result = result_by_case.get(case.case_id)
        if result is None:
            continue
        actual_sequence = tuple(call.tool_name for call in result.observed_tool_calls)

        if actual_sequence == case.expected_tool_sequence:
            correct += 1
    return Score(correct=correct, total=len(cases))


def _argument_rule_matches(actual_value: object, rule: dict[str, object]) -> bool:
    """判断一个实际参数值是否满足冻结规则"""
    operator = rule.get("operator")
    if operator == "equals":
        return actual_value == rule["value"]
    if operator == "non_empty_string":
        return isinstance(actual_value, str) and actual_value.strip() != ""
    if operator == "contains_all":
        keywords = rule.get("value")
        if not isinstance(actual_value, str):
            return False
        if not isinstance(keywords, (list, tuple)):
            raise ValueError("contains_all 的 value 必须是关键词列表")
        if not keywords or not all(isinstance(keyword, str) and keyword for keyword in keywords):
            raise ValueError("contains_all 的关键词必须是非空字符串")
        normalized_actual = actual_value.casefold()
        return all(keyword.casefold() in normalized_actual for keyword in keywords)
    raise ValueError(f"不支持的参数规则：{operator!r}")


def score_parameters(cases: Sequence[AgentEvalCase], results: Sequence[AgentEvalResult]) -> Score:
    """按期望工具调用槽位检查参数规则"""
    result_by_case = {result.case_id: result for result in results}

    total = 0
    correct = 0
    for case in cases:
        total += len(case.expected_argument_rules)
        result = result_by_case.get(case.case_id)
        if result is None:
            continue
        for index, argument_rules in enumerate(case.expected_argument_rules):
            if index >= len(result.observed_tool_calls):
                continue

            actual_call = result.observed_tool_calls[index]
            expected_tool_name = case.expected_tool_sequence[index]

            if actual_call.tool_name != expected_tool_name:
                continue

            slot_matches = True

            for argument_name, rule in argument_rules.items():
                if argument_name not in actual_call.arguments:
                    slot_matches = False
                    break

                if not _argument_rule_matches(actual_call.arguments[argument_name], rule):
                    slot_matches = False
                    break

            if slot_matches:
                correct += 1
    return Score(correct=correct, total=total)


def score_terminal_status(
    cases: Sequence[AgentEvalCase], results: Sequence[AgentEvalResult]
) -> Score:
    """按案例比较实际终态与期望终态"""
    result_by_case: dict[str, AgentEvalResult] = {result.case_id: result for result in results}
    total = 0
    correct = 0
    for case in cases:
        total += 1
        result = result_by_case.get(case.case_id)
        if result is None:
            continue
        if result.observed_terminal_status == case.expected_terminal_status:
            correct += 1
    return Score(correct=correct, total=total)


def compute_dataset_sha256(path: Path) -> str:
    """计算评测数据集原始字节的 SHA-256 哈希值"""
    raw_path = path.read_bytes()
    digest = sha256(raw_path)
    return digest.hexdigest()


def load_agent_eval_cases(path: Path) -> tuple[AgentEvalCase, ...]:
    """读取并校验冻结的 Agent 评测任务"""
    cases: list[AgentEvalCase] = []
    seen_case_ids: set[str] = set()

    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue

        raw_case = json.loads(line)

        if not isinstance(raw_case, dict):
            raise ValueError(f"第 {line_number} 行必须是 JSON 对象")

        case = AgentEvalCase(
            case_id=raw_case["case_id"],
            prompt=raw_case["prompt"],
            expected_tool_sequence=tuple(raw_case["expected_tool_sequence"]),
            expected_argument_rules=tuple(raw_case["expected_argument_rules"]),
            expected_terminal_status=AgentTerminalStatus(raw_case["expected_terminal_status"]),
        )
        if case.case_id in seen_case_ids:
            raise ValueError(f"重复的 case_id: {case.case_id}")

        if len(case.expected_tool_sequence) != len(case.expected_argument_rules):
            raise ValueError(f"{case.case_id} 的工具序列与参数槽位数量不一致")

        seen_case_ids.add(case.case_id)
        cases.append(case)

    return tuple(cases)


def load_agent_eval_suite(config_path: Path) -> AgentEvalSuite:
    """根据冻结配置加载并校验可复现的 Agent 评测套件。"""
    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw_config, dict):
        raise ValueError("评测配置必须是 JSON 对象")

    string_fields = (
        "schema_version",
        "dataset_path",
        "dataset_sha256",
        "tool_schema_version",
        "runner_config_version",
        "parameter_rule_version",
    )
    for field_name in string_fields:
        value = raw_config.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"评测配置 {field_name} 必须是非空字符串")

    case_count = raw_config.get("case_count")
    max_steps = raw_config.get("max_steps")
    if not isinstance(case_count, int) or isinstance(case_count, bool) or case_count <= 0:
        raise ValueError("评测配置 case_count 必须是正整数")
    if not isinstance(max_steps, int) or isinstance(max_steps, bool) or max_steps <= 0:
        raise ValueError("评测配置 max_steps 必须是正整数")

    raw_tool_names = raw_config.get("tool_names")
    raw_operators = raw_config.get("allowed_rule_operators")
    if (
        not isinstance(raw_tool_names, list)
        or not raw_tool_names
        or not all(isinstance(name, str) and name for name in raw_tool_names)
    ):
        raise ValueError("评测配置 tool_names 必须是非空工具名列表")
    if (
        not isinstance(raw_operators, list)
        or not raw_operators
        or not all(isinstance(operator, str) and operator for operator in raw_operators)
    ):
        raise ValueError("评测配置 allowed_rule_operators 必须是非空列表")

    config = AgentEvalConfig(
        schema_version=raw_config["schema_version"],
        dataset_path=raw_config["dataset_path"],
        dataset_sha256=raw_config["dataset_sha256"],
        case_count=case_count,
        tool_schema_version=raw_config["tool_schema_version"],
        tool_names=tuple(raw_tool_names),
        runner_config_version=raw_config["runner_config_version"],
        parameter_rule_version=raw_config["parameter_rule_version"],
        allowed_rule_operators=tuple(raw_operators),
        max_steps=max_steps,
    )
    dataset_path = (config_path.parent / config.dataset_path).resolve()
    actual_hash = compute_dataset_sha256(dataset_path)
    if actual_hash != config.dataset_sha256:
        raise ValueError(
            f"评测数据集 hash 不匹配: 期望 {config.dataset_sha256}, 实际 {actual_hash}"
        )

    cases = load_agent_eval_cases(dataset_path)
    if len(cases) != config.case_count:
        raise ValueError(f"评测案例数不匹配: 期望 {config.case_count}, 实际 {len(cases)}")

    allowed_tools = set(config.tool_names)
    allowed_operators = set(config.allowed_rule_operators)
    for case in cases:
        unknown_tools = set(case.expected_tool_sequence) - allowed_tools
        if unknown_tools:
            raise ValueError(f"{case.case_id} 包含未冻结工具: {sorted(unknown_tools)}")
        for argument_rules in case.expected_argument_rules:
            for rule in argument_rules.values():
                operator = rule.get("operator")
                if operator not in allowed_operators:
                    raise ValueError(f"{case.case_id} 包含未冻结参数规则: {operator!r}")

    return AgentEvalSuite(config=config, dataset_path=dataset_path, cases=cases)
