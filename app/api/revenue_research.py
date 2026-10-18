"""独立收入 HTTP 薄适配：审阅与明确确认，错误外壳只影响本路由组。"""

from collections.abc import Callable, Coroutine
import sqlite3
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.agent.revenue_confirmation import RevenueConfirmationError, RevenueConfirmationService
from app.api.revenue_research_schemas import (
    RevenueConfirmationRequest,
    RevenueConfirmationResponse,
    RevenueReviewRequest,
    RevenueReviewResponse,
    to_confirmation_response,
    to_review_response,
)
from app.documents.models import DocumentNotFoundError, DocumentRecord, DocumentStatus
from app.documents.preparation import DocumentNotReadyError, DocumentReader


class _RevenueUnavailableError(RuntimeError):
    """收入服务未注入；请求不触发任何依赖初始化。"""


_ERRORS: tuple[tuple[type[Exception], int, str, str], ...] = (
    (_RevenueUnavailableError, 503, "revenue_service_unavailable", "收入研究服务未启用"),
    (RequestValidationError, 422, "invalid_revenue_request", "请求字段或类型不符合接口要求"),
    (DocumentNotFoundError, 404, "document_not_found", "文档不存在"),
    (DocumentNotReadyError, 409, "document_not_ready", "只有处理成功的文档可以审阅或确认"),
    (sqlite3.Error, 500, "revenue_storage_error", "收入数据读写失败，无法确认本次操作完成"),
)
_BUSINESS_ERRORS: dict[str, tuple[int, str]] = {
    "confirmation_required": (409, "尚未明确接受审阅内容，无法保存确认"),
    "review_changed": (409, "审阅内容已变化，请重新审阅后明确接受"),
    "source_changed": (409, "来源已变化，请重新审阅"),
    "source_unavailable": (409, "当前来源不可用，无法完成本次操作"),
    "missing_candidate": (409, "未找到完整的两期收入候选"),
    "candidate_conflict": (409, "收入候选存在冲突，无法确认"),
    "scope_mismatch": (409, "候选来源与所选文档范围不一致"),
    "unit_unknown": (409, "收入候选包含无法识别的单位"),
    "unit_conflict": (409, "收入候选单位不符合要求"),
    "source_invalid": (409, "收入候选的来源证据不符合要求"),
    "period_mismatch": (409, "收入候选期间不符合要求"),
    "step_limit": (409, "候选处理未能在限定步骤内完成"),
    "confirmation_kind_mismatch": (409, "已有确认的操作者类型不匹配，无法复用"),
    "confirmation_integrity_error": (500, "确认记录暂时无法安全读取"),
}


class _RevenueRoute(APIRoute):
    """包住本组请求校验/执行/响应；固定安全说明，不回显输入或原异常。"""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                return await original(request)
            except Exception as exc:
                for error_type, status, code, message in _ERRORS:
                    if isinstance(exc, error_type):
                        return JSONResponse(
                            status_code=status,
                            content={"detail": {"code": code, "message": message}},
                        )
                if isinstance(exc, RevenueConfirmationError) and exc.code in _BUSINESS_ERRORS:
                    status, message = _BUSINESS_ERRORS[exc.code]
                    return JSONResponse(
                        status_code=status,
                        content={"detail": {"code": exc.code, "message": message}},
                    )
                return JSONResponse(
                    status_code=500,
                    content={
                        "detail": {
                            "code": "revenue_internal_error",
                            "message": "收入研究服务暂时无法完成本次请求",
                        }
                    },
                )

        return handle


def create_revenue_research_router(
    *,
    service: RevenueConfirmationService | None,
    documents: DocumentReader,
    workspace_id: str | None,
) -> APIRouter:
    """注入已有业务服务与服务端范围；只提供两个 POST，不初始化或执行收入图。"""
    if service is not None and (not isinstance(workspace_id, str) or not workspace_id.strip()):
        raise ValueError("启用收入 HTTP 必须注入服务端 workspace")
    router = APIRouter(
        prefix="/revenue-research", tags=["revenue-research"], route_class=_RevenueRoute
    )

    def enabled_service() -> RevenueConfirmationService:
        """取已注入服务；缺依赖时安全 503，不懒初始化检索或模型。"""
        if service is None:
            raise _RevenueUnavailableError
        return service

    async def ready_document(document_id: str) -> DocumentRecord:
        """核准范围和 ready；业务服务之后仍独立查证实际来源与候选。"""
        document = await documents.get_document(document_id)
        if document.workspace_id != workspace_id:
            raise DocumentNotFoundError(document_id)
        if document.status is not DocumentStatus.READY:
            raise DocumentNotReadyError
        return document

    @router.post("/reviews", response_model=RevenueReviewResponse)
    async def review(payload: RevenueReviewRequest) -> RevenueReviewResponse:
        """审阅只查证与展示；显式取服务端 snapshot 并保留全部证据。"""
        active = enabled_service()
        document = await ready_document(payload.document_id)
        reviewed = await active.preview(document_id=document.document_id)
        return to_review_response(reviewed, document=document)

    @router.post("/confirmations", response_model=RevenueConfirmationResponse)
    async def confirm(payload: RevenueConfirmationRequest) -> RevenueConfirmationResponse:
        """未接受立即拒绝；true 才调用原 confirm，返回已保存或复用的回执。"""
        active = enabled_service()
        if payload.accepted is not True:
            raise RevenueConfirmationError("confirmation_required")
        document = await ready_document(payload.document_id)
        confirmed = await active.confirm(
            document_id=document.document_id,
            reviewed_snapshot_id=payload.snapshot_id,
            accepted=payload.accepted,
            confirmation_kind="local_operator",
        )
        return to_confirmation_response(
            confirmed, document=document, reviewed_snapshot_id=payload.snapshot_id
        )

    return router
