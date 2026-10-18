"""Additive, versioned D5 migrations; never modify legacy rows or constraints."""

from datetime import UTC, datetime
import hashlib
import sqlite3

from app.agent.financial_fact_schema import FINANCIAL_FACT_MIGRATION
from app.reports.schema import REPORT_MIGRATION
from app.research.schema import RESEARCH_MIGRATION
from app.research.task_schema import TASK_MIGRATION
from app.rag.publication_schema import INDEX_PUBLICATION_MIGRATION
from app.documents.source_schema import LAYOUT_MIGRATION, SOURCE_MIGRATION

MIGRATIONS: tuple[tuple[int, str, tuple[str, ...]], ...] = (
    (
        1,
        "company_registry",
        (
            """CREATE TABLE companies (
            company_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL CHECK(length(trim(workspace_id)) > 0),
            name TEXT NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 200),
            security_code TEXT NOT NULL CHECK(length(security_code) BETWEEN 1 AND 32
                AND security_code = upper(security_code)),
            exchange TEXT NOT NULL CHECK(length(exchange) BETWEEN 1 AND 32
                AND exchange = upper(exchange)),
            country TEXT NOT NULL CHECK(length(country) = 2),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(workspace_id, exchange, security_code),
            UNIQUE(workspace_id, company_id)
        )""",
        ),
    ),
    (
        2,
        "report_metadata",
        (
            "CREATE UNIQUE INDEX d5_document_workspace_id ON documents(workspace_id, document_id)",
            """CREATE TABLE report_document_metadata (
            document_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            company_id TEXT NOT NULL,
            report_year INTEGER NOT NULL CHECK(typeof(report_year) = 'integer'
                AND report_year BETWEEN 1 AND 9999),
            report_type TEXT NOT NULL CHECK(report_type IN ('annual','semiannual','quarterly')),
            basis TEXT NOT NULL CHECK(basis IN ('PRC_GAAP','IFRS','US_GAAP','unknown')),
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status = 'pending_verification'),
            created_at TEXT NOT NULL,
            CHECK(length(period_start) = 10 AND length(period_end) = 10
                AND period_start <= period_end
                AND substr(period_start, 1, 4) = printf('%04d', report_year)
                AND substr(period_end, 1, 4) = printf('%04d', report_year)),
            FOREIGN KEY(workspace_id, document_id)
                REFERENCES documents(workspace_id, document_id),
            FOREIGN KEY(workspace_id, company_id)
                REFERENCES companies(workspace_id, company_id)
        )""",
            "CREATE INDEX d5_reports_by_company ON report_document_metadata(workspace_id, company_id)",
            """CREATE TRIGGER d5_report_binding_immutable
            BEFORE UPDATE ON report_document_metadata
            BEGIN SELECT RAISE(ABORT, 'report binding is immutable'); END""",
        ),
    ),
    SOURCE_MIGRATION,
    LAYOUT_MIGRATION,
    FINANCIAL_FACT_MIGRATION,
    INDEX_PUBLICATION_MIGRATION,
    RESEARCH_MIGRATION,
    TASK_MIGRATION,
    REPORT_MIGRATION,
)


def migrate(connection: sqlite3.Connection) -> None:
    """One write transaction includes all DDL and log entries; failures roll back DDL.

    The existing documents repository must initialize its own schema first. Use
    execute, never executescript (which commits a pending transaction implicitly).
    Version/checksum mismatches fail closed rather than blessing schema drift.
    """
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("""CREATE TABLE IF NOT EXISTS analyst_schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )""")
        existing = connection.execute(
            "SELECT version, name, checksum FROM analyst_schema_migrations ORDER BY version"
        ).fetchall()
        expected = {
            version: (name, hashlib.sha256("\n".join(statements).encode()).hexdigest())
            for version, name, statements in MIGRATIONS
        }
        versions = [row[0] for row in existing]
        if versions != list(range(1, len(versions) + 1)):
            raise RuntimeError("non-contiguous analyst migration history")
        for version, name, checksum in existing:
            if expected.get(version) != (name, checksum):
                raise RuntimeError("unsupported analyst migration history")
        for version, name, statements in MIGRATIONS:
            if version in versions:
                continue
            for statement in statements:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO analyst_schema_migrations VALUES (?, ?, ?, ?)",
                (version, name, expected[version][1], datetime.now(UTC).isoformat()),
            )
