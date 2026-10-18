"""Empty/legacy/repeated/failed migrations and persisted business compatibility."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime
from decimal import Decimal
import sqlite3

import pytest
from pydantic import ValidationError

from app.agent.run_models import RunEvent, RunEventType
from app.agent.sqlite_run_repository import SQLiteAgentRunRepository
from app.agent.sqlite_financial_facts import SQLiteRevenueConfirmationRepository
from app.agent.revenue_confirmation import RevenueConfirmationService
from app.companies import migrations
from app.companies.models import (
    CompanyCreate,
    CompanyPatch,
    RegistryConflictError,
    ReportMetadataInput,
)
from app.companies.service import CompanyService
from app.companies.sqlite_repository import SQLiteCompanyRepository
from tests.test_companies_api import company_payload, metadata_payload
from tests.test_revenue_confirmation import Harness


def snapshot(path, tables):
    with closing(sqlite3.connect(path)) as connection:
        return {
            table: (
                connection.execute(
                    "SELECT sql FROM sqlite_master WHERE name=?", (table,)
                ).fetchone()[0],
                connection.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall(),
            )
            for table in tables
        }


def test_empty_database_and_repeated_migrations(tmp_path):
    database = tmp_path / "new" / "documents.db"
    SQLiteCompanyRepository(database)
    tables = ["documents", "companies", "report_document_metadata", "analyst_schema_migrations"]
    before = snapshot(database, tables)
    for _ in range(3):
        SQLiteCompanyRepository(database)
    assert snapshot(database, tables) == before
    assert [row[0] for row in before["analyst_schema_migrations"][1]] == [v for v, _, _ in migrations.MIGRATIONS]
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("shared_run_database", [True, False])
def test_existing_documents_runs_events_confirmations_and_facts_are_unchanged(
    tmp_path,
    shared_run_database,
):
    h = Harness(tmp_path)
    review = h.preview()
    confirmation = h.simulate_acceptance(review)
    run_path = h.database if shared_run_database else tmp_path / "agent-runs.db"
    runs = SQLiteAgentRunRepository(run_path)
    run = runs.start_run(workspace_id="demo", execution_config_version="legacy-test")
    event = RunEvent(
        run_id=run.run_id,
        sequence=1,
        event_type=RunEventType.TOOL_REQUESTED,
        payload={"tool": "search_evidence"},
        occurred_at=datetime.now(UTC),
    )
    runs.append_event(workspace_id="demo", event=event)
    business_tables = ["documents", "revenue_confirmations", "confirmed_revenue_facts"]
    before = snapshot(h.database, business_tables)
    run_before = snapshot(run_path, ["agent_runs", "run_events"])
    for _ in range(3):
        registry = CompanyService(SQLiteCompanyRepository(h.database), workspace_id="demo")
    c = registry.create(CompanyCreate.model_validate(company_payload()))
    registry.bind(
        h.document_id, ReportMetadataInput.model_validate(metadata_payload(c.company_id, 2026))
    )
    assert snapshot(h.database, business_tables) == before
    assert snapshot(run_path, ["agent_runs", "run_events"]) == run_before
    assert SQLiteAgentRunRepository(run_path).get_run(workspace_id="demo", run_id=run.run_id) == run
    assert SQLiteAgentRunRepository(run_path).list_events(
        workspace_id="demo", run_id=run.run_id
    ) == [event]
    reopened = RevenueConfirmationService(
        source_reader=h.reader,
        repository=SQLiteRevenueConfirmationRepository(h.database),
    )
    calculated = asyncio.run(
        reopened.calculate(document_id=h.document_id, confirmation_id=confirmation.confirmation_id)
    )
    assert calculated.result.value == Decimal("20.00")
    assert calculated.confirmation == confirmation
    assert snapshot(h.database, business_tables) == before
    # The legacy fixed CHECK remains exactly intact; D5 does not relax confirmation safety.
    assert "period IN (2024, 2025)" in before["confirmed_revenue_facts"][0]


@pytest.mark.parametrize("failure_at", ["company", "metadata"])
def test_migration_failure_rolls_back_all_new_schema_and_keeps_old_rows(
    tmp_path, monkeypatch, failure_at
):
    h = Harness(tmp_path)
    before = snapshot(h.database, ["documents", "revenue_confirmations", "confirmed_revenue_facts"])
    plans = list(migrations.MIGRATIONS)
    version, name, statements = plans[0 if failure_at == "company" else 1]
    # Force a failure after successful DDL, including the first version's log insertion.
    plans[0 if failure_at == "company" else 1] = (
        version,
        name,
        (*statements, "INSERT INTO missing_d5_table VALUES (1)"),
    )
    monkeypatch.setattr(migrations, "MIGRATIONS", tuple(plans))
    with pytest.raises(sqlite3.OperationalError):
        SQLiteCompanyRepository(h.database)
    assert snapshot(h.database, list(before)) == before
    with closing(sqlite3.connect(h.database)) as connection:
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master")}
        assert (
            not {
                "companies",
                "report_document_metadata",
                "analyst_schema_migrations",
                "d5_document_workspace_id",
                "d5_report_binding_immutable",
            }
            & names
        )
    monkeypatch.undo()
    assert CompanyService(SQLiteCompanyRepository(h.database), workspace_id="demo").list() == []


def test_migration_failure_rolls_back_on_empty_database(tmp_path, monkeypatch):
    database = tmp_path / "documents.db"
    monkeypatch.setattr(
        migrations,
        "MIGRATIONS",
        (
            *migrations.MIGRATIONS,
            (3, "fail", ("INVALID SQL",)),
        ),
    )
    with pytest.raises(sqlite3.OperationalError):
        SQLiteCompanyRepository(database)
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall() == [("documents",)]


@pytest.mark.parametrize("corruption", ["checksum", "future", "gap"])
def test_migration_history_is_checked_before_applying_changes(tmp_path, corruption):
    database = tmp_path / "documents.db"
    SQLiteCompanyRepository(database)
    with closing(sqlite3.connect(database)) as connection, connection:
        if corruption == "checksum":
            connection.execute(
                "UPDATE analyst_schema_migrations SET checksum='broken' WHERE version=1"
            )
        elif corruption == "future":
            connection.execute(
                "INSERT INTO analyst_schema_migrations VALUES (?, 'future', 'x', 'x')",
                (max(v for v, _, _ in migrations.MIGRATIONS) + 1,)
            )
        else:
            connection.execute("DELETE FROM analyst_schema_migrations WHERE version=1")
    before = snapshot(
        database, ["companies", "report_document_metadata", "analyst_schema_migrations"]
    )
    with pytest.raises(RuntimeError, match="migration history"):
        SQLiteCompanyRepository(database)
    assert snapshot(database, list(before)) == before


@pytest.mark.parametrize("operation", ["create", "patch", "bind"])
def test_write_failure_rolls_back_and_service_recovers(tmp_path, operation):
    h = Harness(tmp_path)
    service = CompanyService(SQLiteCompanyRepository(h.database), workspace_id="demo")
    c = service.create(CompanyCreate.model_validate(company_payload()))
    before = snapshot(h.database, ["companies", "report_document_metadata", "documents"])
    table, action = (
        ("report_document_metadata", "INSERT")
        if operation == "bind"
        else ("companies", "UPDATE" if operation == "patch" else "INSERT")
    )
    # AFTER trigger fails after the row has actually been written inside the transaction.
    with closing(sqlite3.connect(h.database)) as connection, connection:
        connection.execute(
            f"CREATE TRIGGER test_fail AFTER {action} ON {table} "
            "BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
        )
    call = {
        "create": lambda: service.create(CompanyCreate.model_validate(company_payload(1))),
        "patch": lambda: service.update(c.company_id, CompanyPatch(name="changed")),
        "bind": lambda: service.bind(
            h.document_id, ReportMetadataInput.model_validate(metadata_payload(c.company_id))
        ),
    }[operation]
    with pytest.raises(sqlite3.IntegrityError, match="injected failure"):
        call()
    assert snapshot(h.database, list(before)) == before
    with closing(sqlite3.connect(h.database)) as connection, connection:
        connection.execute("DROP TRIGGER test_fail")
    assert call() is not None


def test_concurrent_migrations_identity_and_binding_conflicts_are_atomic(tmp_path):
    h = Harness(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        repositories = list(pool.map(lambda _: SQLiteCompanyRepository(h.database), range(4)))
    service = CompanyService(repositories[0], workspace_id="demo")

    def create(_):
        try:
            return service.create(CompanyCreate.model_validate(company_payload()))
        except RegistryConflictError:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        created = list(pool.map(create, range(4)))
    assert sum(item is not None for item in created) == 1
    other = service.create(CompanyCreate.model_validate(company_payload(1)))
    companies = service.list()

    def bind(c):
        try:
            return service.bind(
                h.document_id, ReportMetadataInput.model_validate(metadata_payload(c.company_id))
            )
        except RegistryConflictError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(bind, companies))
    successful = [item for item in results if item is not None]
    assert len(successful) == 1
    assert service.metadata(h.document_id) == successful[0]
    assert other in companies


def test_foreign_keys_and_immutability_prevent_direct_inconsistent_binding(tmp_path):
    h = Harness(tmp_path)
    repo = SQLiteCompanyRepository(h.database)
    service = CompanyService(repo, workspace_id="demo")
    c = service.create(CompanyCreate.model_validate(company_payload()))
    metadata = service.bind(
        h.document_id, ReportMetadataInput.model_validate(metadata_payload(c.company_id))
    )
    with closing(repo._connect()) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"), connection:
            connection.execute("UPDATE report_document_metadata SET company_id='wrong'")
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"), connection:
            connection.execute("DELETE FROM companies WHERE company_id=?", (c.company_id,))
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert service.metadata(h.document_id) == metadata


def test_service_revalidates_constructed_untrusted_inputs(tmp_path):
    service = CompanyService(
        SQLiteCompanyRepository(tmp_path / "documents.db"), workspace_id="demo"
    )
    with pytest.raises(ValidationError):
        service.create(CompanyCreate.model_construct(name="", security_code="bad", exchange="SSE"))
    assert service.list() == []
    with pytest.raises(ValueError):
        CompanyService(service._repository, workspace_id=" ")


def test_migration_log_write_failure_rolls_back_ddl(tmp_path, monkeypatch):
    h = Harness(tmp_path)
    before = snapshot(h.database, ["documents", "revenue_confirmations", "confirmed_revenue_facts"])

    class LogFailureConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            if sql.startswith("INSERT INTO analyst_schema_migrations") and parameters[0] == 2:
                raise sqlite3.OperationalError("injected migration log failure")
            return super().execute(sql, parameters)

    def connect(_):
        connection = sqlite3.connect(h.database, factory=LogFailureConnection)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    monkeypatch.setattr(SQLiteCompanyRepository, "_connect", connect)
    with pytest.raises(sqlite3.OperationalError, match="migration log failure"):
        SQLiteCompanyRepository(h.database)
    assert snapshot(h.database, list(before)) == before
    with closing(sqlite3.connect(h.database)) as connection:
        assert (
            connection.execute("SELECT name FROM sqlite_master WHERE name LIKE 'd5_%'").fetchall()
            == []
        )
        assert (
            connection.execute("SELECT name FROM sqlite_master WHERE name='companies'").fetchall()
            == []
        )
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name='analyst_schema_migrations'"
            ).fetchall()
            == []
        )


def test_version_one_upgrade_failure_retains_prior_version_and_company(tmp_path, monkeypatch):
    h = Harness(tmp_path)
    full_plan = migrations.MIGRATIONS
    monkeypatch.setattr(migrations, "MIGRATIONS", full_plan[:1])
    service = CompanyService(SQLiteCompanyRepository(h.database), workspace_id="demo")
    company = service.create(CompanyCreate.model_validate(company_payload()))
    before = snapshot(h.database, ["companies", "analyst_schema_migrations", "documents"])
    version, name, statements = full_plan[1]
    monkeypatch.setattr(
        migrations,
        "MIGRATIONS",
        (
            full_plan[0],
            (version, name, (*statements, "INVALID UPGRADE SQL")),
        ),
    )
    with pytest.raises(sqlite3.OperationalError):
        SQLiteCompanyRepository(h.database)
    assert snapshot(h.database, list(before)) == before
    monkeypatch.setattr(migrations, "MIGRATIONS", full_plan)
    upgraded = CompanyService(SQLiteCompanyRepository(h.database), workspace_id="demo")
    assert upgraded.get(company.company_id) == company
    assert (
        upgraded.bind(
            h.document_id,
            ReportMetadataInput.model_validate(metadata_payload(company.company_id, 2026)),
        ).report_year
        == 2026
    )
