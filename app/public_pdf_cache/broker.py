"""Controller's sole cache writer. Ticket authorization is injected by private discovery store."""

from contextlib import closing
import asyncio
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from uuid import uuid4
import pymupdf

from app.company_discovery.contracts import DiscoveryError, canonical
from .download import UnknownShaDownloader, MAX_BYTES


def cover_identity(raw, candidate):
    security = candidate["security_identity"]
    if not security["supported"] or security["exchange"] not in ("SSE", "SZSE"):
        raise DiscoveryError("unsupported_market", 422)
    code = security["security_code"]
    if not re.fullmatch(r"6\d{5}" if security["exchange"] == "SSE" else r"[03]\d{5}", code):
        raise DiscoveryError("needs_manual_review")
    if candidate["kind"] != "annual_fulltext" or candidate["language"] != "zh":
        raise DiscoveryError("unsupported_document_kind", 422)
    try:
        with pymupdf.open(stream=raw, filetype="pdf") as pdf:
            if pdf.is_encrypted or not 1 <= len(pdf) <= 3000:
                raise ValueError()
            text = pdf[0].get_text()
        names = set(re.findall(r"[\u4e00-\u9fffA-Za-z（）()·]{2,80}股份有限公司", text))
        codes = set(re.findall(r"(?:公司代码|证券代码|股票代码)\s*[：:]?\s*(\d{6})", text))
        if (
            len(names) != 1
            or codes != {code}
            or not re.search(str(candidate["report_year"]) + r"\s*年\s*(?:年度报告|年报)", text)
        ):
            raise ValueError()
        return dict(
            official_name=next(iter(names)),
            security_code=code,
            exchange=security["exchange"],
            country="CN",
            identity_status="cover_code_name_year_matches",
        )
    except (ValueError, RuntimeError, IndexError):
        raise DiscoveryError("needs_manual_review") from None


class PublicPdfCacheBroker:
    def __init__(self, control_root: Path, *, downloader=None, max_disk_bytes=256 * 1024 * 1024):
        if max_disk_bytes < MAX_BYTES:
            raise ValueError("Capacity must reserve at least one maximum PDF")
        control_root = Path(control_root)
        if control_root.is_symlink():
            raise ValueError("Symlink root forbidden")
        self.root = control_root.resolve() / "public-pdf-cache"
        if self.root.is_symlink():
            raise ValueError("Symlink cache forbidden")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.objects = self.root / "objects"
        if self.objects.is_symlink():
            raise ValueError("Symlink objects forbidden")
        self.objects.mkdir(exist_ok=True, mode=0o700)
        lock = self.root / "writer.lock"
        if lock.is_symlink() or (lock.exists() and lock.stat().st_nlink != 1):
            raise ValueError("Invalid writer lock")
        self.owner_lock = lock.open("a+b")
        try:
            fcntl.flock(self.owner_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.owner_lock.close()
            raise ValueError("Cache already owned") from None
        self.path = self.root / "public.sqlite"
        if self.path.is_symlink() or (self.path.exists() and self.path.stat().st_nlink != 1):
            self.close()
            raise ValueError("Invalid cache DB")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS entries(version_digest TEXT PRIMARY KEY,sha TEXT NOT NULL,provenance TEXT NOT NULL)"
            )
        self.path.chmod(0o600)
        self.downloader = downloader or UnknownShaDownloader()
        self.max_disk_bytes = max_disk_bytes
        self.lock = asyncio.Lock()
        self.ticket_reader = None

    def close(self):
        self.owner_lock.close()

    def set_ticket_reader(self, reader, guard):
        if self.ticket_reader is not None:
            raise ValueError("Broker already bound")
        self.ticket_reader = reader
        self.guard = guard

    def _file(self, sha):
        if not re.fullmatch(r"[a-f0-9]{64}", sha):
            raise DiscoveryError("cache_integrity_error", 503)
        p = self.objects / (sha + ".pdf")
        if (
            p.is_symlink()
            or not p.is_file()
            or p.stat().st_nlink != 1
            or p.stat().st_size > MAX_BYTES
        ):
            raise DiscoveryError("cache_integrity_error", 503)
        raw = p.read_bytes()
        if hashlib.sha256(raw).hexdigest() != sha:
            raise DiscoveryError("cache_integrity_error", 503)
        return raw

    def _lookup(self, key):
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute(
                "SELECT sha,provenance FROM entries WHERE version_digest=?", (key,)
            ).fetchone()
        if row:
            return self._file(row[0]), row[0], json.loads(row[1])
        return None

    def read_ready(self, ticket_id, identity):
        candidate = self.ticket_reader(ticket_id, identity)
        found = self._lookup(candidate["version_digest"])
        if not found:
            raise DiscoveryError("cache_not_ready")
        raw, sha, provenance = found
        resolved = cover_identity(raw, candidate)
        return dict(
            bytes=raw, sha256=sha, provenance=provenance, resolved_identity=resolved, cache_hit=True
        )

    async def prepare(self, ticket_id, identity):
        self.ticket_reader(ticket_id, identity)
        # One controller-wide flight prevents capacity races; version digest makes repeated imports hits.
        async with self.lock:
            candidate = self.ticket_reader(ticket_id, identity)
            found = self._lookup(candidate["version_digest"])
            if found:
                return self.read_ready(ticket_id, identity)
            used = 0
            for p in self.objects.iterdir():
                if p.is_symlink() or not p.is_file() or p.stat().st_nlink != 1:
                    raise DiscoveryError("cache_integrity_error", 503)
                used += p.stat().st_size
            if used + MAX_BYTES > self.max_disk_bytes:
                raise DiscoveryError("cache_capacity_exceeded", 507)
            raw, sha = await self.downloader.download(candidate["pdf_url"])
            if (
                len(raw) > MAX_BYTES
                or hashlib.sha256(raw).hexdigest() != sha
                or not raw.startswith(b"%PDF-")
            ):
                raise DiscoveryError("download_integrity_error", 503)
            resolved = cover_identity(raw, candidate)
            self.ticket_reader(
                ticket_id, identity
            )  # revoke/lease check after network, before public cache publication
            provenance = {
                k: candidate[k]
                for k in (
                    "provider",
                    "announcement_id",
                    "security_identity",
                    "report_year",
                    "kind",
                    "language",
                    "title_raw",
                    "revision_kind",
                    "published_at_ms",
                    "pdf_url",
                    "version_digest",
                )
            }
            target = self.objects / (sha + ".pdf")
            temporary = self.objects / ("pending-" + str(uuid4()))
            try:
                with self.guard(identity):
                    with temporary.open("xb") as f:
                        f.write(raw)
                        f.flush()
                        os.fsync(f.fileno())
                    temporary.chmod(0o400)
                    if target.exists() or target.is_symlink():
                        self._file(sha)
                    else:
                        os.replace(temporary, target)
                    with closing(sqlite3.connect(self.path)) as db, db:
                        db.execute(
                            "INSERT INTO entries VALUES(?,?,?)",
                            (candidate["version_digest"], sha, canonical(provenance)),
                        )
            finally:
                temporary.unlink(missing_ok=True)
            return dict(
                bytes=raw,
                sha256=sha,
                provenance=provenance,
                resolved_identity=resolved,
                cache_hit=False,
            )
