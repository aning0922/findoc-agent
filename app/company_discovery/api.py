"""Inject authenticated controller identity; strict browser DTOs never accept URL/path/identity."""

from typing import Literal
import inspect
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator
from .contracts import DiscoveryError


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SearchRequest(Strict):
    operation_id: str
    mode: Literal["companies", "announcements"]
    query: str | None = Field(default=None, min_length=1, max_length=80)
    security_id: str | None = Field(default=None, max_length=100)
    report_year: int | None = Field(default=None, ge=1990, le=2100)
    kind: Literal["annual_fulltext", "summary"] | None = None

    @model_validator(mode="after")
    def combination(self):
        if self.mode == "companies":
            if (
                not self.query
                or not self.query.strip()
                or any(x is not None for x in (self.security_id, self.report_year, self.kind))
            ):
                raise ValueError("Company search requires query only")
            if any(ord(c) < 32 for c in self.query):
                raise ValueError("Invalid query")
        elif self.query is not None or not self.security_id or self.report_year is None:
            raise ValueError("Announcement search requires selected security and year")
        return self


class ImportRequest(Strict):
    operation_id: str
    candidate_id: str
    candidate_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    company_id: str | None = Field(default=None, min_length=1, max_length=100)
    create_company: bool = False
    confirmed: Literal[True]

    @field_validator("confirmed", mode="before")
    @classmethod
    def exact_confirmation(cls, value):
        if value is not True:
            raise ValueError("Explicit true required")
        return value

    @model_validator(mode="after")
    def consent(self):
        if (
            self.confirmed is not True
            or (self.company_id is None and not self.create_company)
            or (self.company_id and self.create_company)
        ):
            raise ValueError("Choose existing company or explicitly create company")
        return self


class ErrorRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def checked(request):
            try:
                response = await handler(request)
            except DiscoveryError as exc:
                response = JSONResponse({"detail": {"code": exc.code}}, exc.status)
            response.headers["Cache-Control"] = "no-store"
            return response

        return checked


def create_discovery_router(service, identity_provider):
    router = APIRouter(prefix="/cplus/discovery", route_class=ErrorRoute)

    async def identity(request):
        value = identity_provider(request)
        return await value if inspect.isawaitable(value) else value

    @router.post("/searches")
    async def search(body: SearchRequest, request: Request):
        return await service.post_search(body.model_dump(mode="json"), await identity(request))

    @router.get("/searches/{operation_id}")
    async def read_search(operation_id: str, request: Request):
        return service.operation(operation_id, await identity(request), "search")

    @router.post("/imports")
    async def import_pdf(body: ImportRequest, request: Request):
        return await service.post_import(body.model_dump(mode="json"), await identity(request))

    @router.get("/imports/{operation_id}")
    async def read_import(operation_id: str, request: Request):
        return service.operation(operation_id, await identity(request), "import")

    return router
