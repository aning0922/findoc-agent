"""Synchronous idempotent research creation and database-only history routes."""

import asyncio
from collections.abc import Callable
import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import Field, field_validator

from app.api.research_qa import ResearchQuestion
from app.documents.models import DocumentNotFoundError
from app.documents.preparation import DocumentNotReadyError, DocumentTaskPreparer
from app.documents.source_models import SourceError
from app.rag.selected_scope import SelectedScopeSearch
from app.rag.service import RAGService
from app.research.models import Result, operation, safe_error
from app.research.repository import HistoryError, ResearchRepository


class CreateResearchRun(ResearchQuestion):
    operation_id: Annotated[str, Field(min_length=36, max_length=36)]

    @field_validator("operation_id")
    @classmethod
    def valid_operation(cls, value: str) -> str:
        return operation(value)

    @field_validator("document_ids")
    @classmethod
    def valid_ids(cls, value: list[str]) -> list[str]:
        if not value or len(value) != len(set(value)) or any(not d.strip() for d in value):
            raise ValueError("invalid_selection")
        return value

    @field_validator("query")
    @classmethod
    def valid_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("invalid_question")
        return value


def read(call: Callable[[], Any]) -> Any:
    try:
        return call()
    except HistoryError as exc:
        raise HTTPException(exc.status, exc.code) from None
    except sqlite3.Error:
        raise HTTPException(503, "history_read_failed") from None


def create_research_runs_router(
    repository: ResearchRepository,
    preparer: DocumentTaskPreparer | None = None,
    scope: SelectedScopeSearch | None = None,
    rag: RAGService | None = None,
    *,
    generate_once: Callable[[str], str] | None = None,
    execution_config: dict[str, str | int] | None = None,
    focus_preparer: DocumentTaskPreparer | None = None,
) -> APIRouter:
    router = APIRouter()

    def response(identity: str, by_operation: bool = False) -> JSONResponse:
        value = read(lambda: repository.get(identity, by_operation=by_operation))
        body = read(lambda: repository.public(value))
        return JSONResponse(
            body,
            status_code=202 if value.status == "running" else 200,
            headers={"Cache-Control": "no-store"},
        )

    @router.get("/research/runs")
    def history(
        limit: Annotated[int, Query(ge=1, le=50)] = 20,
        cursor: Annotated[str | None, Query(max_length=2048)] = None,
        company_id: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
        workspace_id: str | None = None,
    ) -> JSONResponse:
        if workspace_id is not None:
            raise HTTPException(422, "workspace_is_server_owned")
        return JSONResponse(
            read(lambda: repository.page(limit, cursor, company_id)),
            headers={"Cache-Control": "no-store"},
        )

    @router.get("/research/runs/by-operation/{operation_id}")
    def by_operation(operation_id: str, workspace_id: str | None = None) -> JSONResponse:
        if workspace_id is not None:
            raise HTTPException(422, "workspace_is_server_owned")
        return response(operation_id, True)

    @router.get("/research/runs/{run_id}")
    def detail(run_id: str, workspace_id: str | None = None) -> JSONResponse:
        if workspace_id is not None:
            raise HTTPException(422, "workspace_is_server_owned")
        return response(run_id)

    @router.get("/research/runs/{run_id}/focus")
    async def focus(run_id: str, workspace_id: str | None = None) -> JSONResponse:
        if workspace_id is not None:
            raise HTTPException(422, "workspace_is_server_owned")
        value = read(lambda: repository.get(run_id))
        verifier = focus_preparer or preparer
        if verifier is None:
            raise HTTPException(503, "focus_verification_unavailable")
        try:
            # D6 rereads the pinned PDF bytes and metadata. This is not retrieval,
            # parsing, model execution, a research continuation or a history write.
            selection = await verifier.prepare_many(document_ids=value.document_ids, query=value.query)
            if selection.selection_id != value.selection_id:
                raise SourceError("selection_changed")
            body = read(lambda: repository.focus(value))
            await verifier.revalidate(selection)
        except SourceError as exc:
            raise HTTPException(exc.status, exc.code) from None
        except (DocumentNotFoundError, DocumentNotReadyError):
            raise HTTPException(409, "source_not_ready") from None
        except (ValueError, TypeError, KeyError, IndexError):
            raise HTTPException(503, "focus_evidence_unavailable") from None
        except Exception:
            raise HTTPException(503, "focus_verification_unavailable") from None
        return JSONResponse(body, headers={"Cache-Control": "no-store"})

    if preparer is None or scope is None or rag is None:
        return router

    @router.post("/research/runs")
    async def create(payload: CreateResearchRun) -> JSONResponse:
        assert preparer is not None and scope is not None and rag is not None
        old = read(
            lambda: repository.existing(payload.operation_id, payload.document_ids, payload.query)
        )
        if old is not None:
            return response(old.run_id)
        try:
            selection = await preparer.prepare_many(
                document_ids=payload.document_ids, query=payload.query
            )
        except ValueError:
            raise HTTPException(422, "invalid_selection_or_question") from None
        except DocumentNotFoundError:
            raise HTTPException(404, "resource_not_found") from None
        except DocumentNotReadyError:
            raise HTTPException(409, "source_not_ready") from None
        except SourceError as exc:
            raise HTTPException(exc.status, exc.code) from None
        except Exception:
            raise HTTPException(503, "source_verification_unavailable") from None
        try:
            value, created = repository.register(
                payload.operation_id,
                selection,
                execution_config or {"mode": "verified_excerpts", "max_retries": 0},
            )
        except HistoryError as exc:
            raise HTTPException(exc.status, exc.code) from None
        except SourceError:
            raise HTTPException(409, "source_changed") from None
        except Exception:
            raise HTTPException(503, "research_save_failed") from None
        if not created:
            return response(value.run_id)
        try:
            raw = await rag.answer_selected(selection, scope, generate_once=generate_once)
            result = Result.model_validate(
                {**raw, "documents": [d.model_dump() for d in value.documents]}
            )
        except asyncio.CancelledError:
            # No retry: a provider thread may finish after cancellation, but cannot publish an answer.
            repository.finish(value.run_id, safe_error(value, "interrupted"))
            raise
        except Exception:
            result = safe_error(value, "execution_error")
        try:
            saved = repository.finish(value.run_id, result)
        except Exception:
            # Do not return a candidate answer or a success run_id after rollback.
            raise HTTPException(503, "research_save_failed") from None
        return response(saved.run_id)

    return router
