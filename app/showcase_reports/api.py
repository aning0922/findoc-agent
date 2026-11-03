import inspect

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from .service import ReportError
from .printing import render_print


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Draft(Strict):
    operation_id: str
    job_id: str


class Create(Strict):
    operation_id: str
    draft_id: str
    title: str = Field(min_length=1, max_length=200)
    notes: str = Field(default="", max_length=8000)


class Revision(Strict):
    operation_id: str
    expected_revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    notes: str = Field(default="", max_length=8000)


def create_showcase_report_router(service, *, reader_for_request=None):
    router = APIRouter(prefix="/showcase-reports", tags=["showcase-reports"])

    async def reader(request):
        value = reader_for_request(request) if reader_for_request else None
        return await value if inspect.isawaitable(value) else value

    def error(exc):
        return JSONResponse(
            {
                "detail": {
                    "code": exc.code if isinstance(exc, ReportError) else "report_unavailable"
                }
            },
            status_code=exc.status if isinstance(exc, ReportError) else 503,
            headers={"Cache-Control": "no-store"},
        )

    @router.post("/drafts")
    async def draft(payload: Draft, request: Request):
        try:
            return await service.draft(**payload.model_dump(), reader=await reader(request))
        except Exception as exc:
            return error(exc)

    @router.get("/operations/{operation_id}")
    async def operation(operation_id: str):
        try:
            return service.read_operation(operation_id)
        except Exception as exc:
            return error(exc)

    @router.post("")
    async def create(payload: Create):
        try:
            return service.save(**payload.model_dump())
        except Exception as exc:
            return error(exc)

    @router.get("")
    async def listing():
        return service.list()

    @router.post("/{report_id}/revisions")
    async def revise(report_id: str, payload: Revision):
        try:
            return service.save(report_id=report_id, **payload.model_dump())
        except Exception as exc:
            return error(exc)

    @router.get("/{report_id}/revisions/{revision}")
    async def read(report_id: str, revision: int, request: Request):
        try:
            return await service.revision(report_id, revision, reader=await reader(request))
        except Exception as exc:
            return error(exc)

    @router.get("/{report_id}/revisions/{revision}/print")
    async def printing(report_id: str, revision: int, request: Request):
        try:
            return HTMLResponse(
                render_print(await service.revision(report_id, revision, reader=await reader(request))),
                headers={
                    "Cache-Control": "no-store",
                    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'self'",
                },
            )
        except Exception as exc:
            return error(exc)

    return router
