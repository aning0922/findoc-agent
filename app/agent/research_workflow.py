"""同一文档两期营业收入研究 Workflow 的最小状态变体。

本模块只表达候选、明确确认、确定性计算和终态规则；
不调用模型，不进入生产 runtime，也不是第二套 Agent loop。
"""

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum

from app.agent.finance_tools import CalculateFinancialMetricTool, FinancialMetricError
from app.agent.financial_facts import (
    FinancialFact,
    FinancialFactKey,
    FinancialFactRepository,
    FinancialUnit,
    InMemoryFinancialFactRepository,
)
from app.agent.tool_loop import ToolExecutionContext
from app.rag.retriever import SearchFilters, TrustedContext


TARGET_PERIODS = (2024, 2025)
"""当前最小业务合同唯一允许的两个营业收入期间。"""


class RevenueWorkflowStage(StrEnum):
    """研究 Workflow 当前所在的程序阶段。"""

    COLLECTING_CANDIDATES = "collecting_candidates"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    READY_FOR_CALCULATION = "ready_for_calculation"
    COMPLETED = "completed"
    FAILED = "failed"


class RevenueWorkflowFailureCode(StrEnum):
    """候选检查阶段的稳定业务失败码。"""

    MISSING_CANDIDATE = "missing_candidate"
    CANDIDATE_CONFLICT = "candidate_conflict"
    SCOPE_MISMATCH = "scope_mismatch"
    UNIT_UNKNOWN = "unit_unknown"
    UNIT_CONFLICT = "unit_conflict"
    SOURCE_INVALID = "source_invalid"
    PERIOD_MISMATCH = "period_mismatch"
    STEP_LIMIT = "step_limit"


class RevenueWorkflowTransitionError(RuntimeError):
    """调用方尝试执行当前阶段不允许的状态转移。"""


@dataclass(frozen=True)
class RevenueEvidence:
    """一处候选证据：保存实际命中全文、原文位置及未换算的数字/单位。

    start/end 是 Python 字符位置，text[start:end] 可回看被抽取的完整行。
    来源归属由抽取入口对照已核准文档验证，本类型只检查字段结构。
    """

    chunk_id: str
    source_file: str
    page: int
    text: str
    start: int
    end: int
    raw_value: str
    raw_unit: str | None

    def __post_init__(self) -> None:
        """拒绝空来源、非法页码/位置，以及不能回查的原始数字。"""
        for name in ("chunk_id", "source_file", "text", "raw_value"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} 必须是非空字符串")
        for name in ("page", "start", "end"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} 必须是整数")
        if self.page < 1 or not 0 <= self.start < self.end <= len(self.text):
            raise ValueError("证据页码或原文位置非法")
        if self.raw_value not in self.text[self.start : self.end]:
            raise ValueError("原始数字不在指定证据位置中")
        if self.raw_unit is not None and (
            not isinstance(self.raw_unit, str)
            or not self.raw_unit.strip()
            or self.raw_unit not in self.text[self.start : self.end]
        ):
            raise ValueError("原始单位必须来自指定证据位置")


@dataclass(frozen=True)
class RevenueCandidate:
    """从文档证据提出、但尚未经操作者确认的营业收入候选。

    `source_ref` 是候选事实的唯一引用，可在同一 `chunk_id`
    中分别标识 2024 和 2025 两条候选。它不表示已确认。
    """

    workspace_id: str
    document_id: str
    source_ref: str
    chunk_id: str
    source_file: str
    page: int
    period: int
    value: Decimal
    unit: FinancialUnit | None
    evidence: tuple[RevenueEvidence, ...] = ()
    """规则抽取保留全部证据；空元组仅兼容既有纯 Python 状态变体。"""
    extraction_method: str = "provided"
    extraction_version: str = "v1"

    def __post_init__(self) -> None:
        """校验候选的范围、来源和结构，不将它升格为已确认事实。"""
        for field_name in (
            "workspace_id",
            "document_id",
            "source_ref",
            "chunk_id",
            "source_file",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} 必须是非空字符串")
            if not value.strip():
                raise ValueError(f"{field_name} 必须是非空字符串")
        if isinstance(self.page, bool) or not isinstance(self.page, int):
            raise TypeError("page 必须是正整数")
        if self.page <= 0:
            raise ValueError("page 必须是正整数")
        if self.period not in TARGET_PERIODS:
            raise ValueError("候选期间只能是 2024 或 2025")
        if not isinstance(self.value, Decimal):
            raise TypeError("value 必须是 Decimal")
        if not self.value.is_finite():
            raise ValueError("value 必须是有限 Decimal")
        if self.unit is not None and not isinstance(self.unit, FinancialUnit):
            raise TypeError("unit 必须是 FinancialUnit 或 None")
        if not isinstance(self.evidence, tuple) or not all(
            isinstance(item, RevenueEvidence) for item in self.evidence
        ):
            raise TypeError("evidence 必须是 RevenueEvidence 元组")
        for name in ("extraction_method", "extraction_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} 必须是非空字符串")
        if self.evidence:
            first = self.evidence[0]
            if (first.chunk_id, first.source_file, first.page) != (
                self.chunk_id,
                self.source_file,
                self.page,
            ) or any(item.source_file != self.source_file for item in self.evidence):
                raise ValueError("候选展示来源必须与所保留证据一致")


@dataclass(frozen=True)
class ConfirmedRevenueFact:
    """操作者明确确认后的财务事实与可读来源。"""

    fact: FinancialFact
    chunk_id: str
    source_file: str
    page: int
    evidence: tuple[RevenueEvidence, ...] = ()


@dataclass(frozen=True)
class RevenueGrowthResult:
    """程序公式产生的增长率以及其两条已确认输入来源。"""

    value: Decimal
    unit: str
    formula_id: str
    sources: tuple[ConfirmedRevenueFact, ConfirmedRevenueFact]


FailureCode = RevenueWorkflowFailureCode | str


@dataclass(frozen=True)
class RevenueWorkflowState:
    """单次营业收入研究 Workflow 的不可变业务快照。

    转移函数返回新实例；调用方不应原地改写候选、确认事实或结果。
    """

    workspace_id: str
    document_id: str
    stage: RevenueWorkflowStage
    candidates: tuple[RevenueCandidate, ...] = ()
    confirmed_facts: tuple[ConfirmedRevenueFact, ...] = ()
    result: RevenueGrowthResult | None = None
    failure_code: FailureCode | None = None


def begin_revenue_workflow(*, workspace_id: str, document_id: str) -> RevenueWorkflowState:
    """以服务端已核准的工作区和单文档范围创建初始状态。"""
    for name, value in (("workspace_id", workspace_id), ("document_id", document_id)):
        if not isinstance(value, str):
            raise TypeError(f"{name} 必须是非空字符串")
        if not value.strip():
            raise ValueError(f"{name} 必须是非空字符串")
    return RevenueWorkflowState(
        workspace_id=workspace_id,
        document_id=document_id,
        stage=RevenueWorkflowStage.COLLECTING_CANDIDATES,
    )


def record_revenue_candidates(
    state: RevenueWorkflowState,
    candidates: tuple[RevenueCandidate, ...],
) -> RevenueWorkflowState:
    """检查固定范围内的两期候选，然后进入等待确认或失败终态。

    抽取层先合并相同金额的已知单位证据；本函数要求每期唯一候选。
    单位未知不能进入等待确认，多值候选不能由相似度自动选取。
    """
    _require_stage(state, RevenueWorkflowStage.COLLECTING_CANDIDATES)
    if not isinstance(candidates, tuple) or not all(
        isinstance(candidate, RevenueCandidate) for candidate in candidates
    ):
        raise TypeError("candidates 必须是 RevenueCandidate 元组")

    if any(
        candidate.workspace_id != state.workspace_id or candidate.document_id != state.document_id
        for candidate in candidates
    ):
        return _fail(state, RevenueWorkflowFailureCode.SCOPE_MISMATCH, candidates)

    by_period = {
        period: tuple(candidate for candidate in candidates if candidate.period == period)
        for period in TARGET_PERIODS
    }
    if any(len(by_period[period]) == 0 for period in TARGET_PERIODS):
        return _fail(state, RevenueWorkflowFailureCode.MISSING_CANDIDATE, candidates)
    if any(candidate.unit is None for candidate in candidates):
        return _fail(state, RevenueWorkflowFailureCode.UNIT_UNKNOWN, candidates)
    if any(len(by_period[period]) > 1 for period in TARGET_PERIODS):
        return _fail(state, RevenueWorkflowFailureCode.CANDIDATE_CONFLICT, candidates)

    selected = tuple(by_period[period][0] for period in TARGET_PERIODS)
    if len({candidate.unit for candidate in selected}) != 1:
        return _fail(state, RevenueWorkflowFailureCode.UNIT_CONFLICT, selected)

    return replace(
        state,
        stage=RevenueWorkflowStage.AWAITING_CONFIRMATION,
        candidates=selected,
    )


def confirm_revenue_candidates(state: RevenueWorkflowState) -> RevenueWorkflowState:
    """处理操作者对当前两条候选的明确确认动作。

    输入必须是 `awaiting_confirmation` 状态；输出是包含两条
    `FinancialFact` 的新状态。本函数不计算增长率。
    """
    _require_stage(state, RevenueWorkflowStage.AWAITING_CONFIRMATION)
    confirmed_items: list[ConfirmedRevenueFact] = []
    for candidate in state.candidates:
        if candidate.unit is None:
            raise RevenueWorkflowTransitionError("单位不明的候选不能确认")
        confirmed_items.append(
            ConfirmedRevenueFact(
                fact=FinancialFact(
                    workspace_id=candidate.workspace_id,
                    document_id=candidate.document_id,
                    source_ref=candidate.source_ref,
                    fact_key=FinancialFactKey.REVENUE,
                    period=candidate.period,
                    value=candidate.value,
                    unit=candidate.unit,
                ),
                chunk_id=candidate.chunk_id,
                source_file=candidate.source_file,
                page=candidate.page,
                evidence=candidate.evidence,
            )
        )
    confirmed = tuple(confirmed_items)
    if len(confirmed) != 2:
        raise RevenueWorkflowTransitionError("只有完整的两期候选才能确认")
    return replace(
        state,
        stage=RevenueWorkflowStage.READY_FOR_CALCULATION,
        confirmed_facts=confirmed,
    )


def calculate_confirmed_revenue_growth(
    state: RevenueWorkflowState,
    *,
    repository: FinancialFactRepository | None = None,
) -> RevenueWorkflowState:
    """只读取两条已确认事实，复用现有确定性工具生成带来源结果。

    输入必须是 `ready_for_calculation` 状态。成功返回 `completed`；
    现有计算器拒绝期间、单位或零分母时，返回保留其稳定错误码的失败终态。
    """
    _require_stage(state, RevenueWorkflowStage.READY_FOR_CALCULATION)
    if len(state.confirmed_facts) != 2:
        raise RevenueWorkflowTransitionError("计算前必须有两条已确认事实")

    ordered = tuple(sorted(state.confirmed_facts, key=lambda item: item.fact.period))
    previous, current = ordered
    # 纯 Python 变体保留内存默认值；持久确认入口注入本次查证后的 SQLite 查询。
    if repository is None:
        repository = InMemoryFinancialFactRepository([previous.fact, current.fact])
    calculator = CalculateFinancialMetricTool(repository)
    execution_context = ToolExecutionContext(
        trusted_context=TrustedContext(workspace_id=state.workspace_id),
        filters=SearchFilters(document_id=state.document_id),
    )
    try:
        payload = calculator(
            execution_context,
            metric_id="revenue_growth_rate",
            current_period_source_ref=current.fact.source_ref,
            previous_period_source_ref=previous.fact.source_ref,
        )
    except FinancialMetricError as exc:
        return replace(
            state,
            stage=RevenueWorkflowStage.FAILED,
            failure_code=exc.code.value,
            result=None,
        )

    value = payload.get("value")
    unit = payload.get("unit")
    formula_id = payload.get("formula_id")
    if not isinstance(value, str) or not isinstance(unit, str) or not isinstance(formula_id, str):
        raise RuntimeError("现有计算器返回了非法结果结构")
    result = RevenueGrowthResult(
        value=Decimal(value),
        unit=unit,
        formula_id=formula_id,
        sources=(current, previous),
    )
    return replace(
        state,
        stage=RevenueWorkflowStage.COMPLETED,
        result=result,
    )


def _require_stage(state: RevenueWorkflowState, expected: RevenueWorkflowStage) -> None:
    """拒绝跳过确认或对终态重复执行的非法转移。"""
    if not isinstance(state, RevenueWorkflowState):
        raise TypeError("state 必须是 RevenueWorkflowState")
    if state.stage is not expected:
        raise RevenueWorkflowTransitionError(
            f"当前阶段 {state.stage.value} 不能执行 {expected.value} 阶段的操作"
        )


def _fail(
    state: RevenueWorkflowState,
    code: RevenueWorkflowFailureCode,
    candidates: tuple[RevenueCandidate, ...],
) -> RevenueWorkflowState:
    """生成不含计算结果的候选检查失败终态。"""
    return replace(
        state,
        stage=RevenueWorkflowStage.FAILED,
        candidates=candidates,
        failure_code=code,
    )
