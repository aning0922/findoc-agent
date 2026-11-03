"""Private controller snapshots, durable operations and same-process import tickets."""

from contextlib import closing, contextmanager
import json
from pathlib import Path
import sqlite3
import time
from uuid import UUID, uuid4

from .contracts import DiscoveryError, TrustedImportIdentity, canonical, digest


class DiscoveryService:
    def __init__(self, control_root: Path, provider, cache, binder, identity_validator):
        root = Path(control_root)
        if root.is_symlink():
            raise ValueError("Symlink controller root forbidden")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = root.resolve() / "discovery-private.sqlite"
        if self.path.is_symlink() or (self.path.exists() and self.path.stat().st_nlink != 1):
            raise ValueError("Invalid discovery store")
        self.provider, self.cache, self.binder, self.identity_validator = (
            provider,
            cache,
            binder,
            identity_validator,
        )
        with self.tx() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY,owner TEXT NOT NULL,kind TEXT NOT NULL,digest TEXT NOT NULL,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS candidates(id TEXT PRIMARY KEY,owner TEXT NOT NULL,kind TEXT NOT NULL,security_id TEXT,expires REAL NOT NULL,payload TEXT NOT NULL,digest TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS tickets(id TEXT PRIMARY KEY,owner TEXT NOT NULL,expires REAL NOT NULL,operation_id TEXT NOT NULL,candidate TEXT NOT NULL);
            CREATE TRIGGER IF NOT EXISTS candidate_immutable BEFORE UPDATE ON candidates BEGIN SELECT RAISE(ABORT,'immutable candidate'); END;
            CREATE TRIGGER IF NOT EXISTS ticket_immutable BEFORE UPDATE ON tickets BEGIN SELECT RAISE(ABORT,'immutable ticket'); END;
            """)
        self.path.chmod(0o600)
        cache.set_ticket_reader(self._ticket, self.guard)
        if hasattr(provider, "pacer") and hasattr(cache.downloader, "pacer"):
            cache.downloader.pacer = provider.pacer

    @contextmanager
    def tx(self):
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            with db:
                yield db

    def guard(self, identity):
        if not isinstance(identity, TrustedImportIdentity):
            raise DiscoveryError("trusted_identity_required", 401)
        return identity.guard(self.identity_validator)

    def operation(self, operation_id, identity, kind):
        with self.guard(identity), self.tx() as db:
            row = db.execute(
                "SELECT * FROM operations WHERE id=? AND owner=? AND kind=?",
                (operation_id, identity.owner, kind),
            ).fetchone()
        if not row:
            raise DiscoveryError("operation_not_found", 404)
        return json.loads(row["payload"])

    def _reserve(self, body, identity, kind):
        try:
            if str(UUID(body["operation_id"])) != body["operation_id"]:
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise DiscoveryError("invalid_operation_id", 422) from None
        semantic = digest([kind, body])
        op = body["operation_id"]
        with self.guard(identity), self.tx() as db:
            row = db.execute("SELECT * FROM operations WHERE id=?", (op,)).fetchone()
            if row:
                if row["owner"] != identity.owner:
                    raise DiscoveryError("operation_not_found", 404)
                if row["digest"] != semantic or row["kind"] != kind:
                    raise DiscoveryError("operation_conflict")
                return json.loads(row["payload"])
            receipt = dict(
                schema_version="cplus-discovery-search-v1"
                if kind == "search"
                else "cplus-import-v1",
                operation_id=op,
                state="unknown",
                phase="reserved",
                items=[],
                error_code=None,
            )
            db.execute(
                "INSERT INTO operations VALUES(?,?,?,?,?)",
                (op, identity.owner, kind, semantic, canonical(receipt)),
            )
        return None

    def _update(self, op, identity, **fields):
        with self.guard(identity), self.tx() as db:
            row = db.execute(
                "SELECT payload FROM operations WHERE id=? AND owner=?", (op, identity.owner)
            ).fetchone()
            value = json.loads(row[0])
            value.update(fields)
            db.execute(
                "UPDATE operations SET payload=? WHERE id=? AND owner=?",
                (canonical(value), op, identity.owner),
            )
        return value

    def _candidate(self, candidate_id, identity, kind):
        with self.guard(identity), self.tx() as db:
            row = db.execute(
                "SELECT * FROM candidates WHERE id=? AND owner=? AND kind=?",
                (candidate_id, identity.owner, kind),
            ).fetchone()
        if not row or row["expires"] <= time.time():
            raise DiscoveryError("candidate_expired_or_missing")
        payload = json.loads(row["payload"])
        if digest(payload) != row["digest"]:
            raise DiscoveryError("candidate_integrity_error", 503)
        return {**payload, "candidate_digest": row["digest"]}

    def _security(self, security_id, identity):
        with self.guard(identity), self.tx() as db:
            row = db.execute(
                "SELECT id FROM candidates WHERE owner=? AND kind='company' AND security_id=? ORDER BY expires DESC LIMIT 1",
                (identity.owner, security_id),
            ).fetchone()
        if not row:
            raise DiscoveryError("select_company_candidate_first", 422)
        return self._candidate(row["id"], identity, "company")

    async def post_search(self, body, identity):
        # Strict DTO validation is shared by direct use and HTTP.
        from .api import SearchRequest

        body = SearchRequest.model_validate(body).model_dump(mode="json")
        previous = self._reserve(body, identity, "search")
        if previous:
            return previous
        op = body["operation_id"]
        try:
            if body["mode"] == "companies":
                rows = await self.provider.companies(body["query"])
                kind = "company"
                partial = False
            else:
                selected = self._security(body["security_id"], identity)
                rows, partial = await self.provider.announcements(
                    selected, body["report_year"], body["kind"]
                )
                kind = "announcement"
            items = []
            with self.guard(identity), self.tx() as db:
                for raw in rows:
                    item = dict(raw)
                    # Stable public-version key excludes private search token/expiry.
                    item["version_digest"] = digest(raw)
                    item.update(
                        candidate_id=str(uuid4()),
                        checked_at=time.time(),
                        expires_at=min(identity.expires_at, time.time() + 1800),
                    )
                    sha = digest(item)
                    sid = item.get("security_id") or item["security_identity"]["security_id"]
                    db.execute(
                        "INSERT INTO candidates VALUES(?,?,?,?,?,?,?)",
                        (
                            item["candidate_id"],
                            identity.owner,
                            kind,
                            sid,
                            item["expires_at"],
                            canonical(item),
                            sha,
                        ),
                    )
                    items.append({**item, "candidate_digest": sha})
                receipt = dict(
                    schema_version="cplus-discovery-search-v1",
                    operation_id=op,
                    state="completed",
                    phase="discovered",
                    items=items,
                    partial=partial,
                    limitations=[
                        "Observed public web adapter; revision completeness and long-term API permission unknown."
                    ],
                    fallback="official_site_or_manual_upload",
                )
                db.execute(
                    "UPDATE operations SET payload=? WHERE id=? AND owner=?",
                    (canonical(receipt), op, identity.owner),
                )
            return receipt
        except DiscoveryError as exc:
            return self._update(
                op,
                identity,
                state="failed",
                error_code=exc.code,
                fallback="official_site_or_manual_upload",
            )
        # Other failures leave durable UNKNOWN, never automatically repeat a physical request.

    def _ticket(self, ticket_id, identity):
        with self.guard(identity), self.tx() as db:
            row = db.execute(
                "SELECT * FROM tickets WHERE id=? AND owner=?", (ticket_id, identity.owner)
            ).fetchone()
        if not row or row["expires"] <= time.time():
            raise DiscoveryError("ticket_expired_or_missing", 401)
        return json.loads(row["candidate"])

    async def post_import(self, body, identity):
        from .api import ImportRequest

        body = ImportRequest.model_validate(body).model_dump(mode="json")
        previous = self._reserve(body, identity, "import")
        if previous:
            return previous
        op = body["operation_id"]
        try:
            candidate = self._candidate(body["candidate_id"], identity, "announcement")
            if candidate["candidate_digest"] != body["candidate_digest"]:
                raise DiscoveryError("candidate_digest_mismatch")
            if not candidate["security_identity"]["supported"]:
                raise DiscoveryError("unsupported_market", 422)
            ticket_id = str(uuid4())
            ticket = {
                **candidate,
                "requested_company_id": body["company_id"],
                "create_company": body["create_company"],
                "operation_id": op,
                "owner_generation": identity.generation,
                "owner_instance_id": identity.instance_id,
            }
            with self.guard(identity), self.tx() as db:
                db.execute(
                    "INSERT INTO tickets VALUES(?,?,?,?,?)",
                    (
                        ticket_id,
                        identity.owner,
                        min(identity.expires_at, candidate["expires_at"]),
                        op,
                        canonical(ticket),
                    ),
                )
            self._update(op, identity, phase="downloading", ticket_id=ticket_id)
            cached = await self.cache.prepare(ticket_id, identity)
            self._update(
                op,
                identity,
                phase="binding",
                sha256=cached["sha256"],
                cache_hit=cached["cache_hit"],
            )
            resolved = {
                **cached["resolved_identity"],
                "company_id": body["company_id"],
                "create_company": body["create_company"],
            }

            async def on_phase(phase, *, created_company_id=None):
                if phase not in ("company_created", "uploading"):
                    raise DiscoveryError("invalid_binding_phase")
                existing = self.operation(op, identity, "import").get("created_company_id")
                if existing and created_company_id and existing != created_company_id:
                    raise DiscoveryError("company_binding_conflict")
                fields = {"phase": phase}
                if created_company_id:
                    fields["created_company_id"] = created_company_id
                self._update(op, identity, **fields)

            # Root binder MUST guard before each private child company/upload request and final publish.
            with self.guard(identity):
                pass
            result = await self.binder(
                identity, cached["bytes"], resolved, candidate, on_phase=on_phase
            )
            if (
                not isinstance(result, dict)
                or not result.get("document_id")
                or not result.get("company_id")
            ):
                raise RuntimeError("Invalid binder outcome")
            if body["company_id"] and result["company_id"] != body["company_id"]:
                raise RuntimeError("Binder company mismatch")
            self._ticket(ticket_id, identity)
            return self._update(
                op,
                identity,
                state="completed",
                phase="uploaded",
                document_id=result["document_id"],
                company_id=result["company_id"],
                document_state=result.get("status", "unknown"),
            )
        except DiscoveryError as exc:
            current = self.operation(op, identity, "import")
            # Once binding starts any failure may follow a committed child side effect.
            if current["phase"] in ("binding", "company_created", "uploading"):
                return self._update(op, identity, error_code=exc.code)
            return self._update(
                op,
                identity,
                state="failed",
                error_code=exc.code,
                fallback="official_site_or_manual_upload",
            )
        # Transport/binder exceptions intentionally preserve UNKNOWN and last durable phase.
