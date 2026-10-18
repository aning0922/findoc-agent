"""收入研究的独立本地图：显式调度已有服务，不重写确认或计算规则。

只使用默认字段覆盖；不配置 checkpoint、缓存、重试，也不接生产 runtime。
输入 ID 只是查询线索，候选摘要不作为确认事实或公式输入。
"""

from dataclasses import dataclass
from decimal import Decimal
import logging
from typing import Literal, NotRequired, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.financial_facts import FinancialUnit
from app.agent.revenue_confirmation import (
    ConfirmedRevenueCalculation,
    RevenueConfirmationError,
    RevenueReview,
    RevenueSourceRevision,
)
from app.documents.models import DocumentNotFoundError
from app.documents.preparation import DocumentNotReadyError


logger = logging.getLogger(__name__)
GraphStatus = Literal[
    "previewed", "verification_pending", "needs_confirmation", "completed", "refused", "failed"
]


class RevenueGraphService(Protocol):
    """图只依赖只读公共能力；真实 RevenueConfirmationService 可直接注入。

    preview 接收文档 ID，返回当前可审阅候选；calculate 接收两 ID，只有实际
    核验与计算成功才返回结果。此端口没有 confirm，图不能创建接受动作。
    """

    async def preview(self, *, document_id: str) -> RevenueReview: ...

    async def calculate(
        self, *, document_id: str, confirmation_id: str
    ) -> ConfirmedRevenueCalculation: ...


@dataclass(frozen=True)
class RevenueCandidateSummary:
    """候选摘要的一期：期间、规范金额和单位，仅供本次读取结果展示。"""

    period: int
    value: Decimal
    unit: FinancialUnit | None


@dataclass(frozen=True)
class RevenueReviewSummary:
    """当前候选/版本摘要；不复制完整业务状态，不承担确认有效性判断。"""

    snapshot_id: str
    revision: RevenueSourceRevision
    candidates: tuple[RevenueCandidateSummary, ...]

    @classmethod
    def from_review(cls, review: RevenueReview) -> "RevenueReviewSummary":
        """输入服务返回的当前 review，输出只包含本图需要的不可变摘要。"""
        return cls(
            snapshot_id=review.snapshot_id,
            revision=review.revision,
            candidates=tuple(
                RevenueCandidateSummary(item.period, item.value, item.unit)
                for item in sorted(review.candidates, key=lambda item: item.period)
            ),
        )


class RevenueGraphInput(TypedDict):
    """调用输入：文档 ID 必填，已有确认 ID 可缺省；不接受裸金额或授权标志。"""

    document_id: str
    confirmation_id: NotRequired[str | None]


class RevenueGraphUpdate(TypedDict, total=False):
    """节点局部更新；未返回的字段保留，因此失败必须显式写 result=None。"""

    review_summary: RevenueReviewSummary | None
    status: GraphStatus
    result: ConfirmedRevenueCalculation | None
    error_code: str | None
    error_kind: Literal["business", "program"] | None


class RevenueGraphState(RevenueGraphInput, RevenueGraphUpdate):
    """单次图执行的数据；服务、仓储和连接由装配函数在 State 外持有。"""


def _business_failure(code: str) -> RevenueGraphUpdate:
    """业务拒绝码转为图出口；缺有效确认与其他拒绝分开，均不保留结果。"""
    return {
        "status": "needs_confirmation" if code == "confirmation_required" else "refused",
        "result": None,
        "error_code": code,
        "error_kind": "business",
    }


def _program_failure() -> RevenueGraphUpdate:
    """意外异常转为失败出口；调用方只收到稳定码，异常细节由日志保留。"""
    logger.exception("Revenue graph node failed")
    return {
        "status": "failed",
        "result": None,
        "error_code": "unexpected_error",
        "error_kind": "program",
    }


def _after_preview(state: RevenueGraphState) -> Literal["check_confirmation", "end"]:
    """只读取节点状态选路；读取失败直接结束，边不再调用服务或检索。"""
    return "check_confirmation" if state["status"] == "previewed" else "end"


def _after_confirmation(state: RevenueGraphState) -> Literal["calculate", "end"]:
    """有确认查询线索才送服务核验；该状态不表示确认已有效。"""
    return "calculate" if state["status"] == "verification_pending" else "end"


def build_revenue_graph(
    *, service: RevenueGraphService
) -> CompiledStateGraph[RevenueGraphState, None, RevenueGraphInput, RevenueGraphState]:
    """注入业务服务，装配并编译三个节点；返回图以 await graph.ainvoke(input) 执行。

    本函数只装配，不查来源/数据库；实际业务拒绝在节点运行时映射为出口。
    """

    async def read_review(state: RevenueGraphState) -> RevenueGraphUpdate:
        """读取文档 ID 调用 preview；写当前摘要，且为新执行清除旧输出。"""
        reset: RevenueGraphUpdate = {
            "review_summary": None,
            "result": None,
            "error_code": None,
            "error_kind": None,
        }
        try:
            review = await service.preview(document_id=state["document_id"])
            return {
                **reset,
                "review_summary": RevenueReviewSummary.from_review(review),
                "status": "previewed",
            }
        except RevenueConfirmationError as exc:
            return {**reset, **_business_failure(exc.code)}
        except (DocumentNotFoundError, DocumentNotReadyError):
            return {**reset, **_business_failure("source_unavailable")}
        except Exception:
            return {**reset, **_program_failure()}

    def check_confirmation(state: RevenueGraphState) -> RevenueGraphUpdate:
        """只检查查询 ID 是否具备；不创建确认，不宣称已有确认当前有效。"""
        confirmation_id = state.get("confirmation_id")
        if confirmation_id is None or confirmation_id == "":
            return _business_failure("confirmation_required")
        if not isinstance(confirmation_id, str):
            return _business_failure("invalid_confirmation_id")
        if not confirmation_id.strip():
            return _business_failure("confirmation_required")
        return {"status": "verification_pending", "result": None}

    async def calculate(state: RevenueGraphState) -> RevenueGraphUpdate:
        """只用两 ID 调用 calculate；金额来自服务核验的 SQLite 事实，不取摘要。"""
        confirmation_id = state.get("confirmation_id")
        if not isinstance(confirmation_id, str) or not confirmation_id.strip():
            return _business_failure("confirmation_required")
        try:
            result = await service.calculate(
                document_id=state["document_id"], confirmation_id=confirmation_id
            )
            if not isinstance(result, ConfirmedRevenueCalculation):
                raise TypeError("计算服务没有返回约定的成功对象")
            return {
                "status": "completed",
                "result": result,
                "error_code": None,
                "error_kind": None,
            }
        except RevenueConfirmationError as exc:
            return _business_failure(exc.code)
        except (DocumentNotFoundError, DocumentNotReadyError):
            return _business_failure("source_unavailable")
        except Exception:
            return _program_failure()

    builder = StateGraph(
        RevenueGraphState, input_schema=RevenueGraphInput, output_schema=RevenueGraphState
    )
    builder.add_node("read_review", read_review)
    builder.add_node("check_confirmation", check_confirmation)
    builder.add_node("calculate", calculate)
    builder.add_edge(START, "read_review")
    builder.add_conditional_edges(
        "read_review", _after_preview, {"check_confirmation": "check_confirmation", "end": END}
    )
    builder.add_conditional_edges(
        "check_confirmation", _after_confirmation, {"calculate": "calculate", "end": END}
    )
    # 所有计算出口均结束本次调用；成功/拒绝/失败由 State 明确表达，不盲重试。
    builder.add_edge("calculate", END)
    return builder.compile(name="confirmed_revenue_research")
