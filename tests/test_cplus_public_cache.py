"""Download boundary and cold content hashes; no provider/network in these tests."""

import asyncio
import hashlib
import httpx
import pytest
from app.company_discovery import DiscoveryError
from app.public_pdf_cache.download import UnknownShaDownloader, MAX_BYTES


def test_pinned_unknown_sha_download_and_adversarial_boundaries():
    async def run():
        seen = []

        async def public(host):
            return ["8.8.8.8"]

        def handler(request):
            seen.append(request)
            return httpx.Response(200, content=b"%PDF-synthetic-bytes")

        d = UnknownShaDownloader(resolver=public, transport=httpx.MockTransport(handler))
        raw, sha = await d.download(
            "https://static.cninfo.com.cn/finalpage/2026-03-27/1225038336.PDF"
        )
        assert sha == hashlib.sha256(raw).hexdigest() and seen[0].url.host == "8.8.8.8"
        assert (
            seen[0].headers["host"] == "static.cninfo.com.cn"
            and seen[0].extensions["sni_hostname"] == "static.cninfo.com.cn"
        )
        cases = [
            ("https://evil.test/x.pdf", None, None, "download_url_forbidden"),
            (
                "https://static.cninfo.com.cn/finalpage/2026-03-27/1225038336.PDF",
                ["127.0.0.1"],
                None,
                "download_address_forbidden",
            ),
            (
                "https://static.cninfo.com.cn/finalpage/2026-03-27/1225038336.PDF",
                None,
                httpx.Response(302, headers={"location": "http://127.0.0.1/private"}),
                "download_url_forbidden",
            ),
            (
                "https://static.cninfo.com.cn/finalpage/2026-03-27/1225038336.PDF",
                None,
                httpx.Response(200, headers={"content-length": str(MAX_BYTES + 1)}),
                "download_too_large",
            ),
            (
                "https://static.cninfo.com.cn/finalpage/2026-03-27/1225038336.PDF",
                None,
                httpx.Response(200, content=b"<html>captcha</html>"),
                "download_not_pdf",
            ),
        ]
        for url, addresses, response, error in cases:

            async def resolve(host):
                return addresses or ["8.8.8.8"]

            item = UnknownShaDownloader(
                resolver=resolve, transport=httpx.MockTransport(lambda r: response)
            )
            with pytest.raises(DiscoveryError, match=error):
                await item.download(url)

    asyncio.run(run())
