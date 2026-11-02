"""Transactional preferences on the company's existing SQLite connection factory."""
from __future__ import annotations

from contextlib import closing
from datetime import UTC, datetime
import json
import sqlite3
from uuid import uuid4

from app.companies.sqlite_repository import SQLiteCompanyRepository
from app.memory.models import (
    CreateMemoryRequest, DeleteMemoryRequest, MemoryError, MemoryItem, MemoryList,
    MemoryOperation, PatchMemoryRequest, allowed_value,
)
from app.research.models import canonical, operation, sha

SCOPE = ("demo", "local_operator")


class MemoryRepository:
    """Server-owned demo scope. Constructor does not migrate or open a database."""

    def __init__(self, companies: SQLiteCompanyRepository) -> None:
        self._connect = companies._connect

    @staticmethod
    def _item(row: sqlite3.Row) -> MemoryItem:
        data = dict(row)
        del data["workspace_id"], data["principal_id"]
        return MemoryItem.model_validate(data)

    @staticmethod
    def _operation(row: sqlite3.Row) -> MemoryOperation:
        return MemoryOperation.model_validate({
            "operation_id": row["operation_id"], "memory_id": row["memory_id"],
            "kind": row["kind"], "revision": row["revision"],
            "resource_deleted": bool(row["resource_deleted"]), "created_at": row["created_at"],
        })

    @staticmethod
    def _find(connection: sqlite3.Connection, memory_id: str) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT * FROM memory_items WHERE workspace_id=? AND principal_id=? AND memory_id=?",
            (*SCOPE, memory_id),
        ).fetchone()

    @staticmethod
    def _find_op(connection: sqlite3.Connection, op: str) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT * FROM memory_operations WHERE workspace_id=? AND principal_id=? "
            "AND operation_id=?", (*SCOPE, op),
        ).fetchone()

    @staticmethod
    def _missing(connection: sqlite3.Connection, memory_id: str) -> None:
        deleted = connection.execute(
            "SELECT 1 FROM memory_operations WHERE workspace_id=? AND principal_id=? "
            "AND memory_id=? AND resource_deleted=1", (*SCOPE, memory_id),
        ).fetchone()
        raise MemoryError(410 if deleted else 404,
                          "memory_deleted" if deleted else "resource_not_found")

    def list(self) -> MemoryList:
        with closing(self._connect()) as connection:
            # A read transaction gives items and generation a single consistent snapshot.
            connection.execute("BEGIN")
            rows = connection.execute(
                "SELECT * FROM memory_items WHERE workspace_id=? AND principal_id=? "
                "ORDER BY key", SCOPE,
            ).fetchall()
            generation = connection.execute(
                "SELECT generation FROM memory_context_generation "
                "WHERE workspace_id=? AND principal_id=?", SCOPE,
            ).fetchone()
            return MemoryList(items=[self._item(row) for row in rows],
                              generation=generation[0] if generation else 0)

    def get(self, memory_id: str) -> MemoryItem:
        operation(memory_id)
        with closing(self._connect()) as connection:
            row = self._find(connection, memory_id)
            if row is None:
                self._missing(connection, memory_id)
            return self._item(row)

    def get_operation(self, operation_id: str) -> MemoryOperation:
        operation(operation_id)
        with closing(self._connect()) as connection:
            row = self._find_op(connection, operation_id)
            if row is None:
                raise MemoryError(404, "resource_not_found")
            return self._operation(row)

    @staticmethod
    def _exclude_source(connection: sqlite3.Connection, source_turn_id: str | None,
                        *, validate: bool = False) -> None:
        if source_turn_id is None:
            return
        if validate:
            row = connection.execute(
                "SELECT payload FROM conversation_turns WHERE workspace_id=? AND turn_id=?",
                (SCOPE[0], source_turn_id),
            ).fetchone()
            if row is None:
                raise MemoryError(404, "source_turn_not_found")
            # Only the user utterance is provenance, not the model result or PDF.
            if not isinstance(json.loads(row["payload"]).get("user_text"), str):
                raise MemoryError(503, "memory_integrity_error")
        connection.execute(
            "INSERT OR IGNORE INTO memory_context_exclusions VALUES (?,?,?,?)",
            (*SCOPE, source_turn_id, "memory_source"),
        )

    def recall_context(self) -> MemoryList:
        """Fresh snapshot on every call; Graph injects at most five allowed preferences."""
        return self.list()

    def excluded_source_turn_ids(self) -> frozenset[str]:
        with closing(self._connect()) as connection:
            return frozenset(row[0] for row in connection.execute(
                "SELECT turn_id FROM memory_context_exclusions "
                "WHERE workspace_id=? AND principal_id=?", SCOPE,
            ))

    @staticmethod
    def detach_source_turns_in(connection: sqlite3.Connection, turn_ids: list[str]) -> None:
        """Backend calls inside conversation deletion transaction before deleting turns.

        Changes provenance only, never revisions or committed conversation payloads.
        Exclusions retain only UUIDs to stop old sources reentering fresh context.
        """
        for turn_id in turn_ids:
            operation(turn_id)
            connection.execute(
                "UPDATE memory_items SET source_turn_id=NULL WHERE workspace_id=? "
                "AND principal_id=? AND source_turn_id=?", (*SCOPE, turn_id),
            )

    @staticmethod
    def _changed(connection: sqlite3.Connection) -> None:
        connection.execute(
            "INSERT INTO memory_context_generation VALUES (?,?,1) "
            "ON CONFLICT(workspace_id,principal_id) DO UPDATE SET generation=generation+1", SCOPE,
        )

    def _replay(self, connection: sqlite3.Connection, old: sqlite3.Row,
                request_sha: str) -> MemoryItem | MemoryOperation:
        if old["request_sha"] != request_sha:
            raise MemoryError(409, "operation_request_conflict")
        if old["kind"] == "delete_memory":
            return self._operation(old)
        if old["resource_deleted"]:
            raise MemoryError(410, "memory_deleted")
        item = self._find(connection, old["memory_id"])
        if item is None:
            raise MemoryError(503, "memory_integrity_error")
        if item["revision"] != old["revision"]:
            raise MemoryError(409, "memory_operation_superseded")
        return self._item(item)

    def mutate(self, kind: str, request: CreateMemoryRequest | PatchMemoryRequest |
               DeleteMemoryRequest, memory_id: str | None = None
               ) -> tuple[MemoryItem | MemoryOperation, bool]:
        """Returns (committed readback, replayed); no model, source IO, or hidden retry."""
        expected_type = {"create_memory": CreateMemoryRequest, "update_memory": PatchMemoryRequest,
                         "delete_memory": DeleteMemoryRequest}.get(kind)
        if expected_type is None or not isinstance(request, expected_type):
            raise ValueError("invalid_memory_action")
        if memory_id is not None:
            operation(memory_id)
        if (kind == "create_memory") != (memory_id is None):
            raise ValueError("invalid_memory_target")
        request_sha = sha(canonical({"kind": kind, "memory_id": memory_id,
                                     "request": request.model_dump(exclude={"operation_id"})}))
        replayed = False
        with closing(self._connect()) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                old = self._find_op(connection, request.operation_id)
                if old is not None:
                    self._replay(connection, old, request_sha)
                    replayed = True
                else:
                    self._mutate_in(connection, kind, request, memory_id, request_sha)
        # Read after commit. A failed commit/readback must never expose an in-memory value.
        with closing(self._connect()) as connection:
            connection.execute("BEGIN")
            old = self._find_op(connection, request.operation_id)
            if old is None:
                raise MemoryError(503, "memory_save_failed")
            return self._replay(connection, old, request_sha), replayed

    def _mutate_in(self, connection: sqlite3.Connection, kind: str,
                   request: CreateMemoryRequest | PatchMemoryRequest | DeleteMemoryRequest,
                   memory_id: str | None, request_sha: str) -> None:
        now = datetime.now(UTC).isoformat()
        if isinstance(request, CreateMemoryRequest):
            if connection.execute(
                "SELECT 1 FROM memory_items WHERE workspace_id=? AND principal_id=? "
                "AND type=? AND key=?", (*SCOPE, request.type, request.key),
            ).fetchone():
                raise MemoryError(409, "memory_key_conflict")
            self._exclude_source(connection, request.source_turn_id, validate=True)
            memory_id, revision = str(uuid4()), 1
            connection.execute(
                "INSERT INTO memory_items VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (*SCOPE, memory_id, request.type, request.key, request.value,
                 request.source_turn_id, revision, now, now, now),
            )
        else:
            current = self._find(connection, memory_id)
            if current is None:
                self._missing(connection, memory_id)
            self._item(current)  # Fail closed on a corrupted row before any mutation.
            if current["revision"] != request.expected_revision:
                raise MemoryError(409, "memory_revision_conflict")
            revision = current["revision"] + 1
            self._exclude_source(connection, current["source_turn_id"])
            if isinstance(request, PatchMemoryRequest):
                try:
                    allowed_value(current["key"], request.value)
                except ValueError as exc:
                    raise MemoryError(422, "invalid_memory_value") from exc
                connection.execute(
                    "UPDATE memory_items SET value=?,revision=?,confirmed_at=?,updated_at=? "
                    "WHERE workspace_id=? AND principal_id=? AND memory_id=?",
                    (request.value, revision, now, now, *SCOPE, memory_id),
                )
            else:
                connection.execute(
                    "DELETE FROM memory_items WHERE workspace_id=? AND principal_id=? "
                    "AND memory_id=?", (*SCOPE, memory_id),
                )
                connection.execute(
                    "UPDATE memory_operations SET resource_deleted=1 WHERE workspace_id=? "
                    "AND principal_id=? AND memory_id=?", (*SCOPE, memory_id),
                )
        connection.execute(
            "INSERT INTO memory_operations VALUES (?,?,?,?,?,?,?,?,?)",
            (*SCOPE, request.operation_id, kind, request_sha, memory_id, revision,
             int(kind == "delete_memory"), now),
        )
        connection.execute(
            "INSERT INTO memory_events VALUES (?,?,?,?,?,?,?,?)",
            (*SCOPE, str(uuid4()), memory_id, kind, revision, request.operation_id, now),
        )
        self._changed(connection)
