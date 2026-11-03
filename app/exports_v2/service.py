"""Generation-local immutable export blobs; root supplies trusted resolution and fences."""

import asyncio
from contextlib import contextmanager
import hashlib
import inspect
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from uuid import UUID, uuid4
from datetime import datetime, timezone
from .projection import canonical, digest, matrix, project


class ExportError(Exception):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


class ExportService:
    def __init__(
        self,
        runtime_root,
        *,
        resolver,
        identity_validator,
        publication_guard,
        before_commit_sync,
        authorize_read,
        renderer_python=None,
    ):
        self.root = Path(runtime_root).resolve() / "exports-v2"
        if self.root.is_symlink():
            raise ValueError("symlink_export_root")
        self.root.mkdir(mode=0o700, exist_ok=True)
        self.path = self.root / "exports.sqlite"
        if self.path.is_symlink() or (self.path.exists() and self.path.stat().st_nlink != 1):
            raise ValueError("unsafe_export_store")
        self.resolver, self.validator, self.guard, self.commit, self.reader = (
            resolver,
            identity_validator,
            publication_guard,
            before_commit_sync,
            authorize_read,
        )
        self.python = renderer_python or sys.executable
        with self.tx() as db:
            db.executescript(
                "CREATE TABLE IF NOT EXISTS ops(id TEXT PRIMARY KEY,owner TEXT,digest TEXT,state TEXT,result TEXT);CREATE TABLE IF NOT EXISTS files(export_id TEXT,format TEXT,content BLOB,sha TEXT,PRIMARY KEY(export_id,format));CREATE TRIGGER IF NOT EXISTS no_file_update BEFORE UPDATE ON files BEGIN SELECT RAISE(ABORT,'immutable file');END;CREATE TRIGGER IF NOT EXISTS no_file_delete BEFORE DELETE ON files BEGIN SELECT RAISE(ABORT,'immutable file');END;"
            )
        self.path.chmod(0o600)

    def check(self, identity):
        result = self.validator(identity)
        if inspect.isawaitable(result):
            if inspect.iscoroutine(result):
                result.close()
            raise ExportError("synchronous_identity_validator_required", 503)
        if result is False:
            raise ExportError("identity_rejected", 403)
        return digest(identity.model_dump() if hasattr(identity, "model_dump") else identity)

    def precommit(self, identity):
        self.check(identity)
        value = self.commit(identity)
        if inspect.isawaitable(value):
            if inspect.iscoroutine(value):
                value.close()
            raise ExportError("synchronous_commit_required", 503)
        if value is False:
            raise ExportError("identity_rejected", 403)

    @contextmanager
    def tx(self, identity=None):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            if identity is not None:
                self.precommit(identity)
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def operation(self, oid, identity):
        owner = self.check(identity)
        with self.tx() as db:
            row = db.execute("SELECT * FROM ops WHERE id=? AND owner=?", (oid, owner)).fetchone()
        if not row:
            raise ExportError("export_not_found", 404)
        return dict(
            operation_id=oid,
            state=row["state"],
            result=json.loads(row["result"]) if row["result"] else None,
        )

    async def create(self, body, identity):
        from .api import ExportRequest

        body = ExportRequest.model_validate(body).model_dump()
        owner = self.check(identity)
        oid = body["operation_id"]
        try:
            if str(UUID(oid)) != oid:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise ExportError("invalid_operation_id", 422) from None
        with self.tx(identity) as db:
            row = db.execute("SELECT * FROM ops WHERE id=?", (oid,)).fetchone()
            if row:
                if row["owner"] != owner:
                    raise ExportError("export_not_found", 404)
                if row["digest"] != digest(body):
                    raise ExportError("operation_conflict")
                return dict(
                    operation_id=oid,
                    state=row["state"],
                    result=json.loads(row["result"]) if row["result"] else None,
                )
            db.execute("INSERT INTO ops VALUES(?,?,?,'unknown',NULL)", (oid, owner, digest(body)))
        ref = body["report_ref"]
        resolved = await self.resolver(
            ref["domain"], ref["id"], ref["revision"], ref["payload_sha256"], identity
        )
        display_companies = json.loads(canonical(resolved.get("display_companies") or {}))
        created_at = datetime.now(timezone.utc).isoformat()
        resolved = {**resolved, "display_companies": display_companies, "generated_at": created_at}
        projection = project(ref, resolved)
        common = dict(
            domain=ref["domain"],
            result_id=ref["id"],
            revision=ref["revision"],
            snapshot_sha256=ref["payload_sha256"],
            current_source_status=resolved["display_status"],
            generated_at=created_at,
        )
        for name in ("financial", "evidence"):
            projection[name] = [{**common, **row} for row in projection[name]]
        data = {
            **projection,
            "overview_matrix": matrix(projection["overview"], ["field", "value"]),
            "financial_matrix": matrix(
                projection["financial"],
                [
                    "metric_key",
                    "raw_decimal",
                    "normalized_decimal",
                    "time",
                    "raw_unit",
                    "financial_review",
                    "receipt_ref",
                ],
            ),
            "evidence_matrix": matrix(
                projection["evidence"],
                [
                    "text",
                    "document_id",
                    "source_revision",
                    "physical_page",
                    "interpretation_review_status",
                ],
            ),
        }
        files = {}
        with tempfile.TemporaryDirectory(prefix="staging-", dir=self.root) as temp:
            source = Path(temp) / "snapshot.json"
            source.write_text(canonical(data))
            source.chmod(0o600)
            for fmt in body["formats"]:
                target = Path(temp) / ("artifact." + fmt)
                process = await asyncio.create_subprocess_exec(
                    self.python,
                    str(Path(__file__).with_name("render.py")),
                    fmt,
                    str(source),
                    str(target),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    _, stderr = await asyncio.wait_for(process.communicate(), 90)
                except BaseException:
                    process.kill()
                    await process.wait()
                    raise
                if process.returncode:
                    raise ExportError("renderer_failed", 503)
                target.chmod(0o600)
                content = target.read_bytes()
                if len(content) > 30_000_000:
                    raise ExportError("artifact_too_large", 413)
                files[fmt] = content
        # Re-resolve exact version after rendering. Permission errors are never downgraded.
        current = await self.resolver(
            ref["domain"], ref["id"], ref["revision"], ref["payload_sha256"], identity
        )
        if (
            canonical(current["snapshot"]) != canonical(resolved["snapshot"])
            or current["display_status"] != resolved["display_status"]
            or canonical(current.get("display_companies") or {}) != canonical(display_companies)
        ):
            raise ExportError("export_snapshot_or_status_changed")
        eid = str(uuid4())
        manifest = dict(
            schema_version="cplus-export-manifest-v1",
            created_at=created_at,
            export_id=eid,
            report_ref=ref,
            export_profile_version=body["export_profile_version"],
            display_status=resolved["display_status"],
            historical_snapshot=resolved["display_status"] != "current",
            files=[
                dict(
                    format=f,
                    bytes=len(v),
                    sha256=hashlib.sha256(v).hexdigest(),
                    href=f"/cplus/exports/{eid}/files/{f}",
                )
                for f, v in files.items()
            ],
            snapshot_sha256=ref["payload_sha256"],
            projection_version="business-v2",
            display_companies=display_companies,
            display_companies_sha256=digest(display_companies),
        )
        with self.guard(identity, current), self.tx(identity) as db:
            for fmt, content in files.items():
                db.execute(
                    "INSERT INTO files VALUES(?,?,?,?)",
                    (eid, fmt, content, hashlib.sha256(content).hexdigest()),
                )
            db.execute(
                "UPDATE ops SET state='completed',result=? WHERE id=? AND owner=?",
                (canonical(manifest), oid, owner),
            )
        return self.operation(oid, identity)

    async def file(self, eid, fmt, identity):
        owner = self.check(identity)
        with self.tx() as db:
            rows = db.execute(
                "SELECT result FROM ops WHERE owner=? AND state='completed'", (owner,)
            ).fetchall()
            manifest = next(
                (m for row in rows if (m := json.loads(row[0]))["export_id"] == eid), None
            )
            row = (
                db.execute(
                    "SELECT content,sha FROM files WHERE export_id=? AND format=?", (eid, fmt)
                ).fetchone()
                if manifest
                else None
            )
        if row is None:
            raise ExportError("export_not_found", 404)
        access = self.reader(identity, manifest)
        if inspect.isawaitable(access):
            access = await access
        if access is False:
            raise ExportError("display_permission_denied", 403)
        self.check(identity)
        if hashlib.sha256(row[0]).hexdigest() != row[1]:
            raise ExportError("artifact_integrity_error", 503)
        return row[0], row[1]
