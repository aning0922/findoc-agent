"""D19 explicit writes and DB-only history. Fixed workspace comes from assembly."""

from typing import Annotated, Any
import sqlite3
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from app.agent.operating_research_graph import PersistentTemplateService
from app.research.repository import HistoryError
from app.research.task_contracts import StartTask, StartTaskV2, ResumeTask
from app.research.task_repository import TaskRepository


def create_task_router(
    repository: TaskRepository, service: PersistentTemplateService | None = None
) -> APIRouter:
    router = APIRouter(prefix="/research/tasks", tags=["persistent-research"])

    def response(value: dict[str, Any]) -> JSONResponse:
        code = (
            202
            if value["execution_status"] == "running"
            else 503
            if value["status"] == "failed"
            else 409
            if value["status"] == "refused"
            else 200
        )
        value = repository.public(value)
        return JSONResponse(value, status_code=code, headers={"Cache-Control": "no-store"})

    def failure(exc: Exception) -> JSONResponse:
        return JSONResponse(
            dict(error_code=exc.code if isinstance(exc, HistoryError) else "task_storage_failed"),
            status_code=exc.status if isinstance(exc, HistoryError) else 503,
            headers={"Cache-Control": "no-store"},
        )

    def strict_query(request: Request, allowed: set[str]) -> None:
        if set(request.query_params) - allowed:
            raise HistoryError("unknown_query_parameter", 422)

    @router.get("")
    async def page(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=50)] = 20,
        before: Annotated[int | None, Query(ge=1)] = None,
    ) -> JSONResponse:
        try:
            strict_query(request, {"limit", "before"})
            return JSONResponse(
                repository.page(limit, before), headers={"Cache-Control": "no-store"}
            )
        except (HistoryError, sqlite3.Error) as exc:
            return failure(exc)

    @router.get("/by-operation/{operation_id}")
    async def by_operation(operation_id: str, request: Request) -> JSONResponse:
        try:
            strict_query(request, set())
            return response(repository.by_operation(operation_id))
        except (HistoryError, sqlite3.Error) as exc:
            return failure(exc)

    @router.get("/{task_id}")
    async def get(task_id: str, request: Request) -> JSONResponse:
        try:
            strict_query(request, set())
            return response(repository.get(task_id))
        except (HistoryError, sqlite3.Error) as exc:
            return failure(exc)

    if service is not None:

        @router.post("")
        async def start(payload: StartTaskV2 | StartTask, request: Request) -> JSONResponse:
            try:
                strict_query(request, set())
                return response(await service.start(payload))
            except (HistoryError, sqlite3.Error) as exc:
                return failure(exc)

        @router.post("/{task_id}/resume")
        async def resume(task_id: str, payload: ResumeTask, request: Request) -> JSONResponse:
            try:
                strict_query(request, set())
                return response(await service.resume(task_id, payload))
            except (HistoryError, sqlite3.Error) as exc:
                return failure(exc)

    return router
