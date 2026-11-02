"""SQLite authority for threads, operation receipts and once-registered turns.

No graph or provider is invoked here. Short transactions fence every mutation;
all history methods open query-only snapshots and never repair state.
"""

import base64
from collections.abc import Callable
from contextlib import closing, contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
import json
import sqlite3
from typing import Any, Iterator
from uuid import uuid4

from pydantic import ValidationError

from app.companies.sqlite_repository import SQLiteCompanyRepository
from app.conversations.models import (
    ConversationDetail, ConversationList, ConversationSummary, CreateConversationRequest,
    CreateTurnRequest, DeleteRequest, Identity, OperationRecord, ResolvedQuery, SourceState,
    Turn, TurnData, TurnResult, TurnStatus, Usage, error_result, validate_quote,
)
from app.documents.preparation import PreparedDocumentSelection, SelectedDocumentIdentity
from app.documents.source_models import SourceError
from app.documents.source_repository import SQLiteSourceRepository
from app.rag.retriever import TrustedContext
from app.research.models import canonical, operation, sha


class ConversationError(Exception):
    def __init__(self, code: str, status: int = 503):
        super().__init__(code)
        self.code, self.status = code, status


def now() -> str:
    return datetime.now(UTC).isoformat()


def request_hash(kind: str, target: str | None, payload: dict[str, Any]) -> str:
    return sha(canonical({"kind": kind, "target": target,
                          **{k: v for k, v in payload.items() if k != "operation_id"}}))


class ConversationRepository:
    def __init__(self, registry: SQLiteCompanyRepository, workspace: str):
        if not workspace.strip():
            raise ValueError("workspace_required")
        self.registry = registry
        self.workspace = workspace
        self.sources = SQLiteSourceRepository(registry)

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        with closing(self.registry._connect()) as conn, conn:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            yield conn

    def _op(self, conn: sqlite3.Connection, op: str) -> tuple[OperationRecord, str] | None:
        row = conn.execute(
            "SELECT * FROM conversation_operations WHERE workspace_id=? AND operation_id=?",
            (self.workspace, op),
        ).fetchone()
        if row is None:
            return None
        try:
            value = OperationRecord.model_validate_json(row["payload"])
            expected = value.model_dump()
            if sha(row["payload"]) != row["payload_sha"] or canonical(expected) != row["payload"]:
                raise ValueError("digest")
            for key in ("operation_id", "kind", "conversation_id", "turn_id", "status",
                        "created_at", "ended_at", "error_code"):
                if expected[key] != row[key]:
                    raise ValueError("identity")
            if (int(value.resource_deleted) != row["resource_deleted"]
                    or len(row["request_sha"]) != 64):
                raise ValueError("identity")
            return value, row["request_sha"]
        except (ValueError, TypeError, KeyError):
            raise ConversationError("conversation_integrity_error") from None

    def _existing(self, conn: sqlite3.Connection, op: str, digest: str) -> OperationRecord | None:
        found = self._op(conn, op)
        if found is None:
            return None
        value, saved = found
        if saved != digest:
            raise ConversationError("operation_request_conflict", 409)
        if value.resource_deleted:
            raise ConversationError("conversation_deleted", 410)
        return value

    def existing(self, kind: str, target: str | None, request: Any) -> OperationRecord | None:
        with self._read() as conn:
            # DELETE replays remain successful after its target is gone.
            found = self._op(conn, request.operation_id)
            if found is None:
                return None
            value, digest = found
            if digest != request_hash(kind, target, request.model_dump()):
                raise ConversationError("operation_request_conflict", 409)
            if value.resource_deleted and kind != "delete_conversation":
                raise ConversationError("conversation_deleted", 410)
            return value

    def _save_op(self, conn: sqlite3.Connection, value: OperationRecord,
                 digest: str, *, insert: bool) -> None:
        payload = canonical(value.model_dump())
        args = (value.kind, digest, value.conversation_id, value.turn_id, value.status,
                int(value.resource_deleted), value.created_at, value.ended_at,
                value.error_code, payload, sha(payload), self.workspace, value.operation_id)
        if insert:
            conn.execute("""INSERT INTO conversation_operations
                (kind,request_sha,conversation_id,turn_id,status,resource_deleted,
                 created_at,ended_at,error_code,payload,payload_sha,workspace_id,operation_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", args)
        else:
            changed = conn.execute("""UPDATE conversation_operations SET
                kind=?,request_sha=?,conversation_id=?,turn_id=?,status=?,resource_deleted=?,
                created_at=?,ended_at=?,error_code=?,payload=?,payload_sha=?
                WHERE workspace_id=? AND operation_id=?""", args)
            if changed.rowcount != 1:
                raise ConversationError("conversation_integrity_error")
        stored = self._op(conn, value.operation_id)
        if stored is None or stored[0] != value or stored[1] != digest:
            raise ConversationError("conversation_integrity_error")

    def _scope(self, conn: sqlite3.Connection, cid: str) -> tuple[sqlite3.Row, list[Identity]]:
        row = conn.execute(
            "SELECT * FROM conversations WHERE workspace_id=? AND conversation_id=?",
            (self.workspace, cid),
        ).fetchone()
        if row is None:
            deleted = conn.execute("""SELECT 1 FROM conversation_operations
                WHERE workspace_id=? AND conversation_id=? AND resource_deleted=1 LIMIT 1""",
                (self.workspace, cid),
            ).fetchone()
            raise ConversationError("conversation_deleted" if deleted else "resource_not_found",
                                    410 if deleted else 404)
        try:
            operation(cid)
            docs = [Identity.model_validate(d) for d in json.loads(row["source_payload"])]
            if (sha(row["source_payload"]) != row["source_payload_sha"]
                    or canonical([d.model_dump() for d in docs]) != row["source_payload"]
                    or not 1 <= len(docs) <= 4
                    or [d.document_id for d in docs] != sorted({d.document_id for d in docs})
                    or any(d.workspace_id != self.workspace or d.report_type != "annual"
                           for d in docs)):
                raise ValueError("invalid_scope")
            selection = self._selection(docs, "scope verification")
            if selection.selection_id != row["source_scope_sha"]:
                raise ValueError("scope_hash")
            children = conn.execute("""SELECT * FROM conversation_sources
                WHERE workspace_id=? AND conversation_id=? ORDER BY document_id""",
                (self.workspace, cid),
            ).fetchall()
            actual = [{k: child[k] for k in Identity.model_fields} for child in children]
            if actual != [d.model_dump() for d in docs]:
                raise ValueError("scope_rows")
            return row, docs
        except (ValueError, TypeError, KeyError):
            raise ConversationError("conversation_integrity_error") from None

    def _selection(self, docs: list[Identity], query: str) -> PreparedDocumentSelection:
        return PreparedDocumentSelection(query, TrustedContext(self.workspace),
                                         tuple(SelectedDocumentIdentity(**d.model_dump())
                                               for d in docs))

    def selection(self, cid: str, query: str) -> PreparedDocumentSelection:
        with self._read() as conn:
            return self._selection(self._scope(conn, cid)[1], query)

    def create(self, request: CreateConversationRequest,
               selection: PreparedDocumentSelection) -> tuple[str, bool]:
        docs = [Identity.model_validate(asdict(d)) for d in selection.documents]
        if (selection.context.workspace_id != self.workspace
                or list(selection.document_ids) != request.document_ids
                or any(d.report_type != "annual" for d in docs)):
            raise ConversationError("invalid_request", 422)
        digest = request_hash("create_conversation", None, request.model_dump())
        with closing(self.registry._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            old = self._existing(conn, request.operation_id, digest)
            if old:
                self._scope(conn, old.conversation_id)
                return old.conversation_id, False
            self.sources.verify_selection_in(conn, tuple(d.model_dump() for d in docs))
            cid, timestamp = str(uuid4()), now()
            payload = canonical([d.model_dump() for d in docs])
            conn.execute("""INSERT INTO conversations
                (conversation_id,workspace_id,title,source_scope_sha,source_payload,
                 source_payload_sha,status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,'active',?,?)""",
                (cid, self.workspace, request.title or "新会话", selection.selection_id,
                 payload, sha(payload), timestamp, timestamp),
            )
            columns = list(Identity.model_fields)
            for doc in docs:
                values = doc.model_dump()
                conn.execute(
                    f"INSERT INTO conversation_sources(conversation_id,{','.join(columns)}) "
                    f"VALUES ({','.join('?' for _ in range(len(columns) + 1))})",
                    (cid, *(values[k] for k in columns)),
                )
            self._save_op(conn, OperationRecord(
                operation_id=request.operation_id, kind="create_conversation", status="completed",
                conversation_id=cid, turn_id=None, created_at=timestamp, ended_at=timestamp,
            ), digest, insert=True)
            self._scope(conn, cid)
        return cid, True

    def _turn(self, conn: sqlite3.Connection, cid: str, tid: str) -> tuple[TurnData, str | None]:
        row = conn.execute("""SELECT * FROM conversation_turns
            WHERE workspace_id=? AND conversation_id=? AND turn_id=?""",
            (self.workspace, cid, tid),
        ).fetchone()
        if row is None:
            raise ConversationError("resource_not_found", 404)
        try:
            value = TurnData.model_validate_json(row["payload"])
            if sha(row["payload"]) != row["payload_sha"] or canonical(value.model_dump()) != row["payload"]:
                raise ValueError("digest")
            for key in ("conversation_id", "turn_id", "operation_id", "seq", "status",
                        "created_at", "ended_at"):
                if getattr(value, key) != row[key]:
                    raise ValueError("identity")
            body = CreateTurnRequest(operation_id=value.operation_id, text=value.user_text,
                                     fact_selections=value.fact_selections)
            if request_hash("send_turn", cid, body.model_dump()) != row["request_sha"]:
                raise ValueError("request_hash")
            execution = canonical(value.usage.model_dump())
            if row["execution_json"] != execution or row["execution_sha"] != sha(execution):
                raise ValueError("execution_hash")
            events = conn.execute("""SELECT * FROM conversation_tool_events
                WHERE workspace_id=? AND conversation_id=? AND turn_id=? ORDER BY event_seq""",
                (self.workspace, cid, tid),
            ).fetchall()
            if len(events) != len(value.tool_events):
                raise ValueError("event_count")
            for saved, event in zip(events, value.tool_events, strict=True):
                raw = canonical(event.model_dump())
                if (saved["event_seq"] != event.sequence or saved["payload"] != raw
                        or saved["payload_sha"] != sha(raw)):
                    raise ValueError("event_hash")
            found = self._op(conn, value.operation_id)
            if found is None:
                raise ValueError("missing_operation")
            op, digest = found
            if (op.kind != "send_turn" or op.conversation_id != cid or op.turn_id != tid
                    or op.status != value.status or op.resource_deleted
                    or digest != row["request_sha"] or op.ended_at != value.ended_at):
                raise ValueError("operation_state")
            if value.result:
                scope_row, docs = self._scope(conn, cid)
                validate_quote(value.result, docs, scope_row["source_scope_sha"])
                self._validate_refs(value, docs)
                if (value.resolved_query and value.resolved_query.company_id is not None
                        and value.resolved_query.company_id not in {d.company_id for d in docs}):
                    raise ValueError("focus_outside_scope")
            if value.resolved_query:
                for context_id in value.resolved_query.context_turn_ids:
                    context = conn.execute("""SELECT seq,status,payload,payload_sha
                        FROM conversation_turns WHERE workspace_id=? AND conversation_id=?
                        AND turn_id=?""", (self.workspace, cid, context_id)).fetchone()
                    if (context is None or context["seq"] >= value.seq
                            or context["status"] not in ("completed", "refused")
                            or sha(context["payload"]) != context["payload_sha"]):
                        raise ValueError("invalid_context_turn")
            return value, row["claim"]
        except (ValueError, TypeError, KeyError):
            raise ConversationError("conversation_integrity_error") from None

    @staticmethod
    def _validate_refs(value: TurnData, docs: list[Identity]) -> None:
        assert value.result is not None
        identities = {d.document_id: d for d in docs}
        for ref in value.result.verified_financial_fact_refs:
            doc = identities.get(ref.document_id)
            if doc is None or (doc.company_id, doc.source_revision, doc.report_year) != (
                    ref.company_id, ref.source_revision, ref.report_year):
                raise ValueError("fact_outside_scope")
            matches = [s for s in value.fact_selections if
                       (s.company_id, s.metric_key, s.period, s.fact_set_id,
                        s.fact_id, s.disclosure_version) ==
                       (ref.company_id, ref.metric_key, ref.period, ref.fact_set_id,
                        ref.fact_id, ref.disclosure_version)]
            if len(matches) != 1:
                raise ValueError("fact_not_explicitly_selected")
        for action in value.result.actions:
            if action.document_id is not None:
                doc = identities.get(action.document_id)
                if doc is None or action.source_revision != doc.source_revision:
                    raise ValueError("action_outside_scope")
            if action.research_run_id is not None and action.research_run_id != value.research_run_id:
                raise ValueError("invalid_run_action")

    def _write_turn(self, conn: sqlite3.Connection, value: TurnData, claim: str | None,
                    digest: str, *, insert: bool) -> None:
        payload = canonical(value.model_dump())
        execution = canonical(value.usage.model_dump())
        args = (value.status, value.ended_at, payload, sha(payload), execution, sha(execution), claim,
                self.workspace, value.conversation_id, value.turn_id)
        if insert:
            conn.execute("""INSERT INTO conversation_turns
                (status,ended_at,payload,payload_sha,execution_json,execution_sha,claim,
                 workspace_id,conversation_id,turn_id,seq,operation_id,request_sha,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (*args, value.seq, value.operation_id, digest, value.created_at),
            )
        else:
            changed = conn.execute("""UPDATE conversation_turns SET
                status=?,ended_at=?,payload=?,payload_sha=?,execution_json=?,execution_sha=?,claim=?
                WHERE workspace_id=? AND conversation_id=? AND turn_id=? AND status='running'""",
                args,
            )
            if changed.rowcount != 1:
                raise ConversationError("turn_already_terminal", 409)

    def register(self, cid: str, request: CreateTurnRequest,
                 selection: PreparedDocumentSelection) -> tuple[TurnData, str | None, bool]:
        digest = request_hash("send_turn", cid, request.model_dump())
        with closing(self.registry._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            old = self._existing(conn, request.operation_id, digest)
            if old:
                value, claim = self._turn(conn, cid, old.turn_id or "")
                return value, claim, False
            row, docs = self._scope(conn, cid)
            if (selection.context.workspace_id != self.workspace
                    or [asdict(d) for d in selection.documents] != [d.model_dump() for d in docs]):
                raise ConversationError("source_changed", 409)
            self.sources.verify_selection_in(conn, tuple(d.model_dump() for d in docs))
            if conn.execute("""SELECT 1 FROM conversation_turns
                WHERE workspace_id=? AND conversation_id=? AND status='running'""",
                (self.workspace, cid),
            ).fetchone():
                raise ConversationError("conversation_busy", 409)
            timestamp, tid, claim = now(), str(uuid4()), str(uuid4())
            value = TurnData(conversation_id=cid, turn_id=tid, operation_id=request.operation_id,
                             seq=row["next_seq"], user_text=request.text,
                             fact_selections=request.fact_selections, created_at=timestamp)
            self._save_op(conn, OperationRecord(
                operation_id=request.operation_id, kind="send_turn", status="running",
                conversation_id=cid, turn_id=tid, created_at=timestamp, ended_at=None,
            ), digest, insert=True)
            self._write_turn(conn, value, claim, digest, insert=True)
            conn.execute("""UPDATE conversations SET next_seq=next_seq+1,updated_at=?
                WHERE workspace_id=? AND conversation_id=?""", (timestamp, self.workspace, cid))
            self._turn(conn, cid, tid)
        return value, claim, True

    def reserve(self, cid: str, tid: str, claim: str, counter: str) -> TurnData:
        if counter not in ("model_attempts", "tool_calls"):
            raise ValueError("invalid_budget_counter")
        with closing(self.registry._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            value, saved_claim = self._turn(conn, cid, tid)
            self._fence(value, saved_claim, claim)
            usage = value.usage.model_dump()
            usage[counter] += 1
            try:
                checked = Usage.model_validate(usage)
            except ValidationError:
                raise ConversationError("budget_exhausted", 409) from None
            updated = TurnData.model_validate({**value.model_dump(), "usage": checked.model_dump(),
                "provider_outcome": "unknown" if counter == "model_attempts"
                else value.provider_outcome})
            digest = request_hash("send_turn", cid, CreateTurnRequest(
                operation_id=value.operation_id, text=value.user_text,
                fact_selections=value.fact_selections).model_dump())
            self._write_turn(conn, updated, claim, digest, insert=False)
            self._turn(conn, cid, tid)
        return updated

    @staticmethod
    def _fence(value: TurnData, saved: str | None, claim: str) -> None:
        if value.status != "running" or not claim or saved != claim:
            raise ConversationError("turn_claim_expired", 409)

    def _finish_in(self, conn: sqlite3.Connection, value: TurnData, result: TurnResult,
                   status: TurnStatus, resolved: ResolvedQuery | None,
                   provider_outcome: str) -> TurnData:
        updated = TurnData.model_validate({**value.model_dump(), "status": status,
            "result": result.model_dump(), "resolved_query": resolved.model_dump() if resolved else None,
            "provider_outcome": provider_outcome, "ended_at": now()})
        op, digest = self._op(conn, value.operation_id) or (None, "")
        if op is None:
            raise ConversationError("conversation_integrity_error")
        self._save_op(conn, OperationRecord.model_validate({**op.model_dump(), "status": status,
            "ended_at": updated.ended_at, "error_code": result.error_code}), digest, insert=False)
        self._write_turn(conn, updated, None, digest, insert=False)
        conn.execute("""UPDATE conversations SET updated_at=?
            WHERE workspace_id=? AND conversation_id=?""",
            (updated.ended_at, self.workspace, value.conversation_id))
        return self._turn(conn, value.conversation_id, value.turn_id)[0]

    def finish(self, cid: str, tid: str, claim: str, result: TurnResult,
               *, status: TurnStatus = "completed", resolved: ResolvedQuery | None = None,
               provider_outcome: str | None = None,
               admit: Callable[[sqlite3.Connection, TurnData], None] | None = None) -> TurnData:
        if status == "running":
            raise ValueError("terminal_required")
        with closing(self.registry._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            value, saved_claim = self._turn(conn, cid, tid)
            self._fence(value, saved_claim, claim)
            _, docs = self._scope(conn, cid)
            if status in ("completed", "refused"):
                try:
                    self.sources.verify_selection_in(conn, tuple(d.model_dump() for d in docs))
                    if result.kind in ("confirmed_metric", "comparison") and admit is None:
                        raise ConversationError("financial_admission_required", 409)
                    if admit:
                        admit(conn, value)
                except (SourceError, ConversationError):
                    result, status, resolved = error_result("source_changed"), "failed", None
            return self._finish_in(conn, value, result, status, resolved,
                                   provider_outcome or value.provider_outcome)

    def recover_interrupted(self) -> int:
        """Startup only after acquiring ResearchOwner, before serving requests."""
        with closing(self.registry._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute("""SELECT conversation_id,turn_id FROM conversation_turns
                WHERE workspace_id=? AND status='running'""", (self.workspace,)).fetchall()
            for row in rows:
                value = self._turn(conn, row["conversation_id"], row["turn_id"])[0]
                self._finish_in(conn, value, error_result("interrupted"), "interrupted", None,
                                value.provider_outcome)
            return len(rows)

    def _states(self, conn: sqlite3.Connection, docs: list[Identity]) -> list[SourceState]:
        result = []
        for doc in docs:
            try:
                self.sources.verify_selection_in(conn, (doc.model_dump(),))
                state = "current_at_read"
            except SourceError:
                state = "expired"
            result.append(SourceState(document_id=doc.document_id,
                                      source_revision=doc.source_revision, status=state))
        return result

    def _public_turn(self, conn: sqlite3.Connection, cid: str, tid: str,
                     docs: list[Identity] | None = None) -> Turn:
        value = self._turn(conn, cid, tid)[0]
        if docs is None:
            docs = self._scope(conn, cid)[1]
        return Turn(**value.model_dump(), source_states=self._states(conn, docs),
                    integrity_sha256=sha(canonical(value.model_dump())),
                    financial_fact_validity="validated_at_completion_only"
                    if value.result and value.result.verified_financial_fact_refs else "not_applicable")

    def get_turn(self, cid: str, tid: str) -> Turn:
        with self._read() as conn:
            docs = self._scope(conn, cid)[1]
            return self._public_turn(conn, cid, tid, docs)

    def turn_by_operation(self, cid: str, op: str) -> Turn:
        with self._read() as conn:
            self._scope(conn, cid)
            found = self._op(conn, op)
            if found is None or found[0].conversation_id != cid or found[0].kind != "send_turn":
                raise ConversationError("resource_not_found", 404)
            if found[0].resource_deleted:
                raise ConversationError("conversation_deleted", 410)
            return self._public_turn(conn, cid, found[0].turn_id or "")

    def operation(self, op: str) -> OperationRecord:
        with self._read() as conn:
            found = self._op(conn, op)
            if found is None:
                raise ConversationError("resource_not_found", 404)
            value = found[0]
            if not value.resource_deleted:
                self._scope(conn, value.conversation_id)
                if value.kind == "send_turn":
                    self._turn(conn, value.conversation_id, value.turn_id or "")
            return value

    def conversation_by_operation(self, op: str) -> ConversationDetail:
        value = self.operation(op)
        if value.kind != "create_conversation":
            raise ConversationError("resource_not_found", 404)
        if value.resource_deleted:
            raise ConversationError("conversation_deleted", 410)
        return self.detail(value.conversation_id)

    def _summary(self, conn: sqlite3.Connection, cid: str) -> ConversationSummary:
        row, docs = self._scope(conn, cid)
        active = conn.execute("""SELECT turn_id FROM conversation_turns
            WHERE workspace_id=? AND conversation_id=? AND status='running'""",
            (self.workspace, cid),
        ).fetchone()
        return ConversationSummary(
            conversation_id=cid, title=row["title"], source_scope_sha=row["source_scope_sha"],
            sources=docs, source_states=self._states(conn, docs), created_at=row["created_at"],
            updated_at=row["updated_at"], last_turn_seq=row["next_seq"] - 1,
            active_turn_id=active[0] if active else None,
        )

    def detail(self, cid: str, *, limit: int = 50,
               before_seq: int | None = None) -> ConversationDetail:
        if not 1 <= limit <= 100 or (before_seq is not None and before_seq < 1):
            raise ConversationError("invalid_request", 422)
        with self._read() as conn:
            summary = self._summary(conn, cid)
            rows = conn.execute("""SELECT turn_id,seq FROM conversation_turns
                WHERE workspace_id=? AND conversation_id=? AND seq<? ORDER BY seq DESC LIMIT ?""",
                (self.workspace, cid, before_seq if before_seq is not None
                 else summary.last_turn_seq + 1, limit + 1),
            ).fetchall()
            chosen = rows[:limit]
            turns = [self._public_turn(conn, cid, row["turn_id"], summary.sources)
                     for row in reversed(chosen)]
            return ConversationDetail(**summary.model_dump(), turns=turns,
                next_before_seq=chosen[-1]["seq"] if len(rows) > limit else None)

    def page(self, limit: int = 20, cursor: str | None = None) -> ConversationList:
        if not 1 <= limit <= 50:
            raise ConversationError("invalid_cursor_or_limit", 422)
        with self._read() as conn:
            ceiling = conn.execute("""SELECT coalesce(max(sequence),0) FROM conversations
                WHERE workspace_id=?""", (self.workspace,)).fetchone()[0]
            before = ceiling + 1
            if cursor is not None:
                try:
                    if len(cursor) > 2048:
                        raise ValueError()
                    data = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
                    if (set(data) != {"v", "workspace", "ceiling", "before"}
                            or data["v"] != 1 or data["workspace"] != self.workspace
                            or type(data["ceiling"]) is not int or data["ceiling"] < 0
                            or type(data["before"]) is not int
                            or not 1 <= data["before"] <= data["ceiling"]):
                        raise ValueError()
                    ceiling, before = data["ceiling"], data["before"]
                except (ValueError, TypeError, KeyError):
                    raise ConversationError("invalid_cursor_or_limit", 422) from None
            rows = conn.execute("""SELECT conversation_id,sequence FROM conversations
                WHERE workspace_id=? AND sequence<=? AND sequence<? ORDER BY sequence DESC LIMIT ?""",
                (self.workspace, ceiling, before, limit + 1),
            ).fetchall()
            next_cursor = None
            if len(rows) > limit:
                next_cursor = base64.urlsafe_b64encode(canonical(dict(
                    v=1, workspace=self.workspace, ceiling=ceiling,
                    before=rows[limit - 1]["sequence"],
                )).encode()).decode()
            return ConversationList(items=[self._summary(conn, r["conversation_id"])
                                           for r in rows[:limit]], next_cursor=next_cursor)

    def delete(self, cid: str, request: DeleteRequest) -> OperationRecord:
        digest = request_hash("delete_conversation", cid, request.model_dump())
        with closing(self.registry._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            found = self._op(conn, request.operation_id)
            if found:
                if found[1] != digest:
                    raise ConversationError("operation_request_conflict", 409)
                return found[0]
            self._scope(conn, cid)
            if conn.execute("""SELECT 1 FROM conversation_turns
                WHERE workspace_id=? AND conversation_id=? AND status='running'""",
                (self.workspace, cid),
            ).fetchone():
                raise ConversationError("conversation_busy", 409)
            # Validate every row before deleting; never silently bless corruption.
            turns = conn.execute("""SELECT turn_id FROM conversation_turns
                WHERE workspace_id=? AND conversation_id=?""", (self.workspace, cid)).fetchall()
            for row in turns:
                self._turn(conn, cid, row[0])
            operations = conn.execute("""SELECT operation_id FROM conversation_operations
                WHERE workspace_id=? AND conversation_id=?""", (self.workspace, cid)).fetchall()
            for row in operations:
                saved, saved_sha = self._op(conn, row[0]) or (None, "")
                if saved is None:
                    raise ConversationError("conversation_integrity_error")
                self._save_op(conn, saved.model_copy(update={"resource_deleted": True}),
                              saved_sha, insert=False)
            conn.execute("DELETE FROM conversations WHERE workspace_id=? AND conversation_id=?",
                         (self.workspace, cid))
            timestamp = now()
            result = OperationRecord(operation_id=request.operation_id,
                kind="delete_conversation", status="completed", conversation_id=cid,
                turn_id=None, resource_deleted=True, created_at=timestamp, ended_at=timestamp)
            self._save_op(conn, result, digest, insert=True)
        return self.operation(request.operation_id)
