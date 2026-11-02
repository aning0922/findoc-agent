"""Deterministic bounded structural snapshots; not financial truth or model prose.

Each version describes the last <=32 older turns in an explicit covered range.
Older versions are disposable: only two retained, with self-contained provenance.
"""

from contextlib import closing
import json
from typing import Literal

from pydantic import Field

from app.conversations.models import Metric
from app.conversations.repository import ConversationError, ConversationRepository, now
from app.conversations.service import TurnExecution
from app.memory.candidates import extract_user_memory_candidates
from app.memory.service import MemoryService
from app.research.models import Strict, canonical, sha


class Focus(Strict):
    company_id: str
    metric_key: Metric | None
    periods: list[int] = Field(max_length=2)
    intent: Literal["source_quote", "confirmed_metric", "compare_metric", "clarify", "unsupported"]


class Summary(Strict):
    schema_version: Literal["summary_v1"] = "summary_v1"
    version: int
    covered_from_seq: int
    covered_through_seq: int
    source_scope_sha: str
    memory_generation: int
    source_turn_ids: list[str] = Field(max_length=32)
    source_digest: str
    focus: Focus | None
    focus_turn_id: str | None
    barrier: bool
    progress: Literal["completed", "refused", "none"]


class SummaryRepository:
    def __init__(self, conversations: ConversationRepository):
        self.conversations = conversations

    def _derive(self, conn, cid, cutoff, generation, excluded, version):
        repo = self.conversations
        scope, _ = repo._scope(conn, cid)
        rows = conn.execute("""SELECT turn_id,seq,payload_sha FROM conversation_turns
            WHERE workspace_id=? AND conversation_id=? AND seq<=?
            ORDER BY seq DESC LIMIT 32""", (repo.workspace, cid, cutoff)).fetchall()
        if not rows:
            return None
        chosen = None
        for row in rows:
            turn = repo._turn(conn, cid, row["turn_id"])[0]
            if (chosen is None and turn.status in ("completed", "refused")
                    and turn.turn_id not in excluded
                    and not extract_user_memory_candidates(turn.user_text, turn.turn_id)
                    and not (turn.result and turn.result.memory_candidates)):
                chosen = turn
        focus = chosen.resolved_query if chosen else None
        barrier = focus is None or focus.resolution == "ambiguous" or focus.company_id is None
        structural = None if barrier else Focus(company_id=focus.company_id,
            metric_key=focus.metric_key, periods=focus.periods, intent=focus.intent)
        provenance = [(r["turn_id"], r["seq"], r["payload_sha"]) for r in reversed(rows)]
        return Summary(version=version, covered_from_seq=rows[-1]["seq"],
            covered_through_seq=rows[0]["seq"], source_scope_sha=scope["source_scope_sha"],
            memory_generation=generation, source_turn_ids=[p[0] for p in provenance],
            source_digest=sha(canonical(provenance)), focus=structural,
            focus_turn_id=chosen.turn_id if chosen else None, barrier=barrier,
            progress=chosen.status if chosen else "none")

    def refresh(self, execution: TurnExecution, memory: MemoryService) -> None:
        """Service POST hook, before invoking graph. Never called by GET or tools."""
        if execution.turn.seq <= 9:
            return
        snapshot = memory.recall_context()
        excluded = memory.excluded_source_turn_ids()
        repo, cid = self.conversations, execution.turn.conversation_id
        with closing(repo.registry._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            current, claim = repo._turn(conn, cid, execution.turn.turn_id)
            repo._fence(current, claim, execution.claim)
            repo.check_generation_in(conn, snapshot.generation)
            version = conn.execute("""SELECT coalesce(max(version),0)+1 FROM conversation_summaries
                WHERE workspace_id=? AND conversation_id=?""", (repo.workspace, cid)).fetchone()[0]
            value = self._derive(conn, cid, execution.turn.seq - 9, snapshot.generation, excluded, version)
            if value is None:
                return
            payload = canonical(value.model_dump())
            conn.execute("INSERT INTO conversation_summaries VALUES(?,?,?,?,?,?,?,?,?,?)",
                (repo.workspace, cid, version, value.covered_from_seq, value.covered_through_seq,
                 value.source_scope_sha, snapshot.generation, payload, sha(payload), now()))
            conn.execute("""DELETE FROM conversation_summaries WHERE workspace_id=?
                AND conversation_id=? AND version<?""", (repo.workspace, cid, version - 1))
            self._decode(conn, cid, snapshot.generation, excluded)

    def _decode(self, conn, cid, generation, excluded):
        repo = self.conversations
        row = conn.execute("""SELECT * FROM conversation_summaries WHERE workspace_id=?
            AND conversation_id=? ORDER BY version DESC LIMIT 1""", (repo.workspace, cid)).fetchone()
        if row is None:
            return None
        try:
            value = Summary.model_validate_json(row["payload"])
            if sha(row["payload"]) != row["payload_sha"] or canonical(value.model_dump()) != row["payload"]:
                raise ValueError("digest")
            for key in ("version", "covered_from_seq", "covered_through_seq", "source_scope_sha", "memory_generation"):
                if getattr(value, key) != row[key]:
                    raise ValueError("identity")
            if value.memory_generation != generation:
                return None  # Never revive a preference-associated old context.
            expected = self._derive(conn, cid, value.covered_through_seq, generation, excluded, value.version)
            if value != expected:
                raise ValueError("provenance")
            return value
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            raise ConversationError("summary_integrity_error") from None

    def read(self, cid, generation, excluded) -> Summary | None:
        with self.conversations._read() as conn:
            return self._decode(conn, cid, generation, excluded)
