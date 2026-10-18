"""Finite SQLite history repository; all GET paths are database-only."""

import base64
from contextlib import closing
from dataclasses import asdict
from datetime import UTC, datetime
import fcntl
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3
from typing import Any, cast
import uuid

from app.companies.sqlite_repository import SQLiteCompanyRepository
from app.documents.preparation import PreparedDocumentSelection
from app.documents.source_models import SourceError
from app.documents.source_repository import SQLiteSourceRepository
from app.research.models import Envelope, Result, canonical, request_sha, safe_error, sha


class HistoryError(Exception):
    def __init__(self, code: str, status: int = 503):
        super().__init__(code)
        self.code, self.status = code, status


class ResearchOwner:
    """Single synchronous writer process. OS releases flock on crash; no durable task claim."""

    def __init__(self, root: Path):
        self.file = (root / "research-execution.lock").open("a+b")
        try:
            fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise RuntimeError("research_runtime_already_owned") from None

    def close(self) -> None:
        self.file.close()


class ResearchRepository:
    def __init__(self, registry: SQLiteCompanyRepository, workspace: str):
        self.registry = registry
        self.workspace = workspace
        self.sources = SQLiteSourceRepository(registry)

    def _decode(self, row: sqlite3.Row) -> Envelope:
        try:
            if sha(row["payload"]) != row["payload_sha"]:
                raise ValueError("digest")
            value = Envelope.model_validate_json(row["payload"])
            if any(
                getattr(value, k) != row[k]
                for k in ("run_id", "workspace_id", "operation_id", "created_at", "status")
            ):
                raise ValueError("identity")
            if request_sha(value.document_ids, value.query) != row["request_sha"]:
                raise ValueError("request")
            if canonical(value.model_dump()) != row["payload"]:
                raise ValueError("noncanonical")
            return value
        except (ValueError, TypeError, KeyError):
            raise HistoryError("history_integrity_error") from None

    def _row(
        self, conn: sqlite3.Connection, identity: str, by_operation: bool = False
    ) -> sqlite3.Row:
        column = "operation_id" if by_operation else "run_id"
        row = conn.execute(
            f"SELECT * FROM research_runs WHERE workspace_id=? AND {column}=?",
            (self.workspace, identity),
        ).fetchone()
        if row is None:
            raise HistoryError("resource_not_found", 404)
        return cast(sqlite3.Row, row)

    def get(self, identity: str, *, by_operation: bool = False) -> Envelope:
        with closing(self.registry._connect()) as conn:
            return self._decode(self._row(conn, identity, by_operation))

    def existing(self, op: str, ids: list[str], query: str) -> Envelope | None:
        try:
            record = self.get(op, by_operation=True)
        except HistoryError as exc:
            if exc.status == 404:
                return None
            raise
        if request_sha(record.document_ids, record.query) != request_sha(ids, query):
            raise HistoryError("operation_request_conflict", 409)
        return record

    def register(
        self, op: str, selection: PreparedDocumentSelection, config: dict[str, str | int]
    ) -> tuple[Envelope, bool]:
        value = Envelope.model_validate(
            dict(
                execution_config=config,
                run_id=str(uuid.uuid4()),
                operation_id=op,
                workspace_id=self.workspace,
                query=selection.query,
                document_ids=list(selection.document_ids),
                selection_id=selection.selection_id,
                documents=[asdict(d) for d in selection.documents],
                created_at=datetime.now(UTC).isoformat(),
            )
        )
        with closing(self.registry._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM research_runs WHERE workspace_id=? AND operation_id=?",
                (self.workspace, op),
            ).fetchone()
            if row is not None:
                old = self._decode(row)
                if request_sha(old.document_ids, old.query) != request_sha(
                    value.document_ids, value.query
                ):
                    raise HistoryError("operation_request_conflict", 409)
                return old, False
            self.sources.verify_selection_in(conn, tuple(d.model_dump() for d in value.documents))
            payload = canonical(value.model_dump())
            conn.execute(
                """INSERT INTO research_runs
                (run_id,workspace_id,operation_id,request_sha,created_at,status,payload,payload_sha)
                VALUES (?,?,?,?,?,?,?,?)""",
                (
                    value.run_id,
                    self.workspace,
                    op,
                    request_sha(value.document_ids, value.query),
                    value.created_at,
                    value.status,
                    payload,
                    sha(payload),
                ),
            )
        return value, True

    def _finish(self, conn: sqlite3.Connection, old: Envelope, result: Result) -> Envelope:
        value = Envelope.model_validate(
            {
                **old.model_dump(),
                "status": result.outcome,
                "ended_at": datetime.now(UTC).isoformat(),
                "result": result.model_dump(),
            }
        )
        payload = canonical(value.model_dump())
        changed = conn.execute(
            """UPDATE research_runs SET status=?,payload=?,payload_sha=?
            WHERE workspace_id=? AND run_id=? AND status='running'""",
            (value.status, payload, sha(payload), self.workspace, old.run_id),
        )
        if changed.rowcount != 1:
            raise HistoryError("run_already_terminal", 409)
        # Readback shares the transaction, including triggers/integrity checks.
        return self._decode(self._row(conn, old.run_id))

    def finish(self, run_id: str, result: Result) -> Envelope:
        with closing(self.registry._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            old = self._decode(self._row(conn, run_id))
            if old.status != "running":
                raise HistoryError("run_already_terminal", 409)
            if result.outcome != "system_error":
                try:
                    self.sources.verify_selection_in(
                        conn, tuple(d.model_dump() for d in old.documents)
                    )
                except SourceError:
                    result = safe_error(old, "source_changed")
            return self._finish(conn, old, result)

    def recover_interrupted(self) -> int:
        """Startup only, under ResearchOwner, before accepting requests. Never run from GET."""
        with closing(self.registry._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT * FROM research_runs WHERE workspace_id=? AND status='running'",
                (self.workspace,),
            ).fetchall()
            for row in rows:
                old = self._decode(row)
                self._finish(conn, old, safe_error(old, "interrupted"))
            return len(rows)

    def public(self, value: Envelope) -> dict[str, Any]:
        # This projection is advisory DB validity at read time. PDF access still checks D6 bytes.
        with closing(self.registry._connect()) as conn, conn:
            conn.execute("BEGIN")
            states = []
            for doc in value.documents:
                try:
                    self.sources.verify_selection_in(conn, (doc.model_dump(),))
                    status = "current_at_read"
                except SourceError:
                    status = "expired"
                states.append(
                    dict(
                        document_id=doc.document_id,
                        source_revision=doc.source_revision,
                        status=status,
                    )
                )
        return {
            **value.model_dump(),
            "integrity_sha256": sha(canonical(value.model_dump())),
            "historical_snapshot": True,
            "source_states": states,
        }

    def focus(self, value: Envelope) -> dict[str, Any]:
        """Independent GET projection: no history writes, retrieval, models or facts."""
        from app.research.answer_focus import project_focus

        with closing(self.registry._connect()) as conn, conn:
            conn.execute("BEGIN")
            identities = tuple(d.model_dump() for d in value.documents)
            self.sources.verify_selection_in(conn, identities)
            names = {d.company_id: self.registry._company(conn, self.workspace, d.company_id).name
                     for d in value.documents}
            result = project_focus(value, names, lambda c: self.sources.page_evidence(
                c.source_revision, c.physical_page,
            ))
            self.sources.verify_selection_in(conn, identities)
            return result

    def page(
        self, limit: int = 20, cursor: str | None = None, company_id: str | None = None
    ) -> dict[str, Any]:
        if not 1 <= limit <= 50:
            raise HistoryError("invalid_cursor_or_limit", 422)
        with closing(self.registry._connect()) as conn, conn:
            conn.execute("BEGIN")
            secret = conn.execute("SELECT secret FROM research_cursor_key WHERE id=1").fetchone()[0]
            last: list[str] | None = None
            ceiling = conn.execute(
                "SELECT coalesce(max(sequence),0) FROM research_runs WHERE workspace_id=?",
                (self.workspace,),
            ).fetchone()[0]
            if cursor:
                try:
                    if len(cursor) > 2048:
                        raise ValueError()
                    encoded, signature = cursor.split(".")
                    expected = hmac.new(secret, encoded.encode(), hashlib.sha256).hexdigest()
                    if not hmac.compare_digest(signature, expected):
                        raise ValueError()
                    data = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
                    if (
                        set(data) != {"v", "workspace", "company", "ceiling", "last"}
                        or data["v"] != 1
                        or data["workspace"] != self.workspace
                        or data["company"] != company_id
                        or type(data["ceiling"]) is not int
                        or data["ceiling"] < 0
                        or data["ceiling"] > ceiling
                        or not isinstance(data["last"], list)
                        or len(data["last"]) != 2
                        or any(not isinstance(s, str) for s in data["last"])
                    ):
                        raise ValueError()
                    ceiling, last = data["ceiling"], data["last"]
                except (ValueError, TypeError, KeyError):
                    raise HistoryError("invalid_cursor_or_limit", 422) from None
            sql = "SELECT * FROM research_runs WHERE workspace_id=? AND sequence<=?"
            args: list[Any] = [self.workspace, ceiling]
            if company_id:
                sql += " AND EXISTS(SELECT 1 FROM json_each(payload, '$.documents') WHERE json_extract(value,'$.company_id')=?)"
                args.append(company_id)
            if last:
                sql += " AND (created_at,run_id)<(?,?)"
                args.extend(last)
            sql += " ORDER BY created_at DESC, run_id DESC LIMIT ?"
            args.append(limit + 1)
            rows = conn.execute(sql, args).fetchall()
            values = [self._decode(row) for row in rows[:limit]]
            next_cursor = None
            if len(rows) > limit:
                tail = values[-1]
                data = dict(
                    v=1,
                    workspace=self.workspace,
                    company=company_id,
                    ceiling=ceiling,
                    last=[tail.created_at, tail.run_id],
                )
                encoded = base64.urlsafe_b64encode(canonical(data).encode()).decode().rstrip("=")
                next_cursor = (
                    encoded + "." + hmac.new(secret, encoded.encode(), hashlib.sha256).hexdigest()
                )
            items = [
                {
                    k: v.model_dump()[k]
                    for k in (
                        "run_id",
                        "operation_id",
                        "query",
                        "created_at",
                        "ended_at",
                        "document_ids",
                        "documents",
                        "status",
                    )
                }
                for v in values
            ]
            return dict(schema_version="research-history-v1", items=items, next_cursor=next_cursor)
