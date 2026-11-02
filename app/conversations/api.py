"""Strict conversation HTTP routes; repository-only construction is read-only."""

from collections.abc import Callable
import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.conversations.models import CreateConversationRequest, CreateTurnRequest, DeleteRequest
from app.conversations.repository import ConversationError, ConversationRepository
from app.conversations.service import ConversationService
from app.documents.models import DocumentNotFoundError
from app.documents.preparation import DocumentNotReadyError
from app.documents.source_models import SourceError


def reject_scope(request: Request) -> None:
    if any(key in request.query_params for key in (
            "workspace_id", "owner_id", "principal_id", "source_revision", "selection_id")):
        raise HTTPException(422, "workspace_is_server_owned")


def invoke(call: Callable[[], Any], *, write: bool = False) -> Any:
    try:
        return call()
    except ConversationError as exc:
        raise HTTPException(exc.status, exc.code) from None
    except SourceError as exc:
        raise HTTPException(exc.status, exc.code) from None
    except sqlite3.Error:
        raise HTTPException(503, "conversation_save_failed" if write
                            else "conversation_read_failed") from None
    except Exception:
        raise HTTPException(503, "conversation_save_failed" if write
                            else "conversation_read_failed") from None


def response(value: Any, status: int = 200) -> JSONResponse:
    return JSONResponse(value.model_dump(), status_code=status,
                        headers={"Cache-Control": "no-store"})


def create_conversation_router(repository: ConversationRepository,
                               service: ConversationService | None = None) -> APIRouter:
    router = APIRouter(tags=["conversations"], dependencies=[Depends(reject_scope)])

    @router.get("/conversations")
    def history(limit: Annotated[int, Query(ge=1, le=50)] = 20,
                cursor: Annotated[str | None, Query(max_length=2048)] = None) -> JSONResponse:
        return response(invoke(lambda: repository.page(limit, cursor)))

    @router.get("/conversations/by-operation/{operation_id}")
    def created_by_operation(operation_id: str) -> JSONResponse:
        return response(invoke(lambda: repository.conversation_by_operation(operation_id)))

    @router.get("/conversation-operations/{operation_id}")
    def by_operation(operation_id: str) -> JSONResponse:
        return response(invoke(lambda: repository.operation(operation_id)))

    @router.get("/conversations/{conversation_id}")
    def detail(conversation_id: str,
               limit: Annotated[int, Query(ge=1, le=100)] = 50,
               before_seq: Annotated[int | None, Query(ge=1)] = None) -> JSONResponse:
        return response(invoke(lambda: repository.detail(conversation_id, limit=limit,
                                                         before_seq=before_seq)))

    @router.get("/conversations/{conversation_id}/turns/by-operation/{operation_id}")
    def turn_by_operation(conversation_id: str, operation_id: str) -> JSONResponse:
        return response(invoke(lambda: repository.turn_by_operation(conversation_id, operation_id)))

    @router.get("/conversations/{conversation_id}/turns/{turn_id}")
    def turn(conversation_id: str, turn_id: str) -> JSONResponse:
        return response(invoke(lambda: repository.get_turn(conversation_id, turn_id)))

    if service is None:
        return router

    async def write(call: Callable[[], Any]) -> Any:
        try:
            return await call()
        except ConversationError as exc:
            raise HTTPException(exc.status, exc.code) from None
        except DocumentNotFoundError:
            raise HTTPException(404, "resource_not_found") from None
        except DocumentNotReadyError:
            raise HTTPException(409, "source_not_ready") from None
        except SourceError as exc:
            # The new Conversation contract uses source_changed for a source
            # race before registration; legacy source/research APIs are unchanged.
            raise HTTPException(exc.status, "source_changed" if exc.code == "selection_changed"
                                else exc.code) from None
        except Exception:
            raise HTTPException(503, "conversation_save_failed") from None

    @router.post("/conversations")
    async def create(payload: CreateConversationRequest) -> JSONResponse:
        value, created = await write(lambda: service.create(payload))
        return response(value, 201 if created else 200)

    @router.post("/conversations/{conversation_id}/turns")
    async def send(conversation_id: str, payload: CreateTurnRequest) -> JSONResponse:
        value = await write(lambda: service.send(conversation_id, payload))
        return response(value, 202 if value.status == "running" else 200)

    @router.delete("/conversations/{conversation_id}")
    def delete(conversation_id: str, payload: DeleteRequest) -> JSONResponse:
        return response(invoke(lambda: repository.delete(conversation_id, payload), write=True))

    return router
