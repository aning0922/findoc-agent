"""Reuse DocumentService/ObjectStore; only server-created parsed evidence can be read."""

import asyncio
import hashlib
from importlib.metadata import version
import re
from typing import Any

import pymupdf

from app.companies.models import ReportMetadataInput
from app.companies.service import CompanyService
from app.documents.models import DocumentRecord, DocumentStatus
from app.documents.ports import ObjectStore
from app.documents.service import DocumentService
from app.documents.source_models import BindingCorrectionInput, ReportUploadInput, SourceError
from app.documents.source_repository import SQLiteSourceRepository, revision_id
from app.rag.parse.models import DocChunk

PARSER_VERSION = f"fast-pdf-v4;table-geometry-v2;pymupdf={version('pymupdf')};pdfplumber={version('pdfplumber')}"


def inspect_pdf(content: bytes) -> tuple[int, str]:
    try:
        with pymupdf.open(stream=content, filetype="pdf") as pdf:
            if pdf.needs_pass or pdf.page_count < 1 or pdf.is_repaired:
                raise ValueError("unsupported PDF")
            # Touch every page to reject broken page trees; no OCR or fabricated page count.
            for page in pdf:
                _ = page.rect
            cover = pdf[0].get_text()
            return int(pdf.page_count), cover
    except Exception as exc:
        raise SourceError("pdf_invalid", 415) from exc


def assess(cover: str, company_name: str, payload: ReportMetadataInput) -> dict[str, Any]:
    normalized = re.sub(r"\s+", "", cover)
    # Only title/cover information; comparative columns and filenames are not report identity.
    names = sorted(
        {
            name
            for line in cover.splitlines()
            for name in re.findall(
                r"[\u4e00-\u9fff]{2,40}(?:股份有限公司|有限责任公司)",
                re.sub(r"\s+", "", line),
            )
        }
    )
    years = sorted(set(int(y) for y in re.findall(r"(\d{4})年(?:年度|度)报告", normalized)))
    company_match = re.sub(r"\s+", "", company_name) in names
    company_state = (
        ("matches_cover" if company_match else "conflict") if len(names) == 1 else "manual_check"
    )
    year_state = (
        "matches_cover"
        if years == [payload.report_year]
        else ("conflict" if len(years) == 1 else "manual_check")
    )
    type_state = (
        "matches_cover"
        if len(years) == 1 and payload.report_type == "annual"
        else ("conflict" if len(years) == 1 else "manual_check")
    )
    return dict(
        status="pending_verification",
        company=company_state,
        report_year=year_state,
        report_type=type_state,
        detected_companies=names,
        detected_report_years=years,
        basis="manual_check",
        period="manual_check",
        financial_facts="not_verified",
    )


class DocumentSourceService:
    def __init__(
        self,
        *,
        documents: DocumentService,
        objects: ObjectStore,
        companies: CompanyService,
        repository: SQLiteSourceRepository,
        parser_version: str = PARSER_VERSION,
    ) -> None:
        if not parser_version.strip():
            raise ValueError("parser version is required")
        self.documents = documents
        self.objects = objects
        self.companies = companies
        self.repository = repository
        self.parser_version = parser_version

    def capture(self, document: DocumentRecord, content: bytes, blocks: list[DocChunk]) -> None:
        if hashlib.sha256(content).hexdigest() != document.content_sha256:
            raise SourceError("source_changed")
        pages, _ = inspect_pdf(content)
        self.repository.capture(document, pages, self.parser_version, blocks)

    async def upload(
        self, *, filename: str, content: bytes, payload: ReportUploadInput
    ) -> dict[str, Any]:
        # Validate bounded bytes and enterprise before persisting/dispatching anything.
        self.documents._validate_upload(source_file=filename, content=content)
        pages, cover = await asyncio.to_thread(inspect_pdf, content)
        company = await asyncio.to_thread(self.companies.get, payload.company_id)
        metadata = ReportMetadataInput.model_validate(payload.model_dump(exclude={"source_url"}))
        assessment = assess(cover, company.name, metadata)
        if "conflict" in assessment.values():
            raise SourceError("report_identity_conflict")
        result = await self.documents.upload_document(source_file=filename, content=content)
        bound = await asyncio.to_thread(
            self.repository.bind_report,
            result.record.workspace_id,
            result.record.document_id,
            metadata,
            payload.source_url,
            assessment,
        )
        return dict(
            document_id=result.record.document_id,
            duplicate=result.duplicate,
            document_status=result.record.status.value,
            metadata=bound.model_dump(mode="json", exclude={"workspace_id"}),
            assessment=assessment,
            physical_pages=pages,
            source_url=payload.source_url,
            source_url_status="user_declared",
        )

    async def _checked(
        self, document_id: str, company_id: str | None, expected_revision: str | None
    ) -> tuple[dict[str, Any], bytes]:
        document = await self.documents.get_document(document_id)
        metadata = await asyncio.to_thread(self.companies.metadata, document_id)
        if company_id is not None and metadata.company_id != company_id:
            raise SourceError("resource_not_found", 404)
        if document.status != DocumentStatus.READY:
            raise SourceError("source_not_ready")
        revision = revision_id(document, self.parser_version)
        if expected_revision is not None and revision != expected_revision:
            raise SourceError("source_changed")
        source = await asyncio.to_thread(self.repository.source, document.workspace_id, revision)
        if any(
            source[key] != value
            for key, value in {
                "document_id": document_id,
                "content_sha256": document.content_sha256,
                "attempt": document.attempt,
                "parser_version": self.parser_version,
            }.items()
        ):
            raise SourceError("source_changed")
        try:
            content = await asyncio.to_thread(self.objects.read_bytes, document.object_key)
        except FileNotFoundError as exc:
            raise SourceError("source_file_missing", 404) from exc
        except Exception as exc:
            raise SourceError("source_storage_unavailable", 503) from exc
        if hashlib.sha256(content).hexdigest() != document.content_sha256:
            raise SourceError("source_changed")
        try:
            pages, cover = await asyncio.to_thread(inspect_pdf, content)
        except SourceError as exc:
            raise SourceError("source_corrupt") from exc
        if pages != source["physical_pages"]:
            raise SourceError("source_changed")
        company = await asyncio.to_thread(self.companies.get, metadata.company_id)
        assessment = assess(cover, company.name, metadata)
        if "conflict" in assessment.values():
            raise SourceError("report_identity_conflict")
        origin = await asyncio.to_thread(self.repository.origin, document.workspace_id, document_id)
        ids = await asyncio.to_thread(self.repository.evidence_ids, revision)
        response = dict(
            document_id=document_id,
            company_id=metadata.company_id,
            report_year=metadata.report_year,
            report_type=metadata.report_type,
            period_start=metadata.period_start.isoformat(),
            period_end=metadata.period_end.isoformat(),
            basis=metadata.basis,
            metadata_status=metadata.status,
            assessment=assessment,
            source_revision=revision,
            content_sha256=document.content_sha256,
            attempt=document.attempt,
            parser_version=self.parser_version,
            physical_pages=pages,
            evidence_ids=ids,
            source_url=origin["source_url"] if origin else None,
            source_url_status="user_declared" if origin else "not_provided",
        )
        # Revalidate persisted state after object/evidence reads to close correction/retry races.
        after = await self.documents.get_document(document_id)
        latest = await asyncio.to_thread(self.companies.metadata, document_id)
        if after != document or latest != metadata:
            raise SourceError("source_changed")
        await asyncio.to_thread(self.repository.source, document.workspace_id, revision)
        return response, content

    async def source(
        self,
        document_id: str,
        *,
        company_id: str | None = None,
        source_revision: str | None = None,
        page: int | None = None,
    ) -> dict[str, Any]:
        response, _ = await self._checked(document_id, company_id, source_revision)
        if page is not None and not 1 <= page <= response["physical_pages"]:
            raise SourceError("resource_not_found", 404)
        return response

    async def verify_selection(self, identities: tuple[dict[str, Any], ...]) -> None:
        """Final shared-DB snapshot check, following all per-source object checks."""
        await asyncio.to_thread(self.repository.verify_selection, identities)

    async def file(
        self, document_id: str, *, source_revision: str, company_id: str | None = None
    ) -> bytes:
        _, content = await self._checked(document_id, company_id, source_revision)
        return content

    async def evidence(
        self,
        document_id: str,
        evidence_id: str,
        *,
        source_revision: str,
        company_id: str | None = None,
    ) -> dict[str, Any]:
        source, _ = await self._checked(document_id, company_id, source_revision)
        evidence = await asyncio.to_thread(self.repository.evidence, source_revision, evidence_id)
        if not 1 <= evidence["physical_page"] <= source["physical_pages"]:
            raise SourceError("resource_not_found", 404)
        await self._checked(document_id, company_id, source_revision)
        return dict(
            **evidence,
            document_id=document_id,
            company_id=source["company_id"],
            bbox=None,
            location_mode="page_and_excerpt",
        )

    async def parsed_evidence(
        self, document_id: str, *, company_id: str, source_revision: str
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        source, _ = await self._checked(document_id, company_id, source_revision)
        records = await asyncio.to_thread(self.repository.evidence_batch, source_revision)
        if any(not 1 <= e["physical_page"] <= source["physical_pages"] for e in records):
            raise SourceError("source_evidence_corrupt")
        await self._checked(document_id, company_id, source_revision)
        return source, records

    async def correct(self, document_id: str, payload: BindingCorrectionInput) -> dict[str, Any]:
        document = await self.documents.get_document(document_id)
        # Correcting to demonstrably wrong cover data is forbidden as well.
        try:
            content = await asyncio.to_thread(self.objects.read_bytes, document.object_key)
        except Exception as exc:
            raise SourceError("source_storage_unavailable", 503) from exc
        if hashlib.sha256(content).hexdigest() != document.content_sha256:
            raise SourceError("source_changed")
        _, cover = await asyncio.to_thread(inspect_pdf, content)
        company = await asyncio.to_thread(self.companies.get, payload.metadata.company_id)
        if "conflict" in assess(cover, company.name, payload.metadata).values():
            raise SourceError("report_identity_conflict")
        result = await asyncio.to_thread(
            self.repository.correct, document.workspace_id, document, payload
        )
        # Do not project internal workspace fields even within audit metadata.
        for key in ("old_metadata", "new_metadata"):
            result[key].pop("workspace_id", None)
        return result

    async def page_context(self, document_id: str, revision: str, page: int) -> str:
        source, _ = await self._checked(document_id, None, revision)
        if not 1 <= page <= source['physical_pages']:
            raise SourceError('invalid_evidence_page')
        records = await asyncio.to_thread(self.repository.page_evidence, revision, page)
        for record in records:
            structure = (record.get("layout") or {}).get("table_structure")
            if structure and structure["status"] == "unsupported":
                raise SourceError("table_structure_unsupported")
        text = '\n'.join(e['text'] for e in records if e['physical_page'] == page)
        await self._checked(document_id, None, revision)
        return text

    async def reindex(self, document_id: str, expected_attempt: int) -> dict[str, Any]:
        document = await self.documents.get_document(document_id)
        await asyncio.to_thread(self.repository.request_reindex, document.workspace_id,
                                document_id, expected_attempt)
        record = await self.documents.retry_document(document_id)
        return dict(document_id=record.document_id, status=record.status.value,
                    attempt=record.attempt)

    async def history(self, document_id: str) -> list[dict[str, Any]]:
        document = await self.documents.get_document(document_id)
        history = await asyncio.to_thread(
            self.repository.history, document.workspace_id, document_id
        )
        for item in history:
            for key in ("old_metadata_json", "new_metadata_json"):
                item[key].pop("workspace_id", None)
        return history
