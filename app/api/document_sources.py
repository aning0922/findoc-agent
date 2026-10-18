"""Version-pinned PDF/evidence reads and explicit report binding actions."""

from collections.abc import Awaitable, Callable
from typing import Annotated, TypeVar

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError

from app.companies.models import RegistryConflictError, RegistryNotFoundError
from app.documents.models import DocumentNotFoundError, DocumentTooLargeError, InvalidDocumentError
from app.documents.source_models import (
    BindingCorrectionInput, ReportUploadInput, ReindexInput, SourceError,
)
from app.documents.source_service import DocumentSourceService

T = TypeVar("T")
Revision = Annotated[str, Query(pattern=r"^[0-9a-f]{64}$")]


def create_source_router(service: DocumentSourceService | None, max_upload_bytes: int) -> APIRouter:
    router = APIRouter()

    async def call(action: Callable[[DocumentSourceService], Awaitable[T]]) -> T:
        if service is None:
            raise HTTPException(503, "来源服务未启用")
        try:
            return await action(service)
        except SourceError as exc:
            raise HTTPException(exc.status, exc.code) from exc
        except (DocumentNotFoundError, RegistryNotFoundError) as exc:
            raise HTTPException(404, "resource_not_found") from exc
        except RegistryConflictError as exc:
            raise HTTPException(409, "report_binding_conflict") from exc
        except DocumentTooLargeError as exc:
            raise HTTPException(413, "file_too_large") from exc
        except InvalidDocumentError as exc:
            raise HTTPException(415, "pdf_invalid") from exc
        except Exception as exc:
            raise HTTPException(500, "source_service_unavailable") from exc

    @router.post("/report-documents", status_code=202)
    async def upload(
        file: Annotated[UploadFile, File()], metadata: Annotated[str, Form()]
    ) -> object:
        try:
            content = await file.read(max_upload_bytes + 1)
        finally:
            await file.close()
        try:
            payload = ReportUploadInput.model_validate_json(metadata)
        except ValidationError as exc:
            raise HTTPException(422, "invalid_report_metadata") from exc
        return await call(
            lambda s: s.upload(filename=file.filename or "", content=content, payload=payload)
        )

    @router.post("/documents/{document_id}/reindex", status_code=202)
    async def reindex(document_id: str, payload: ReindexInput) -> object:
        return await call(lambda s: s.reindex(document_id, payload.expected_attempt))

    @router.get("/documents/{document_id}/source")
    async def source(
        document_id: str,
        company_id: str | None = None,
        source_revision: Revision | None = None,
        page: Annotated[int | None, Query(ge=1)] = None,
    ) -> object:
        return await call(
            lambda s: s.source(
                document_id, company_id=company_id, source_revision=source_revision, page=page
            )
        )

    @router.get("/documents/{document_id}/file")
    async def file(
        document_id: str, source_revision: Revision, company_id: str | None = None
    ) -> Response:
        content = await call(
            lambda s: s.file(document_id, source_revision=source_revision, company_id=company_id)
        )
        return Response(
            content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{document_id}.pdf"',
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @router.get("/documents/{document_id}/evidence/{evidence_id}")
    async def evidence(
        document_id: str, evidence_id: str, source_revision: Revision, company_id: str | None = None
    ) -> object:
        return await call(
            lambda s: s.evidence(
                document_id, evidence_id, source_revision=source_revision, company_id=company_id
            )
        )

    @router.post("/documents/{document_id}/binding-corrections")
    async def correct(document_id: str, payload: BindingCorrectionInput) -> object:
        return await call(lambda s: s.correct(document_id, payload))

    @router.get("/documents/{document_id}/binding-corrections")
    async def history(document_id: str) -> object:
        return await call(lambda s: s.history(document_id))

    return router
