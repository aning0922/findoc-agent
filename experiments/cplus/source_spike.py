"""Explicit-plan HTTPS spike, max20 requests, >=1 second start spacing; no retries/proxy/auth."""

import hashlib
import json
from pathlib import Path
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit
import httpx

OUT = Path("docs/cplus/evidence/D01")


def run(plan):
    ledger_path = OUT / "requests.json"
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else []
    with httpx.Client(
        trust_env=False,
        follow_redirects=False,
        timeout=25,
        headers={"User-Agent": "FinDoc-research-spike/1.0", "Accept-Encoding": "identity"},
    ) as client:
        for spec in plan:
            if len(ledger) >= 20:
                raise ValueError("20 request cap reached")
            url = spec["url"]
            if urlsplit(url).scheme != "https" or urlsplit(url).hostname not in {
                "www.cninfo.com.cn",
                "static.cninfo.com.cn",
            }:
                raise ValueError("Official HTTPS hosts only")
            if ledger:
                delay = 1.1 - (time.time() - ledger[-1]["started_epoch"])
                if delay > 0:
                    time.sleep(delay)
            start = time.time()
            record = {
                "number": len(ledger) + 1,
                "label": spec["label"],
                "method": spec.get("method", "GET"),
                "url": url,
                "form": spec.get("data"),
                "started_epoch": start,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
            try:
                with client.stream(
                    record["method"], url, data=spec.get("data"), headers=spec.get("headers")
                ) as response:
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw) >= spec.get("max_bytes", 2_000_000):
                            break
                    body = bytes(raw)
                    text = body.decode("utf-8", errors="replace")
                    record.update(
                        status=response.status_code,
                        bytes_read=len(body),
                        sha256=hashlib.sha256(body).hexdigest(),
                        headers={
                            k: response.headers.get(k)
                            for k in ["content-type", "content-length", "location"]
                        },
                        elapsed_seconds=round(time.time() - start, 3),
                    )
                    details = {
                        "snippet": text[:600],
                        "scripts": re.findall(r'<script[^>]+src=["\']([^"\']+)', text),
                        "endpoint_context": re.findall(
                            r".{0,100}(?:url:|url :|column:|plate:|stock:|searchkey:|keyWord:|hisAnnouncement|topSearch|pinyin|拼音|stockList|fulltext|category_ndbg|searchkey|orgId|announcementId).{0,150}",
                            text,
                        )[:300],
                    }
                    if body.startswith(b"%PDF-"):
                        import pymupdf

                        with pymupdf.open(stream=body, filetype="pdf") as pdf:
                            details = {
                                "pdf_magic": True,
                                "pages": len(pdf),
                                "cover_excerpt": pdf[0].get_text()[:500],
                            }
                    try:
                        details["json"] = json.loads(text)
                    except ValueError:
                        pass
                    (OUT / (spec["label"] + ".json")).write_text(
                        json.dumps(details, ensure_ascii=False, indent=2) + "\n"
                    )
            except Exception as exc:
                record.update(
                    status=None,
                    error=type(exc).__name__,
                    elapsed_seconds=round(time.time() - start, 3),
                    bytes_read=0,
                )
            ledger.append(record)
            ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps(record, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    run(json.loads(Path(sys.argv[1]).read_text()))
