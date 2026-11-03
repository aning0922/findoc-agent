"""UNIT_FAKE: isolated synthetic PDFs and fake OCR; no financial confirmation."""

import asyncio
from uuid import uuid4

import pymupdf
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.documents.source_models import ReportUploadInput
from app.documents.source_repository import revision_id
from app.parsing import ParseV2Service, create_parse_router
from app.parsing.service import ParseError
from tests.test_document_sources import Harness, metadata


class Engine:
    adapter_version = "fake-v1"
    name = "FAKE"
    timeout_seconds = 1

    def __init__(self):
        self.calls = 0
        self.fail_at = None
        self.change = None

    def recognize(self, image):
        self.calls += 1
        if self.change:
            self.change()
        if self.calls == self.fail_at:
            raise TimeoutError()
        return {
            "lines": [
                {"text": "营业收入候选未核对", "bbox": [0.1, 0.1, 0.2, 0.11], "confidence": 0.9},
                {"text": "123", "bbox": [0.6, 0.1, 0.7, 0.11], "confidence": 0.8},
                {"text": "净利润", "bbox": [0.1, 0.15, 0.2, 0.16], "confidence": 0.9},
                {"text": "45", "bbox": [0.6, 0.15, 0.7, 0.16], "confidence": 0.8},
            ],
            "request_revision": 3,
            "os_version": "fake",
        }


def run(coro):
    return asyncio.run(coro)


def fixture(tmp_path):
    h = Harness(tmp_path)
    with pymupdf.open() as pdf:
        image = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), False)
        image.clear_with(128)
        for _ in range(2):
            page = pdf.new_page()
            page.insert_image(page.rect, stream=image.tobytes("png"))
        content = pdf.tobytes()
    result = run(
        h.service.upload(
            filename="scan.pdf",
            content=content,
            payload=ReportUploadInput(**metadata(h.company.company_id)),
        )
    )
    doc = result["document_id"]
    from app.documents.models import DocumentStatus, FailureStage

    h.docs.transition_status(
        doc, expected_status=DocumentStatus.QUEUED, new_status=DocumentStatus.PARSING
    )
    h.docs.transition_status(
        doc,
        expected_status=DocumentStatus.PARSING,
        new_status=DocumentStatus.FAILED,
        failed_stage=FailureStage.PARSING,
        error_code="PDF_NO_TEXT",
        safe_error_message="未从该PDF提取到可索引文本",
    )
    record = run(h.documents.get_document(doc))
    engine = Engine()
    service = ParseV2Service(
        runtime_root=tmp_path, documents=h.documents, sources=h.service, engine=engine
    )
    return h, doc, record, content, revision_id(record, h.service.parser_version), engine, service


def test_complete_replay_search_partial_keeps_active(tmp_path):
    h, doc, record, content, rev, engine, s = fixture(tmp_path)
    op = str(uuid4())
    r = run(s.retry(doc, op, rev))
    assert r["state"] == "completed" and engine.calls == 2
    assert run(s.retry(doc, op, rev)) == r and engine.calls == 2
    q = run(s.quality(doc))
    assert q["artifact_id"] == r["artifact_id"]
    assert q["source_status"] == "current" and not q["legacy_source_verified"]
    grid = q["pages"][0]["tables"][0]
    assert grid["quality"] == "needs_review" and grid["row_count"] == 2
    assert [(c["row"], c["column"], c["text"]) for c in grid["cells"]] == [
        (0, 0, "营业收入候选未核对"),
        (0, 1, "123"),
        (1, 0, "净利润"),
        (1, 1, "45"),
    ]
    assert grid["cells"][1]["bbox"] == [0.6, 0.1, 0.7, 0.11]
    assert q["identity_assessment"]["financial_facts"] == "not_verified"
    assert run(s.search(doc, r["artifact_id"], "营业收入"))["items"][0]["physical_page"] == 1
    assert run(s.image(doc, r["artifact_id"], 1)).startswith(b"\x89PNG")
    assert run(s.file(doc, r["artifact_id"])) == content
    engine.fail_at = engine.calls + 2
    partial = run(s.retry(doc, str(uuid4()), rev))
    assert partial["state"] == "partial"
    assert run(s.quality(doc))["artifact_id"] == r["artifact_id"]
    assert run(s.quality(doc, partial["artifact_id"]))["state"] == "partial"
    with pytest.raises(ParseError, match="operation_conflict"):
        run(s.retry(doc, op, "0" * 64))
    with pytest.raises(ParseError, match="operation_not_found"):
        s.operation("different-document", op)


def test_changed_source_blocks_publication_and_image(tmp_path):
    h, doc, record, content, rev, engine, s = fixture(tmp_path)
    first = run(s.retry(doc, str(uuid4()), rev))
    engine.change = lambda: h.objects.put_bytes(record.object_key, b"%PDF-corrupted")
    changed = run(s.retry(doc, str(uuid4()), rev))
    assert changed["state"] == "failed"
    assert run(s.quality(doc, first["artifact_id"]))["source_status"] == "stale"
    with pytest.raises(ParseError, match="source_changed"):
        run(s.image(doc, first["artifact_id"], 1))
    h.objects.put_bytes(record.object_key, content)
    assert run(s.quality(doc))["artifact_id"] == first["artifact_id"]
    assert run(s.quality(doc, changed["artifact_id"]))["error_code"] == "source_changed"
    with pytest.raises(ParseError, match="artifact_unavailable"):
        run(s.search(doc, changed["artifact_id"], "营业收入"))


def test_fast_text_and_http_contract(tmp_path):
    h = Harness(tmp_path)
    with pymupdf.open() as pdf:
        p = pdf.new_page()
        p.insert_text((40, 80), "This is a text layer with more than twenty characters.")
        raw = pdf.tobytes()
    value = run(
        h.service.upload(
            filename="text.pdf",
            content=raw,
            payload=ReportUploadInput(**metadata(h.company.company_id)),
        )
    )
    doc = value["document_id"]
    rec = run(h.documents.get_document(doc))
    rev = revision_id(rec, h.service.parser_version)
    engine = Engine()
    s = ParseV2Service(
        runtime_root=tmp_path, documents=h.documents, sources=h.service, engine=engine
    )
    app = FastAPI()
    app.include_router(create_parse_router(s))
    client = TestClient(app)
    identity = client.get(f"/documents/{doc}/parse-identity")
    assert identity.status_code == 200 and identity.json()["source_revision"] == rev
    assert identity.json()["legacy_source_verified"] is False
    body = {"operation_id": str(uuid4()), "expected_source_revision": rev}
    r = client.post(f"/documents/{doc}/parse-retry", json=body)
    assert r.status_code == 200 and r.json()["state"] == "completed" and engine.calls == 0
    artifact = r.json()["artifact_id"]
    assert (
        client.get(f"/documents/{doc}/parse-quality", params={"artifact_id": artifact}).json()[
            "pages"
        ][0]["method"]
        == "fast"
    )
    assert (
        client.get(f"/documents/{doc}/parse-operations/{body['operation_id']}").json() == r.json()
    )
    assert client.get(
        f"/documents/{doc}/parse-artifacts/{artifact}/search", params={"q": "text layer"}
    ).json()["items"]
    assert (
        client.get(f"/documents/{doc}/parse-quality").json()["engine"]["name"]
        == "PyMuPDF text layer"
    )
    with pymupdf.open() as pdf:
        pdf.new_page()
        page = pdf.new_page()
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), False)
        pix.clear_with(128)
        page.insert_image(page.rect, stream=pix.tobytes("png"))
        page.insert_text((40, 40), "Scanned table with a sufficiently long text header.")
        white_page = pdf.new_page()
        white = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), False)
        white.clear_with(255)
        white_page.insert_image(white_page.rect, stream=white.tobytes("png"))
        mixed = pdf.tobytes()
    identity, _ = run(s.snapshot(doc))
    parsed = s.parse(identity, mixed)
    assert parsed["state"] == "completed" and parsed["pages_processed"] == 3
    assert parsed["pages"][0]["method_reason"] == "empty_page"
    assert (
        parsed["pages"][1]["method"] == "ocr"
        and parsed["pages"][1]["method_reason"] == "substantial_image_coverage"
    )
    assert parsed["pages"][2]["method_reason"] == "raster_blank_heuristic"
    assert "blank_page_heuristic" in parsed["pages"][2]["warnings"]
    assert engine.calls == 1
    s.max_pages = 1
    limited = s.parse(identity, mixed)
    assert (
        limited["state"] == "partial"
        and limited["pages_processed"] == 1
        and limited["page_limit"] == 1
    )
    assert (
        client.post(f"/documents/{doc}/parse-retry", json={**body, "path": "/etc"}).status_code
        == 422
    )
