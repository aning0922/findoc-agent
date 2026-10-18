"""Additive research persistence; old Agent and finance tables are untouched."""

RESEARCH_MIGRATION = (
    7,
    "research_runs_v1",
    (
        """CREATE TABLE research_runs (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL UNIQUE,
        workspace_id TEXT NOT NULL,
        operation_id TEXT NOT NULL,
        request_sha TEXT NOT NULL,
        created_at TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('running','answered','refused','system_error')),
        payload TEXT NOT NULL,
        payload_sha TEXT NOT NULL,
        UNIQUE(workspace_id, operation_id)
    )""",
        "CREATE INDEX research_history ON research_runs(workspace_id, created_at DESC, run_id DESC)",
        "CREATE TABLE research_cursor_key (id INTEGER PRIMARY KEY CHECK(id=1), secret BLOB NOT NULL)",
        "INSERT INTO research_cursor_key VALUES (1, randomblob(32))",
        """CREATE TRIGGER research_terminal_immutable BEFORE UPDATE ON research_runs
        WHEN OLD.status != 'running'
        BEGIN SELECT RAISE(ABORT, 'research terminal is immutable'); END""",
        """CREATE TRIGGER research_identity_immutable BEFORE UPDATE ON research_runs
        WHEN NEW.run_id != OLD.run_id OR NEW.workspace_id != OLD.workspace_id
        OR NEW.operation_id != OLD.operation_id OR NEW.request_sha != OLD.request_sha
        OR NEW.created_at != OLD.created_at OR NEW.sequence != OLD.sequence
        BEGIN SELECT RAISE(ABORT, 'research identity is immutable'); END""",
    ),
)
