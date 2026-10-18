"""Scoped registry and immutable report bindings in the existing documents database."""

from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
import sqlite3
import json
import uuid

from app.companies.migrations import migrate
from app.companies.models import (
    Company,
    CompanyCreate,
    CompanyPatch,
    RegistryConflictError,
    RegistryNotFoundError,
    ReportMetadata,
    ReportMetadataInput,
)
from app.documents.sqlite_repository import SQLiteDocumentRepository


class SQLiteCompanyRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        # Reuse the sole legacy document DDL on both empty and existing databases.
        SQLiteDocumentRepository(database_path)
        with closing(self._connect()) as connection:
            migrate(connection)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _company(connection: sqlite3.Connection, workspace: str, company_id: str) -> Company:
        row = connection.execute(
            "SELECT * FROM companies WHERE workspace_id = ? AND company_id = ?",
            (workspace, company_id),
        ).fetchone()
        if row is None:
            raise RegistryNotFoundError
        return Company.model_validate(dict(row))

    def create(self, workspace: str, payload: CompanyCreate) -> Company:
        company_id, now = str(uuid.uuid4()), datetime.now(UTC).isoformat()
        with closing(self._connect()) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    connection.execute(
                        "INSERT INTO companies VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            company_id,
                            workspace,
                            payload.name,
                            payload.security_code,
                            payload.exchange,
                            payload.country,
                            now,
                            now,
                        ),
                    )
                except sqlite3.IntegrityError as exc:
                    # Only a business identity duplicate maps to a public conflict.
                    if connection.execute(
                        "SELECT 1 FROM companies WHERE workspace_id=? AND exchange=? "
                        "AND security_code=?",
                        (workspace, payload.exchange, payload.security_code),
                    ).fetchone():
                        raise RegistryConflictError from exc
                    raise
                return self._company(connection, workspace, company_id)

    def get(self, workspace: str, company_id: str) -> Company:
        with closing(self._connect()) as connection:
            return self._company(connection, workspace, company_id)

    def list(self, workspace: str) -> list[Company]:
        with closing(self._connect()) as connection:
            return [
                Company.model_validate(dict(row))
                for row in connection.execute(
                    "SELECT * FROM companies WHERE workspace_id = ? ORDER BY created_at, company_id",
                    (workspace,),
                )
            ]

    def update(self, workspace: str, company_id: str, payload: CompanyPatch) -> Company:
        with closing(self._connect()) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                current = self._company(connection, workspace, company_id)
                updated = CompanyCreate.model_validate(
                    {
                        **{key: getattr(current, key) for key in CompanyCreate.model_fields},
                        **payload.model_dump(exclude_unset=True),
                    }
                )
                duplicate = connection.execute(
                    "SELECT 1 FROM companies WHERE workspace_id=? AND exchange=? "
                    "AND security_code=? AND company_id != ?",
                    (workspace, updated.exchange, updated.security_code, company_id),
                ).fetchone()
                if duplicate:
                    raise RegistryConflictError
                connection.execute(
                    "UPDATE companies SET name=?, security_code=?, exchange=?, country=?, "
                    "updated_at=? WHERE workspace_id=? AND company_id=?",
                    (
                        updated.name,
                        updated.security_code,
                        updated.exchange,
                        updated.country,
                        datetime.now(UTC).isoformat(),
                        workspace,
                        company_id,
                    ),
                )
                return self._company(connection, workspace, company_id)

    @staticmethod
    def _check_document(connection: sqlite3.Connection, workspace: str, document_id: str) -> None:
        if (
            connection.execute(
                "SELECT 1 FROM documents WHERE workspace_id=? AND document_id=?",
                (workspace, document_id),
            ).fetchone()
            is None
        ):
            raise RegistryNotFoundError

    def bind(
        self, workspace: str, document_id: str, payload: ReportMetadataInput
    ) -> ReportMetadata:
        with closing(self._connect()) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                return self._bind(connection, workspace, document_id, payload)

    def _bind(
        self,
        connection: sqlite3.Connection,
        workspace: str,
        document_id: str,
        payload: ReportMetadataInput,
    ) -> ReportMetadata:
        self._check_document(connection, workspace, document_id)
        self._company(connection, workspace, payload.company_id)
        row = connection.execute(
            "SELECT * FROM report_document_metadata WHERE workspace_id=? AND document_id=?",
            (workspace, document_id),
        ).fetchone()
        if row is not None:
            metadata = self._metadata(connection, workspace, document_id)
            if any(
                getattr(metadata, key) != getattr(payload, key)
                for key in ReportMetadataInput.model_fields
            ):
                raise RegistryConflictError
            return metadata
        connection.execute(
            "INSERT INTO report_document_metadata VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                document_id,
                workspace,
                payload.company_id,
                payload.report_year,
                payload.report_type,
                payload.basis,
                payload.period_start.isoformat(),
                payload.period_end.isoformat(),
                "pending_verification",
                datetime.now(UTC).isoformat(),
            ),
        )
        return self._metadata(connection, workspace, document_id)

    @staticmethod
    def _metadata(
        connection: sqlite3.Connection, workspace: str, document_id: str
    ) -> ReportMetadata:
        row = connection.execute(
            "SELECT * FROM report_document_metadata WHERE workspace_id=? AND document_id=?",
            (workspace, document_id),
        ).fetchone()
        if row is None:
            raise RegistryNotFoundError
        correction = connection.execute(
            "SELECT new_metadata_json FROM report_binding_corrections "
            "WHERE workspace_id=? AND document_id=? ORDER BY sequence DESC LIMIT 1",
            (workspace, document_id),
        ).fetchone()
        return ReportMetadata.model_validate(json.loads(correction[0]) if correction else dict(row))

    def metadata(self, workspace: str, document_id: str) -> ReportMetadata:
        with closing(self._connect()) as connection:
            self._check_document(connection, workspace, document_id)
            return self._metadata(connection, workspace, document_id)
