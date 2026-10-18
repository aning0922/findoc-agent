"""All 18 fixed-SHA records through real parser/captured sources/HTTP candidates.

Gold records are loaded only by this acceptance test, after extraction. Embedding
and vector index are controlled; this proves no real RAG/LLM or human acceptance.
"""

import asyncio
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from app.agent.revenue_confirmation import RevenueConfirmationService, RevenueSourceReader
from app.agent.revenue_extraction import RevenueCandidateService
from app.agent.sqlite_financial_facts import SQLiteRevenueConfirmationRepository
from app.api.app import create_app
from app.companies.models import CompanyCreate
from app.documents.models import DocumentStatus
from app.documents.preparation import DocumentTaskPreparer
from tests.test_document_sources import Harness, metadata


@pytest.fixture(scope="module")
def batch(tmp_path_factory):
    h = Harness(tmp_path_factory.mktemp("d7-real"))
    h.original_companies = {
        name: h.companies.create(CompanyCreate(name=name, security_code=code, exchange="SZSE"))
        for name, code in [
            ("美的集团股份有限公司", "000333"),
            ("珠海格力电器股份有限公司", "000651"),
        ]
    }
    h.candidates = RevenueCandidateService(
        preparer=DocumentTaskPreparer(document_service=h.documents),
        retriever=Mock(),
        sources=h.service,
    )
    h.revenue = RevenueConfirmationService(
        source_reader=RevenueSourceReader(
            documents=h.documents, objects=h.objects, candidates=h.candidates
        ),
        repository=SQLiteRevenueConfirmationRepository(h.db),
    )
    h.client = TestClient(
        create_app(
            h.documents,
            source_service=h.service,
            candidate_service=h.candidates,
            revenue_service=h.revenue,
            revenue_workspace_id="demo",
        )
    )
    return h


@pytest.mark.local_data
@pytest.mark.parametrize("report_id", ["midea-2024", "midea-2025", "gree-2024", "gree-2025"])
def test_original_d7_acceptance(batch, report_id, tmp_path):
    h = batch
    manifest = json.loads(Path("product/validation/sources.json").read_text())
    original = next(r for r in manifest if r["id"] == report_id)
    path = Path(original["path"])
    if not path.exists():
        pytest.skip("Fixed-SHA original unavailable")
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == original["sha256"]
    truth = [
        r
        for r in json.loads(Path("product/validation/manual-benchmark.json").read_text())["facts"]
        if r["document_id"] == report_id
    ]
    company = h.original_companies[truth[0]["company"]]
    year = int(report_id.rsplit("-", 1)[1])
    upload = h.upload(raw, {**metadata(company.company_id, year), "source_url": original["url"]})
    assert upload.status_code == 202, upload.text
    h.id = upload.json()["document_id"]
    started = time.perf_counter()
    assert h.processor.process(h.id).status == DocumentStatus.READY
    parse_seconds = time.perf_counter() - started
    original_read = h.objects.read_bytes
    reads = Mock(wraps=original_read)
    h.objects.read_bytes = reads
    timing = {}

    def timed(name, action):
        measurements = []
        counts = []
        for _ in range(3):
            before = reads.call_count
            start = time.perf_counter()
            value = action()
            measurements.append(time.perf_counter() - start)
            counts.append(reads.call_count - before)
        timing[name] = dict(seconds=measurements, pdf_reads_per_request=counts)
        return value

    h.source = timed("source_get", lambda: h.client.get(f"/documents/{h.id}/source").json())
    h.rev = h.source["source_revision"]
    assert (
        h.source["company_id"] == company.company_id
        and h.source["content_sha256"] == original["sha256"]
    )
    file = timed(
        "file_get",
        lambda: h.client.get(f"/documents/{h.id}/file", params=dict(source_revision=h.rev)),
    )
    assert file.content == raw
    timed(
        "evidence_get",
        lambda: h.client.get(
            f"/documents/{h.id}/evidence/{h.source['evidence_ids'][0]}",
            params=dict(source_revision=h.rev),
        ),
    )
    selection = dict(
        company_id=company.company_id,
        source_revision=h.rev,
        metric_keys=list(dict.fromkeys(r["metric"] for r in truth)),
        periods=sorted({r["period"] for r in truth}),
    )
    response = timed(
        "candidates_get",
        lambda: h.client.get(f"/documents/{h.id}/financial-candidates", params=selection),
    )
    assert response.status_code == 200, response.text
    outcomes = response.json()["candidates"]
    proofs = []
    for expected in truth:
        actual = next(
            c
            for c in outcomes
            if c["period"] == expected["period"] and c["metric_key"] == expected["metric"]
        )
        checks = {
            key: actual[key] == expected[gold]
            for key, gold in [
                ("value_cny_yuan", "value_cny_yuan"),
                ("raw_value", "raw_value"),
                ("raw_unit", "raw_unit"),
                ("physical_page", "physical_page"),
                ("currency", "currency"),
                ("scope", "scope"),
                ("accounting_basis", "accounting_basis"),
                ("period_start", "period_start"),
                ("period_end", "period_end"),
            ]
        }
        checks.update(
            status=actual["status"] == "candidate",
            company=actual["company_id"] == company.company_id,
            sha=actual["content_sha256"] == original["sha256"],
            revision=actual["source_revision"] == h.rev,
            statement_page=any(
                e["role"] == "statement" and e["physical_page"] == expected["statement_page"]
                for e in actual["evidence"]
            ),
        )
        # Resolve all supporting IDs through the same trustworthy public source API.
        for e in actual["evidence"] + actual["basis_evidence"]:
            read = h.client.get(
                f"/documents/{h.id}/evidence/{e['evidence_id']}",
                params=dict(source_revision=h.rev, company_id=company.company_id),
            )
            assert read.status_code == 200 and read.json()["physical_page"] == e["physical_page"]
            assert read.json()["source_revision"] == actual["source_revision"]
        proofs.append(
            dict(
                id=expected["id"],
                expected=expected,
                actual=actual,
                checks=checks,
                success=all(checks.values()),
                human_operator_confirmation="pending",
            )
        )
    # GET has no writes; candidate results survive service reconnection identically.
    reopened = RevenueCandidateService(
        preparer=h.candidates._preparer, retriever=Mock(), sources=h.service
    )
    assert (
        asyncio.run(
            reopened.collect_metrics(
                document_id=h.id,
                company_id=company.company_id,
                source_revision=h.rev,
                metric_keys=tuple(selection["metric_keys"]),
                periods=tuple(selection["periods"]),
            )
        )
        == response.json()
    )
    if len(selection["periods"]) == 2:
        review = h.client.post("/revenue-research/reviews", json=dict(document_id=h.id))
        assert review.status_code == 200, review.text
        canceled = h.client.post(
            "/revenue-research/confirmations",
            json=dict(document_id=h.id, snapshot_id=review.json()["snapshot_id"], accepted=False),
        )
        assert canceled.status_code == 409
        with closing(sqlite3.connect(h.db)) as c:
            assert c.execute("SELECT count(*) FROM revenue_confirmations").fetchone()[0] == 0
    h.candidates._retriever.retrieve.assert_not_called()
    h.objects.read_bytes = original_read
    output = dict(
        report_id=report_id,
        source=h.source,
        parse_and_capture_seconds=parse_seconds,
        performance=timing,
        results=proofs,
        database=str(h.db),
    )
    (tmp_path / "d7-report-proof.json").write_text(json.dumps(output, ensure_ascii=False, indent=2))
    assert all(p["success"] for p in proofs), [
        (p["id"], p["checks"], p["actual"]["failure_reason"]) for p in proofs
    ]
