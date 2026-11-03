"""Confirmed research leads; SQLite is authoritative, embeddings never establish facts."""

import asyncio
from contextlib import closing, contextmanager
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from uuid import UUID, uuid4

from app.documents.source_models import SourceError


def canonical(obj):
    return json.dumps(
        obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )


def now():
    return datetime.now(UTC).isoformat()


class MemoryError(Exception):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


class ResearchMemoryService:
    def __init__(
        self,
        *,
        runtime_root: Path,
        workspace_id: str,
        sources,
        conversations,
        embedder,
        embedding_model_version: str,
        parse_service=None,
    ):
        root = runtime_root.resolve()
        if not workspace_id or not embedding_model_version or not (root / "documents.db").is_file():
            raise ValueError("invalid_memory_scope")
        if (
            sources.documents._repository._database_path.resolve() != root / "documents.db"
            or sources.documents.workspace_id != workspace_id
            or conversations.workspace != workspace_id
            or conversations.registry._database_path.resolve() != root / "documents.db"
        ):
            raise ValueError("memory_runtime_mismatch")
        if parse_service is not None and (
            Path(parse_service.root).resolve() != root or parse_service.sources is not sources
        ):
            raise ValueError("memory_parse_runtime_mismatch")
        self.root, self.workspace, self.sources, self.conversations = (
            root,
            workspace_id,
            sources,
            conversations,
        )
        self.embedder, self.model_version, self.parse_service = (
            embedder,
            embedding_model_version,
            parse_service,
        )
        self.path = root / "research-memory.db"
        with self.tx() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS generation (workspace TEXT PRIMARY KEY, value INTEGER NOT NULL)"
            )
            db.execute("INSERT OR IGNORE INTO generation VALUES (?,0)", (workspace_id,))
            db.execute(
                "CREATE TABLE IF NOT EXISTS items (workspace TEXT NOT NULL, id TEXT PRIMARY KEY, revision INTEGER NOT NULL, type TEXT NOT NULL, text TEXT NOT NULL, refs TEXT NOT NULL, created_at TEXT NOT NULL, confirmed_at TEXT NOT NULL, revoked_at TEXT, embedding_revision INTEGER, embedding_model TEXT, vector TEXT)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS operations (workspace TEXT NOT NULL, id TEXT PRIMARY KEY, kind TEXT NOT NULL, request_hash TEXT NOT NULL, state TEXT NOT NULL, item_id TEXT NOT NULL, revision INTEGER NOT NULL)"
            )
        self.path.chmod(0o600)

    @contextmanager
    def tx(self):
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            with db:
                yield db

    @staticmethod
    def uuid(value):
        try:
            if str(UUID(value)) != value:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise MemoryError("invalid_uuid", 422) from None

    def _generation(self, db):
        return db.execute(
            "SELECT value FROM generation WHERE workspace=?", (self.workspace,)
        ).fetchone()[0]

    def check_generation(self, expected):
        with self.tx() as db:
            value = self._generation(db)
        if value != expected:
            raise MemoryError("memory_context_changed")
        return value

    @contextmanager
    def publication_guard(self, expected_generation, memory_revisions=None):
        """Hold a rollback-journal read lock through the caller's final commit.

        memory_revisions, if provided, maps recalled IDs to their revisions.
        This guards this memory database only; callers must validate sources separately.
        """
        if type(expected_generation) is not int or expected_generation < 0:
            raise MemoryError("invalid_memory_generation", 422)
        if memory_revisions is not None:
            if not isinstance(memory_revisions, dict) or len(memory_revisions) > 5:
                raise MemoryError("invalid_memory_revisions", 422)
            for memory_id, revision in memory_revisions.items():
                self.uuid(memory_id)
                if type(revision) is not int or revision < 1:
                    raise MemoryError("invalid_memory_revisions", 422)
        uri = self.path.resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=5, isolation_level=None)) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN")
            try:
                generation = self._generation(
                    db
                )  # Acquire SHARED lock before checking journal mode.
                mode = db.execute("PRAGMA journal_mode").fetchone()[0].lower()
                if mode not in ("delete", "truncate", "persist"):
                    raise MemoryError("memory_fence_unsupported_journal", 503)
                if generation != expected_generation:
                    raise MemoryError("memory_context_changed")
                for memory_id, revision in (memory_revisions or {}).items():
                    row = db.execute(
                        "SELECT revision FROM items WHERE workspace=? AND id=? AND revoked_at IS NULL",
                        (self.workspace, memory_id),
                    ).fetchone()
                    if row is None or row["revision"] != revision:
                        raise MemoryError("memory_context_changed")
                yield
            finally:
                db.execute("ROLLBACK")

    async def recall_snapshot(self, q, company_id=None):
        """Return a bounded semantic snapshot and its generation for publication_guard."""
        if not isinstance(q, str):
            raise MemoryError("invalid_query", 422)
        return await self.list(q=q, company_id=company_id)

    async def validate_refs(self, refs, *, kind, text):
        cid, tids = refs.get("source_conversation_id"), refs.get("source_turn_ids") or []
        company, doc, revision = (
            refs.get("company_id"),
            refs.get("document_id"),
            refs.get("source_revision"),
        )
        evidence, artifact = refs.get("evidence_id"), refs.get("artifact_id")
        page, line_index = refs.get("physical_page"), refs.get("source_line_index")
        if (
            bool(cid) != bool(tids)
            or len(tids) > 8
            or len(set(tids)) != len(tids)
            or (any((doc, revision, evidence, artifact)) and not all((doc, revision, company)))
        ):
            raise MemoryError("invalid_source_reference", 422)
        if not artifact and (page is not None or line_index is not None):
            raise MemoryError("invalid_source_reference", 422)
        if kind == "saved_evidence" and not (
            doc and revision and company and (bool(evidence) != bool(artifact))
        ):
            raise MemoryError("evidence_reference_required", 422)
        if kind != "saved_evidence" and (
            evidence or artifact or page is not None or line_index is not None
        ):
            raise MemoryError("invalid_source_reference", 422)
        if company:
            await asyncio.to_thread(self.sources.companies.get, company)
        if cid:
            self.uuid(cid)
            detail = await asyncio.to_thread(self.conversations.detail, cid, limit=1)
            if company and not any(source.company_id == company for source in detail.sources):
                raise MemoryError("source_outside_conversation", 422)
            if doc and not any(
                source.document_id == doc and source.source_revision == revision
                for source in detail.sources
            ):
                raise MemoryError("source_outside_conversation", 422)
            for tid in tids:
                self.uuid(tid)
                turn = await asyncio.to_thread(self.conversations.get_turn, cid, tid)
                if turn.status not in ("completed", "refused"):
                    raise MemoryError("source_turn_unavailable")
        if artifact:
            if (
                self.parse_service is None
                or type(page) is not int
                or type(line_index) is not int
                or page < 1
                or line_index < 0
            ):
                raise MemoryError("artifact_evidence_unsupported", 422)
            value = await self.parse_service.quality(doc, artifact)
            if (
                value["source_status"] != "current"
                or value["source_revision"] != revision
                or value["company_id"] != company
                or value["state"] == "failed"
            ):
                raise MemoryError("source_turn_unavailable")
            matches = [
                p
                for p in value["pages"]
                if p["physical_page"] == page and p["status"] == "completed"
            ]
            if len(matches) != 1 or line_index >= len(matches[0].get("lines", [])):
                raise MemoryError("invalid_source_reference", 422)
            original = matches[0]["lines"][line_index]["text"]
            if text and text != original:
                raise MemoryError("evidence_text_mismatch", 422)
            text = original
        elif doc:
            await self.sources.source(doc, company_id=company, source_revision=revision)
            if evidence:
                evidence_value = await self.sources.evidence(
                    doc, evidence, source_revision=revision, company_id=company
                )
                original = evidence_value["text"]
                if text and text != original:
                    raise MemoryError("evidence_text_mismatch", 422)
                text = original
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
            raise MemoryError("invalid_memory_text", 422)
        return text

    def _projection(self, row, generation, source_status="current"):
        return dict(
            schema_version="research-memory-v1",
            memory_id=row["id"],
            revision=row["revision"],
            type=row["type"],
            text=row["text"],
            **json.loads(row["refs"]),
            created_at=row["created_at"],
            confirmed_at=row["confirmed_at"],
            revoked_at=row["revoked_at"],
            embedding_model_version=row["embedding_model"],
            embedding_revision=row["embedding_revision"],
            memory_generation=generation,
            source_status=source_status,
            source_kind=(
                "ocr_candidate_unreviewed"
                if json.loads(row["refs"]).get("artifact_id")
                else "source_evidence"
                if json.loads(row["refs"]).get("evidence_id")
                else "user_note"
            ),
        )

    def operation(self, op):
        self.uuid(op)
        with self.tx() as db:
            row = db.execute(
                "SELECT * FROM operations WHERE workspace=? AND id=?", (self.workspace, op)
            ).fetchone()
        if not row:
            raise MemoryError("operation_not_found", 404)
        return dict(
            operation_id=op, state=row["state"], memory_id=row["item_id"], revision=row["revision"]
        )

    async def mutate(
        self,
        *,
        kind,
        operation_id,
        memory_id=None,
        expected_revision=None,
        memory_type=None,
        text=None,
        refs=None,
        confirmed=None,
    ):
        self.uuid(operation_id)
        if memory_id is not None:
            self.uuid(memory_id)
        if confirmed is not True and kind != "delete":
            raise MemoryError("confirmation_required", 422)
        request = dict(
            kind=kind,
            memory_id=memory_id,
            expected_revision=expected_revision,
            memory_type=memory_type,
            text=text,
            refs=refs,
            confirmed=confirmed,
        )
        rh = hashlib.sha256(canonical(request).encode()).hexdigest()
        with self.tx() as db:
            op = db.execute(
                "SELECT * FROM operations WHERE workspace=? AND id=?",
                (self.workspace, operation_id),
            ).fetchone()
            if op and op["request_hash"] != rh:
                raise MemoryError("operation_conflict")
        if op:
            return self.operation(operation_id)
        if kind == "create":
            if memory_type not in ("research_question", "note", "saved_evidence"):
                raise MemoryError("invalid_memory_type", 422)
            allowed = (
                "company_id",
                "source_conversation_id",
                "source_turn_ids",
                "document_id",
                "source_revision",
                "evidence_id",
                "artifact_id",
                "physical_page",
                "source_line_index",
            )
            refs = refs or {}
            if set(refs) - set(allowed):
                raise MemoryError("invalid_source_reference", 422)
            refs = {key: refs.get(key, [] if key == "source_turn_ids" else None) for key in allowed}
            text = await self.validate_refs(refs, kind=memory_type, text=text)
        elif kind == "patch":
            with self.tx() as db:
                row = db.execute(
                    "SELECT * FROM items WHERE workspace=? AND id=?", (self.workspace, memory_id)
                ).fetchone()
            if not row or row["revoked_at"]:
                raise MemoryError("memory_not_found", 404)
            if row["type"] == "saved_evidence":
                raise MemoryError("evidence_immutable", 409)
            text = await self.validate_refs(json.loads(row["refs"]), kind=row["type"], text=text)
        elif kind != "delete":
            raise MemoryError("invalid_memory_action", 422)
        with self.tx() as db:
            prior = db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
            if prior:
                if prior["workspace"] != self.workspace or prior["request_hash"] != rh:
                    raise MemoryError("operation_conflict")
                return dict(
                    operation_id=operation_id,
                    state=prior["state"],
                    memory_id=prior["item_id"],
                    revision=prior["revision"],
                )
            if kind == "create":
                count = db.execute(
                    "SELECT count(*) FROM items WHERE workspace=? AND revoked_at IS NULL",
                    (self.workspace,),
                ).fetchone()[0]
                if count >= 20:
                    raise MemoryError("memory_limit_reached")
                memory_id, revision, instant = str(uuid4()), 1, now()
                db.execute(
                    "INSERT INTO items VALUES (?,?,?,?,?,?,?,?,NULL,NULL,NULL,NULL)",
                    (
                        self.workspace,
                        memory_id,
                        revision,
                        memory_type,
                        text,
                        canonical(refs),
                        instant,
                        instant,
                    ),
                )
            else:
                row = db.execute(
                    "SELECT * FROM items WHERE workspace=? AND id=?", (self.workspace, memory_id)
                ).fetchone()
                if not row or row["revoked_at"]:
                    raise MemoryError("memory_not_found", 404)
                if row["revision"] != expected_revision:
                    raise MemoryError("memory_revision_conflict")
                revision = row["revision"] + 1
                if kind == "delete":
                    db.execute(
                        "UPDATE items SET revision=?,revoked_at=?,vector=NULL,embedding_revision=NULL WHERE id=?",
                        (revision, now(), memory_id),
                    )
                else:
                    db.execute(
                        "UPDATE items SET revision=?,text=?,confirmed_at=?,vector=NULL,embedding_revision=NULL WHERE id=?",
                        (revision, text, now(), memory_id),
                    )
            db.execute("UPDATE generation SET value=value+1 WHERE workspace=?", (self.workspace,))
            db.execute(
                "INSERT INTO operations VALUES (?,?,?,?,'completed',?,?)",
                (self.workspace, operation_id, kind, rh, memory_id, revision),
            )
        if kind != "delete":
            try:
                vectors = await asyncio.to_thread(self.embedder, [text])
                vec = [float(v) for v in vectors[0]]
                if (
                    len(vectors) != 1
                    or not vec
                    or any(not math.isfinite(v) for v in vec)
                    or not any(vec)
                ):
                    raise ValueError("bad_embedding")
                with self.tx() as db:
                    db.execute(
                        "UPDATE items SET vector=?,embedding_revision=?,embedding_model=? WHERE workspace=? AND id=? AND revision=? AND revoked_at IS NULL",
                        (
                            canonical(vec),
                            revision,
                            self.model_version,
                            self.workspace,
                            memory_id,
                            revision,
                        ),
                    )
            except Exception:
                # Committed note remains visible but unindexed; never manufacture a vector.
                pass
        return self.operation(operation_id)

    async def _source_status(self, row):
        refs = json.loads(row["refs"])
        try:
            await self.validate_refs(refs, kind=row["type"], text=row["text"])
            return "current"
        except SourceError as exc:
            if exc.status in (404, 409, 410) or exc.code in ("source_changed", "source_not_ready"):
                return "stale"
            raise
        except MemoryError as exc:
            if exc.code in ("source_turn_unavailable", "evidence_text_mismatch"):
                return "stale"
            raise
        except Exception as exc:
            if getattr(exc, "status", None) in (404, 409, 410):
                return "stale"
            raise

    async def list(self, *, company_id=None, q=None):
        if q is not None and (not q.strip() or len(q) > 2000):
            raise MemoryError("invalid_query", 422)
        with self.tx() as db:
            generation = self._generation(db)
            rows = db.execute(
                "SELECT * FROM items WHERE workspace=? AND revoked_at IS NULL ORDER BY created_at DESC",
                (self.workspace,),
            ).fetchall()
        matched = []
        for row in rows:
            refs = json.loads(row["refs"])
            if company_id and refs.get("company_id") != company_id:
                continue
            status = await self._source_status(row)
            if q and (
                status != "current"
                or row["embedding_revision"] != row["revision"]
                or row["embedding_model"] != self.model_version
                or not row["vector"]
            ):
                continue
            matched.append((row, status))
        if q and matched:
            vectors = await asyncio.to_thread(self.embedder, [q])
            query = [float(v) for v in vectors[0]]
            if len(vectors) != 1 or not query or any(not math.isfinite(v) for v in query):
                raise MemoryError("embedding_unavailable", 503)
            qnorm = math.sqrt(sum(v * v for v in query))
            if not qnorm:
                raise MemoryError("embedding_unavailable", 503)
            scored = []
            for row, status in matched:
                v = json.loads(row["vector"])
                if len(v) != len(query) or any(not math.isfinite(x) for x in v):
                    raise MemoryError("embedding_integrity_error", 503)
                norm = math.sqrt(sum(x * x for x in v))
                if not norm:
                    raise MemoryError("embedding_integrity_error", 503)
                scored.append((sum(a * b for a, b in zip(query, v)) / (qnorm * norm), row, status))
            matched = [
                (row, status)
                for _, row, status in sorted(scored, key=lambda x: (-x[0], x[1]["id"]))[:5]
            ]
        with self.tx() as db:
            if self._generation(db) != generation:
                raise MemoryError("memory_context_changed")
            fresh = []
            for row, status in matched:
                current = db.execute(
                    "SELECT * FROM items WHERE workspace=? AND id=? AND revision=? AND revoked_at IS NULL",
                    (self.workspace, row["id"], row["revision"]),
                ).fetchone()
                if current:
                    fresh.append(self._projection(current, generation, status))
        return dict(
            schema_version="research-memory-list-v1",
            memory_generation=generation,
            items=fresh,
            limitations=["研究记忆仅为线索，不是已核准财务事实。"],
        )
