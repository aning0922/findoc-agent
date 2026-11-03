"""Server scope recovery and final source/conversation/memory publication fences."""
import asyncio
from contextlib import contextmanager, nullcontext
from dataclasses import asdict
import time

from app.memory.candidates import extract_user_memory_candidates
from app.showcase_research.models import ResearchError
from app.showcase_research.store import sha


class Scopes:
    def __init__(self, store, conversations, preparer, sources, *, preferences=None, memory=None):
        self.store, self.conversations, self.preparer, self.sources = store, conversations, preparer, sources
        self.preferences, self.memory = preferences, memory
        if sources.repository.registry._database_path.resolve() != store.root / "documents.db":
            raise ValueError("Research source root mismatch")
        if conversations.registry._database_path.resolve() != store.root / "documents.db":
            raise ValueError("Research conversation root mismatch")
        if memory is not None and memory.path.resolve().parent != store.root:
            raise ValueError("Research memory root mismatch")

    @staticmethod
    def check_identity(identity):
        if identity.lease_expires_at <= time.time():
            raise ResearchError("lease_expired", 401)

    async def freeze(self, identity, conversation_id, text):
        self.check_identity(identity)
        if identity.workspace_id != self.conversations.workspace:
            raise ResearchError("workspace_mismatch", 403)
        selection = await asyncio.to_thread(self.conversations.selection, conversation_id, text)
        await self.preparer.revalidate(selection)
        detail = await asyncio.to_thread(self.conversations.detail, conversation_id, limit=8)
        history = []
        for turn in detail.turns:
            if turn.status not in ("completed", "refused") or extract_user_memory_candidates(turn.user_text, turn.turn_id):
                continue
            history.append({"turn_id": turn.turn_id, "user_text": turn.user_text,
                            "focus": turn.resolved_query.model_dump() if turn.resolved_query else None})
        choices = [f.model_dump() for f in detail.turns[-1].fact_selections] if detail.turns else []
        pref = self.preferences.recall_context() if self.preferences else None
        excluded = self.preferences.excluded_source_turn_ids() if self.preferences else frozenset()
        history = [item for item in history if item["turn_id"] not in excluded]
        memories = await self.memory.recall_snapshot(text) if self.memory else {"memory_generation": 0, "items": []}
        docs = [asdict(doc) for doc in selection.documents]
        companies = await asyncio.to_thread(self.conversations.registry.list, identity.workspace_id)
        allowed_companies = {doc.company_id for doc in selection.documents}
        notes = [item for item in memories["items"] if item.get("source_status") in ("current", "current_valid") and
                 (not item.get("company_id") or item["company_id"] in allowed_companies) and
                 (not item.get("document_id") or item["document_id"] in selection.document_ids)][:5]
        scope = {"runtime_instance_id": identity.instance_id, "lease_generation": identity.lease_generation,
                 "lease_expires_at": identity.lease_expires_at, "workspace_id": identity.workspace_id,
                 "principal_id": identity.principal_id, "conversation_id": conversation_id,
                 "sources": docs, "source_scope_sha": selection.selection_id,
                 "selected_fact_refs": choices, "fact_selection_sha": sha(choices),
                 "memory_generation": memories["memory_generation"], "memory_items": notes,
                 "preference_generation": pref.generation if pref else None,
                 "preferences": [{"key": p.key, "value": p.value} for p in pref.items[:5]] if pref else [],
                 "history": history, "companies": [c.model_dump(mode="json") for c in companies],
                 "allowed_tools": ["search_evidence", "read_confirmed_facts", "recall_notes"], "query": text}
        scope["scope_hash"] = sha(scope)
        return scope

    def identity(self, scope, current):
        self.check_identity(current)
        if any(scope[key] != value for key, value in {
            "runtime_instance_id": current.instance_id, "lease_generation": current.lease_generation,
            "workspace_id": current.workspace_id, "principal_id": current.principal_id,
            "lease_expires_at": current.lease_expires_at}.items()):
            raise ResearchError("runtime_scope_changed", 403)

    def before_model(self, scope):
        if time.time() >= scope["lease_expires_at"]:
            raise ResearchError("lease_expired", 401)
        if self.memory:
            self.memory.check_generation(scope["memory_generation"])
        if self.preferences and self.preferences.recall_context().generation != scope["preference_generation"]:
            raise ResearchError("preference_context_changed")

    @contextmanager
    def publication(self, scope):
        if time.time() >= scope["lease_expires_at"]:
            raise ResearchError("lease_expired", 401)
        revisions = {m["memory_id"]: m["revision"] for m in scope["memory_items"]}
        guard = self.memory.publication_guard(scope["memory_generation"], revisions) if self.memory else nullcontext()
        # The memory SHARED lock remains held until our SQLite transaction COMMIT finishes.
        with guard:
            with self.store.tx(attachments={"source_db": self.store.root / "documents.db"}) as db:
                self.sources.repository.verify_selection_in(db, tuple(scope["sources"]))
                _, documents = self.conversations._scope(db, scope["conversation_id"])
                if [doc.model_dump() for doc in documents] != scope["sources"]:
                    raise ResearchError("conversation_scope_changed")
                if self.preferences:
                    self.conversations.check_generation_in(db, scope["preference_generation"])
                for note in scope["memory_items"]:
                    note_cid = note.get("source_conversation_id")
                    if note_cid:
                        self.conversations._scope(db, note_cid)
                        for turn_id in note.get("source_turn_ids", []):
                            turn, _ = self.conversations._turn(db, note_cid, turn_id)
                            if turn.status not in ("completed", "refused"):
                                raise ResearchError("memory_source_turn_changed")
                for item in scope["history"]:
                    turn, _ = self.conversations._turn(db, scope["conversation_id"], item["turn_id"])
                    if turn.user_text != item["user_text"]:
                        raise ResearchError("conversation_history_changed")
                for company in scope["companies"]:
                    if company["company_id"] not in {d["company_id"] for d in scope["sources"]}:
                        continue
                    from app.companies.models import Company
                    row = db.execute("SELECT * FROM companies WHERE company_id=? AND workspace_id=?",
                                     (company["company_id"], scope["workspace_id"])).fetchone()
                    if row is None or Company.model_validate(dict(row)).model_dump(mode="json") != company:
                        raise ResearchError("company_identity_changed")
                if time.time() >= scope["lease_expires_at"]:
                    raise ResearchError("lease_expired", 401)
                yield db

    @staticmethod
    def public(scope):
        return {key: scope[key] for key in ("scope_hash", "runtime_instance_id", "lease_generation", "source_scope_sha",
                                          "fact_selection_sha", "memory_generation", "allowed_tools")}
