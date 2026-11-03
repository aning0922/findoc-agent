from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from app.retrieval_v2.service import resolve
from .models import TemplateRunRequest


def create_template_run_router(service, identity_provider):
    router = APIRouter(prefix="/cplus/template-runs")

    def fail(exc):
        return JSONResponse(
            {"detail": {"code": getattr(exc, "code", "template_run_unavailable")}},
            status_code=getattr(exc, "status", 503),
        )

    @router.post("")
    async def create(payload: TemplateRunRequest, request: Request):
        try:
            return await service.create(payload, await resolve(identity_provider(request)))
        except Exception as exc:
            return fail(exc)

    @router.get("/operations/{operation_id}")
    async def operation(operation_id: str, request: Request):
        try:
            return service.operation(
                operation_id, await service.owner(await resolve(identity_provider(request)))
            )
        except Exception as exc:
            return fail(exc)

    @router.get("/{identifier}")
    async def read(identifier: str, request: Request):
        try:
            return await service.read(identifier, await resolve(identity_provider(request)))
        except Exception as exc:
            return fail(exc)

    return router
