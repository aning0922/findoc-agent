import inspect
from typing import Literal
from fastapi import APIRouter, Request
from fastapi.responses import Response, JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .service import ExportError


class Ref(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    domain: Literal[
        "showcase_report_v2",
        "annual_diff_v1",
        "checkup_v1",
        "peer_comparison_v1",
        "research_answer_v1",
    ]
    id: str = Field(min_length=1, max_length=100)
    revision: int = Field(ge=1)
    payload_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    operation_id: str
    report_ref: Ref
    formats: list[Literal["csv", "xlsx", "pptx"]] = Field(min_length=1, max_length=3)
    export_profile_version: Literal["research-v1"]

    @model_validator(mode="after")
    def unique(self):
        if len(set(self.formats)) != len(self.formats):
            raise ValueError("duplicate_formats")
        return self


class Route(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def checked(request):
            try:
                response = await handler(request)
            except ExportError as exc:
                response = JSONResponse({"detail": {"code": exc.code}}, exc.status)
            response.headers["Cache-Control"] = "no-store"
            return response

        return checked


def create_export_router(service, identity_provider):
    router = APIRouter(prefix="/cplus/exports", route_class=Route)

    async def identity(request):
        value = identity_provider(request)
        return await value if inspect.isawaitable(value) else value

    @router.post("")
    async def create(body: ExportRequest, request: Request):
        return await service.create(body.model_dump(), await identity(request))

    @router.get("/operations/{operation_id}")
    async def operation(operation_id: str, request: Request):
        return service.operation(operation_id, await identity(request))

    @router.get("/{export_id}/files/{format}")
    async def file(export_id: str, format: Literal["csv", "xlsx", "pptx"], request: Request):
        raw, sha = await service.file(export_id, format, await identity(request))
        types = {
            "csv": "text/csv; charset=utf-8",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        }
        return Response(
            raw,
            media_type=types[format],
            headers={
                "Content-Disposition": f'attachment; filename="research.{format}"',
                "ETag": f'"{sha}"',
            },
        )

    return router
