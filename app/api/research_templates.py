"""D18 read-only preflight/execution. No model dispatch, confirmation or persistence."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.research.template_contracts import TemplateRequest
from app.research.templates import TemplateService


def create_template_router(service: TemplateService) -> APIRouter:
    router = APIRouter(prefix="/research/templates", tags=["limited-research"])

    async def response(payload: TemplateRequest, execute: bool) -> JSONResponse:
        session = await service.prepare(payload)
        result = await session.execute_readonly() if execute else session.payload()
        status = (503 if result["status"] == "failed" else
                  404 if result["error_code"] == "resource_not_found" else
                  409 if result["status"] == "refused" else 200)
        return JSONResponse(result, status_code=status, headers={"Cache-Control": "no-store"})

    @router.post("/prepare")
    async def prepare(payload: TemplateRequest) -> JSONResponse:
        return await response(payload, False)

    @router.post("/execute-readonly")
    async def execute(payload: TemplateRequest) -> JSONResponse:
        return await response(payload, True)

    return router
