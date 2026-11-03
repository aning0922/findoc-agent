"""Independent immutable statement snapshots. No legacy fact writes, provider or auto approval."""

from contextlib import contextmanager
from pathlib import Path
import json
import sqlite3
import time
from uuid import uuid4
from decimal import Decimal, localcontext
from datetime import datetime, UTC
from app.finance_v2.service import OwnerAuthorization
from app.finance_v2.contracts import FinanceError
from .extraction import extract, canonical, sha


class StatementService:
    def __init__(self, runtime_root, sources, companies=None):
        self.root = Path(runtime_root).resolve()
        self.sources = sources
        self.companies = companies or sources.companies
        if sources.repository.registry._database_path.resolve() != self.root / "documents.db":
            raise ValueError("source_root_mismatch")
        self.path = self.root / "financial-statements-v3.db"
        with self.tx() as db:
            db.executescript(
                "CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY,kind TEXT,payload TEXT,sha TEXT); CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY,digest TEXT,state TEXT,result TEXT);"
            )
            for action in ("UPDATE", "DELETE"):
                db.execute(
                    f"CREATE TRIGGER IF NOT EXISTS immutable_{action} BEFORE {action} ON records BEGIN SELECT RAISE(ABORT,'immutable'); END"
                )
        self.path.chmod(0o600)

    @contextmanager
    def tx(self, source=False, authorization=None):
        db = sqlite3.connect(self.path, timeout=5, uri=True)
        db.row_factory = sqlite3.Row
        try:
            if source:
                db.execute(
                    "ATTACH DATABASE ? AS source_db",
                    ((self.root / "documents.db").as_uri() + "?mode=ro",),
                )
            db.execute("BEGIN" if source else "BEGIN IMMEDIATE")
            if source:
                # BEGIN alone holds no source SHARED lock. Read before checking journal.
                db.execute("SELECT name FROM source_db.sqlite_master LIMIT 1").fetchall()
                if db.execute("PRAGMA source_db.journal_mode").fetchone()[0].lower() == "wal":
                    raise FinanceError("wal_source_fence_unsupported", 503)
            yield db
            if authorization is not None:
                self.owner(authorization)
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _record(self, db, kind, value):
        db.execute(
            "INSERT INTO records VALUES (?,?,?,?)",
            (value["id"], kind, canonical(value), sha(value)),
        )
        return value

    def read(self, record_id, kind=None, db=None):
        if db is None:
            with self.tx() as connection:
                return self.read(record_id, kind, connection)
        row = db.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
        if row is None or kind and row["kind"] != kind:
            raise FinanceError("statement_record_not_found", 404)
        value = json.loads(row["payload"])
        if sha(value) != row["sha"]:
            raise FinanceError("statement_integrity_error", 503)
        return value

    def reserve(self, op, request):
        from uuid import UUID

        if str(UUID(op)) != op:
            raise FinanceError("invalid_operation_id", 422)
        digest = sha(request)
        with self.tx() as db:
            row = db.execute("SELECT * FROM operations WHERE id=?", (op,)).fetchone()
            if row:
                if row["digest"] != digest:
                    raise FinanceError("operation_conflict")
                if row["state"] != "completed":
                    raise FinanceError("operation_unknown")
                return json.loads(row["result"])
            db.execute("INSERT INTO operations VALUES (?,?,'unknown',NULL)", (op, digest))

    def finish(self, db, op, value):
        db.execute(
            "UPDATE operations SET state='completed',result=? WHERE id=?", (canonical(value), op)
        )
        return value

    def operation(self, op):
        with self.tx() as db:
            row = db.execute("SELECT * FROM operations WHERE id=?", (op,)).fetchone()
        if not row:
            raise FinanceError("operation_not_found", 404)
        return {
            "operation_id": op,
            "state": row["state"],
            "historical_snapshot": True,
            "result": json.loads(row["result"]) if row["result"] else None,
        }

    async def context(self, document, revision):
        source = await self.sources.source(document, source_revision=revision)
        raw = await self.sources.file(document, source_revision=revision)
        if source.get("report_type") != "annual" or any(
            source.get("assessment", {}).get(k) != "matches_cover"
            for k in ("company", "report_year", "report_type")
        ):
            raise FinanceError("statement_identity_unverified")
        source = {
            **source,
            "company_snapshot": self.companies.get(source["company_id"]).model_dump(mode="json"),
        }
        return source, extract(source, raw)

    def guard(self, db, contexts):
        self.sources.repository.verify_selection_in(
            db,
            tuple(
                {**source, "workspace_id": self.sources.documents._workspace_id}
                for source, _ in contexts
            ),
        )

        for source, _ in contexts:
            current = self.sources.repository.registry._company(
                db, self.sources.documents._workspace_id, source["company_id"]
            ).model_dump(mode="json")
            if current != source["company_snapshot"]:
                raise FinanceError("statement_company_changed")

    def owner(self, authorization):
        if (
            not isinstance(authorization, OwnerAuthorization)
            or authorization.runtime_root.resolve() != self.root
            or not authorization.principal
            or authorization.expires_at <= time.time()
        ):
            raise FinanceError("owner_authorization_required", 403)

    async def collect(self, operation_id, document_id, expected_source_revision):
        old = self.reserve(operation_id, ["collect", document_id, expected_source_revision])
        if old:
            return await self.collection(old["id"])
        source, cells = await self.context(document_id, expected_source_revision)
        value = {
            "id": str(uuid4()),
            "collection_id": None,
            "schema_version": "statement-collection-v3",
            "source": source,
            "cells": cells,
            "human_approvals": 0,
        }
        value["collection_id"] = value["id"]
        value["payload_sha256"] = sha(value)
        with self.tx(source=True) as db:
            self.guard(db, [(source, cells)])
            self._record(db, "collection", value)
            return self.finish(db, operation_id, value)

    async def selected(self, refs):
        collections = [
            self.read(ref["collection_id"] if isinstance(ref, dict) else ref, "collection")
            for ref in refs
        ]
        contexts = []
        for c in collections:
            context = await self.context(c["source"]["document_id"], c["source"]["source_revision"])
            if context[0] != c["source"] or context[1] != c["cells"]:
                raise FinanceError("statement_source_changed")
            contexts.append(context)
        for index, ref in enumerate(refs):
            if isinstance(ref, dict) and "cell_ids" in ref:
                chosen = ref["cell_ids"]
                if len(set(chosen)) != len(chosen) or set(chosen) - {
                    c["cell_id"] for c in collections[index]["cells"]
                }:
                    raise FinanceError("invalid_collection_cell_selection", 422)
                collections[index] = {
                    **collections[index],
                    "cells": [c for c in collections[index]["cells"] if c["cell_id"] in chosen],
                }
        return collections, contexts

    async def review(self, operation_id, cell_refs):
        old = self.reserve(operation_id, ["review", cell_refs])
        if old:
            return old
        with self.tx() as db:
            all_collections = [
                self.read(r[0], "collection", db)
                for r in db.execute("SELECT id FROM records WHERE kind='collection'")
            ]
        picked = []
        collections = {}
        for ref in cell_refs:
            matches = [
                (c, cell)
                for c in all_collections
                for cell in c["cells"]
                if cell["cell_id"] == ref["cell_id"]
                and cell["cell_revision"] == ref["cell_revision"]
                and cell["payload_sha256"] == ref["payload_sha256"]
            ]
            unique = {sha(cell): (c, cell) for c, cell in matches}
            if len(unique) != 1:
                raise FinanceError("cell_reference_ambiguous_or_missing")
            c, cell = next(iter(unique.values()))
            collections[c["id"]] = c
            picked.append(cell)
        if not picked or len({c["cell_id"] for c in picked}) != len(picked):
            raise FinanceError("invalid_cell_selection", 422)
        _, contexts = await self.selected(list(collections))
        value = {
            "id": str(uuid4()),
            "schema_version": "statement-review-v3",
            "cells": picked,
            "collection_refs": list(collections),
            "acceptable": all(
                c["extraction_status"] == "candidate" and c["source_kind"] == "fast_text"
                for c in picked
            ),
        }
        value["review_id"] = value["id"]
        value["review_sha256"] = sha(value)
        with self.tx(source=True) as db:
            self.guard(db, contexts)
            self._record(db, "review", value)
            return self.finish(db, operation_id, value)

    async def confirm(self, operation_id, review_id, review_sha256, confirmed, authorization):
        self.owner(authorization)
        if confirmed is not True:
            raise FinanceError("explicit_confirmation_required", 422)
        review = self.read(review_id, "review")
        if review["review_sha256"] != review_sha256 or not review["acceptable"]:
            raise FinanceError("review_not_acceptable")
        _, contexts = await self.selected(review["collection_refs"])
        old = self.reserve(operation_id, ["confirm", review_id, review_sha256])
        if old:
            return old
        value = {
            "id": str(uuid4()),
            "schema_version": "statement-receipt-v3",
            "review_id": review_id,
            "cell_refs": [
                {"cell_id": c["cell_id"], "payload_sha256": c["payload_sha256"]}
                for c in review["cells"]
            ],
            "confirmation_kind": "local_operator",
            "confirmed_at": datetime.now(UTC).isoformat(),
            "actor": authorization.principal,
        }
        value["receipt_id"] = value["id"]
        with self.tx(source=True, authorization=authorization) as db:
            self.guard(db, contexts)
            self.owner(authorization)
            self._record(db, "receipt", value)
            return self.finish(db, operation_id, value)

    async def revoke(self, receipt_id, operation_id, reason, authorization):
        self.owner(authorization)
        self.read(receipt_id, "receipt")
        old = self.reserve(operation_id, ["revoke", receipt_id, reason])
        if old:
            return old
        value = {
            "id": str(uuid4()),
            "receipt_id": receipt_id,
            "reason": reason,
            "revoked_at": datetime.now(UTC).isoformat(),
            "actor": authorization.principal,
        }
        with self.tx(authorization=authorization) as db:
            self.owner(authorization)
            self._record(db, "revocation", value)
            return self.finish(db, operation_id, value)

    def admitted(self, db, cell):
        revoked = {
            json.loads(r[0])["receipt_id"]
            for r in db.execute("SELECT payload FROM records WHERE kind='revocation'")
        }
        for row in db.execute("SELECT * FROM records WHERE kind='receipt'"):
            receipt = self.read(row["id"], "receipt", db)
            if receipt["id"] not in revoked and any(
                r["cell_id"] == cell["cell_id"] and r["payload_sha256"] == cell["payload_sha256"]
                for r in receipt["cell_refs"]
            ):
                return receipt["id"]
        return None

    async def trends(self, operation_id, collection_refs, metric_keys, candidate_view=False):
        collections, contexts = await self.selected(collection_refs)
        old = self.reserve(operation_id, ["trends", collection_refs, metric_keys, candidate_view])
        if old:
            with self.tx(source=True) as db:
                self.guard(db, contexts)
                if any(
                    point.get("receipt_ref") and self.admitted(db, point) != point["receipt_ref"]
                    for point in old["points"]
                ):
                    raise FinanceError("projection_confirmation_revoked")
            return old
        points = []
        seen = set()
        with self.tx(source=True) as db:
            self.guard(db, contexts)
            for collection in collections:
                for cell in collection["cells"]:
                    if (
                        cell["metric_key"] not in metric_keys
                        or cell["extraction_status"] != "candidate"
                    ):
                        continue
                    key = (cell["company_id"], cell["metric_key"], canonical(cell["time"]))
                    if key in seen:
                        raise FinanceError("explicit_disclosure_selection_required")
                    seen.add(key)
                    receipt = self.admitted(db, cell)
                    if receipt or candidate_view:
                        points.append(
                            {
                                **cell,
                                "source_status": "current",
                                "financial_review": "local_operator_confirmed"
                                if receipt
                                else "unconfirmed",
                                "receipt_ref": receipt,
                            }
                        )
            changes = []
            groups = {}
            for point in points:
                groups.setdefault((point["company_id"], point["metric_key"]), []).append(point)
            for (company, key), series in groups.items():
                series = sorted(series, key=lambda p: canonical(p["time"]))
                for earlier, later in zip(series, series[1:]):
                    comparable = (
                        earlier["basis"] == later["basis"]
                        and earlier["time"]["kind"] == later["time"]["kind"]
                    )
                    with localcontext() as context:
                        context.prec = max(
                            60,
                            len(earlier["normalized_decimal"])
                            + len(later["normalized_decimal"])
                            + 20,
                        )
                        old_value, new_value = (
                            Decimal(earlier["normalized_decimal"]),
                            Decimal(later["normalized_decimal"]),
                        )
                        delta = new_value - old_value
                        growth = (
                            format(delta / old_value * 100, ".6f")
                            if comparable and old_value > 0
                            else None
                        )
                    changes.append(
                        {
                            "company_id": company,
                            "metric_key": key,
                            "input_refs": [earlier["cell_id"], later["cell_id"]],
                            "from_time": earlier["time"],
                            "to_time": later["time"],
                            "delta_decimal": format(delta, "f") if comparable else None,
                            "change_percent_decimal": growth,
                            "reason": None
                            if growth is not None
                            else "incomparable_or_nonpositive_baseline",
                            "formula_version": "positive-base-change-v1;decimal;half-even;6dp",
                            "financial_review": "local_operator_confirmed"
                            if all(p["receipt_ref"] for p in (earlier, later))
                            else "unconfirmed",
                        }
                    )
            value = {
                "id": str(uuid4()),
                "schema_version": "statement-trend-v3",
                "changes": changes,
                "points": points,
                "collection_refs": collection_refs,
                "candidate_view": candidate_view,
                "limitations": [
                    "No missing points filled; selected versions only; candidates are unconfirmed."
                ],
            }
            self._record(db, "trend", value)
            return self.finish(db, operation_id, value)

    async def collection(self, collection_id):
        value = self.read(collection_id, "collection")
        try:
            await self.selected([collection_id])
            state = "current"
        except Exception:
            state = "unavailable"
        return {**value, "source_status": state, "historical_snapshot": True}

    async def list_collections(self, company_id):
        self.companies.get(company_id)
        with self.tx() as db:
            values = [
                self.read(r[0], "collection", db)
                for r in db.execute("SELECT id FROM records WHERE kind='collection'")
            ]
        return {
            "schema_version": "statement-collection-list-v3",
            "collections": [
                await self.collection(c["id"])
                for c in values
                if c["source"]["company_id"] == company_id
            ],
            "historical_snapshot": True,
        }
