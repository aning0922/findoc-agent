"""Durable operation namespace, shared provider/tool reservations and public events."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

from app.showcase_research.models import ResearchError


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class ResearchStore:
    def __init__(self, root: Path):
        if not root.is_absolute() or not (root / "documents.db").is_file():
            raise ValueError("Existing absolute generation root required")
        self.root, self.path = root.resolve(), root.resolve() / "showcase-research.db"
        with self.tx() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sr_records (kind TEXT NOT NULL,id TEXT PRIMARY KEY,payload TEXT NOT NULL,sha TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sr_operations (id TEXT PRIMARY KEY,kind TEXT NOT NULL,digest TEXT NOT NULL,state TEXT NOT NULL,target_id TEXT,result TEXT,error TEXT);
                CREATE TABLE IF NOT EXISTS sr_budgets (id TEXT PRIMARY KEY,deadline REAL NOT NULL,max_attempts INTEGER NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,tools INTEGER NOT NULL DEFAULT 0,input_tokens INTEGER NOT NULL DEFAULT 0,output_tokens INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS sr_attempts (id TEXT PRIMARY KEY,run_id TEXT NOT NULL,agent_id TEXT NOT NULL,
                    kind TEXT NOT NULL,state TEXT NOT NULL,input_tokens INTEGER NOT NULL,output_limit INTEGER NOT NULL,created_at TEXT NOT NULL,ended_at TEXT);
                CREATE TABLE IF NOT EXISTS sr_handoffs (intent_id TEXT PRIMARY KEY,conversation_id TEXT NOT NULL,task_operation_id TEXT NOT NULL UNIQUE,task_id TEXT,state TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sr_events (run_id TEXT NOT NULL,seq INTEGER NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(run_id,seq));
                CREATE TABLE IF NOT EXISTS sr_jobs (id TEXT PRIMARY KEY,plan_id TEXT NOT NULL UNIQUE,conversation_id TEXT NOT NULL,
                    mode TEXT NOT NULL,state TEXT NOT NULL,scope TEXT NOT NULL,result TEXT,error TEXT,created_at TEXT NOT NULL,ended_at TEXT);
                CREATE TABLE IF NOT EXISTS sr_steps (id TEXT PRIMARY KEY,run_id TEXT NOT NULL,agent_id TEXT NOT NULL,state TEXT NOT NULL,payload TEXT NOT NULL);
                CREATE TRIGGER IF NOT EXISTS sr_records_immutable_update BEFORE UPDATE ON sr_records BEGIN SELECT RAISE(ABORT,'immutable research record'); END;
                CREATE TRIGGER IF NOT EXISTS sr_records_immutable_delete BEFORE DELETE ON sr_records BEGIN SELECT RAISE(ABORT,'immutable research record'); END;
            """)
        self.path.chmod(0o600)
        with self.tx() as db:
            db.execute("UPDATE sr_jobs SET state='interrupted',error='runtime_restarted',ended_at=? WHERE state IN ('queued','running')", (timestamp(),))
            db.execute("UPDATE sr_steps SET state='interrupted' WHERE state='running'")

    @contextmanager
    def tx(self, *, attachments=None):
        db = sqlite3.connect(self.path, timeout=5, uri=True)
        db.row_factory = sqlite3.Row
        try:
            for alias, path in (attachments or {}).items():
                if alias not in ("source_db", "memory_db") or not Path(path).is_file():
                    raise ResearchError("context_fence_unavailable", 503)
                db.execute(f"ATTACH DATABASE ? AS {alias}", (Path(path).resolve().as_uri() + "?mode=ro",))
                if db.execute(f"PRAGMA {alias}.journal_mode").fetchone()[0].lower() == "wal":
                    raise ResearchError("wal_context_fence_unsupported", 503)
            db.execute("BEGIN" if attachments else "BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def reserve_operation(self, operation_id, kind, payload):
        digest = sha([kind, payload])
        with self.tx() as db:
            row = db.execute("SELECT * FROM sr_operations WHERE id=?", (operation_id,)).fetchone()
            if row:
                if row["kind"] != kind or row["digest"] != digest:
                    raise ResearchError("operation_conflict")
                if row["state"] == "completed":
                    return json.loads(row["result"])
                if row["state"] == "failed":
                    raise ResearchError(row["error"])
                raise ResearchError("operation_unknown")
            db.execute("INSERT INTO sr_operations VALUES (?,?,?,'unknown',NULL,NULL,NULL)", (operation_id, kind, digest))
        return None

    @staticmethod
    def finish(db, operation_id, result, target_id=None):
        db.execute("UPDATE sr_operations SET state='completed',result=?,target_id=? WHERE id=?", (canonical(result), target_id, operation_id))

    @staticmethod
    def record(db, kind, record_id, payload):
        db.execute("INSERT INTO sr_records VALUES (?,?,?,?)", (kind, record_id, canonical(payload), sha(payload)))

    def get(self, record_id, kind):
        with self.tx() as db:
            row = db.execute("SELECT * FROM sr_records WHERE id=? AND kind=?", (record_id, kind)).fetchone()
        if row is None:
            raise ResearchError("research_record_not_found", 404)
        value = json.loads(row["payload"])
        if sha(value) != row["sha"]:
            raise ResearchError("research_record_corrupt", 503)
        return value

    def create_budget(self, run_id, deadline, max_attempts=10):
        with self.tx() as db:
            db.execute("INSERT OR IGNORE INTO sr_budgets(id,deadline,max_attempts) VALUES (?,?,?)", (run_id, deadline, max_attempts))

    def reserve_call(self, run_id, agent_id, *, kind="model", input_tokens=0, output_limit=1024):
        with self.tx() as db:
            row = db.execute("SELECT * FROM sr_budgets WHERE id=?", (run_id,)).fetchone()
            if row is None or row["deadline"] <= time.time():
                raise ResearchError("budget_deadline_exhausted")
            if kind == "model":
                if row["attempts"] >= min(10, row["max_attempts"]) or row["input_tokens"] + input_tokens > 48000 or row["output_tokens"] + output_limit > 12000:
                    raise ResearchError("model_budget_exhausted")
                db.execute("UPDATE sr_budgets SET attempts=attempts+1,input_tokens=input_tokens+?,output_tokens=output_tokens+? WHERE id=?", (input_tokens, output_limit, run_id))
            else:
                if row["tools"] >= 12:
                    raise ResearchError("tool_budget_exhausted")
                db.execute("UPDATE sr_budgets SET tools=tools+1 WHERE id=?", (run_id,))
            attempt_id = str(uuid4())
            db.execute("INSERT INTO sr_attempts VALUES (?,?,?,?,?,?,?,?,NULL)", (attempt_id, run_id, agent_id, kind, "unknown", input_tokens, output_limit, timestamp()))
        return attempt_id

    def returned(self, attempt_id):
        with self.tx() as db:
            db.execute("UPDATE sr_attempts SET state='returned',ended_at=? WHERE id=?", (timestamp(), attempt_id))

    def usage(self, run_id):
        with self.tx() as db:
            row = db.execute("SELECT * FROM sr_budgets WHERE id=?", (run_id,)).fetchone()
            unknown = db.execute("SELECT COUNT(*) FROM sr_attempts WHERE run_id=? AND state='unknown'", (run_id,)).fetchone()[0]
        return {**dict(row), "unknown_attempts": unknown, "provider_tokens_actual": None}

    def event(self, run_id, agent_id, label, state, *, event_type="phase", public_summary=None):
        with self.tx() as db:
            seq = db.execute("SELECT COALESCE(MAX(seq),0)+1 FROM sr_events WHERE run_id=?", (run_id,)).fetchone()[0]
            value = {"schema_version": "execution-event-v1", "job_id": run_id, "event_seq": seq, "event_type": event_type,
                     "agent_id": agent_id, "label": label, "state": state, "public_summary": public_summary or label, "timestamp": timestamp()}
            db.execute("INSERT INTO sr_events VALUES (?,?,?)", (run_id, seq, canonical(value)))
        return value

    def events(self, run_id, after=0):
        with self.tx() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT payload FROM sr_events WHERE run_id=? AND seq>? ORDER BY seq LIMIT 200", (run_id, after))]
