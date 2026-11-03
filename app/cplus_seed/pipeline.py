"""Owned synchronous source/processor assembly. No application, auth or provider client."""

from contextlib import contextmanager
import os
from app.companies.models import CompanyCreate
from app.companies.service import CompanyService
from app.companies.sqlite_repository import SQLiteCompanyRepository
from app.documents.local_object_store import LocalObjectStore
from app.documents.sqlite_repository import SQLiteDocumentRepository
from app.documents.service import DocumentService
from app.documents.source_repository import SQLiteSourceRepository, revision_id
from app.documents.source_service import DocumentSourceService, PARSER_VERSION
from app.documents.source_models import ReportUploadInput
from app.documents.fast_pdf_parser import parse_fast_pdf_bytes
from app.documents.processor import DocumentProcessor


@contextmanager
def real_pipeline(root):
    # Explicit offline engine setup before importing FlagEmbedding, before any Milvus client.
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", TOKENIZERS_PARALLELISM="false")
    from app.rag.embed import embed

    embed(["C+ public seed offline initialization"])
    from app.rag.store import get_client
    from app.rag.publications import IndexPublications

    repository = SQLiteDocumentRepository(root / "documents.db")
    registry = SQLiteCompanyRepository(root / "documents.db")
    companies = CompanyService(registry, workspace_id="demo")
    objects = LocalObjectStore(root / "objects")
    queued = []

    class Queue:
        def dispatch(self, document_id):
            queued.append(document_id)
            return True

    documents = DocumentService(
        repository=repository, object_store=objects, dispatcher=Queue(), workspace_id="demo"
    )
    sources = DocumentSourceService(
        documents=documents,
        objects=objects,
        companies=companies,
        repository=SQLiteSourceRepository(registry),
    )
    client = get_client(str(root / "milvus.db"))
    try:
        publications = IndexPublications(registry, client)

        def index(document_id, rows):
            result = publications.publish(document_id, rows)
            publications.cleanup()
            return result

        processor = DocumentProcessor(
            repository=repository,
            object_store=objects,
            parser=parse_fast_pdf_bytes,
            embedder=embed,
            index_document=index,
            data_version="cplus-public-seed-v2",
            source_identity=lambda r: dict(
                source_revision=revision_id(r, PARSER_VERSION),
                content_sha256=r.content_sha256,
                attempt=r.attempt,
                parser_version=PARSER_VERSION,
            ),
            source_recorder=sources.capture,
        )

        class Pipeline:
            async def add(self, item, raw):
                matches = [
                    c
                    for c in companies.list()
                    if c.security_code == item["security_code"] and c.exchange == item["exchange"]
                ]
                if len(matches) > 1 or (matches and matches[0].name != item["official_name"]):
                    raise ValueError("existing_company_identity_conflict")
                if (
                    item.get("binding_mode")
                    == "root_approved_existing_company_manual_upload_fallback"
                    and len(matches) != 1
                ):
                    raise ValueError("manual_fallback_company_missing")
                company = (
                    matches[0]
                    if matches
                    else companies.create(
                        CompanyCreate(
                            name=item["official_name"],
                            security_code=item["security_code"],
                            exchange=item["exchange"],
                            country="CN",
                        )
                    )
                )
                year = item["report_year"]
                uploaded = await sources.upload(
                    filename=f"{item['security_code']}-{year}.pdf",
                    content=raw,
                    payload=ReportUploadInput(
                        company_id=company.company_id,
                        report_year=year,
                        report_type="annual",
                        basis="unknown",
                        period_start=f"{year}-01-01",
                        period_end=f"{year}-12-31",
                        source_url=item["source_url"],
                    ),
                )
                doc = uploaded["document_id"]
                record = processor.process(doc)
                if record.status.value != "ready":
                    raise ValueError("new_document_not_ready:" + str(record.error_code))
                identity = await sources.source(doc, company_id=company.company_id)
                if any(
                    identity["assessment"][k] != "matches_cover"
                    for k in ("company", "report_year", "report_type")
                ):
                    raise ValueError("source_identity_unverified")
                publications.assert_current("demo", doc, identity["source_revision"])
                return identity

        yield Pipeline()
    finally:
        client.close()  # No background dispatcher, HTTP server, research owner or provider ever exists.
