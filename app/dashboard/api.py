"""Private runtime router; the demo gateway owns authentication and generation admission."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.dashboard.service import DashboardError, DashboardService


def create_dashboard_router(service: DashboardService) -> APIRouter:
    router = APIRouter(prefix="/dashboard", tags=["dashboard"])

    def response(value, status=200):
        return JSONResponse(value, status_code=status, headers={"Cache-Control": "no-store"})

    def failure(exc):
        code = exc.code if isinstance(exc, DashboardError) else "dashboard_read_failed"
        status = exc.status if isinstance(exc, DashboardError) else 503
        return response(
            dict(detail=dict(code=code, message="概览暂不可用，请重试或核查资料状态。")), status
        )

    @router.get("/overview")
    async def overview(request: Request):
        if request.query_params:
            return failure(DashboardError("unknown_query_parameter", 422))
        try:
            return response(await service.overview_enriched())
        except Exception as exc:
            return failure(exc)

    @router.get("/charts")
    async def charts(
        request: Request,
        company_id: str = "",
        metric_key: str = "revenue",
        sample_mode: str = "false",
    ):
        if set(request.query_params) - {"company_id", "metric_key", "sample_mode"} or any(
            len(request.query_params.getlist(k)) != 1 for k in request.query_params
        ):
            return failure(DashboardError("unknown_or_duplicate_query_parameter", 422))
        if sample_mode not in {"true", "false"}:
            return failure(DashboardError("invalid_sample_mode", 422))
        try:
            return response(
                await service.charts(
                    company_id=company_id, metric_key=metric_key, sample_mode=sample_mode == "true"
                )
            )
        except Exception as exc:
            return failure(exc)

    return router
