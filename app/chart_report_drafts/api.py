from typing import Literal
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import Field
from app.retrieval_v2.models import Strict
from app.retrieval_v2.service import resolve


class ChartReportRequest(Strict):
    operation_id: str
    trend_id: str
    chart_kind: Literal["line", "bar"]
    metric_keys: list[
        Literal[
            "revenue",
            "net_profit_parent",
            "operating_cash_flow",
            "total_assets",
            "total_liabilities",
        ]
    ] = Field(min_length=1, max_length=5)


def create_chart_report_draft_router(service, identity_provider):
    router = APIRouter(prefix="/cplus/report-drafts")

    def fail(exc):
        return JSONResponse(
            {"detail": {"code": getattr(exc, "code", "chart_report_unavailable")}},
            status_code=getattr(exc, "status", 503),
        )

    @router.post("")
    async def create(payload: ChartReportRequest, request: Request):
        try:
            return await service.create(payload, await resolve(identity_provider(request)))
        except Exception as exc:
            return fail(exc)

    @router.get("/operations/{operation_id}")
    async def operation(operation_id: str, request: Request):
        try:
            return await service.operation(operation_id, await resolve(identity_provider(request)))
        except Exception as exc:
            return fail(exc)

    @router.get("/{identifier}")
    async def read(identifier: str, request: Request):
        try:
            return await service.read(identifier, await resolve(identity_provider(request)))
        except Exception as exc:
            return fail(exc)

    return router
