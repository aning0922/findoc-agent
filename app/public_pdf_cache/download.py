"""Unknown-SHA official PDF download: public DNS pin + TLS SNI on every hop."""

import asyncio
import hashlib
import ipaddress
from urllib.parse import urlsplit, urljoin
import httpx
from app.disclosures.download import resolve_public
from app.company_discovery.contracts import DiscoveryError
from app.company_discovery.provider import pdf_url
from app.company_discovery.pacing import RequestPacer

MAX_BYTES = 20 * 1024 * 1024


def validate_url(url):
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.hostname != "static.cninfo.com.cn"
        or parts.port not in (None, 443)
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
    ):
        raise DiscoveryError("download_url_forbidden")
    if pdf_url(parts.path.lstrip("/")) != url:
        raise DiscoveryError("download_url_forbidden")


class UnknownShaDownloader:
    def __init__(self, *, resolver=resolve_public, transport=None):
        self.resolver, self.transport = resolver, transport
        self.requests = 0
        self.lock = asyncio.Lock()
        self.last = 0
        self.pacer = RequestPacer()
        self.observations = []

    async def download(self, url):
        import time

        try:
            async with asyncio.timeout(60):
                async with (
                    self.lock,
                    httpx.AsyncClient(
                        trust_env=False,
                        follow_redirects=False,
                        transport=self.transport,
                        timeout=20,
                    ) as client,
                ):
                    for hop in range(4):
                        validate_url(url)
                        host = urlsplit(url).hostname
                        addresses = await self.resolver(host)
                        if not addresses or any(
                            not ipaddress.ip_address(a).is_global for a in addresses
                        ):
                            raise DiscoveryError("download_address_forbidden")
                        await self.pacer.wait()
                        started = time.monotonic()
                        self.requests += 1
                        pinned = httpx.URL(url).copy_with(host=addresses[0])
                        async with client.stream(
                            "GET",
                            pinned,
                            headers={"Host": host, "Accept-Encoding": "identity"},
                            extensions={"sni_hostname": host},
                        ) as r:
                            if r.status_code in (301, 302, 303, 307, 308):
                                if hop == 3 or not r.headers.get("location"):
                                    raise DiscoveryError("download_redirect_limit")
                                url = urljoin(url, r.headers["location"])
                                continue
                            if r.status_code in (403, 429):
                                raise DiscoveryError("external_blocked", 503)
                            if (
                                r.status_code != 200
                                or r.headers.get("content-encoding", "identity") != "identity"
                            ):
                                raise DiscoveryError("download_http_failed", 503)
                            length = r.headers.get("content-length")
                            if length and (not length.isdigit() or int(length) > MAX_BYTES):
                                raise DiscoveryError("download_too_large", 413)
                            raw = bytearray()
                            async for chunk in r.aiter_bytes():
                                raw.extend(chunk)
                                if len(raw) > MAX_BYTES:
                                    raise DiscoveryError("download_too_large", 413)
                            raw = bytes(raw)
                            if length and len(raw) != int(length):
                                raise DiscoveryError("download_incomplete")
                            if not raw.startswith(b"%PDF-"):
                                raise DiscoveryError("download_not_pdf", 415)
                            self.observations.append(
                                dict(
                                    url=url,
                                    status=r.status_code,
                                    bytes=len(raw),
                                    sha256=hashlib.sha256(raw).hexdigest(),
                                    elapsed_seconds=time.monotonic() - started,
                                )
                            )
                            return raw, hashlib.sha256(raw).hexdigest()
        except (httpx.HTTPError, OSError, ValueError, TimeoutError):
            raise DiscoveryError("download_failed", 503) from None
        raise DiscoveryError("download_redirect_limit")
