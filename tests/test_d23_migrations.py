"""Review migration 9 against version 8; DDL/log/constraint failures are atomic."""

from contextlib import closing
import hashlib
import json
import os
import shutil
import sqlite3
from pathlib import Path
import pytest
from app.companies import migrations
from app.companies.sqlite_repository import SQLiteCompanyRepository
from tests.test_companies_migrations import snapshot


@pytest.mark.parametrize("failure", ["ddl", "log", "none"])
def test_v8_upgrade_rollback_retry_preserves_all_prior_ddl_rows(tmp_path, monkeypatch, failure):
    proof = json.loads(
        Path(
            os.environ.get(
                "FINDOC_MIGRATION_TEST_PROOF", "product/validation/d21-real-research.json"
            )
        ).read_text()
    )
    db = tmp_path / "documents.db"
    shutil.copy2(Path(proof["runtime_root"]) / "documents.db", db)
    with closing(sqlite3.connect(db)) as conn:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name!='sqlite_sequence'"
            )
        ]
        assert conn.execute("SELECT max(version) FROM analyst_schema_migrations").fetchone()[0] == 8
    before = snapshot(db, tables)
    full = migrations.MIGRATIONS
    if failure == "ddl":
        v, n, ddl = full[8]
        monkeypatch.setattr(
            migrations, "MIGRATIONS", (*full[:8], (v, n, (*ddl, "INVALID D23 DDL")))
        )
    if failure == "log":
        with sqlite3.connect(db) as conn:
            conn.execute(
                "CREATE TRIGGER d23_log_fault BEFORE INSERT ON analyst_schema_migrations WHEN NEW.version=9 BEGIN SELECT RAISE(ABORT,'injected migration failure'); END"
            )
    if failure != "none":
        with pytest.raises(sqlite3.Error):
            SQLiteCompanyRepository(db)
        assert snapshot(db, tables) == before
        with sqlite3.connect(db) as conn:
            assert not conn.execute(
                "SELECT name FROM sqlite_master WHERE name='reports'"
            ).fetchall()
            conn.execute("DROP TRIGGER IF EXISTS d23_log_fault")
        monkeypatch.setattr(migrations, "MIGRATIONS", full)
    for _ in range(3):
        SQLiteCompanyRepository(db)
    after = snapshot(db, tables)
    assert {k: v for k, v in after.items() if k != "analyst_schema_migrations"} == {
        k: v for k, v in before.items() if k != "analyst_schema_migrations"
    }
    assert after["analyst_schema_migrations"][1][:8] == before["analyst_schema_migrations"][1]
    with sqlite3.connect(db) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        log = conn.execute(
            "SELECT version,name,checksum FROM analyst_schema_migrations ORDER BY version"
        ).fetchall()
    assert log[-1] == (9, full[8][1], hashlib.sha256("\n".join(full[8][2]).encode()).hexdigest())
    (tmp_path / f"d23-migration-{failure}.json").write_text(
        json.dumps(
            dict(failure=failure, versions=log, old_tables_unchanged=True, foreign_keys_ok=True)
        )
    )


@pytest.mark.parametrize("damage", ["unknown", "missing", "modified"])
def test_reviewed_migration_history_fail_closed(tmp_path, damage):
    db = tmp_path / "documents.db"
    SQLiteCompanyRepository(db)
    with sqlite3.connect(db) as conn:
        if damage == "unknown":
            conn.execute(
                "INSERT INTO analyst_schema_migrations VALUES(10,'unknown','unknown','today')"
            )
        elif damage == "missing":
            conn.execute("DELETE FROM analyst_schema_migrations WHERE version=8")
        else:
            conn.execute("UPDATE analyst_schema_migrations SET checksum='changed' WHERE version=9")
    with pytest.raises(RuntimeError):
        SQLiteCompanyRepository(db)
    from app.api.report_history import create_report_history_app

    with pytest.raises(RuntimeError):
        create_report_history_app(db)
