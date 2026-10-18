"""Real PDFs, SQLite, HTTP, ObjectStore; controlled embeddings/index only.

Small PDFs are generated fixtures. Four local original PDFs are byte-verified
against the D1 manifest; no model/retrieval or financial metric extraction occurs.
"""

import asyncio
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pymupdf
import pytest

from app.api.app import create_app
from app.companies import migrations
from app.companies.models import CompanyCreate, ReportMetadataInput
from app.companies.service import CompanyService
from app.companies.sqlite_repository import SQLiteCompanyRepository
from app.documents.fast_pdf_parser import parse_fast_pdf_bytes
from app.documents.local_object_store import LocalObjectStore
from app.documents.models import DocumentNotFoundError, DocumentStatus
from app.documents.processor import DocumentProcessor
from app.documents.service import DocumentService
from app.documents.source_repository import SQLiteSourceRepository
from app.documents.source_service import DocumentSourceService
from app.documents.sqlite_repository import SQLiteDocumentRepository
from app.rag.ingest import ReplaceResult
from tests.test_companies_migrations import snapshot
from tests.test_revenue_confirmation import Harness as RevenueHarness


def pdf_bytes(text="Example report pending identity verification", pages=2):
    with pymupdf.open() as pdf:
        for _ in range(pages):
            pdf.new_page().insert_text((50, 100), text)
        return pdf.tobytes()


def metadata(company_id, year=2025, **changes):
    return dict(
        company_id=company_id,
        report_year=year,
        report_type="annual",
        basis="PRC_GAAP",
        period_start=f"{year}-01-01",
        period_end=f"{year}-12-31",
        **changes,
    )


class Harness:
    def __init__(self, root, workspace="demo"):
        self.root = root
        self.db = root / "documents.db"
        self.docs = SQLiteDocumentRepository(self.db)
        self.registry = SQLiteCompanyRepository(self.db)
        self.companies = CompanyService(self.registry, workspace_id=workspace)
        self.company = self.companies.create(
            CompanyCreate(name="Example Corporation", security_code="000001", exchange="SZSE")
        )
        self.other = self.companies.create(
            CompanyCreate(name="Other Corporation", security_code="000002", exchange="SZSE")
        )
        self.objects = LocalObjectStore(root / "objects")
        self.dispatcher = Mock()
        self.dispatcher.dispatch.return_value = True
        self.documents = DocumentService(
            repository=self.docs,
            object_store=self.objects,
            dispatcher=self.dispatcher,
            workspace_id=workspace,
        )
        self.sources = SQLiteSourceRepository(self.registry)
        self.service = DocumentSourceService(
            documents=self.documents,
            objects=self.objects,
            companies=self.companies,
            repository=self.sources,
        )
        self.client = TestClient(
            create_app(self.documents, company_service=self.companies, source_service=self.service)
        )
        self.indexer = Mock(
            side_effect=lambda doc, rows: ReplaceResult(
                inserted=len(rows),
                updated=0,
                skipped=0,
                final_ids=frozenset(row["chunk_id"] for row in rows),
            )
        )
        self.embedder = Mock(side_effect=lambda texts: [[0.1] for _ in texts])
        self.processor = DocumentProcessor(
            repository=self.docs,
            object_store=self.objects,
            parser=parse_fast_pdf_bytes,
            embedder=self.embedder,
            index_document=self.indexer,
            data_version="test-controlled",
            chunker=lambda blocks: [
                b.model_copy(update={"chunk_id": f"chunk-{i}"}) for i, b in enumerate(blocks)
            ],
            source_recorder=self.service.capture,
        )

    def upload(self, content=None, payload=None, filename="misleading-1900.pdf"):
        return self.client.post(
            "/report-documents",
            files={
                "file": (filename, pdf_bytes() if content is None else content, "application/pdf")
            },
            data={"metadata": json.dumps(payload or metadata(self.company.company_id))},
        )

    def ready(self):
        uploaded = self.upload()
        assert uploaded.status_code == 202, uploaded.text
        self.id = uploaded.json()["document_id"]
        assert self.processor.process(self.id).status == DocumentStatus.READY
        response = self.client.get(f"/documents/{self.id}/source")
        assert response.status_code == 200, response.text
        self.source = response.json()
        self.rev = self.source["source_revision"]
        return self

    def query(self, endpoint="source", **query):
        return self.client.get(
            f"/documents/{self.id}/{endpoint}", params={"source_revision": self.rev, **query}
        )

    def correct(self, **changes):
        payload = dict(
            expected_attempt=self.docs.get(self.id).attempt,
            metadata=metadata(self.other.company_id),
            reason="Explicit fixture correction",
        )
        payload.update(changes)
        return self.client.post(f"/documents/{self.id}/binding-corrections", json=payload)


@pytest.fixture
def h(tmp_path):
    return Harness(tmp_path).ready()


def test_source_file_evidence_and_restart_consistent(h):
    source = h.source
    assert source["physical_pages"] == 2 and source["attempt"] == 1
    assert source["metadata_status"] == "pending_verification"
    assert source["assessment"]["company"] == "manual_check"
    assert source["assessment"]["financial_facts"] == "not_verified"
    assert source["assessment"]["basis"] == "manual_check"
    raw = h.query("file")
    assert hashlib.sha256(raw.content).hexdigest() == source["content_sha256"]
    assert raw.headers["content-type"] == "application/pdf"
    assert raw.headers["cache-control"] == "no-store"
    eid = source["evidence_ids"][0]
    evidence = h.query(f"evidence/{eid}").json()
    assert evidence["text"] and evidence["physical_page"] in (1, 2)
    assert evidence["bbox"] is None and evidence["location_mode"] == "page_and_excerpt"
    assert evidence["source_revision"] == h.rev
    assert h.query(page=2).status_code == 200
    restarted = DocumentSourceService(
        documents=h.documents,
        objects=h.objects,
        companies=CompanyService(SQLiteCompanyRepository(h.db), workspace_id="demo"),
        repository=SQLiteSourceRepository(SQLiteCompanyRepository(h.db)),
    )
    assert asyncio.run(restarted.source(h.id)) == source
    assert str(h.root) not in json.dumps(source)
    assert "workspace_id" not in source and "object_key" not in source
    assert h.embedder.call_count == 1 and h.indexer.call_count == 1


@pytest.mark.parametrize("endpoint", ["source", "file", "evidence/made-up"])
def test_different_company_unknown_and_workspace_isolation(h, endpoint):
    assert h.query(endpoint, company_id=h.other.company_id).status_code == 404
    assert (
        h.client.get(
            f"/documents/unknown/{endpoint}", params={"source_revision": h.rev}
        ).status_code
        == 404
    )
    outsider = DocumentService(
        repository=h.docs,
        object_store=h.objects,
        dispatcher=h.dispatcher,
        workspace_id="other-workspace",
    )
    service = DocumentSourceService(
        documents=outsider,
        objects=h.objects,
        companies=CompanyService(h.registry, workspace_id="other-workspace"),
        repository=h.sources,
    )
    client = TestClient(create_app(outsider, source_service=service))
    assert (
        client.get(
            f"/documents/{h.id}/{endpoint}",
            params={"source_revision": h.rev, "workspace_id": "demo"},
        ).status_code
        == 404
    )
    assert h.query(endpoint, workspace_id="other-workspace").status_code in (200, 404)
    with pytest.raises(DocumentNotFoundError):
        asyncio.run(outsider.retry_document(h.id))


@pytest.mark.parametrize("status", ["queued", "parsing", "indexing", "failed"])
@pytest.mark.parametrize("endpoint", ["source", "file", "evidence/made-up"])
def test_nonready_blocks_all_reads(h, status, endpoint):
    with closing(sqlite3.connect(h.db)) as conn, conn:
        conn.execute(
            "UPDATE documents SET status=?, failed_stage=?, error_code=?, "
            "safe_error_message=? WHERE document_id=?",
            (
                status,
                "queued" if status == "failed" else None,
                "TEST_FAILURE" if status == "failed" else None,
                "fixture" if status == "failed" else None,
                h.id,
            ),
        )
    assert h.query(endpoint).status_code == 409


@pytest.mark.parametrize("endpoint", ["source", "file", "evidence/made-up"])
@pytest.mark.parametrize("failure", ["missing", "changed", "storage", "unsafe_key"])
def test_source_file_damage_or_storage_errors_are_safe(h, monkeypatch, endpoint, failure):
    doc = h.docs.get(h.id)
    if failure == "missing":
        (h.root / "objects" / doc.object_key).unlink()
    elif failure == "changed":
        h.objects.put_bytes(doc.object_key, b"%PDF-broken")
    elif failure == "unsafe_key":
        with closing(sqlite3.connect(h.db)) as conn, conn:
            conn.execute(
                "UPDATE documents SET object_key=? WHERE document_id=?", ("../../secret.pdf", h.id)
            )
    else:
        monkeypatch.setattr(
            h.objects, "read_bytes", Mock(side_effect=OSError("/secret/server/key"))
        )
    result = h.query(endpoint)
    assert result.status_code == (
        404 if failure == "missing" else 409 if failure == "changed" else 503
    )
    assert "secret" not in result.text and str(h.root) not in result.text


@pytest.mark.parametrize(
    "change",
    [
        "sha",
        "attempt",
        "parser_version",
        "invalidated",
        "pages",
        "stored_sha",
        "stored_attempt",
        "stored_parser",
    ],
)
@pytest.mark.parametrize("endpoint", ["source", "file", "evidence/made-up"])
def test_source_versions_fail_closed(h, change, endpoint):
    with closing(sqlite3.connect(h.db)) as conn, conn:
        if change in ("sha", "attempt"):
            column, value = ("content_sha256", "a" * 64) if change == "sha" else ("attempt", 2)
            conn.execute(f"UPDATE documents SET {column}=? WHERE document_id=?", (value, h.id))
        elif change.startswith("stored_"):
            column, value = {
                "stored_sha": ("content_sha256", "b" * 64),
                "stored_attempt": ("attempt", 8),
                "stored_parser": ("parser_version", "corrupt-version"),
            }[change]
            conn.execute(f"UPDATE document_sources SET {column}=?", (value,))
        elif change == "invalidated":
            conn.execute("UPDATE document_sources SET invalidated_at='fixture'")
        elif change == "pages":
            conn.execute("UPDATE document_sources SET physical_pages=3")
        else:
            h.service.parser_version = "fast-pdf-v2"
    assert h.query(endpoint).status_code == 409
    assert h.client.get(f"/documents/{h.id}/source").status_code == 409


@pytest.mark.parametrize("page,status", [(0, 422), (-1, 422), (3, 404), (10000, 404)])
def test_physical_page_bounds(h, page, status):
    assert h.query(page=page).status_code == status


def test_trusted_evidence_only_and_no_client_coordinates(h):
    assert (
        h.query("evidence/forged", page=1, text="fabricated", bbox="0,0,100,100").status_code == 404
    )
    eid = h.source["evidence_ids"][0]
    evidence = h.query(f"evidence/{eid}", text="fabricated", bbox="0,0,100,100").json()
    assert evidence["text"] != "fabricated" and evidence["bbox"] is None
    with closing(sqlite3.connect(h.db)) as conn, conn:
        conn.execute("UPDATE document_evidence SET physical_page=9999 WHERE evidence_id=?", (eid,))
    assert h.query(f"evidence/{eid}").status_code == 409


def test_duplicate_content_same_binding_or_conflict(h):
    raw = h.query("file").content
    assert h.upload(raw).json()["duplicate"] is True
    assert h.upload(raw).json()["document_id"] == h.id
    assert h.upload(raw, metadata(h.other.company_id)).status_code == 409
    assert h.upload(raw, metadata(h.company.company_id, 2024)).status_code == 409
    assert h.companies.metadata(h.id).company_id == h.company.company_id
    assert len(asyncio.run(h.documents.list_documents())) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("workspace_id", "other"),
        ("status", "verified"),
        ("company_id", "unknown"),
        ("source_url", "file:///secret"),
        ("report_year", "2025"),
    ],
)
def test_report_upload_strict_metadata(tmp_path, field, value):
    h = Harness(tmp_path)
    payload = metadata(h.company.company_id)
    payload[field] = value
    assert h.upload(payload=payload).status_code == (404 if field == "company_id" else 422)
    assert not asyncio.run(h.documents.list_documents())


@pytest.mark.parametrize("content", [b"%PDF-invalid", b"not pdf"])
def test_upload_invalid_real_pdf_never_dispatches(tmp_path, content):
    h = Harness(tmp_path)
    assert h.upload(content).status_code == 415
    assert not asyncio.run(h.documents.list_documents())
    h.dispatcher.dispatch.assert_not_called()


def test_upload_origin_and_binding_rollback(h):
    with closing(sqlite3.connect(h.db)) as conn, conn:
        conn.execute(
            "CREATE TRIGGER origin_abort AFTER INSERT ON report_source_origins "
            "BEGIN SELECT RAISE(ABORT, 'fixture secret'); END"
        )
    data = pdf_bytes("A different report with unknown identity")
    result = h.upload(data)
    assert result.status_code == 500 and "secret" not in result.text
    doc = h.docs.find_by_content("demo", hashlib.sha256(data).hexdigest())
    with closing(sqlite3.connect(h.db)) as conn:
        assert (
            conn.execute(
                "SELECT 1 FROM report_document_metadata WHERE document_id=?", (doc.document_id,)
            ).fetchone()
            is None
        )
    assert h.client.get(f"/documents/{doc.document_id}/source").status_code == 404


def test_explicit_correction_preserves_original_and_invalidates_old_references(h):
    before = snapshot(h.db, ["report_document_metadata"])
    old_rev, old_eid = h.rev, h.source["evidence_ids"][0]
    corrected = h.correct()
    assert corrected.status_code == 200, corrected.text
    audit = corrected.json()
    assert audit["old_attempt"] == 1 and audit["new_attempt"] == 2
    assert audit["action_kind"] == "explicit_user_request"
    assert h.companies.metadata(h.id).company_id == h.other.company_id
    assert snapshot(h.db, ["report_document_metadata"]) == before
    assert h.docs.get(h.id).status == DocumentStatus.FAILED
    assert h.query("file").status_code == 409
    assert h.query(f"evidence/{old_eid}").status_code == 409
    assert (
        h.client.put(f"/documents/{h.id}/metadata", json=metadata(h.company.company_id)).status_code
        == 409
    )
    assert (
        h.upload(
            h.objects.read_bytes(h.docs.get(h.id).object_key), metadata(h.company.company_id)
        ).status_code
        == 409
    )
    assert h.correct(expected_attempt=1).status_code == 409
    history = h.client.get(f"/documents/{h.id}/binding-corrections").json()
    assert len(history) == 1 and history[0]["reason"] == audit["reason"]
    assert "workspace_id" not in json.dumps(history)
    assert h.client.post(f"/documents/{h.id}/retry").status_code == 202
    assert h.processor.process(h.id).status == DocumentStatus.READY
    new = h.client.get(f"/documents/{h.id}/source").json()
    assert new["attempt"] == 3 and new["source_revision"] != old_rev
    assert new["company_id"] == h.other.company_id
    assert new["metadata_status"] == "pending_verification"
    assert h.query("file").status_code == 409
    assert h.query(f"evidence/{old_eid}", source_revision=new["source_revision"]).status_code == 404
    assert h.query("file", source_revision=new["source_revision"]).status_code == 200
    with closing(sqlite3.connect(h.db)) as conn:
        assert conn.execute(
            "SELECT invalidated_at FROM document_sources WHERE source_revision=?", (old_rev,)
        ).fetchone()[0]
    for statement in (
        'UPDATE report_binding_corrections SET reason="silent"',
        "DELETE FROM report_binding_corrections",
        'UPDATE report_document_metadata SET company_id="silent"',
    ):
        with closing(sqlite3.connect(h.db)) as conn, pytest.raises(sqlite3.IntegrityError):
            conn.execute(statement)


@pytest.mark.parametrize("table", ["report_binding_corrections", "document_sources", "documents"])
def test_correction_transaction_failure_rolls_back_all(h, table):
    tables = [
        "documents",
        "report_document_metadata",
        "report_binding_corrections",
        "document_sources",
    ]
    before = snapshot(h.db, tables)
    operation = "INSERT" if table == "report_binding_corrections" else "UPDATE"
    with closing(sqlite3.connect(h.db)) as conn, conn:
        conn.execute(
            f"CREATE TRIGGER failure AFTER {operation} ON {table} "
            "BEGIN SELECT RAISE(ABORT, 'secret audit fixture'); END"
        )
    result = h.correct()
    assert result.status_code == 500 and "secret" not in result.text
    assert snapshot(h.db, tables) == before
    assert h.query("file").status_code == 200


@pytest.mark.parametrize(
    "changes",
    [
        dict(reason=" "),
        dict(expected_attempt="1"),
        dict(operator="invented-human"),
        dict(workspace_id="other"),
        dict(expected_attempt=99),
    ],
)
def test_correction_strict_and_stale(h, changes):
    assert h.correct(**changes).status_code == (
        409 if changes.get("expected_attempt") == 99 else 422
    )
    assert h.companies.metadata(h.id).company_id == h.company.company_id


def test_old_revenue_confirmation_invalidated_without_rewriting_history(tmp_path):
    legacy = RevenueHarness(tmp_path)
    original = legacy.documents_repository.get(legacy.document_id)
    real_content = pdf_bytes("2024 revenue 100; 2025 revenue 120; controlled evidence")
    # Use a real PDF as the source while retrieval candidates remain controlled fixtures.
    with closing(sqlite3.connect(legacy.database)) as conn, conn:
        conn.execute(
            "UPDATE documents SET content_sha256=? WHERE document_id=?",
            (hashlib.sha256(real_content).hexdigest(), legacy.document_id),
        )
    legacy.objects.put_bytes(original.object_key, real_content)
    review = legacy.preview()
    confirmation = legacy.simulate_acceptance(review)
    before = snapshot(legacy.database, ["revenue_confirmations", "confirmed_revenue_facts"])
    registry = SQLiteCompanyRepository(legacy.database)
    companies = CompanyService(registry, workspace_id="demo")
    a = companies.create(CompanyCreate(name="A", security_code="1", exchange="SZSE"))
    b = companies.create(CompanyCreate(name="B", security_code="2", exchange="SZSE"))
    companies.bind(legacy.document_id, ReportMetadataInput.model_validate(metadata(a.company_id)))
    service = DocumentSourceService(
        documents=legacy.documents,
        objects=legacy.objects,
        companies=companies,
        repository=SQLiteSourceRepository(registry),
    )
    from app.documents.source_models import BindingCorrectionInput

    asyncio.run(
        service.correct(
            legacy.document_id,
            BindingCorrectionInput.model_validate(
                dict(
                    expected_attempt=1,
                    metadata=metadata(b.company_id),
                    reason="simulated correction test",
                )
            ),
        )
    )
    from app.agent.revenue_confirmation import RevenueConfirmationError

    with pytest.raises(RevenueConfirmationError, match="source_unavailable"):
        legacy.calculate(confirmation.confirmation_id)
    with closing(sqlite3.connect(legacy.database)) as conn, conn:
        conn.execute(
            "UPDATE documents SET status='ready', failed_stage=NULL, error_code=NULL, "
            "safe_error_message=NULL WHERE document_id=?",
            (legacy.document_id,),
        )
    with pytest.raises(RevenueConfirmationError, match="source_changed|review_changed"):
        legacy.calculate(confirmation.confirmation_id)
    assert snapshot(legacy.database, ["revenue_confirmations", "confirmed_revenue_facts"]) == before


def test_v3_upgrade_failure_and_recovery(tmp_path, monkeypatch):
    plan = migrations.MIGRATIONS
    monkeypatch.setattr(migrations, "MIGRATIONS", plan[:2])
    registry = SQLiteCompanyRepository(tmp_path / "documents.db")
    before = snapshot(
        registry._database_path,
        ["documents", "companies", "report_document_metadata", "analyst_schema_migrations"],
    )
    version, name, statements = plan[2]
    monkeypatch.setattr(
        migrations,
        "MIGRATIONS",
        (*plan[:2], (version, name, (*statements, "INVALID D6 MIGRATION"))),
    )
    with pytest.raises(sqlite3.OperationalError):
        SQLiteCompanyRepository(registry._database_path)
    assert snapshot(registry._database_path, list(before)) == before
    with closing(sqlite3.connect(registry._database_path)) as conn:
        assert (
            conn.execute("SELECT name FROM sqlite_master WHERE name LIKE 'd6_%'").fetchall() == []
        )
        assert (
            conn.execute("SELECT name FROM sqlite_master WHERE name='document_sources'").fetchone()
            is None
        )
    monkeypatch.setattr(migrations, "MIGRATIONS", plan)
    SQLiteCompanyRepository(registry._database_path)
    SQLiteCompanyRepository(registry._database_path)
    with closing(sqlite3.connect(registry._database_path)) as conn:
        assert conn.execute("SELECT version FROM analyst_schema_migrations").fetchall() == [(version,) for version, _, _ in plan]
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.fixture(scope="module")
def original_reports_harness(tmp_path_factory):
    h = Harness(tmp_path_factory.mktemp("d6-original-reports"))
    h.original_companies = {
        name: h.companies.create(CompanyCreate(name=name, security_code=code, exchange="SZSE"))
        for name, code in [
            ("美的集团股份有限公司", "000333"),
            ("珠海格力电器股份有限公司", "000651"),
        ]
    }
    return h


@pytest.mark.local_data
@pytest.mark.parametrize(
    "report_id,company_name,year,pages",
    [
        ("midea-2024", "美的集团股份有限公司", 2024, 295),
        ("midea-2025", "美的集团股份有限公司", 2025, 276),
        ("gree-2024", "珠海格力电器股份有限公司", 2024, 248),
        ("gree-2025", "珠海格力电器股份有限公司", 2025, 219),
    ],
)
def test_four_original_reports(
    tmp_path, report_id, company_name, year, pages, original_reports_harness
):
    manifest = json.loads(Path("product/validation/sources.json").read_text())
    original = next(item for item in manifest if item["id"] == report_id)
    source_path = Path(original["path"])
    if not source_path.exists():
        pytest.skip("Original local PDF unavailable; download manifest URL and verify SHA first")
    raw = source_path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == original["sha256"] and len(raw) == original["bytes"]
    # Copy bytes into the brand-new independent test root first; originals remain untouched.
    imported = tmp_path / "original.pdf"
    imported.write_bytes(raw)
    h = original_reports_harness
    company = h.original_companies[company_name]
    payload = {**metadata(company.company_id, year), "source_url": original["url"]}
    uploaded = h.upload(imported.read_bytes(), payload)
    assert uploaded.status_code == 202, uploaded.text
    h.id = uploaded.json()["document_id"]
    assert uploaded.json()["assessment"]["company"] == "matches_cover"
    assert uploaded.json()["assessment"]["report_year"] == "matches_cover"
    assert uploaded.json()["assessment"]["basis"] == "manual_check"
    assert h.processor.process(h.id).status == DocumentStatus.READY
    result = h.client.get(f"/documents/{h.id}/source")
    assert result.status_code == 200, result.text
    h.source = result.json()
    h.rev = h.source["source_revision"]
    assert h.source["content_sha256"] == original["sha256"] and h.source["physical_pages"] == pages
    assert h.source["company_id"] == company.company_id and h.source["report_year"] == year
    assert h.source["source_url"] == original["url"]
    assert h.query("file", company_id=company.company_id).content == raw
    opposite = next(c for c in h.original_companies.values() if c.company_id != company.company_id)
    assert h.query("file", company_id=opposite.company_id).status_code == 404
    eid = h.source["evidence_ids"][0]
    assert h.query(f"evidence/{eid}").status_code == 200
    assert h.query(page=pages).status_code == 200
    assert h.query(page=pages + 1).status_code == 404
    assert h.upload(raw, payload).json()["document_id"] == h.id
    assert h.upload(raw, {**payload, "company_id": h.company.company_id}).status_code == 409
    assert h.upload(raw, {**payload, **metadata(company.company_id, year - 1)}).status_code == 409
    assert hashlib.sha256(source_path.read_bytes()).hexdigest() == original["sha256"]
    proof = dict(
        report_id=report_id,
        **h.source,
        original_bytes=len(raw),
        file_sha_verified=True,
        restart_consistent=True,
        controlled=["embedding", "vector index", "chunk IDs/segmentation (blocks retained)"],
        parser="real parse_fast_pdf_bytes",
        financial_facts_verified=False,
        batch_database=str(h.db),
    )
    restarted = DocumentSourceService(
        documents=h.documents,
        objects=h.objects,
        companies=CompanyService(SQLiteCompanyRepository(h.db), workspace_id="demo"),
        repository=SQLiteSourceRepository(SQLiteCompanyRepository(h.db)),
    )
    assert asyncio.run(restarted.source(h.id)) == h.source
    proof.pop("evidence_ids")
    (tmp_path / "report-proof.json").write_text(json.dumps(proof, indent=2, ensure_ascii=False))


def test_cross_document_and_workspace_evidence_cannot_be_reused(h, tmp_path):
    other = Harness(tmp_path / "foreign", workspace="foreign")
    uploaded = other.upload(h.query("file").content)
    other.id = uploaded.json()["document_id"]
    assert other.processor.process(other.id).status == DocumentStatus.READY
    other.source = other.client.get(f"/documents/{other.id}/source").json()
    other.rev = other.source["source_revision"]
    foreign_eid = other.source["evidence_ids"][0]
    assert h.query(f"evidence/{foreign_eid}").status_code == 404
    assert h.query("file", source_revision=other.rev).status_code == 409
    assert h.id != other.id  # Same bytes have distinct server workspace identities.
    assert h.docs.get(h.id).workspace_id == "demo"


@pytest.mark.parametrize("field,value", [("text", "forged evidence"), ("kind", "forged")])
def test_corrupt_evidence_never_published(h, field, value):
    eid = h.source["evidence_ids"][0]
    with closing(sqlite3.connect(h.db)) as conn, conn:
        conn.execute(f"UPDATE document_evidence SET {field}=? WHERE evidence_id=?", (value, eid))
    assert h.query(f"evidence/{eid}").status_code == 409


def test_source_race_during_storage_read_rejects_old_success(h, monkeypatch):
    read = h.objects.read_bytes

    def mutate(key):
        content = read(key)
        with closing(sqlite3.connect(h.db)) as conn, conn:
            conn.execute("UPDATE documents SET attempt=attempt+1 WHERE document_id=?", (h.id,))
        return content

    monkeypatch.setattr(h.objects, "read_bytes", mutate)
    assert h.query("file").status_code == 409


def test_concurrent_corrections_only_one_audit_and_invalidation(h):
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: h.correct(expected_attempt=1).status_code, range(2)))
    assert sorted(results) == [200, 409]
    assert len(h.client.get(f"/documents/{h.id}/binding-corrections").json()) == 1
    assert h.docs.get(h.id).attempt == 2


def test_source_capture_failure_leaves_failed_doc_and_no_partial_evidence(tmp_path):
    h = Harness(tmp_path)
    uploaded = h.upload()
    doc_id = uploaded.json()["document_id"]
    with closing(sqlite3.connect(h.db)) as conn, conn:
        conn.execute(
            "CREATE TRIGGER capture_failure AFTER INSERT ON document_evidence "
            "BEGIN SELECT RAISE(ABORT, 'capture fixture'); END"
        )
    doc = h.processor.process(doc_id)
    assert doc.status == DocumentStatus.FAILED and doc.error_code == "PDF_PARSE_FAILED"
    with closing(sqlite3.connect(h.db)) as conn:
        assert conn.execute("SELECT count(*) FROM document_sources").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM document_evidence").fetchone()[0] == 0
    assert h.client.get(f"/documents/{doc_id}/source").status_code == 409
    h.indexer.assert_not_called()


def test_upload_object_write_error_safe_and_unbound(tmp_path, monkeypatch):
    h = Harness(tmp_path)
    monkeypatch.setattr(h.objects, "put_bytes", Mock(side_effect=OSError("/secret/object/root")))
    result = h.upload()
    assert result.status_code == 500 and "secret" not in result.text
    assert not asyncio.run(h.documents.list_documents())
    h.dispatcher.dispatch.assert_not_called()


@pytest.mark.parametrize("endpoint", ["source", "file", "evidence/unknown", "binding-corrections"])
def test_disabled_source_service(h, endpoint):
    client = TestClient(create_app(h.documents))
    assert (
        client.get(f"/documents/{h.id}/{endpoint}", params={"source_revision": h.rev}).status_code
        == 503
    )


def test_required_version_on_file_and_evidence(h):
    for endpoint in ("file", "evidence/unknown"):
        assert h.client.get(f"/documents/{h.id}/{endpoint}").status_code == 422
        assert h.query(endpoint, source_revision="forged").status_code == 422


def test_wrong_d5_first_binding_requires_explicit_correction(tmp_path):
    h = Harness(tmp_path)
    name = "测试上市股份有限公司"
    real_company = h.companies.create(CompanyCreate(name=name, security_code="3", exchange="SZSE"))
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text(
            (50, 100), f"{name}\n2025 年年度报告\n真实封面信息用于来源核对", fontname="china-s"
        )
        content = pdf.tobytes()
    uploaded = asyncio.run(
        h.documents.upload_document(source_file="wrong-2024.pdf", content=content)
    )
    h.id = uploaded.record.document_id
    assert h.processor.process(h.id).status == DocumentStatus.READY
    old = metadata(h.other.company_id, 2024)
    assert h.client.put(f"/documents/{h.id}/metadata", json=old).status_code == 200
    assert h.client.get(f"/documents/{h.id}/source").status_code == 409
    new = metadata(real_company.company_id)
    assert h.upload(content, new).status_code == 409  # Same ID, no bypass through deduplication.
    assert h.client.put(f"/documents/{h.id}/metadata", json=new).status_code == 409
    correction = h.correct(
        metadata=new, reason="Fix the mistaken initial binding against PDF cover"
    )
    assert correction.status_code == 200, correction.text
    assert correction.json()["old_metadata"]["report_year"] == 2024
    assert correction.json()["new_metadata"]["report_year"] == 2025
    assert h.client.post(f"/documents/{h.id}/retry").status_code == 202
    assert h.processor.process(h.id).status == DocumentStatus.READY
    source = h.client.get(f"/documents/{h.id}/source").json()
    assert source["company_id"] == real_company.company_id
    assert source["assessment"]["company"] == "matches_cover"
    assert source["metadata_status"] == "pending_verification"


@pytest.mark.parametrize("status", ["queued", "parsing", "indexing"])
def test_correction_cannot_race_active_processor(h, status):
    with closing(sqlite3.connect(h.db)) as conn, conn:
        conn.execute("UPDATE documents SET status=? WHERE document_id=?", (status, h.id))
    assert h.correct().status_code == 409
    assert h.companies.metadata(h.id).company_id == h.company.company_id
    assert h.client.get(f"/documents/{h.id}/binding-corrections").json() == []


def test_runtime_shares_source_service_and_initialization_failure_closes(tmp_path, monkeypatch):
    from app.api import runtime_factory
    from tests.test_runtime_revenue import assembled

    dependencies = assembled.__wrapped__(tmp_path, monkeypatch)
    app = runtime_factory.create_runtime_app(tmp_path)
    source = app.state.source_service
    assert source.documents is app.state.revenue_service._source_reader._documents
    assert source.objects is app.state.revenue_service._source_reader._objects
    assert source.companies is app.state.company_service
    assert source.repository.registry is app.state.company_service._repository
    with TestClient(app) as client:
        assert client.get("/documents/unknown/source").status_code == 404
    monkeypatch.setattr(
        runtime_factory, "SQLiteSourceRepository", Mock(side_effect=OSError("fixture"))
    )
    with pytest.raises(OSError, match="fixture"):
        runtime_factory.create_runtime_app(tmp_path)
    assert dependencies[5].close.call_count == 2
