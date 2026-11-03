from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from app.parsing.service import ParseError


class ParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    operation_id: str
    expected_source_revision: str = Field(pattern=r"^[a-f0-9]{64}$")


def create_parse_router(service):
    router = APIRouter(prefix="/documents", tags=["parse-v2"])

    def fail(exc):
        return JSONResponse(
            {
                "detail": {
                    "code": exc.code if isinstance(exc, ParseError) else "parse_unavailable",
                    "message": "解析暂不可用，请查看操作状态。",
                }
            },
            exc.status if isinstance(exc, ParseError) else 503,
            headers={"Cache-Control": "no-store"},
        )

    @router.get("/{document_id}/parse-identity")
    async def identity(document_id: str):
        try:
            value, _ = await service.snapshot(document_id)
            return {**value, "legacy_source_verified": False, "identity_assessment": "manual_check"}
        except Exception as exc:
            return fail(exc)

    @router.post("/{document_id}/parse-retry")
    async def retry(document_id: str, payload: ParseRequest):
        try:
            return await service.retry(document_id, **payload.model_dump())
        except Exception as exc:
            return fail(exc)

    @router.get("/{document_id}/parse-operations/{operation_id}")
    async def operation(document_id: str, operation_id: str):
        try:
            return service.operation(document_id, operation_id)
        except Exception as exc:
            return fail(exc)

    @router.get("/{document_id}/parse-quality")
    async def quality(document_id: str, artifact_id: str | None = None):
        try:
            return await service.quality(document_id, artifact_id)
        except Exception as exc:
            return fail(exc)

    @router.get("/{document_id}/parse-artifacts/{artifact_id}/pages/{page}/image")
    async def image(document_id: str, artifact_id: str, page: int):
        try:
            return Response(
                await service.image(document_id, artifact_id, page),
                media_type="image/png",
                headers={"Cache-Control": "no-store"},
            )
        except Exception as exc:
            return fail(exc)

    @router.get("/{document_id}/parse-artifacts/{artifact_id}/file")
    async def file(document_id: str, artifact_id: str):
        try:
            return Response(
                await service.file(document_id, artifact_id),
                media_type="application/pdf",
                headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
            )
        except Exception as exc:
            return fail(exc)

    @router.get("/{document_id}/parse-artifacts/{artifact_id}/search")
    async def search(document_id: str, artifact_id: str, q: str):
        try:
            return await service.search(document_id, artifact_id, q)
        except Exception as exc:
            return fail(exc)

    return router
