import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from .models import VerifiedJobReader, VerifiedJobSnapshot


class ReportError(Exception):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class ShowcaseReportService:
    def __init__(
        self, runtime_root: Path, *, workspace_id: str, verified_job_reader: VerifiedJobReader
    ):
        if not (runtime_root / "documents.db").is_file() or not workspace_id:
            raise ValueError("report_runtime_invalid")
        self.path = runtime_root.resolve() / "showcase-reports.db"
        self.workspace, self.reader = workspace_id, verified_job_reader
        with self.tx() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS drafts(id TEXT PRIMARY KEY, workspace TEXT, snapshot TEXT);
            CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY, workspace TEXT, current_revision INTEGER);
            CREATE TABLE IF NOT EXISTS revisions(report_id TEXT, revision INTEGER, payload TEXT, PRIMARY KEY(report_id,revision));
            CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY, workspace TEXT, digest TEXT, result TEXT);
            CREATE TRIGGER IF NOT EXISTS immutable_revision_update BEFORE UPDATE ON revisions BEGIN SELECT RAISE(ABORT,'immutable revision'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_revision_delete BEFORE DELETE ON revisions BEGIN SELECT RAISE(ABORT,'immutable revision'); END;
            """)
        self.path.chmod(0o600)

    @contextmanager
    def tx(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE")
            with db:
                yield db
        finally:
            db.close()

    def operation(self, db, oid, request):
        try:
            if str(UUID(oid)) != oid:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise ReportError("invalid_operation_id", 422) from None
        digest = hashlib.sha256(encode(request).encode()).hexdigest()
        row = db.execute("SELECT * FROM operations WHERE id=?", (oid,)).fetchone()
        if row:
            if row["workspace"] != self.workspace or row["digest"] != digest:
                raise ReportError("operation_conflict")
            return digest, json.loads(row["result"])
        return digest, None

    def record(self, db, oid, digest, result):
        db.execute(
            "INSERT INTO operations VALUES (?,?,?,?)", (oid, self.workspace, digest, encode(result))
        )
        return result

    async def verified(self, job_id):
        value = await self.reader(job_id)
        if (
            not isinstance(value, VerifiedJobSnapshot)
            or value.job_id != job_id
            or value.workspace_id != self.workspace
        ):
            raise ReportError("job_scope_invalid", 403)
        for finding in value.findings:
            if finding.kind == "confirmed_financial" and not finding.financial_refs:
                raise ReportError("financial_refs_required", 422)
            if finding.kind == "sourced_excerpt" and not finding.evidence_refs:
                raise ReportError("evidence_refs_required", 422)
        return value.model_dump()

    async def draft(self, *, operation_id, job_id):
        request = dict(action="draft", job_id=job_id)
        with self.tx() as db:
            _, prior = self.operation(db, operation_id, request)
        if prior:
            return prior
        snapshot = await self.verified(job_id)
        with self.tx() as db:
            digest, prior = self.operation(db, operation_id, request)
            if prior:
                return prior
            did = str(uuid4())
            db.execute("INSERT INTO drafts VALUES (?,?,?)", (did, self.workspace, encode(snapshot)))
            return self.record(db, operation_id, digest, dict(draft_id=did, snapshot=snapshot))

    def save(
        self,
        *,
        operation_id,
        title,
        notes="",
        draft_id=None,
        report_id=None,
        expected_revision=None,
    ):
        if (
            not title.strip()
            or len(title) > 200
            or len(notes) > 8000
            or bool(draft_id) == bool(report_id)
        ):
            raise ReportError("invalid_report_request", 422)
        request = dict(
            action="save",
            title=title,
            notes=notes,
            draft_id=draft_id,
            report_id=report_id,
            expected_revision=expected_revision,
        )
        with self.tx() as db:
            digest, prior = self.operation(db, operation_id, request)
            if prior:
                return prior
            if draft_id:
                row = db.execute(
                    "SELECT snapshot FROM drafts WHERE id=? AND workspace=?",
                    (draft_id, self.workspace),
                ).fetchone()
                if not row:
                    raise ReportError("draft_not_found", 404)
                snapshot, report_id, revision = json.loads(row["snapshot"]), str(uuid4()), 1
                db.execute("INSERT INTO reports VALUES (?,?,?)", (report_id, self.workspace, 1))
            else:
                row = db.execute(
                    "SELECT current_revision FROM reports WHERE id=? AND workspace=?",
                    (report_id, self.workspace),
                ).fetchone()
                if not row:
                    raise ReportError("report_not_found", 404)
                if row[0] != expected_revision:
                    raise ReportError("report_revision_conflict")
                previous = db.execute(
                    "SELECT payload FROM revisions WHERE report_id=? AND revision=?",
                    (report_id, row[0]),
                ).fetchone()
                snapshot, revision = json.loads(previous[0])["snapshot"], row[0] + 1
                db.execute(
                    "UPDATE reports SET current_revision=? WHERE id=?", (revision, report_id)
                )
            payload = dict(
                schema_version="showcase-report-v2",
                report_id=report_id,
                revision=revision,
                title=title,
                notes=notes,
                created_at=datetime.now(UTC).isoformat(),
                snapshot=snapshot,
            )
            db.execute(
                "INSERT INTO revisions VALUES (?,?,?)", (report_id, revision, encode(payload))
            )
            return self.record(db, operation_id, digest, payload)

    def list(self):
        with self.tx() as db:
            return [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT v.payload FROM reports r JOIN revisions v ON v.report_id=r.id AND v.revision=r.current_revision WHERE r.workspace=? ORDER BY r.rowid DESC LIMIT 100",
                    (self.workspace,),
                )
            ]

    async def revision(self, report_id, revision):
        with self.tx() as db:
            row = db.execute(
                "SELECT v.payload FROM revisions v JOIN reports r ON r.id=v.report_id WHERE r.workspace=? AND r.id=? AND v.revision=?",
                (self.workspace, report_id, revision),
            ).fetchone()
        if not row:
            raise ReportError("report_not_found", 404)
        payload = json.loads(row[0])
        try:
            latest = await self.verified(payload["snapshot"]["job_id"])
            statuses = {f["finding_id"]: f["source_status"] for f in latest["findings"]}
            status = (
                "current"
                if all(
                    statuses.get(f["finding_id"]) == "current"
                    for f in payload["snapshot"]["findings"]
                )
                else "stale"
            )
        except Exception:
            status = "unavailable"
        return {
            **payload,
            "current_source_status": status,
            "history_notice": "已保存的只读版本；来源状态单独复验，内容不自动更新。",
        }
