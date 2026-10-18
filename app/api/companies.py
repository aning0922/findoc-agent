"""Thin company/metadata adapter; synchronous service calls run in FastAPI's threadpool."""

from collections.abc import Callable
from datetime import date, datetime
from typing import TypeVar

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from app.companies.models import (
    CompanyCreate,
    CompanyPatch,
    RegistryConflictError,
    RegistryNotFoundError,
    ReportMetadataInput,
    ReportType,
    Basis,
)
from app.companies.service import CompanyService

T = TypeVar("T")


class CompanyResponse(CompanyCreate):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    company_id: str
    created_at: datetime
    updated_at: datetime


class ReportMetadataResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    document_id: str
    company_id: str
    report_year: int
    report_type: ReportType
    basis: Basis
    period_start: date
    period_end: date
    status: str
    created_at: datetime


def create_company_router(service: CompanyService | None) -> APIRouter:
    router = APIRouter()

    def call(action: Callable[[CompanyService], T]) -> T:
        if service is None:
            raise HTTPException(503, "企业服务未启用")
        try:
            return action(service)
        except RegistryNotFoundError as exc:
            raise HTTPException(404, "资源不存在") from exc
        except RegistryConflictError as exc:
            raise HTTPException(409, "业务身份或财报归属冲突") from exc
        except Exception as exc:
            raise HTTPException(500, "企业服务暂时不可用") from exc

    @router.post("/companies", response_model=CompanyResponse, status_code=201)
    def create(payload: CompanyCreate) -> object:
        return call(lambda s: s.create(payload))

    @router.get("/companies", response_model=list[CompanyResponse])
    def list_companies() -> object:
        return call(lambda s: s.list())

    @router.get("/companies/{company_id}", response_model=CompanyResponse)
    def get(company_id: str) -> object:
        return call(lambda s: s.get(company_id))

    @router.patch("/companies/{company_id}", response_model=CompanyResponse)
    def update(company_id: str, payload: CompanyPatch) -> object:
        return call(lambda s: s.update(company_id, payload))

    @router.put("/documents/{document_id}/metadata", response_model=ReportMetadataResponse)
    def bind(document_id: str, payload: ReportMetadataInput) -> object:
        return call(lambda s: s.bind(document_id, payload))

    @router.get("/documents/{document_id}/metadata", response_model=ReportMetadataResponse)
    def metadata(document_id: str) -> object:
        return call(lambda s: s.metadata(document_id))

    return router
