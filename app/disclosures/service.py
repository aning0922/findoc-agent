"""Verified demo catalogue and generation-local import ledger; no financial acceptance."""

import asyncio
from datetime import UTC, datetime
from contextlib import closing, contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import UUID

from app.disclosures.download import DisclosureError, SafeDownloader
from app.documents.source_models import ReportUploadInput

CATALOG = tuple(json.loads(Path(__file__).with_name("catalog.json").read_text()))


class DisclosureService:
    def __init__(self, *, runtime_root: Path, sources, companies, downloader=None):
        self.root = runtime_root.resolve()
        expected = self.root / "documents.db"
        if (
            sources.documents._repository._database_path.resolve() != expected
            or companies._repository._database_path.resolve() != expected
            or sources.companies is not companies
        ):
            raise ValueError("disclosure_runtime_mismatch")
        self.sources, self.companies = sources, companies
        self.downloader = downloader or SafeDownloader()
        self.path = self.root / "disclosure-imports.db"
        # Main runtime initializes its own root; never create arbitrary missing roots here.
        if not expected.is_file():
            raise ValueError("disclosure_runtime_missing")
        with self._tx() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS imports (operation_id TEXT PRIMARY KEY, "
                "request_hash TEXT NOT NULL,state TEXT NOT NULL,phase TEXT NOT NULL, "
                "result TEXT,error_code TEXT)"
            )
        self.path.chmod(0o600)

    @contextmanager
    def _tx(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            with db:
                yield db

    def search(self, code, report_year=None):
        needle = code.strip()
        rows = [
            dict(r)
            for r in CATALOG
            if needle
            and (needle == r["company_code"] or needle in r["company_name"])
            and (report_year is None or report_year == r["report_year"])
        ]
        return dict(
            schema_version="disclosure-search-v1",
            source_scope="verified_demo_catalog",
            items=rows,
            limitations=[
                "已验证演示目录：两家公司2024/2025年度正文；非全市场实时查询。",
                "发布日期与更正状态未经本目录独立验证，空值不表示没有更正。",
            ],
            fallback="未找到所需资料时，请从官方站获取PDF并使用现有手动上传入口。",
        )

    @staticmethod
    def _uuid(value):
        try:
            if str(UUID(value)) != value:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise DisclosureError("invalid_operation_id", 422) from None

    def operation(self, operation_id):
        self._uuid(operation_id)
        with self._tx() as db:
            row = db.execute(
                "SELECT * FROM imports WHERE operation_id=?", (operation_id,)
            ).fetchone()
        if row is None:
            raise DisclosureError("import_not_found", 404)
        return dict(
            schema_version="disclosure-import-v1",
            operation_id=operation_id,
            state=row["state"],
            phase=row["phase"],
            error_code=row["error_code"],
            result=json.loads(row["result"]) if row["result"] else None,
        )

    async def import_candidate(self, *, operation_id, candidate_id, company_id):
        self._uuid(operation_id)
        digest = hashlib.sha256(
            json.dumps([candidate_id, company_id], separators=(",", ":")).encode()
        ).hexdigest()
        # Recover durable outcomes before new network/source IO. Unknown is never auto-retried.
        with self._tx() as db:
            row = db.execute(
                "SELECT * FROM imports WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if row and row["request_hash"] != digest:
                raise DisclosureError("operation_conflict")
        if row:
            return self.operation(operation_id)
        candidate = next((r for r in CATALOG if r["candidate_id"] == candidate_id), None)
        if candidate is None:
            raise DisclosureError("candidate_not_found", 404)
        company = await asyncio.to_thread(self.companies.get, company_id)
        if (
            company.security_code != candidate["company_code"]
            or company.exchange != "SZSE"
            or company.name != candidate["company_name"]
            or company.country != "CN"
        ):
            raise DisclosureError("candidate_company_mismatch")
        with self._tx() as db:
            existing = db.execute(
                "SELECT * FROM imports WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if existing:
                if existing["request_hash"] != digest:
                    raise DisclosureError("operation_conflict")
            else:
                db.execute(
                    "INSERT INTO imports VALUES (?,?,'unknown','downloading',NULL,NULL)",
                    (operation_id, digest),
                )
        if existing:
            return self.operation(operation_id)
        try:
            content = await self.downloader.download(candidate["official_url"], candidate["sha256"])
        except DisclosureError as exc:
            with self._tx() as db:
                db.execute(
                    "UPDATE imports SET state='failed',error_code=? WHERE operation_id=?",
                    (exc.code, operation_id),
                )
            return self.operation(operation_id)
        with self._tx() as db:
            db.execute("UPDATE imports SET phase='uploading' WHERE operation_id=?", (operation_id,))
        year = candidate["report_year"]
        payload = ReportUploadInput(
            company_id=company_id,
            report_year=year,
            report_type="annual",
            basis="PRC_GAAP",
            period_start=f"{year}-01-01",
            period_end=f"{year}-12-31",
            source_url=candidate["official_url"],
        )
        try:
            result = await self.sources.upload(
                filename=f"{candidate['company_code']}-{year}.pdf", content=content, payload=payload
            )
            result["disclosure_import"] = dict(
                candidate_id=candidate_id,
                official_url=candidate["official_url"],
                sha256=hashlib.sha256(content).hexdigest(),
                bytes=len(content),
                downloaded_at=datetime.now(UTC).isoformat(),
                catalog_checked_at=candidate["checked_at"],
                validation="https_public_address_pinned_sha_match",
            )
            with self._tx() as db:
                db.execute(
                    "UPDATE imports SET state='completed',phase='uploaded',result=? "
                    "WHERE operation_id=?",
                    (json.dumps(result, ensure_ascii=False), operation_id),
                )
        except Exception:
            # Upload may have committed bytes/rows before failing. Never claim safe retry.
            with self._tx() as db:
                db.execute(
                    "UPDATE imports SET error_code='import_outcome_unknown' WHERE operation_id=?",
                    (operation_id,),
                )
        return self.operation(operation_id)
