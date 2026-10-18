"""Finite D16 QA entrypoint; selected IDs are re-authorized for each request."""

from typing import Annotated, Callable
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import Field
from app.companies.models import StrictInput
from app.documents.models import DocumentNotFoundError
from app.documents.preparation import DocumentNotReadyError, DocumentTaskPreparer
from app.documents.source_models import SourceError
from app.rag.selected_scope import SelectedScopeSearch
from app.rag.service import RAGService


class ResearchQuestion(StrictInput):
    document_ids: list[str]
    query: Annotated[str, Field(min_length=1, max_length=1000)]


def create_research_qa_router(
    preparer: DocumentTaskPreparer,
    scope: SelectedScopeSearch,
    rag: RAGService,
    *,
    generate_once: Callable[[str], str] | None = None,
) -> APIRouter:
    router = APIRouter()

    @router.post("/research/questions")
    async def answer(payload: ResearchQuestion) -> JSONResponse:
        try:
            selected = await preparer.prepare_many(
                document_ids=payload.document_ids, query=payload.query
            )
        except ValueError as exc:
            raise HTTPException(422, "invalid_selection_or_question") from exc
        except DocumentNotFoundError as exc:
            raise HTTPException(404, "resource_not_found") from exc
        except DocumentNotReadyError as exc:
            raise HTTPException(409, "source_not_ready") from exc
        except SourceError as exc:
            raise HTTPException(exc.status, exc.code) from exc
        except Exception as exc:
            raise HTTPException(503, "source_verification_unavailable") from exc
        result = await rag.answer_selected(selected, scope, generate_once=generate_once)
        status = 200
        if result["outcome"] == "system_error":
            status = 409 if result["error_code"] == "source_changed" else 503
        return JSONResponse(result, status_code=status, headers={"Cache-Control": "no-store"})

    return router
