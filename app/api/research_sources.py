"""Selection-only endpoints. Browser cannot submit workspace, revisions, expressions or query."""

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from app.agent.sqlite_financial_facts import disclosure_version_for_source
from pydantic import Field, StrictStr

from app.companies.models import RegistryNotFoundError, StrictInput
from app.documents.models import DocumentNotFoundError
from app.documents.preparation import DocumentNotReadyError, DocumentTaskPreparer
from app.documents.service import DocumentService
from app.documents.source_models import SourceError
from app.documents.source_service import DocumentSourceService


class SelectionRequest(StrictInput):
    document_ids: Annotated[list[StrictStr], Field(min_length=1)]


def create_research_source_router(
    documents: DocumentService, sources: DocumentSourceService | None,
    *, max_selected_documents: int = 4,
) -> APIRouter:
    router = APIRouter()
    preparer = DocumentTaskPreparer(
        document_service=documents, sources=sources,
        workspace_id=documents.workspace_id if sources is not None else None,
        max_selected_documents=max_selected_documents,
    )

    def enabled() -> DocumentSourceService:
        if sources is None:
            raise HTTPException(503, "selection_verification_unavailable")
        return sources

    @router.get("/research/sources")
    async def candidates() -> dict[str, Any]:
        active = enabled()
        rows = []
        for document in await documents.list_documents():
            try:
                meta = active.companies.metadata(document.document_id)
            except RegistryNotFoundError:
                continue  # Unbound legacy documents are never offered as verified reports.
            reason = None
            identity = None
            try:
                selected = await preparer.prepare_many(
                    document_ids=[document.document_id], query="范围核验"
                )
                identity = selected.documents[0]
            except DocumentNotReadyError:
                reason = "source_not_ready"
            except SourceError as exc:
                reason = exc.code
            except (DocumentNotFoundError, RegistryNotFoundError):
                reason = "resource_not_found"
            except Exception:
                raise HTTPException(503, "selection_verification_unavailable") from None
            rows.append(dict(document_id=document.document_id,
                             company_id=identity.company_id if identity else meta.company_id,
                             report_year=identity.report_year if identity else meta.report_year,
                             report_type=identity.report_type if identity else meta.report_type,
                             source_file=document.source_file,
                             status="ready" if identity else document.status.value,
                             selectable=reason is None, reason=reason))
        return dict(schema_version="research-source-options-v1",
                    max_selected_documents=preparer.max_selected_documents, documents=rows)

    @router.get("/research/disclosures/{document_id}")
    async def disclosure(
        document_id: str, request: Request, response: Response, company_id: str,
        source_revision: Annotated[str, Query(pattern=r"^[a-f0-9]{64}$")],
    ) -> dict[str, Any]:
        response.headers["Cache-Control"] = "no-store"
        if set(request.query_params) != {"company_id", "source_revision"}:
            raise HTTPException(422, "invalid_disclosure_query")
        try:
            source = await enabled().source(
                document_id, company_id=company_id, source_revision=source_revision
            )
        except SourceError as exc:
            raise HTTPException(exc.status, exc.code) from exc
        except (DocumentNotFoundError, RegistryNotFoundError):
            raise HTTPException(404, "resource_not_found") from None
        return dict(schema_version="research-disclosure-options-v1", source=source,
                    disclosure_versions=[disclosure_version_for_source(source)],
                    automatic_selection=False, confirmed=False)

    @router.post("/research/selections/prepare")
    async def prepare(payload: SelectionRequest) -> dict[str, Any]:
        enabled()
        try:
            selection = await preparer.prepare_many(document_ids=payload.document_ids, query="范围核验")
            await preparer.revalidate(selection)
        except ValueError:
            raise HTTPException(422, "invalid_document_selection") from None
        except DocumentNotReadyError:
            raise HTTPException(409, "source_not_ready") from None
        except (DocumentNotFoundError, RegistryNotFoundError):
            raise HTTPException(404, "resource_not_found") from None
        except SourceError as exc:
            raise HTTPException(exc.status, exc.code) from exc
        except Exception:
            raise HTTPException(503, "selection_verification_unavailable") from None
        return dict(schema_version="research-selection-v1", selection_id=selection.selection_id,
                    documents=[asdict(d) for d in selection.documents],
                    retrieval_ready=False, blocker="index_source_revision_unverified",
                    research_started=False)

    return router
