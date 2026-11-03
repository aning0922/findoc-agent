"""Bounded HTTPS download. Pin a validated public DNS address for each TLS hop."""

import asyncio
import hashlib
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import httpx

ALLOWED_HOSTS = frozenset({"www.midea.com.cn", "static.cninfo.com.cn", "disc.static.szse.cn"})
MAX_BYTES = 20 * 1024 * 1024


class DisclosureError(Exception):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


async def resolve_public(host):
    answers = await asyncio.to_thread(socket.getaddrinfo, host, 443, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(a[4][0] for a in answers))


class SafeDownloader:
    def __init__(
        self,
        *,
        resolver=resolve_public,
        transport=None,
        max_bytes=MAX_BYTES,
        total_timeout=60,
        max_redirects=3,
    ):
        if not 0 < max_bytes <= MAX_BYTES or not 0 < total_timeout <= 120:
            raise ValueError("invalid_download_limits")
        self.resolver, self.transport = resolver, transport
        self.max_bytes, self.total_timeout, self.max_redirects = (
            max_bytes,
            total_timeout,
            max_redirects,
        )

    async def download(self, url, expected_sha):
        try:
            async with asyncio.timeout(self.total_timeout):
                async with httpx.AsyncClient(
                    trust_env=False, follow_redirects=False, transport=self.transport, timeout=20
                ) as client:
                    for hop in range(self.max_redirects + 1):
                        parts = urlsplit(url)
                        host = parts.hostname
                        if (
                            parts.scheme != "https"
                            or host not in ALLOWED_HOSTS
                            or parts.username is not None
                            or parts.password is not None
                            or parts.port not in (None, 443)
                            or parts.fragment
                        ):
                            raise DisclosureError("download_url_forbidden")
                        addresses = await self.resolver(host)
                        if not addresses or any(
                            not ipaddress.ip_address(a).is_global for a in addresses
                        ):
                            raise DisclosureError("download_address_forbidden")
                        # Connect to the exact checked IP, preserve original Host and TLS hostname.
                        pinned = httpx.URL(url).copy_with(host=addresses[0])
                        async with client.stream(
                            "GET",
                            pinned,
                            headers={"Host": host, "Accept-Encoding": "identity"},
                            extensions={"sni_hostname": host},
                        ) as response:
                            if response.status_code in (301, 302, 303, 307, 308):
                                if hop == self.max_redirects or not response.headers.get(
                                    "location"
                                ):
                                    raise DisclosureError("download_redirect_limit")
                                url = urljoin(url, response.headers["location"])
                                continue
                            if response.status_code != 200:
                                raise DisclosureError("download_http_failed", 502)
                            if (
                                response.headers.get("content-encoding", "identity").lower()
                                != "identity"
                            ):
                                raise DisclosureError("download_encoding_forbidden")
                            length = response.headers.get("content-length")
                            if length and (not length.isdigit() or int(length) > self.max_bytes):
                                raise DisclosureError("download_too_large", 413)
                            content = bytearray()
                            async for chunk in response.aiter_bytes():
                                content.extend(chunk)
                                if len(content) > self.max_bytes:
                                    raise DisclosureError("download_too_large", 413)
                            raw = bytes(content)
                            if not raw.startswith(b"%PDF-"):
                                raise DisclosureError("download_not_pdf", 415)
                            if hashlib.sha256(raw).hexdigest() != expected_sha:
                                raise DisclosureError("download_sha_mismatch")
                            return raw
        except DisclosureError:
            raise
        except (httpx.HTTPError, OSError, ValueError, TimeoutError) as exc:
            raise DisclosureError("download_failed", 502) from exc
        raise DisclosureError("download_redirect_limit")
