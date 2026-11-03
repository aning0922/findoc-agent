"""Controller fake boundary checks; no real provider, models or financial approvals."""

import asyncio
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import pymupdf
import pytest

from app.company_discovery import (
    CNInfoProvider,
    DiscoveryError,
    DiscoveryService,
    TrustedImportIdentity,
    create_discovery_router,
)
from app.public_pdf_cache import PublicPdfCacheBroker


def oid():
    return str(uuid4())


def pdf(code="600690"):
    with pymupdf.open() as doc:
        page = doc.new_page()
        for i, text in enumerate(["海尔智家股份有限公司", f"公司代码：{code}", "2025 年年度报告"]):
            page.insert_text((40, 60 + i * 30), text, fontname="china-s")
        return doc.tobytes()


class Download:
    def __init__(self):
        self.calls = 0

    async def download(self, url):
        self.calls += 1
        raw = pdf()
        return raw, hashlib.sha256(raw).hexdigest()


def setup(root, *, binder=None, download=None):
    state = {"generation": 1, "publications": 0, "bound": []}

    @contextmanager
    def fence():
        yield
        state["publications"] += 1

    identity = TrustedImportIdentity(1, "instance-one", "demo-principal", time.time() + 600, fence)

    def validator(i):
        if i.generation != state["generation"]:
            raise DiscoveryError("generation_changed", 401)

    async def bind(i, raw, resolved, announcement, *, on_phase):
        with i.guard(validator):
            assert raw.startswith(b"%PDF-")
            assert resolved["official_name"] == "海尔智家股份有限公司"
        await on_phase("company_created", created_company_id="company-one")
        await on_phase("uploading")
        state["bound"].append(i.generation)
        return dict(
            document_id="document-one",
            company_id=resolved["company_id"] or "company-one",
            status="queued",
        )

    def handler(request):
        if request.url.path.endswith("topSearch/query"):
            return httpx.Response(
                200,
                json=[
                    dict(
                        code="600690",
                        pinyin="hezj",
                        sjstsBond="false",
                        category="A股",
                        type="shj",
                        delisted="false",
                        orgId="gssh0600690",
                        zwjc="海尔智家",
                    ),
                    dict(
                        code="06690",
                        pinyin="hezj",
                        sjstsBond="false",
                        category="港股",
                        type="hke",
                        delisted="false",
                        orgId="gssh0600690",
                        zwjc="海尔智家",
                    ),
                ],
            )
        return httpx.Response(
            200,
            json=json.loads(Path("docs/cplus/evidence/D01/haier-annual.json").read_text())["json"],
        )

    from app.company_discovery.provider import security

    assert (
        security(dict(code="000333", type="shj", category="A股", delisted="false"))["exchange"]
        == "SZSE"
    )
    assert (
        security(dict(code="600690", type="shj", category="A股", delisted="false"))["exchange"]
        == "SSE"
    )
    assert (
        security(dict(code="06690", type="hke", category="港股", delisted="false"))["supported"]
        is False
    )
    provider = CNInfoProvider(transport=httpx.MockTransport(handler))
    cache = PublicPdfCacheBroker(root, downloader=download or Download())
    service = DiscoveryService(root, provider, cache, binder or bind, validator)
    app = FastAPI()
    app.include_router(create_discovery_router(service, lambda request: identity))
    return service, cache, identity, state, TestClient(app)


async def candidate(service, identity, query="hezj"):
    companies = await service.post_search(
        dict(operation_id=oid(), mode="companies", query=query), identity
    )
    result = await service.post_search(
        dict(
            operation_id=oid(),
            mode="announcements",
            security_id=companies["items"][0]["security_id"],
            report_year=2025,
        ),
        identity,
    )
    return companies, next(
        c for c in result["items"] if c["kind"] == "annual_fulltext" and c["language"] == "zh"
    )


def test_search_snapshot_router_owner_and_import_cache_across_generation(tmp_path):
    async def run():
        service, cache, identity, state, client = setup(tmp_path)
        try:
            companies, c = await candidate(service, identity)
            assert len(companies["items"]) == 2 and not companies["items"][1]["supported"]
            count = service.provider.requests
            path = "/cplus/discovery/searches/" + companies["operation_id"]
            assert client.get(path).json() == companies and service.provider.requests == count
            body = dict(
                operation_id=oid(),
                candidate_id=c["candidate_id"],
                candidate_digest=c["candidate_digest"],
                create_company=True,
                confirmed=True,
            )
            first = await service.post_import(body, identity)
            assert (
                first["state"] == "completed"
                and first["document_state"] == "queued"
                and first["created_company_id"] == "company-one"
            )
            assert await service.post_import(body, identity) == first
            with pytest.raises(DiscoveryError, match="operation_conflict"):
                await service.post_import(
                    {**body, "company_id": "different", "create_company": False}, identity
                )
            assert cache.downloader.calls == 1
            assert (
                client.post(
                    "/cplus/discovery/imports", json={**body, "url": "https://evil.test/a.pdf"}
                ).status_code
                == 422
            )
            assert (
                client.post("/cplus/discovery/imports", json={**body, "confirmed": 1}).status_code
                == 422
            )
            state["generation"] = 2
            with pytest.raises(DiscoveryError, match="generation_changed"):
                await service.post_import(body, identity)
            second_identity = TrustedImportIdentity(
                2, "instance-two", identity.principal, time.time() + 600, identity.fence
            )
            with pytest.raises(DiscoveryError, match="ticket_expired_or_missing"):
                cache.read_ready(first["ticket_id"], second_identity)
            _, c2 = await candidate(service, second_identity)
            second = await service.post_import(
                {
                    **body,
                    "operation_id": oid(),
                    "candidate_id": c2["candidate_id"],
                    "candidate_digest": c2["candidate_digest"],
                },
                second_identity,
            )
            assert second["cache_hit"] and cache.downloader.calls == 1 and state["bound"] == [1, 2]
            assert all(p.stat().st_nlink == 1 for p in cache.objects.iterdir())
            public = (cache.path).read_bytes()
            assert (
                b"demo-principal" not in public
                and b"instance-one" not in public
                and b"company-one" not in public
            )
        finally:
            cache.close()

    asyncio.run(run())


def test_unknown_binding_phase_never_replays_and_lease_revokes_download(tmp_path):
    async def run():
        calls = []

        async def broken(i, raw, resolved, announcement, *, on_phase):
            calls.append(1)
            await on_phase("company_created", created_company_id="created-before-disconnect")
            raise TimeoutError()

        service, cache, identity, state, _ = setup(tmp_path / "broken", binder=broken)
        try:
            _, c = await candidate(service, identity)
            body = dict(
                operation_id=oid(),
                candidate_id=c["candidate_id"],
                candidate_digest=c["candidate_digest"],
                create_company=True,
                confirmed=True,
            )
            with pytest.raises(TimeoutError):
                await service.post_import(body, identity)
            recovered = await service.post_import(body, identity)
            assert (
                recovered["state"] == "unknown"
                and recovered["created_company_id"] == "created-before-disconnect"
                and calls == [1]
            )
        finally:
            cache.close()
        service, cache, identity, state, _ = setup(tmp_path / "revoked")
        original = cache.downloader.download

        async def revoked(url):
            raw = await original(url)
            state["generation"] = 2
            return raw

        cache.downloader.download = revoked
        try:
            _, c = await candidate(service, identity)
            body = dict(
                operation_id=oid(),
                candidate_id=c["candidate_id"],
                candidate_digest=c["candidate_digest"],
                create_company=True,
                confirmed=True,
            )
            with pytest.raises(DiscoveryError, match="generation_changed"):
                await service.post_import(body, identity)
            assert state["bound"] == [] and list(cache.objects.iterdir()) == []
        finally:
            cache.close()

        class WrongCover:
            async def download(self, url):
                raw = pdf("000333")
                return raw, hashlib.sha256(raw).hexdigest()

        service, cache, identity, state, _ = setup(tmp_path / "wrong-cover", download=WrongCover())
        try:
            _, c = await candidate(service, identity)
            receipt = await service.post_import(
                dict(
                    operation_id=oid(),
                    candidate_id=c["candidate_id"],
                    candidate_digest=c["candidate_digest"],
                    create_company=True,
                    confirmed=True,
                ),
                identity,
            )
            assert receipt["state"] == "failed" and receipt["error_code"] == "needs_manual_review"
            assert state["bound"] == [] and list(cache.objects.iterdir()) == []
        finally:
            cache.close()

    asyncio.run(run())


def test_same_announcement_across_code_pinyin_and_name_reuses_public_bytes(tmp_path):
    from app.company_discovery.contracts import digest

    async def run():
        service, cache, identity, state, _ = setup(tmp_path)
        identity = TrustedImportIdentity(
            1, identity.instance_id, identity.principal, time.time() + 3600, identity.fence
        )
        snapshots = []
        try:
            for query, match in (
                ("600690", "code_exact"),
                ("hezj", "pinyin_exact"),
                ("海尔智家", "provider_name_candidate"),
            ):
                _, c = await candidate(service, identity, query)
                assert c["security_identity"]["match_type"] == match
                assert c["candidate_digest"] == digest(
                    {k: v for k, v in c.items() if k != "candidate_digest"}
                )
                body = dict(
                    operation_id=oid(),
                    candidate_id=c["candidate_id"],
                    candidate_digest=c["candidate_digest"],
                    create_company=True,
                    confirmed=True,
                )
                bad = await service.post_import(
                    {**body, "operation_id": oid(), "candidate_digest": "0" * 64}, identity
                )
                assert bad["error_code"] == "candidate_digest_mismatch"
                result = await service.post_import(body, identity)
                assert result["state"] == "completed"
                assert result["cache_hit"] is bool(snapshots)
                snapshots.append(c)
            assert len({c["version_digest"] for c in snapshots}) == 1
            assert len({c["candidate_digest"] for c in snapshots}) == 3
            assert cache.downloader.calls == 1
            # Each authorized private binding still runs; only public PDF bytes are reused.
            assert state["bound"] == [1, 1, 1]
        finally:
            cache.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "field,value",
    [
        ("announcement_id", "1225038337"),
        ("pdf_locator", "finalpage/2026-03-28/1225038337.PDF"),
        ("pdf_url", "https://static.cninfo.com.cn/finalpage/2026-03-28/1225038337.PDF"),
        ("report_year", 2024),
        ("language", "en"),
        ("kind", "summary"),
        ("title_raw", "2025年年度报告（修订版）"),
        ("revision_kind", "revised"),
        ("published_at_ms", 1774656000000),
        ("supersession_status", "superseded"),
        ("security_code", "600691"),
        ("exchange", "SZSE"),
        ("provider_org_id", "another-org"),
        ("supported", False),
    ],
)
def test_public_version_preserves_announcement_and_security_changes(field, value):
    from copy import deepcopy
    from app.company_discovery.contracts import announcement_version_digest, digest

    raw = dict(
        provider="cninfo_public_web",
        announcement_id="1225038336",
        report_year=2025,
        language="zh",
        kind="annual_fulltext",
        title_raw="2025年年度报告",
        revision_kind=None,
        published_at_ms=1774569600000,
        supersession_status=None,
        pdf_locator="finalpage/2026-03-27/1225038336.PDF",
        pdf_url="https://static.cninfo.com.cn/finalpage/2026-03-27/1225038336.PDF",
        security_identity=dict(
            security_code="600690",
            exchange="SSE",
            provider_org_id="gssh0600690",
            supported=True,
            match_type="code_exact",
            pinyin="hezj",
        ),
    )
    matched = deepcopy(raw)
    matched["security_identity"].update(match_type="provider_name_candidate", pinyin="alias")
    assert announcement_version_digest(raw) == announcement_version_digest(matched)
    assert digest(raw) != digest(matched)
    changed = deepcopy(raw)
    target = changed["security_identity"] if field in raw["security_identity"] else changed
    target[field] = value
    assert announcement_version_digest(raw) != announcement_version_digest(changed)
