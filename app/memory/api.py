"""Dependency-injected memory API, with optional DB-only read surface."""
from collections.abc import Callable
from typing import Annotated, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from app.memory.models import (
    CreateMemoryRequest, DeleteMemoryRequest, MemoryError, MemoryItem, MemoryList,
    MemoryOperation, PatchMemoryRequest,
)
from app.memory.service import MemoryService

T = TypeVar("T")
UUIDPath = Annotated[str, Path(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
                             r"[0-9a-f]{4}-[0-9a-f]{12}$")]


class NoStoreRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def no_store(request: Request) -> Response:
            try:
                response = await handler(request)
            except HTTPException as exc:
                exc.headers = {**(exc.headers or {}), "Cache-Control": "no-store"}
                raise
            except RequestValidationError as exc:
                response = await request_validation_exception_handler(request, exc)
            response.headers["Cache-Control"] = "no-store"
            return response

        return no_store


def reject_scope(request: Request) -> None:
    if {"workspace_id", "owner_id", "principal_id", "source_revision", "selection_id"}.intersection(
        request.query_params
    ):
        raise HTTPException(422, "workspace_is_server_owned")


def create_memory_router(service: MemoryService, *, read_only: bool = False) -> APIRouter:
    router = APIRouter(route_class=NoStoreRoute, dependencies=[Depends(reject_scope)])

    def call(action: Callable[[], T]) -> T:
        try:
            return action()
        except MemoryError as exc:
            raise HTTPException(exc.status_code, exc.detail) from exc
        except Exception as exc:
            raise HTTPException(503, "memory_service_unavailable") from exc

    @router.get("/memories", response_model=MemoryList)
    def list_memories() -> MemoryList:
        return call(service.list)

    @router.get("/memory-operations/{operation_id}", response_model=MemoryOperation)
    def get_operation(operation_id: UUIDPath) -> MemoryOperation:
        return call(lambda: service.get_operation(operation_id))

    @router.get("/memories/{memory_id}", response_model=MemoryItem)
    def get_memory(memory_id: UUIDPath) -> MemoryItem:
        return call(lambda: service.get(memory_id))

    if read_only:
        return router

    @router.post("/memories", response_model=MemoryItem, status_code=201)
    def create_memory(request: CreateMemoryRequest, response: Response) -> MemoryItem:
        item, replayed = call(lambda: service.create(request))
        response.status_code = 200 if replayed else 201
        return item

    @router.patch("/memories/{memory_id}", response_model=MemoryItem)
    def update_memory(memory_id: UUIDPath, request: PatchMemoryRequest) -> MemoryItem:
        return call(lambda: service.update(memory_id, request))

    @router.delete("/memories/{memory_id}", response_model=MemoryOperation)
    def delete_memory(memory_id: UUIDPath, request: DeleteMemoryRequest) -> MemoryOperation:
        return call(lambda: service.delete(memory_id, request))

    return router
