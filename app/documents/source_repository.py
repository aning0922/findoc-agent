"""Source snapshots and explicit binding corrections in the existing documents DB."""

from contextlib import closing
from datetime import UTC, datetime
import hashlib
import json
import sqlite3
import uuid
from typing import Any

from app.companies.models import RegistryConflictError, ReportMetadata, ReportMetadataInput
from app.companies.sqlite_repository import SQLiteCompanyRepository
from app.documents.models import DocumentRecord
from app.documents.source_models import BindingCorrectionInput, SourceError
from app.rag.parse.models import DocChunk, PDFLayout


def revision_id(document: DocumentRecord, parser_version: str) -> str:
    parts = [document.document_id, document.content_sha256, document.attempt, parser_version]
    return hashlib.sha256(json.dumps(parts, separators=(",", ":")).encode()).hexdigest()


def evidence_digest(page: int, text: str, kind: str) -> str:
    return hashlib.sha256(
        json.dumps([page, text, kind], ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


class SQLiteSourceRepository:
    def __init__(self, registry: SQLiteCompanyRepository) -> None:
        self.registry = registry

    def capture(
        self, document: DocumentRecord, pages: int, parser_version: str, blocks: list[DocChunk]
    ) -> None:
        revision = revision_id(document, parser_version)
        if any(b.page > pages for b in blocks):
            raise SourceError("invalid_evidence_page")
        with closing(self.registry._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            current = conn.execute(
                "SELECT * FROM documents WHERE document_id=? AND workspace_id=?",
                (document.document_id, document.workspace_id),
            ).fetchone()
            if (
                current is None
                or any(
                    current[k] != getattr(document, k)
                    for k in (
                        "content_sha256",
                        "attempt",
                    )
                )
                or current["status"] != "parsing"
            ):
                raise SourceError("source_changed")
            if conn.execute(
                "SELECT 1 FROM document_sources WHERE source_revision=?", (revision,)
            ).fetchone():
                raise SourceError("source_already_captured")
            conn.execute(
                "INSERT INTO document_sources VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                (
                    revision,
                    document.workspace_id,
                    document.document_id,
                    document.content_sha256,
                    document.attempt,
                    parser_version,
                    pages,
                    datetime.now(UTC).isoformat(),
                ),
            )
            for i, block in enumerate(blocks):
                text = block.table_md if block.type == "table" and block.table_md else block.text
                evidence_id = hashlib.sha256(f"{revision}:{i}".encode()).hexdigest()
                conn.execute(
                    "INSERT INTO document_evidence VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        evidence_id,
                        revision,
                        block.page,
                        text,
                        block.type,
                        evidence_digest(block.page, text, block.type),
                    ),
                )
                if block.layout is not None:
                    payload = block.layout.model_dump_json()
                    conn.execute(
                        "INSERT INTO document_evidence_layout VALUES (?, ?, ?)",
                        (evidence_id, payload, hashlib.sha256(payload.encode()).hexdigest()),
                    )

    def source(self, workspace: str, revision: str) -> dict[str, Any]:
        with closing(self.registry._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM document_sources WHERE workspace_id=? AND source_revision=?",
                (workspace, revision),
            ).fetchone()
            if row is None or row["invalidated_at"] is not None:
                raise SourceError("source_changed")
            return dict(row)

    def verify_selection(self, identities: tuple[dict[str, Any], ...]) -> None:
        """One read transaction checks the entire set after individual PDF byte checks."""
        with closing(self.registry._connect()) as conn, conn:
            conn.execute("BEGIN")
            self.verify_selection_in(conn, identities)

    def verify_selection_in(self, conn: sqlite3.Connection,
                            identities: tuple[dict[str, Any], ...]) -> None:
        """Reuse the exact D15 source check inside a caller-owned transaction."""
        for identity in identities:
            workspace, document_id = identity["workspace_id"], identity["document_id"]
            row = conn.execute(
                "SELECT d.status, d.content_sha256, d.attempt, s.parser_version, "
                "s.invalidated_at FROM documents d JOIN document_sources s "
                "ON d.document_id=s.document_id AND d.workspace_id=s.workspace_id "
                "AND d.content_sha256=s.content_sha256 AND d.attempt=s.attempt "
                "WHERE d.workspace_id=? AND d.document_id=? AND s.source_revision=?",
                (workspace, document_id, identity["source_revision"]),
            ).fetchone()
            if (row is None or row["status"] != "ready" or row["invalidated_at"] is not None
                    or any(row[k] != identity[k]
                           for k in ("content_sha256", "attempt", "parser_version"))):
                raise SourceError("selection_changed")
            metadata = self.registry._metadata(conn, workspace, document_id).model_dump(mode="json")
            if any(metadata[k] != identity[k] for k in (
                "company_id", "report_year", "report_type", "period_start", "period_end", "basis",
            )):
                raise SourceError("selection_changed")
            self.registry._company(conn, workspace, identity["company_id"])

    def evidence(self, revision: str, evidence_id: str) -> dict[str, Any]:
        with closing(self.registry._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM document_evidence WHERE source_revision=? AND evidence_id=?",
                (revision, evidence_id),
            ).fetchone()
            if row is None:
                raise SourceError("resource_not_found", 404)
            result = dict(row)
            if result.pop("payload_sha256") != evidence_digest(
                result["physical_page"],
                result["text"],
                result["kind"],
            ):
                raise SourceError("source_evidence_corrupt")
            layout = conn.execute(
                "SELECT payload_json, payload_sha256 FROM document_evidence_layout "
                "WHERE evidence_id=?",
                (evidence_id,),
            ).fetchone()
            result["layout"] = None
            if layout is not None:
                if hashlib.sha256(layout[0].encode()).hexdigest() != layout[1]:
                    raise SourceError("source_evidence_corrupt")
                try:
                    result["layout"] = PDFLayout.model_validate_json(layout[0]).model_dump(
                        mode="json"
                    )
                except ValueError as exc:
                    raise SourceError("source_evidence_corrupt") from exc
            return result

    def page_evidence(self, revision: str, page: int) -> list[dict[str, Any]]:
        """Read and verify only the requested physical page, preserving whole stored blocks."""
        with closing(self.registry._connect()) as conn:
            ids = [row[0] for row in conn.execute(
                'SELECT evidence_id FROM document_evidence '
                'WHERE source_revision=? AND physical_page=? ORDER BY evidence_id',
                (revision, page),
            )]
        return [self.evidence(revision, eid) for eid in ids]

    def evidence_batch(self, revision: str) -> list[dict[str, Any]]:
        """Read the captured snapshot, never retrieve or reparse to fill missing evidence."""
        return [self.evidence(revision, eid) for eid in self.evidence_ids(revision)]

    def evidence_ids(self, revision: str) -> list[str]:
        with closing(self.registry._connect()) as conn:
            return [
                row[0]
                for row in conn.execute(
                    "SELECT evidence_id FROM document_evidence WHERE source_revision=? "
                    "ORDER BY physical_page, evidence_id",
                    (revision,),
                )
            ]

    def origin(self, workspace: str, document_id: str) -> dict[str, Any] | None:
        with closing(self.registry._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM report_source_origins WHERE workspace_id=? AND document_id=?",
                (workspace, document_id),
            ).fetchone()
            return dict(row) if row else None

    def bind_report(
        self,
        workspace: str,
        document_id: str,
        payload: ReportMetadataInput,
        source_url: str | None,
        assessment: dict[str, Any],
    ) -> ReportMetadata:
        with closing(self.registry._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            metadata = self.registry._bind(conn, workspace, document_id, payload)
            existing = conn.execute(
                "SELECT source_url FROM report_source_origins WHERE document_id=?", (document_id,)
            ).fetchone()
            if existing and existing[0] != source_url:
                raise RegistryConflictError
            if not existing:
                conn.execute(
                    "INSERT INTO report_source_origins VALUES (?, ?, ?, ?, ?)",
                    (
                        document_id,
                        workspace,
                        source_url,
                        json.dumps(assessment, ensure_ascii=False),
                        datetime.now(UTC).isoformat(),
                    ),
                )
            return metadata

    def correct(
        self,
        workspace: str,
        document: DocumentRecord,
        payload: BindingCorrectionInput,
    ) -> dict[str, Any]:
        with closing(self.registry._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            self.registry._check_document(conn, workspace, document.document_id)
            self.registry._company(conn, workspace, payload.metadata.company_id)
            old = self.registry._metadata(conn, workspace, document.document_id)
            current = conn.execute(
                "SELECT * FROM documents WHERE document_id=?", (document.document_id,)
            ).fetchone()
            if (
                current["attempt"] != payload.expected_attempt
                or current["content_sha256"] != document.content_sha256
                or current["status"] not in ("ready", "failed")
            ):
                raise SourceError("correction_conflict")
            if all(
                getattr(old, k) == getattr(payload.metadata, k)
                for k in ReportMetadataInput.model_fields
            ):
                raise SourceError("correction_has_no_changes")
            now = datetime.now(UTC).isoformat()
            new = ReportMetadata.model_validate(
                {
                    **payload.metadata.model_dump(),
                    "workspace_id": workspace,
                    "document_id": document.document_id,
                    "status": "pending_verification",
                    "created_at": now,
                }
            )
            sequence = conn.execute(
                "SELECT coalesce(max(sequence), 0)+1 "
                "FROM report_binding_corrections WHERE document_id=?",
                (document.document_id,),
            ).fetchone()[0]
            audit = dict(
                correction_id=str(uuid.uuid4()),
                sequence=sequence,
                document_id=document.document_id,
                reason=payload.reason,
                action_kind="explicit_user_request",
                old_attempt=current["attempt"],
                new_attempt=current["attempt"] + 1,
                created_at=now,
                old_metadata=json.loads(old.model_dump_json()),
                new_metadata=json.loads(new.model_dump_json()),
            )
            conn.execute(
                "INSERT INTO report_binding_corrections VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    audit["correction_id"],
                    workspace,
                    document.document_id,
                    sequence,
                    old.model_dump_json(),
                    new.model_dump_json(),
                    payload.reason,
                    audit["action_kind"],
                    audit["old_attempt"],
                    audit["new_attempt"],
                    now,
                ),
            )
            conn.execute(
                "UPDATE document_sources SET invalidated_at=? "
                "WHERE workspace_id=? AND document_id=? AND invalidated_at IS NULL",
                (now, workspace, document.document_id),
            )
            conn.execute(
                "UPDATE index_publications SET state='revoked' "
                "WHERE workspace_id=? AND document_id=? AND state='active'",
                (workspace, document.document_id),
            )
            conn.execute(
                "UPDATE documents SET status='failed', failed_stage='queued', "
                "error_code='SOURCE_BINDING_CORRECTED', "
                "safe_error_message='绑定已纠错，请显式重试并重新核对', "
                "attempt=attempt+1, updated_at=? WHERE workspace_id=? AND document_id=?",
                (now, workspace, document.document_id),
            )
            # Readback is inside the transaction so trigger/readback failures roll back everything.
            if self.registry._metadata(conn, workspace, document.document_id) != new:
                raise SourceError("correction_readback_failed", 500)
            return audit

    def request_reindex(self, workspace: str, document_id: str, expected_attempt: int) -> None:
        """Explicit ready-to-failed invalidation, followed by the existing retry workflow."""
        with closing(self.registry._connect()) as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            changed = conn.execute(
                "UPDATE documents SET status='failed', failed_stage='queued', "
                "error_code='REINDEX_REQUESTED', safe_error_message='已请求重建来源索引', updated_at=? "
                "WHERE workspace_id=? AND document_id=? AND attempt=? AND status='ready'",
                (datetime.now(UTC).isoformat(), workspace, document_id, expected_attempt),
            )
            if changed.rowcount != 1:
                raise SourceError('reindex_conflict')
            conn.execute("UPDATE document_sources SET invalidated_at=? "
                         "WHERE workspace_id=? AND document_id=? AND invalidated_at IS NULL",
                         (datetime.now(UTC).isoformat(), workspace, document_id))
            conn.execute("UPDATE index_publications SET state='revoked' "
                         "WHERE workspace_id=? AND document_id=? AND state='active'",
                         (workspace, document_id))

    def history(self, workspace: str, document_id: str) -> list[dict[str, Any]]:
        with closing(self.registry._connect()) as conn:
            self.registry._check_document(conn, workspace, document_id)
            rows = conn.execute(
                "SELECT * FROM report_binding_corrections WHERE workspace_id=? "
                "AND document_id=? ORDER BY sequence",
                (workspace, document_id),
            ).fetchall()
            return [
                {
                    k: (json.loads(v) if k.endswith("_json") else v)
                    for k, v in dict(row).items()
                    if k != "workspace_id"
                }
                for row in rows
            ]
