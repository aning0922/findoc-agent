"""D10 upgrade transactions preserve D4-D9 DDL, rows, receipts and calculations."""

from contextlib import closing
from decimal import Decimal
import json
import sqlite3
import pytest

from app.companies import migrations
from app.companies.sqlite_repository import SQLiteCompanyRepository
from tests.test_companies_migrations import snapshot
from tests.test_financial_reviews import financial_harness, recovery
from tests.test_d10_financial_facts import receipt, persist, fact_counts
from tests.test_revenue_confirmation import Harness as LegacyHarness


@pytest.mark.parametrize("failure", ["ddl", "log", "none"])
def test_upgrade_d4_d9_preserves_history_failure_retry_repeat_and_restart(
    tmp_path, monkeypatch, failure
):
    full = migrations.MIGRATIONS
    monkeypatch.setattr(migrations, "MIGRATIONS", full[:4])
    h = financial_harness(tmp_path)
    accepted, q = receipt(h)
    legacy = LegacyHarness(tmp_path)
    old = legacy.simulate_acceptance(legacy.preview())
    tables = [
        "documents",
        "companies",
        "report_document_metadata",
        "document_sources",
        "document_evidence",
        "document_evidence_layout",
        "report_binding_corrections",
        "financial_acceptance_receipts",
        "revenue_confirmations",
        "confirmed_revenue_facts",
        "analyst_schema_migrations",
    ]
    before = snapshot(h.db, tables)
    if failure == "ddl":
        v, n, ddl = full[4]
        monkeypatch.setattr(
            migrations, "MIGRATIONS", (*full[:4], (v, n, (*ddl, "INVALID D10 DDL")))
        )
    else:
        monkeypatch.setattr(migrations, "MIGRATIONS", full)
    if failure == "log":
        with closing(sqlite3.connect(h.db)) as c, c:
            c.execute(
                "CREATE TRIGGER d10_migration_fault BEFORE INSERT ON analyst_schema_migrations WHEN NEW.version=5 BEGIN SELECT RAISE(ABORT,'test'); END"
            )
    if failure != "none":
        with pytest.raises(sqlite3.Error):
            SQLiteCompanyRepository(h.db)
        assert snapshot(h.db, tables) == before
        with closing(sqlite3.connect(h.db)) as c, c:
            assert (
                c.execute(
                    "SELECT name FROM sqlite_master WHERE name IN ('financial_fact_sets','confirmed_financial_facts')"
                ).fetchall()
                == []
            )
            c.execute("DROP TRIGGER IF EXISTS d10_migration_fault")
        monkeypatch.setattr(migrations, "MIGRATIONS", full)
    for _ in range(3):
        SQLiteCompanyRepository(h.db)
    after = snapshot(h.db, tables)
    assert {k: v for k, v in after.items() if k != "analyst_schema_migrations"} == {
        k: v for k, v in before.items() if k != "analyst_schema_migrations"
    }
    assert after["analyst_schema_migrations"][1][:4] == before["analyst_schema_migrations"][1]
    assert "period IN (2024, 2025)" in after["confirmed_revenue_facts"][0]
    assert legacy.calculate(old.confirmation_id).result.value == Decimal("20.00")
    assert recovery(h, q).json() == accepted and fact_counts(h) == (0, 0)
    assert persist(h, accepted).status_code == 200 and fact_counts(h) == (1, 6)
    with closing(sqlite3.connect(h.db)) as c:
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert c.execute("PRAGMA foreign_key_check").fetchall() == []
        versions = c.execute(
            "SELECT version,name,checksum FROM analyst_schema_migrations"
        ).fetchall()
    (tmp_path / f"d10-migration-{failure}-proof.json").write_text(
        json.dumps(
            dict(
                failure_injection=failure,
                legacy_ddl_and_rows_unchanged=True,
                receipt_readback_unchanged=True,
                legacy_growth="20.00",
                retries=3,
                versions=versions,
                integrity_check="ok",
                foreign_key_check=[],
            ),
            indent=2,
        )
    )


def test_empty_d10_failure_keeps_only_documents_then_retries(tmp_path, monkeypatch):
    full = migrations.MIGRATIONS
    v, n, ddl = full[4]
    monkeypatch.setattr(migrations, "MIGRATIONS", (*full[:4], (v, n, (*ddl, "INVALID D10 DDL"))))
    db = tmp_path / "empty.db"
    with pytest.raises(sqlite3.OperationalError):
        SQLiteCompanyRepository(db)
    with closing(sqlite3.connect(db)) as c:
        assert c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [
            ("documents",)
        ]
    monkeypatch.setattr(migrations, "MIGRATIONS", full)
    SQLiteCompanyRepository(db)
    with closing(sqlite3.connect(db)) as c:
        assert c.execute("SELECT version FROM analyst_schema_migrations").fetchall() == [(version,) for version, _, _ in full]
