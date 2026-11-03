"""UNIT_FAKE: temporary SQLite/synthetic PDF and fake HTTP, no financial acceptance."""

import asyncio
import hashlib
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import pymupdf
import pytest

from app.companies.models import CompanyCreate
from app.disclosures import DisclosureService, create_disclosure_router
from app.disclosures.download import DisclosureError, SafeDownloader
import app.disclosures.service as module
from tests.test_document_sources import Harness


def run(coro):
    return asyncio.run(coro)


async def public(host):
    return ["93.184.216.34"]


def setup(tmp_path, monkeypatch):
    h = Harness(tmp_path)
    company = h.companies.create(
        CompanyCreate(name="珠海格力电器股份有限公司", security_code="000651", exchange="SZSE")
    )
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((40, 80), company.name, fontname="china-s")
        page.insert_text((40, 110), "2025年年度报告", fontname="china-s")
        content = pdf.tobytes()
    original = next(
        r for r in module.CATALOG if r["company_code"] == "000651" and r["report_year"] == 2025
    )
    candidate = {**original, "sha256": hashlib.sha256(content).hexdigest()}
    monkeypatch.setattr(module, "CATALOG", (candidate,))
    calls = []

    def http(request):
        calls.append(request)
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "static.cninfo.com.cn"
        assert request.extensions["sni_hostname"] == "static.cninfo.com.cn"
        return httpx.Response(200, content=content)

    service = DisclosureService(
        runtime_root=tmp_path,
        sources=h.service,
        companies=h.companies,
        downloader=SafeDownloader(resolver=public, transport=httpx.MockTransport(http)),
    )
    return h, company, candidate, service, calls


def test_actual_upload_dedup_replay_and_unknown(tmp_path, monkeypatch):
    h, company, candidate, svc, calls = setup(tmp_path, monkeypatch)
    request = dict(
        operation_id=str(uuid4()),
        candidate_id=candidate["candidate_id"],
        company_id=company.company_id,
    )
    with pytest.raises(DisclosureError, match="candidate_company_mismatch"):
        run(svc.import_candidate(**{**request, "company_id": h.company.company_id}))
    assert not calls
    result = run(svc.import_candidate(**request))
    assert result["state"] == "completed"
    assert result["result"]["metadata"]["report_year"] == 2025
    assert result["result"]["assessment"]["financial_facts"] == "not_verified"
    doc = result["result"]["document_id"]
    assert h.processor.process(doc).status.value == "ready"
    assert run(svc.import_candidate(**request)) == result and len(calls) == 1
    with pytest.raises(DisclosureError, match="operation_conflict"):
        run(svc.import_candidate(**{**request, "candidate_id": "different"}))
    duplicate = run(svc.import_candidate(**{**request, "operation_id": str(uuid4())}))
    assert duplicate["result"]["duplicate"] and duplicate["result"]["document_id"] == doc
    # A possible post-commit failure must never silently re-enter upload on same operation.
    upload = AsyncMock(side_effect=OSError("fake uncertain post-commit failure"))
    monkeypatch.setattr(h.service, "upload", upload)
    unknown = {**request, "operation_id": str(uuid4())}
    assert run(svc.import_candidate(**unknown))["state"] == "unknown"
    assert run(svc.import_candidate(**unknown))["state"] == "unknown"
    assert upload.await_count == 1


def test_downloader_pins_and_rejects_redirect_private_size_sha():
    content = b"%PDF-test"
    sha = hashlib.sha256(content).hexdigest()

    async def execute():
        for ips in (["127.0.0.1"], ["169.254.169.254"], ["::1"], ["93.184.216.34", "10.0.0.1"]):

            async def resolver(host):
                return ips

            downloader = SafeDownloader(
                resolver=resolver,
                transport=httpx.MockTransport(
                    lambda r: (_ for _ in ()).throw(AssertionError("must not connect"))
                ),
            )
            with pytest.raises(DisclosureError, match="download_address_forbidden"):
                await downloader.download("https://static.cninfo.com.cn/a.pdf", sha)
        for response, expected in [
            (
                httpx.Response(302, headers={"location": "https://127.0.0.1/a"}),
                "download_url_forbidden",
            ),
            (httpx.Response(200, content=content), "download_sha_mismatch"),
            (httpx.Response(200, content=b"not pdf"), "download_not_pdf"),
            (httpx.Response(200, headers={"content-length": "999999999"}), "download_too_large"),
        ]:
            downloader = SafeDownloader(
                resolver=public, transport=httpx.MockTransport(lambda r: response)
            )
            with pytest.raises(DisclosureError, match=expected):
                await downloader.download("https://static.cninfo.com.cn/a.pdf", "0" * 64)
        seen = []

        async def by_host(host):
            seen.append(host)
            return ["93.184.216.34"] if len(seen) == 1 else ["10.1.2.3"]

        downloader = SafeDownloader(
            resolver=by_host,
            transport=httpx.MockTransport(
                lambda r: httpx.Response(
                    302, headers={"location": "https://www.midea.com.cn/b.pdf"}
                )
            ),
        )
        with pytest.raises(DisclosureError, match="download_address_forbidden"):
            await downloader.download("https://static.cninfo.com.cn/a.pdf", sha)
        assert seen == ["static.cninfo.com.cn", "www.midea.com.cn"]

        async def slow(host):
            await asyncio.sleep(1)
            return ["93.184.216.34"]

        with pytest.raises(DisclosureError, match="download_failed"):
            await SafeDownloader(resolver=slow, total_timeout=0.01).download(
                "https://static.cninfo.com.cn/a.pdf", sha
            )

    run(execute())


def test_router_catalog_scope_and_operation_queries(tmp_path, monkeypatch):
    h, company, candidate, svc, calls = setup(tmp_path, monkeypatch)
    app = FastAPI()
    app.include_router(create_disclosure_router(svc))
    client = TestClient(app)
    found = client.get("/disclosures/search", params={"code": "格力", "report_year": ""})
    assert found.status_code == 200 and len(found.json()["items"]) == 1
    assert found.json()["source_scope"] == "verified_demo_catalog"
    assert found.json()["items"][0]["is_amendment"] is None
    assert client.get("/disclosures/search?code=unknown").json()["items"] == []
    assert client.get("/disclosures/search?code=格力&report_year=bad").status_code == 422
    assert client.get("/disclosures/search?code=a&code=b").status_code == 422
    request = dict(
        operation_id=str(uuid4()),
        candidate_id=candidate["candidate_id"],
        company_id=company.company_id,
    )
    assert (
        client.post("/disclosures/import", json={**request, "url": "http://127.0.0.1"}).status_code
        == 422
    )
    value = client.post("/disclosures/import", json=request)
    assert value.status_code == 200 and value.headers["cache-control"] == "no-store"
    assert client.get("/disclosures/imports/" + request["operation_id"]).json() == value.json()
    assert client.get("/disclosures/imports/" + str(uuid4())).status_code == 404
