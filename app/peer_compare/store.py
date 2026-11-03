from contextlib import closing, contextmanager
import json
from pathlib import Path
import sqlite3
from uuid import UUID
from app.retrieval_v2.service import canonical, sha
from app.retrieval_v2.models import RetrievalError


class Store:
    def __init__(self, root, name):
        self.path = Path(root) / f"{name}.db"
        with self.tx() as db:
            db.executescript("""CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY,owner TEXT,digest TEXT,state TEXT,result TEXT);
            CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY,owner TEXT,payload TEXT);
            CREATE TRIGGER IF NOT EXISTS immutable_update BEFORE UPDATE ON snapshots BEGIN SELECT RAISE(ABORT,'immutable'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_delete BEFORE DELETE ON snapshots BEGIN SELECT RAISE(ABORT,'immutable'); END;""")
        self.path.chmod(0o600)

    @contextmanager
    def tx(self, before_commit=None):
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            with db:
                yield db
                if before_commit is not None:
                    before_commit()

    def reserve(self, op, owner, body):
        try:
            if str(UUID(op)) != op:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise RetrievalError("invalid_operation", 422) from None
        with self.tx() as db:
            r = db.execute("SELECT * FROM operations WHERE id=?", (op,)).fetchone()
            if r:
                if r["owner"] != owner or r["digest"] != sha(body):
                    raise RetrievalError("operation_conflict")
                return False
            db.execute(
                "INSERT INTO operations VALUES (?,?,?,'unknown',NULL)", (op, owner, sha(body))
            )
        return True

    def operation(self, op, owner):
        with self.tx() as db:
            r = db.execute(
                "SELECT * FROM operations WHERE id=? AND owner=?", (op, owner)
            ).fetchone()
        if not r:
            raise RetrievalError("operation_not_found", 404)
        return dict(
            operation_id=op,
            state=r["state"],
            result=json.loads(r["result"]) if r["result"] else None,
        )

    def read(self, key, owner):
        with self.tx() as db:
            r = db.execute(
                "SELECT payload FROM snapshots WHERE id=? AND owner=?", (key, owner)
            ).fetchone()
        if not r:
            raise RetrievalError("result_not_found", 404)
        return json.loads(r[0])

    def finish(self, db, key, owner, op, payload):
        db.execute("INSERT INTO snapshots VALUES (?,?,?)", (key, owner, canonical(payload)))
        db.execute(
            "UPDATE operations SET state='completed',result=? WHERE id=?", (canonical(payload), op)
        )
