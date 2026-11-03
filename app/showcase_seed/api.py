"""GET-only preset archive; root gateway retains current lease checks for all reads."""

from uuid import UUID
from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.showcase_seed.archive import ArchiveError


class ArchiveRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def checked(request):
            try:
                response = await handler(request)
            except ArchiveError as exc:
                response = JSONResponse(
                    {"detail": {"code": exc.code, "message": exc.code.replace("_", " ")}},
                    exc.status,
                )
            response.headers["Cache-Control"] = "no-store"
            return response

        return checked


def create_showcase_archive_router(service):
    router = APIRouter(
        prefix="/showcase-archive", route_class=ArchiveRoute, tags=["preset-archive"]
    )

    @router.get("/items")
    async def items(
        kind: Literal["job", "report"] | None = None, limit: int = Query(default=20, ge=1, le=20)
    ):
        return await service.list(kind=kind, limit=limit)

    @router.get("/jobs/{archive_id}")
    async def job(archive_id: UUID):
        return await service.job(str(archive_id))

    @router.get("/reports/{archive_id}/revisions/{revision}")
    async def report(archive_id: UUID, revision: int):
        if revision < 1:
            raise ArchiveError("invalid_revision", 422)
        return await service.report(str(archive_id), revision)

    return router
