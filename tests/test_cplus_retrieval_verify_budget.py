"""Bound expensive source verification to admitted top-k, preserving backfill/fences."""

import asyncio
from types import SimpleNamespace

import pytest

from app.rag.retriever import SearchHit
from app.retrieval_v2 import HybridRetrievalService, SourceRef
from app.retrieval_v2.models import EvidenceRef, RetrievalError


def service_fixture(tmp_path):
    sources = SimpleNamespace(
        documents=SimpleNamespace(
            _repository=SimpleNamespace(_database_path=tmp_path / "documents.db")
        )
    )
    ref = SourceRef(
        kind="fast",
        workspace_id="demo",
        company_id="c",
        document_id="d",
        source_revision="revision",
        content_sha256="content",
        parser_version="fixture",
        report_year=2025,
        identity_status="fast_source_verified",
    )
    records = [
        EvidenceRef(
            source_ref=ref,
            evidence_id=f"e-{i:02}",
            physical_page=i + 1,
            text=f"独立候选段落-{i:02}",
        )
        for i in range(20)
    ]

    async def dense(query, refs, top_k):
        return [
            SearchHit(
                0.9 - i * 0.01,
                f"chunk-{i}",
                e.text,
                e.physical_page,
                "fixture.pdf",
                "paragraph",
                workspace_id="demo",
                document_id="d",
                source_revision="revision",
            )
            for i, e in enumerate(records)
        ]

    service = HybridRetrievalService(tmp_path, sources, None, dense)

    async def current(ref):
        return records

    service.records = current
    return service, ref, records


@pytest.mark.parametrize("reject", [set(), {"e-00", "e-01"}, set(f"e-{i:02}" for i in range(20))])
def test_rank_then_verify_limits_work_and_backfills_rejections(tmp_path, reject):
    service, ref, records = service_fixture(tmp_path)
    checked = []

    async def verify(evidence):
        checked.append(evidence.evidence_id)
        if evidence.evidence_id in reject:
            raise RetrievalError("exact_evidence_unverified")
        return evidence

    service.verify = verify
    result = asyncio.run(service.search([ref], "unmatched query", top_k=5))
    expected = [e.evidence_id for e in records if e.evidence_id not in reject][:5]
    assert [r["evidence_ref"]["evidence_id"] for r in result["items"]] == expected
    assert checked == [e.evidence_id for e in records[: len(expected) + len(reject)]]
    assert len(checked) == (5 + len(reject) if expected else 20)
    assert all(r["dense_cosine"] is not None for r in result["items"])


def test_top_results_still_use_original_fresh_source_and_page_gate(tmp_path):
    service, ref, records = service_fixture(tmp_path)
    reads, pages = [], []

    async def current(source):
        reads.append(source)
        return records

    async def page_context(document, revision, page):
        pages.append(page)
        if page == 1:
            raise RetrievalError("table_structure_unsupported")

    service.records = current
    service.sources.page_context = page_context
    result = asyncio.run(service.search([ref], "unmatched query", top_k=2))
    assert [r["evidence_ref"]["physical_page"] for r in result["items"]] == [2, 3]
    assert len(reads) == 4  # initial scope plus every attempted quote's original verifier
    assert pages == [1, 2, 3]

    # A changed current record is never admitted from stale dense/index content.
    async def changed(source):
        reads.append(source)
        return records if len(reads) == 1 else []

    reads.clear()
    pages.clear()
    service.records = changed
    assert asyncio.run(service.search([ref], "unmatched query", top_k=2))["items"] == []
    assert pages == []
