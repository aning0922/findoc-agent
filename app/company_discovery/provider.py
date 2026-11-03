"""Observed CNInfo public web adapter; no SLA/open API permission implied."""

import asyncio
import time
import re
import httpx

from .contracts import DiscoveryError
from .pacing import RequestPacer

BASE = "https://www.cninfo.com.cn/new"


def pdf_url(locator):
    import re

    if not isinstance(locator, str) or not re.fullmatch(
        r"finalpage/\d{4}-\d{2}-\d{2}/[A-Za-z0-9_-]+\.[Pp][Dd][Ff]", locator
    ):
        raise DiscoveryError("official_pdf_locator_invalid")
    return "https://static.cninfo.com.cn/" + locator


def security(row):
    code, kind = row.get("code"), row.get("type")
    # CNInfo type=shj is returned for BOTH Shanghai and Shenzhen A shares.
    exchange = None
    if row.get("category") == "A股" and isinstance(code, str):
        if re.fullmatch(r"6\d{5}", code):
            exchange = "SSE"
        elif re.fullmatch(r"[03]\d{5}", code):
            exchange = "SZSE"
    supported = (
        exchange is not None and row.get("category") == "A股" and row.get("delisted") == "false"
    )
    return dict(
        provider="cninfo_public_web",
        security_id=f"cninfo:{exchange or kind}:{code}",
        security_code=code,
        exchange=exchange,
        provider_security_type=kind,
        provider_category=row.get("category"),
        provider_org_id=row.get("orgId"),
        display_name=row.get("zwjc"),
        official_name=None,
        pinyin=row.get("pinyin"),
        delisted_raw=row.get("delisted"),
        identity_status="provider_candidate",
        supported=supported,
        match_type="provider_candidate",
    )


class CNInfoProvider:
    def __init__(self, *, transport=None, interval=1.1):
        if interval < 1:
            raise ValueError("Provider interval must be >=1s")
        self.transport, self.interval = transport, interval
        self.pacer = RequestPacer(interval)
        self.observations = []
        self.blocked_until = 0
        self.lock, self.last, self.requests = asyncio.Lock(), 0, 0

    async def _post(self, suffix, form):
        if suffix not in ("/information/topSearch/query", "/hisAnnouncement/query"):
            raise DiscoveryError("provider_endpoint_forbidden")
        async with self.lock:
            if time.monotonic() < self.blocked_until:
                raise DiscoveryError("external_blocked", 503)
            await self.pacer.wait()
            started = time.monotonic()
            self.requests += 1
            async with httpx.AsyncClient(
                trust_env=False, follow_redirects=False, transport=self.transport, timeout=20
            ) as client:
                try:
                    async with client.stream(
                        "POST", BASE + suffix, data=form, headers={"Accept-Encoding": "identity"}
                    ) as r:
                        if r.status_code in (403, 429):
                            self.blocked_until = time.monotonic() + 300
                            raise DiscoveryError("external_blocked", 503)
                        if r.status_code != 200:
                            raise DiscoveryError("source_unavailable", 503)
                        raw = bytearray()
                        async for chunk in r.aiter_bytes():
                            raw.extend(chunk)
                            if len(raw) > 2_000_000:
                                raise DiscoveryError("provider_response_too_large", 503)
                        self.observations.append(
                            dict(
                                url=BASE + suffix,
                                status=r.status_code,
                                bytes=len(raw),
                                elapsed_seconds=time.monotonic() - started,
                            )
                        )
                        return __import__("json").loads(raw)
                except (httpx.HTTPError, ValueError):
                    raise DiscoveryError("source_unavailable", 503) from None

    async def companies(self, query):
        rows = await self._post("/information/topSearch/query", {"keyWord": query, "maxNum": "10"})
        if not isinstance(rows, list):
            raise DiscoveryError("provider_schema_changed", 503)
        result = []
        for row in rows[:10]:
            item = security(row)
            if not all(
                isinstance(item[k], str) and item[k]
                for k in (
                    "security_code",
                    "provider_org_id",
                    "display_name",
                    "provider_security_type",
                )
            ):
                raise DiscoveryError("provider_schema_changed", 503)
            item["match_type"] = (
                "code_exact"
                if query == item["security_code"]
                else "pinyin_exact"
                if query.lower() == str(item["pinyin"]).lower()
                else "provider_name_candidate"
            )
            result.append(item)
        return result

    async def announcements(self, selected, year, kind=None):
        if not selected["supported"]:
            raise DiscoveryError("unsupported_market", 422)
        # Financial year and publication year remain separate; bound search to following year through today.
        rows = await self._post(
            "/hisAnnouncement/query",
            dict(
                pageNum="1",
                pageSize="20",
                column="sse" if selected["exchange"] == "SSE" else "szse",
                tabName="fulltext",
                plate="sh" if selected["exchange"] == "SSE" else "sz",
                stock=selected["security_code"] + "," + selected["provider_org_id"],
                searchkey=str(year) + "年年度报告",
                category="category_ndbg_szsh;",
                seDate=f"{year + 1}-01-01~{__import__('datetime').date.today().isoformat()}",
                sortName="time",
                sortType="desc",
                isHLtitle="false",
            ),
        )
        if not isinstance(rows, dict) or not isinstance(rows.get("announcements"), list):
            raise DiscoveryError("provider_schema_changed", 503)
        items = []
        for row in rows["announcements"][:20]:
            if (
                row.get("secCode") != selected["security_code"]
                or row.get("orgId") != selected["provider_org_id"]
            ):
                raise DiscoveryError("provider_identity_mismatch", 503)
            title = row.get("announcementTitle", "")
            item_kind = "summary" if "摘要" in title else "annual_fulltext"
            language = "en" if "英文" in title else "zh"
            if kind and kind != item_kind:
                continue
            locator = row.get("adjunctUrl")
            url = pdf_url(locator)
            aid = row.get("announcementId")
            if not isinstance(aid, str) or not aid.isdigit():
                raise DiscoveryError("provider_schema_changed", 503)
            items.append(
                dict(
                    provider="cninfo_public_web",
                    announcement_id=aid,
                    security_identity={
                        k: v
                        for k, v in selected.items()
                        if k
                        not in (
                            "candidate_id",
                            "candidate_digest",
                            "version_digest",
                            "checked_at",
                            "expires_at",
                        )
                    },
                    report_year=year,
                    kind=item_kind,
                    language=language,
                    title_raw=title,
                    revision_kind="revised"
                    if any(w in title for w in ("修订", "更正", "更新版"))
                    else None,
                    supersession_status=None,
                    published_at_ms=row.get("announcementTime"),
                    pdf_locator=locator,
                    pdf_url=url,
                    official_page_url=f"{BASE}/disclosure/detail?stockCode={selected['security_code']}&announcementId={aid}",
                    verification_state="official_metadata_unreviewed",
                )
            )
        return items, bool(rows.get("hasMore"))
