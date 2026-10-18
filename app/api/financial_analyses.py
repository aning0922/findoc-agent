"""Strict IDs-only D11 API. Simulation is unavailable on this router."""

from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent.financial_analysis import FinancialAnalysisService, FinancialFactReference
from app.agent.revenue_confirmation import RevenueConfirmationError, RevenueConfirmationService
from app.api.financial_reviews import FinancialRoute, Hash, Id, Year


class AnalysisFactSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    fact_set_id: Id
    fact_id: Id
    period: Year
    source_revision: Hash
    disclosure_version: Id | None = None


class FinancialAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["financial-analysis-v1"]
    company_id: Id
    metric_key: Literal["revenue", "net_profit_parent", "operating_cash_flow"]
    current: AnalysisFactSelection | None
    previous: AnalysisFactSelection | None


class CompanyComparisonSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    metric_key: Literal["revenue", "net_profit_parent", "operating_cash_flow"]
    a: AnalysisFactSelection | None
    b: AnalysisFactSelection | None


class CompanyComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["financial-company-comparison-v1"]
    company_a_id: Id
    company_b_id: Id
    period: Year
    selections: list[CompanyComparisonSelection] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def unique_metrics(self) -> "CompanyComparisonRequest":
        if len({s.metric_key for s in self.selections}) != len(self.selections):
            raise ValueError("Duplicate metrics are not allowed")
        return self


class AnalysisRoute(FinancialRoute):
    failure_message = "本次财务分析被阻断，未发布计算结果，请核对事实与来源状态。"
    failure_code = "financial_analysis_failed"
    failure_payload = {"schema": "financial-analysis-v1", "status": "blocked"}


class ComparisonRoute(AnalysisRoute):
    failure_message = "本次双企业比较被阻断，未发布计算结果，请核对双方事实与来源。"
    failure_code = "financial_company_comparison_failed"
    failure_payload = {"schema": "financial-company-comparison-v1", "status": "blocked"}


def create_financial_analysis_router(
    *,
    service: RevenueConfirmationService | None,
    workspace_id: str | None,
) -> APIRouter:
    router = APIRouter(prefix="/analyses", tags=["financial-analysis"], route_class=AnalysisRoute)
    analysis = (
        FinancialAnalysisService(facts=service, workspace_id=workspace_id)
        if service is not None and workspace_id
        else None
    )

    @router.post("")
    async def analyze(payload: FinancialAnalysisRequest) -> object:
        if analysis is None:
            raise RevenueConfirmationError("financial_service_unavailable")
        result = await analysis.analyze(
            company_id=payload.company_id,
            metric_key=payload.metric_key,
            current=FinancialFactReference(**payload.current.model_dump())
            if payload.current
            else None,
            previous=FinancialFactReference(**payload.previous.model_dump())
            if payload.previous
            else None,
        )
        return JSONResponse(
            status_code=409 if result["status"] == "blocked" else 200, content=result
        )

    comparison_router = APIRouter(prefix="/company-comparison", route_class=ComparisonRoute)

    @comparison_router.post("")
    async def compare(payload: CompanyComparisonRequest) -> object:
        if analysis is None:
            raise RevenueConfirmationError("financial_service_unavailable")
        result = await analysis.compare(
            company_a_id=payload.company_a_id,
            company_b_id=payload.company_b_id,
            period=payload.period,
            selections={
                s.metric_key: (
                    FinancialFactReference(**s.a.model_dump()) if s.a else None,
                    FinancialFactReference(**s.b.model_dump()) if s.b else None,
                )
                for s in payload.selections
            },
        )
        return JSONResponse(
            status_code=409 if result["status"] == "blocked" else 200, content=result
        )

    router.include_router(comparison_router)
    return router
