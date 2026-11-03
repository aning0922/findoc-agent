"""One durable slot, short IMMEDIATE transactions, no runtime data in this DB."""
from contextlib import contextmanager
import fcntl
from pathlib import Path
import sqlite3


class ControlStore:
    def __init__(self, root: Path):
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = root / "demo_control.db"
        self._lock = (root / "controller.lock").open("a+")
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._lock.close()
            raise RuntimeError("Only one demo controller may own this control root") from None
        with self.tx() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS slot (
                    id INTEGER PRIMARY KEY CHECK(id=1), state TEXT NOT NULL,
                    generation INTEGER NOT NULL, session_hash TEXT, expires REAL,
                    reset_id TEXT, seed_version TEXT);
                INSERT OR IGNORE INTO slot VALUES (1,'available',0,NULL,NULL,NULL,NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    hash TEXT PRIMARY KEY, generation INTEGER UNIQUE NOT NULL,
                    expires REAL NOT NULL, revoked TEXT, owner_until REAL);
                CREATE TABLE IF NOT EXISTS operations (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, request_hash TEXT NOT NULL,
                    owner_hash TEXT NOT NULL, generation INTEGER NOT NULL,
                    reset_id TEXT, state TEXT NOT NULL, deadline REAL NOT NULL,
                    session_hash TEXT);
                CREATE TABLE IF NOT EXISTS resets (
                    id TEXT PRIMARY KEY, generation INTEGER UNIQUE NOT NULL,
                    state TEXT NOT NULL, phase TEXT NOT NULL, error_code TEXT);
            """)
        self.path.chmod(0o600)

    @contextmanager
    def tx(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def close(self):
        if not self._lock.closed:
            fcntl.flock(self._lock, fcntl.LOCK_UN)
            self._lock.close()
