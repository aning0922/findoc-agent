from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from app.retrieval_v2.service import resolve
from .models import AnnualDiffError, AnnualDiffRequest


def create_annual_diff_router(service, identity_provider):
    router = APIRouter(prefix="/cplus/annual-diffs", tags=["annual-diff"])

    def fail(exc):
        from app.cplus.diagnostics import safe_failure
        safe_failure('annual',exc)
        return JSONResponse(
            {
                "detail": {
                    "code": exc.code
                    if isinstance(exc, AnnualDiffError)
                    else "annual_diff_unavailable"
                }
            },
            status_code=exc.status if isinstance(exc, AnnualDiffError) else 503,
            headers={"Cache-Control": "no-store"},
        )

    @router.post("")
    async def create(payload: AnnualDiffRequest, request: Request):
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

    @router.get("/{result_id}")
    async def read(result_id: str, request: Request):
        try:
            return await service.read(result_id, await resolve(identity_provider(request)))
        except Exception as exc:
            return fail(exc)

    return router
