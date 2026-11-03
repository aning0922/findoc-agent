"""Independent, append-only OCR artifacts. Neither legacy evidence nor financial facts."""

import asyncio
from contextlib import closing, contextmanager
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from uuid import UUID, uuid4

import pymupdf

from app.documents.source_repository import revision_id


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(value).hexdigest()


class ParseError(Exception):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


class ParseV2Service:
    def __init__(
        self, *, runtime_root: Path, documents, sources, engine, max_pages=50, max_seconds=180
    ):
        self.root = runtime_root.resolve()
        if (
            documents is not sources.documents
            or documents._repository._database_path.resolve() != self.root / "documents.db"
        ):
            raise ValueError("parse_runtime_mismatch")
        if (
            not (self.root / "documents.db").is_file()
            or not 1 <= max_pages <= 300
            or not 1 <= max_seconds <= 300
        ):
            raise ValueError("parse_configuration_invalid")
        self.documents, self.sources, self.engine = documents, sources, engine
        self.max_pages, self.max_seconds = max_pages, max_seconds
        self.path = self.root / "parse-v2.db"
        self.lock = asyncio.Lock()
        with self.tx() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, document_id TEXT NOT NULL, request_hash TEXT NOT NULL, state TEXT NOT NULL, artifact_id TEXT)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS artifacts (id TEXT PRIMARY KEY, document_id TEXT NOT NULL, payload TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TRIGGER IF NOT EXISTS artifact_no_update BEFORE UPDATE ON artifacts BEGIN SELECT RAISE(ABORT,'immutable artifact'); END"
            )
            db.execute(
                "CREATE TRIGGER IF NOT EXISTS artifact_no_delete BEFORE DELETE ON artifacts BEGIN SELECT RAISE(ABORT,'immutable artifact'); END"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS active (document_id TEXT PRIMARY KEY, artifact_id TEXT NOT NULL)"
            )
            db.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS page_index USING fts5(artifact_id UNINDEXED, document_id UNINDEXED, page UNINDEXED, text, tokenize='trigram')"
            )
        self.path.chmod(0o600)

    @contextmanager
    def tx(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            with db:
                yield db

    async def snapshot(self, document_id):
        record = await self.documents.get_document(document_id)
        raw = await asyncio.to_thread(self.sources.objects.read_bytes, record.object_key)
        if digest(raw) != record.content_sha256:
            raise ParseError("source_changed")
        metadata = await asyncio.to_thread(self.sources.companies.metadata, document_id)
        identity = dict(
            document_id=document_id,
            company_id=metadata.company_id,
            report_year=metadata.report_year,
            report_type=metadata.report_type,
            content_sha256=record.content_sha256,
            source_revision=revision_id(record, self.sources.parser_version),
            attempt=record.attempt,
            parser_version=self.sources.parser_version,
            metadata_sha256=digest(canonical(metadata.model_dump(mode="json")).encode()),
        )
        return identity, raw

    @staticmethod
    def validate_uuid(value):
        try:
            if str(UUID(value)) != value:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise ParseError("invalid_operation_id", 422) from None

    def operation(self, document_id, operation_id):
        self.validate_uuid(operation_id)
        with self.tx() as db:
            row = db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
            if row is None:
                raise ParseError("operation_not_found", 404)
            artifact = (
                db.execute(
                    "SELECT document_id FROM artifacts WHERE id=?", (row["artifact_id"],)
                ).fetchone()
                if row["artifact_id"]
                else None
            )
        # Document is also bound into the digest; include it even while operation is unknown.
        if row["document_id"] != document_id or (
            artifact and artifact["document_id"] != document_id
        ):
            raise ParseError("operation_not_found", 404)
        return dict(operation_id=operation_id, state=row["state"], artifact_id=row["artifact_id"])

    async def retry(self, document_id, operation_id, expected_source_revision):
        self.validate_uuid(operation_id)
        request_hash = digest(canonical([document_id, expected_source_revision]).encode())
        with self.tx() as db:
            prior = db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
            if prior:
                if prior["request_hash"] != request_hash:
                    raise ParseError("operation_conflict")
                return dict(
                    operation_id=operation_id,
                    state=prior["state"],
                    artifact_id=prior["artifact_id"],
                )
        identity, raw = await self.snapshot(document_id)
        if identity["source_revision"] != expected_source_revision:
            raise ParseError("source_changed")
        if self.lock.locked():
            raise ParseError("parse_busy", 423)
        with self.tx() as db:
            prior = db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
            if prior:
                if prior["request_hash"] != request_hash:
                    raise ParseError("operation_conflict")
                return dict(
                    operation_id=operation_id,
                    state=prior["state"],
                    artifact_id=prior["artifact_id"],
                )
            db.execute(
                "INSERT INTO operations VALUES (?,?,?,'unknown',NULL)",
                (operation_id, document_id, request_hash),
            )
        async with self.lock:
            worker = asyncio.create_task(asyncio.to_thread(self.parse, identity, raw))
            try:
                artifact = await asyncio.shield(worker)
            except asyncio.CancelledError:
                # Keep the single-worker lock until the underlying thread exits.
                await worker
                raise
            try:
                now, _ = await self.snapshot(document_id)
                if now != identity:
                    raise ParseError("source_changed")
            except Exception:
                artifact["state"] = "failed"
                artifact["error_code"] = "source_changed"
            artifact["output_sha256"] = digest(canonical(artifact).encode())
            with self.tx() as db:
                db.execute(
                    "INSERT INTO artifacts VALUES (?,?,?)",
                    (artifact["artifact_id"], document_id, canonical(artifact)),
                )
                for page in artifact["pages"]:
                    if (
                        artifact["error_code"] != "source_changed"
                        and page["status"] == "completed"
                        and page["text"]
                    ):
                        db.execute(
                            "INSERT INTO page_index VALUES (?,?,?,?)",
                            (
                                artifact["artifact_id"],
                                document_id,
                                page["physical_page"],
                                page["text"],
                            ),
                        )
                if artifact["state"] == "completed":
                    db.execute(
                        "INSERT INTO active VALUES (?,?) ON CONFLICT(document_id) DO UPDATE SET artifact_id=excluded.artifact_id",
                        (document_id, artifact["artifact_id"]),
                    )
                db.execute(
                    "UPDATE operations SET state=?, artifact_id=? WHERE id=?",
                    (artifact["state"], artifact["artifact_id"], operation_id),
                )
        return dict(
            operation_id=operation_id, state=artifact["state"], artifact_id=artifact["artifact_id"]
        )

    def parse(self, identity, raw):
        config = dict(
            dpi=180,
            max_pages=self.max_pages,
            max_seconds=self.max_seconds,
            adapter_version=self.engine.adapter_version,
            engine_name=self.engine.name,
            engine_timeout_seconds=getattr(self.engine, "timeout_seconds", None),
            engine_script_sha256=digest(self.engine.script.read_bytes())
            if hasattr(self.engine, "script")
            else None,
        )
        result = dict(
            schema_version="parse-artifact-v2",
            artifact_id=str(uuid4()),
            **identity,
            engine={"name": self.engine.name, "version": "unknown"},
            adapter_version=self.engine.adapter_version,
            config_hash=digest(canonical(config).encode()),
            model_revision="unknown",
            state="failed",
            pages_total=0,
            ocr_pages=0,
            created_at=datetime.now(UTC).isoformat(),
            pages=[],
            error_code=None,
            identity_assessment={
                "document_id": identity["document_id"],
                "pdf_sha256": identity["content_sha256"],
                "artifact_id": None,
                "company_id": identity["company_id"],
                "report_year": identity["report_year"],
                "report_type": identity["report_type"],
                "method": "unverified",
                "status": "manual_check",
                "evidence_refs": [],
                "review_receipt_id": None,
                "financial_facts": "not_verified",
            },
            legacy_source_verified=False,
            limitations=[
                "OCR 转录未人工核对；不能用于确认财务事实。",
                "来源封面身份沿用旧准入，OCR 不自动放行。",
            ],
        )
        result["identity_assessment"]["artifact_id"] = result["artifact_id"]
        started = time.monotonic()
        try:
            with pymupdf.open(stream=raw, filetype="pdf") as pdf:
                result["pages_total"] = pdf.page_count
                for i in range(min(pdf.page_count, self.max_pages)):
                    if time.monotonic() - started >= self.max_seconds:
                        result["error_code"] = "parse_deadline_exceeded"
                        break
                    page = pdf[i]
                    text = page.get_text().strip()
                    p = dict(
                        physical_page=i + 1,
                        method="fast",
                        status="completed",
                        text=text,
                        tables=[],
                        warnings=[],
                    )
                    if len(text) < 20:
                        p["method"] = "ocr"
                        result["ocr_pages"] += 1
                        try:
                            if page.rect.width * 2.5 * page.rect.height * 2.5 > 20_000_000:
                                raise ValueError("page_too_large")
                            pix = page.get_pixmap(matrix=pymupdf.Matrix(2.5, 2.5), alpha=False)
                            if pix.width * pix.height > 20_000_000:
                                raise ValueError("page_too_large")
                            output = self.engine.recognize(pix.tobytes("png"))
                            p["text"] = "\n".join(line["text"] for line in output["lines"])
                            p["lines"] = output["lines"]
                            p["warnings"].append("ocr_transcription_unreviewed")
                            p["tables"] = [
                                dict(
                                    table_id=f"page-{i + 1}-candidate",
                                    quality="needs_review",
                                    cells=[],
                                    warning="表格结构未核对；请对照原图。",
                                )
                            ]
                            result["engine"]["version"] = str(
                                output.get("request_revision", "unknown")
                            )
                            result["engine"]["os_version"] = output.get("os_version", "unknown")
                            if not p["text"]:
                                raise ValueError("ocr_empty")
                        except Exception:
                            p.update(status="failed", text="", lines=[])
                            p["warnings"].append("ocr_failed")
                    result["pages"].append(p)
            complete = len(result["pages"]) == result["pages_total"] and all(
                p["status"] == "completed" for p in result["pages"]
            )
            succeeded = any(p["status"] == "completed" for p in result["pages"])
            result["state"] = "completed" if complete else "partial" if succeeded else "failed"
            if result["state"] != "completed" and not result["error_code"]:
                result["error_code"] = "pages_incomplete"
        except Exception:
            result["error_code"] = "parse_failed"
        return result

    async def quality(self, document_id, artifact_id=None):
        with self.tx() as db:
            if artifact_id is None:
                row = db.execute(
                    "SELECT artifact_id FROM active WHERE document_id=?", (document_id,)
                ).fetchone()
                if row is None:
                    raise ParseError("artifact_not_found", 404)
                artifact_id = row["artifact_id"]
            row = db.execute(
                "SELECT payload FROM artifacts WHERE id=? AND document_id=?",
                (artifact_id, document_id),
            ).fetchone()
        if row is None:
            raise ParseError("artifact_not_found", 404)
        value = json.loads(row["payload"])
        output_sha = value.pop("output_sha256", None)
        if output_sha != digest(canonical(value).encode()):
            raise ParseError("artifact_integrity_error", 503)
        value["output_sha256"] = output_sha
        try:
            current, _ = await self.snapshot(document_id)
            value["source_status"] = (
                "current" if all(current[k] == value[k] for k in current) else "stale"
            )
        except Exception:
            value["source_status"] = "stale"
        return value

    async def image(self, document_id, artifact_id, page):
        artifact = await self.quality(document_id, artifact_id)
        if artifact["source_status"] != "current":
            raise ParseError("source_changed")
        identity, raw = await self.snapshot(document_id)
        if any(identity[k] != artifact[k] for k in identity):
            raise ParseError("source_changed")
        if page < 1 or page > artifact["pages_total"]:
            raise ParseError("page_not_found", 404)

        def render():
            with pymupdf.open(stream=raw, filetype="pdf") as pdf:
                target = pdf[page - 1]
                if target.rect.width * 1.5 * target.rect.height * 1.5 > 20_000_000:
                    raise ParseError("page_too_large", 413)
                pix = target.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
                if pix.width * pix.height > 20_000_000:
                    raise ParseError("page_too_large", 413)
                return pix.tobytes("png")

        image = await asyncio.to_thread(render)
        after, _ = await self.snapshot(document_id)
        if after != identity:
            raise ParseError("source_changed")
        return image

    async def file(self, document_id, artifact_id):
        artifact = await self.quality(document_id, artifact_id)
        identity, raw = await self.snapshot(document_id)
        if artifact["source_status"] != "current" or any(
            identity[k] != artifact[k] for k in identity
        ):
            raise ParseError("source_changed")
        return raw

    async def search(self, document_id, artifact_id, query):
        artifact = await self.quality(document_id, artifact_id)
        if artifact["source_status"] != "current":
            raise ParseError("source_changed")
        if artifact["state"] == "failed":
            raise ParseError("artifact_unavailable")
        if not 3 <= len(query.strip()) <= 200:
            raise ParseError("query_length_invalid", 422)
        match = '"' + query.strip().replace('"', '""') + '"'
        with self.tx() as db:
            rows = db.execute(
                "SELECT page,text FROM page_index WHERE page_index MATCH ? AND artifact_id=? AND document_id=? LIMIT 20",
                (match, artifact_id, document_id),
            ).fetchall()
        page_text = {p["physical_page"]: p["text"] for p in artifact["pages"]}
        if any(page_text.get(int(r["page"])) != r["text"] for r in rows):
            raise ParseError("index_integrity_error", 503)
        after, _ = await self.snapshot(document_id)
        if any(after[k] != artifact[k] for k in after):
            raise ParseError("source_changed")
        return dict(
            artifact_id=artifact_id,
            source_revision=artifact["source_revision"],
            status="candidate_unreviewed",
            items=[dict(physical_page=int(r["page"]), text=r["text"]) for r in rows],
        )
