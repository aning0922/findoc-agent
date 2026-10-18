"""D22 explicit drafts and D23 append-only reports; history can mount GET routes alone."""

import sqlite3
from typing import Annotated, Any
from fastapi import APIRouter, Request, Query, Path
from fastapi.responses import JSONResponse
from fastapi.responses import Response
from urllib.parse import quote
from app.reports.export_service import ReportExportService
from app.reports.markdown import RENDERER_VERSION
from app.research.models import sha
from app.reports.contracts import GenerateDraft
from app.reports.persistence_contracts import SaveReport, CreateRevision
from app.reports.persistence_service import ReportPersistenceService
from app.reports.repository import ReportRepository
from app.reports.service import ReportService
from app.research.repository import HistoryError


def create_report_router(
    service: ReportService | None = None, *, repository: ReportRepository | None = None
) -> APIRouter:
    router = APIRouter(prefix="/reports", tags=["reports"])
    persistence = ReportPersistenceService(service) if service else None
    repo = persistence.repository if persistence else repository
    if repo is None:
        raise ValueError("report_repository_required")

    def response(value: dict[str, Any]) -> JSONResponse:
        return JSONResponse(value, headers={"Cache-Control": "no-store"})

    def failure(exc: HistoryError | sqlite3.Error) -> JSONResponse:
        return JSONResponse(
            dict(
                error_code=exc.code
                if isinstance(exc, HistoryError)
                else "report_storage_unavailable"
            ),
            status_code=exc.status if isinstance(exc, HistoryError) else 503,
            headers={"Cache-Control": "no-store"},
        )

    def query(request: Request, allowed: set[str]) -> None:
        if set(request.query_params) - allowed or any(
            len(request.query_params.getlist(k)) != 1 for k in request.query_params
        ):
            raise HistoryError("unknown_query_parameter", 422)

    @router.get("")
    async def page(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=50)] = 20,
        before: Annotated[int | None, Query(ge=1)] = None,
    ) -> JSONResponse:
        try:
            query(request, {"limit", "before"})
            return response(repo.page(limit, before))
        except (HistoryError, sqlite3.Error) as exc:
            return failure(exc)

    @router.get("/by-operation/{operation_id}")
    async def operation(operation_id: str, request: Request) -> JSONResponse:
        try:
            query(request, set())
            return response(repo.by_operation(operation_id))
        except (HistoryError, sqlite3.Error) as exc:
            return failure(exc)

    @router.get("/{report_id}/revisions/{revision}")
    async def detail(
        report_id: str, revision: Annotated[int, Path(ge=1)], request: Request
    ) -> JSONResponse:
        try:
            query(request, set())
            return response(repo.get(report_id, revision))
        except (HistoryError, sqlite3.Error) as exc:
            return failure(exc)

    if service and persistence:
        exporter = ReportExportService(service)

        @router.get("/{report_id}/revisions/{revision}/markdown")
        async def markdown_export(
            report_id: Annotated[
                str, Path(pattern=r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")
            ],
            revision: Annotated[int, Path(ge=1, le=2**63 - 1)],
            request: Request,
        ) -> Response:
            try:
                query(request, set())
                content, name, payload_sha, simulated = await exporter.export(report_id, revision)
                return Response(
                    content,
                    media_type="text/markdown; charset=utf-8",
                    headers={
                        "Content-Disposition": f"attachment; filename=\"FinDoc-{report_id}-v{revision}.md\"; filename*=UTF-8''{quote(name, safe='')}",
                        "Cache-Control": "no-store",
                        "X-Content-Type-Options": "nosniff",
                        "X-Report-Id": report_id,
                        "X-Report-Revision": str(revision),
                        "X-Report-Payload-SHA256": payload_sha,
                        "X-Markdown-SHA256": sha(content.decode("utf-8")),
                        "X-Report-Eligibility": "simulated_test"
                        if simulated
                        else "qualified_at_export",
                        "X-Markdown-Renderer": RENDERER_VERSION,
                    },
                )
            except (HistoryError, sqlite3.Error) as exc:
                return failure(exc)

        @router.post("/drafts")
        async def generate(payload: GenerateDraft, request: Request) -> JSONResponse:
            try:
                query(request, set())
                return response((await service.generate(payload)).model_dump(mode="json"))
            except (HistoryError, sqlite3.Error) as exc:
                return failure(exc)

        @router.post("")
        async def save(payload: SaveReport, request: Request) -> JSONResponse:
            try:
                query(request, set())
                return response(await persistence.save(payload))
            except (HistoryError, sqlite3.Error) as exc:
                return failure(exc)

        @router.post("/{report_id}/revisions")
        async def append(report_id: str, payload: CreateRevision, request: Request) -> JSONResponse:
            try:
                query(request, set())
                return response(await persistence.save(payload, report_id))
            except (HistoryError, sqlite3.Error) as exc:
                return failure(exc)

    return router
