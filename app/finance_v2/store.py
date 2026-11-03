"""Independent v2 SQLite only. Existing documents DB is attached read-only for final fences."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3

from app.finance_v2.contracts import FinanceError
from app.finance_v2.extraction import canonical, digest


class FinanceStore:
    def __init__(self, root: Path):
        if not root.is_absolute():
            raise ValueError("Finance v2 requires an absolute generation root")
        self.root = root.resolve()
        self.path = self.root / "finance-v2.db"
        if not (self.root / "documents.db").is_file():
            raise ValueError("Existing generation documents.db required")
        with self.tx() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS fv2_schema (version INTEGER PRIMARY KEY CHECK(version=1));
                INSERT OR IGNORE INTO fv2_schema VALUES (1);
                CREATE TABLE IF NOT EXISTS fv2_metrics (
                    id TEXT PRIMARY KEY,company_id TEXT NOT NULL,payload TEXT NOT NULL,
                    sha TEXT NOT NULL,source_json TEXT NOT NULL,company_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS fv2_reviews (id TEXT PRIMARY KEY,payload TEXT NOT NULL,sha TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS fv2_receipts (id TEXT PRIMARY KEY,payload TEXT NOT NULL,sha TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS fv2_receipt_items (receipt_id TEXT NOT NULL,metric_id TEXT NOT NULL,
                    PRIMARY KEY(receipt_id,metric_id),FOREIGN KEY(receipt_id) REFERENCES fv2_receipts(id),
                    FOREIGN KEY(metric_id) REFERENCES fv2_metrics(id));
                CREATE TABLE IF NOT EXISTS fv2_revocations (receipt_id TEXT PRIMARY KEY,payload TEXT NOT NULL,sha TEXT NOT NULL,
                    FOREIGN KEY(receipt_id) REFERENCES fv2_receipts(id));
                CREATE TABLE IF NOT EXISTS fv2_analyses (id TEXT PRIMARY KEY,payload TEXT NOT NULL,sha TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS fv2_operations (id TEXT PRIMARY KEY,kind TEXT NOT NULL,digest TEXT NOT NULL,
                    state TEXT NOT NULL,result TEXT,error_code TEXT);
                CREATE INDEX IF NOT EXISTS fv2_metrics_company ON fv2_metrics(company_id,id);
            """)
            for table in ("fv2_metrics", "fv2_reviews", "fv2_receipts", "fv2_receipt_items", "fv2_revocations", "fv2_analyses"):
                for mutation in ("UPDATE", "DELETE"):
                    db.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_{mutation.lower()} BEFORE {mutation} ON {table} "
                               "BEGIN SELECT RAISE(ABORT,'immutable finance v2 snapshot'); END")
        self.path.chmod(0o600)

    @contextmanager
    def tx(self, *, source=False):
        db = sqlite3.connect(self.path, timeout=5, uri=True)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            if source:
                uri = (self.root / "documents.db").as_uri() + "?mode=ro"
                db.execute("ATTACH DATABASE ? AS source_db", (uri,))
                # A shared source read lock must protect the final source snapshot through commit.
                # Existing runtime is rollback-journal SQLite; WAL would allow a newer source commit.
                if db.execute("PRAGMA source_db.journal_mode").fetchone()[0].lower() == "wal":
                    raise FinanceError("source_wal_atomic_fence_unsupported", 503)
            db.execute("BEGIN" if source else "BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def decode(self, row):
        if row is None:
            raise FinanceError("metric_or_snapshot_not_found", 404)
        value = json.loads(row["payload"])
        if digest(value) != row["sha"]:
            raise FinanceError("finance_snapshot_corrupt", 503)
        return value

    def reserve(self, operation_id, kind, payload):
        request_digest = digest([kind, payload])
        with self.tx() as db:
            row = db.execute("SELECT * FROM fv2_operations WHERE id=?", (operation_id,)).fetchone()
            if row:
                if row["kind"] != kind or row["digest"] != request_digest:
                    raise FinanceError("operation_conflict")
                if row["state"] == "failed":
                    raise FinanceError(row["error_code"])
                if row["state"] != "completed":
                    raise FinanceError("operation_unknown")
                return json.loads(row["result"])
            db.execute("INSERT INTO fv2_operations VALUES (?,?,?,'unknown',NULL,NULL)", (operation_id, kind, request_digest))
        return None

    @staticmethod
    def finish(db, operation_id, result):
        db.execute("UPDATE fv2_operations SET state='completed',result=? WHERE id=?", (canonical(result), operation_id))

    def failed(self, operation_id, code):
        with self.tx() as db:
            db.execute("UPDATE fv2_operations SET state='failed',error_code=? WHERE id=? AND state='unknown'", (code, operation_id))
