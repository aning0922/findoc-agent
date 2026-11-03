"""Source-bound v2 candidates, explicit independent receipts, and Decimal analysis."""
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import inspect
import json
from pathlib import Path
import time
from uuid import uuid4

from app.documents.source_models import SourceError
from app.documents.source_repository import evidence_digest
from app.finance_v2.contracts import FinanceError
from app.finance_v2.extraction import canonical, debt_ratio, digest, extract
from app.finance_v2.models import ExtendedMetricV2
from app.finance_v2.store import FinanceStore
from app.rag.parse.models import PDFLayout


@dataclass(frozen=True)
class OwnerAuthorization:
    """Server-created capability, never a request DTO. Integration must verify current owner grant."""
    runtime_root: Path
    principal: str
    expires_at: float


def now():
    return datetime.now(timezone.utc).isoformat()


class ExtendedFinanceService:
    def __init__(self, root: Path, sources, *, confirmation_kind="local_operator"):
        resolved = root.resolve()
        if confirmation_kind not in ("local_operator", "simulated_test"):
            raise ValueError("Invalid server confirmation kind")
        if confirmation_kind == "simulated_test" and (
                not resolved.name.startswith("findoc-finance-v2-test-") or
                resolved.is_relative_to(Path(__file__).resolve().parents[2])):
            raise ValueError("simulated_test requires an explicitly named isolated test root outside the repository")
        actual_db = sources.repository.registry._database_path.resolve()
        if actual_db != resolved / "documents.db":
            raise ValueError("Source service must belong to the same fixed generation root")
        self.store = FinanceStore(root)
        self.root, self.sources = self.store.root, sources
        self.confirmation_kind = confirmation_kind
        self.workspace = sources.documents._workspace_id

    def _owner(self, authorization):
        if (not isinstance(authorization, OwnerAuthorization) or authorization.runtime_root.resolve() != self.root
                or not authorization.principal or authorization.expires_at <= time.time()):
            raise FinanceError("owner_authorization_required", 403)

    async def _perform(self, request, kind, work, *, replay_check=None):
        payload = request.model_dump(mode="json")
        replay = self.store.reserve(request.operation_id, kind, payload)
        if replay is not None:
            if replay_check:
                replay_check(replay)
            return replay
        try:
            result = work()
            return await result if inspect.isawaitable(result) else result
        except (FinanceError, SourceError) as exc:
            self.store.failed(request.operation_id, exc.code)
            raise
        except Exception:
            self.store.failed(request.operation_id, "finance_operation_failed")
            raise FinanceError("finance_operation_failed", 503) from None

    async def _read(self, company_id, document_id, revision):
        source, records = await self.sources.parsed_evidence(document_id, company_id=company_id, source_revision=revision)
        company = (await asyncio.to_thread(self.sources.companies.get, company_id)).model_dump(mode="json")
        return source, records, company

    def _guard(self, db, contexts, metrics=()):
        identities = tuple({**source, "workspace_id": self.workspace} for source, _, _ in contexts)
        self.sources.repository.verify_selection_in(db, identities)
        for source, records, company in contexts:
            current = db.execute("SELECT * FROM companies WHERE workspace_id=? AND company_id=?",
                                 (self.workspace, source["company_id"])).fetchone()
            # datetime serialization follows the existing Company model.
            from app.companies.models import Company
            if current is None or Company.model_validate(dict(current)).model_dump(mode="json") != company:
                raise FinanceError("source_company_changed")
            relevant = {r["evidence_id"]: r for r in records}
            for metric in metrics:
                if metric["document_id"] != source["document_id"]:
                    continue
                for ref in [*metric["evidence_refs"], *metric["basis_refs"]]:
                    record = relevant.get(ref["evidence_id"])
                    row = db.execute("SELECT * FROM document_evidence WHERE evidence_id=? AND source_revision=?",
                                     (ref["evidence_id"], source["source_revision"])).fetchone()
                    if (record is None or row is None or row["physical_page"] != ref["physical_page"] or
                            row["payload_sha256"] != evidence_digest(row["physical_page"], row["text"], row["kind"]) or
                            row["text"] != record["text"]):
                        raise FinanceError("source_evidence_changed")
                    if "layout_sha256" in ref:
                        layout = db.execute("SELECT * FROM document_evidence_layout WHERE evidence_id=?", (ref["evidence_id"],)).fetchone()
                        if layout is None:
                            raise FinanceError("source_evidence_changed")
                        import hashlib
                        if hashlib.sha256(layout["payload_json"].encode()).hexdigest() != layout["payload_sha256"]:
                            raise FinanceError("source_evidence_changed")
                        if digest(PDFLayout.model_validate_json(layout["payload_json"]).model_dump(mode="json")) != ref["layout_sha256"]:
                            raise FinanceError("source_evidence_changed")

    async def collect(self, request):
        async def work():
            context = await self._read(request.company_id, request.document_id, request.expected_source_revision)
            source, records, company = context
            metrics = extract(source, records)
            result = {"schema_version": "extended-metric-collection-v2", "metrics": metrics,
                      "limitations": ["Extracted candidates only; no human financial approval."]}
            with self.store.tx(source=True) as db:
                self._guard(db, [context], metrics)
                for metric in metrics:
                    row = db.execute("SELECT * FROM fv2_metrics WHERE id=?", (metric["metric_id"],)).fetchone()
                    if row and self.store.decode(row) != metric:
                        raise FinanceError("metric_identity_conflict")
                    db.execute("INSERT OR IGNORE INTO fv2_metrics VALUES (?,?,?,?,?,?)", (
                        metric["metric_id"], request.company_id, canonical(metric), digest(metric), canonical(source), canonical(company)))
                self.store.finish(db, request.operation_id, result)
            return result
        return await self._perform(request, "collect", work)

    async def _selected(self, metric_refs):
        with self.store.tx() as db:
            rows = [db.execute("SELECT * FROM fv2_metrics WHERE id=?", (ref,)).fetchone() for ref in metric_refs]
            metrics = [self.store.decode(row) for row in rows]
        groups = {(metric["company_id"], metric["document_id"], metric["source_revision"]) for metric in metrics}
        contexts = []
        for company, document, revision in sorted(groups):
            context = await self._read(company, document, revision)
            source, records, current_company = context
            current = {m["metric_id"]: m for m in extract(source, records)}
            for row, metric in zip(rows, metrics):
                if metric["document_id"] != document:
                    continue
                if (current.get(metric["metric_id"]) != metric or json.loads(row["source_json"]) != source or
                        json.loads(row["company_json"]) != current_company):
                    raise FinanceError("metric_source_changed")
            contexts.append(context)
        return metrics, contexts

    def _receipt(self, db, metric_id, *, production=True, receipt_id=None):
        rows = db.execute("SELECT r.* FROM fv2_receipts r JOIN fv2_receipt_items i ON r.id=i.receipt_id "
                          "WHERE i.metric_id=? AND (? IS NULL OR r.id=?) ORDER BY r.rowid DESC", (metric_id, receipt_id, receipt_id)).fetchall()
        for row in rows:
            receipt = self.store.decode(row)
            if production and receipt["confirmation_kind"] != "local_operator":
                continue
            if db.execute("SELECT 1 FROM fv2_revocations WHERE receipt_id=?", (receipt["receipt_id"],)).fetchone():
                continue
            review = self.store.decode(db.execute("SELECT * FROM fv2_reviews WHERE id=?", (receipt["review_id"],)).fetchone())
            if (not review["acceptable"] or receipt["review_sha256"] != digest(review) or metric_id not in receipt["metric_refs"]
                    or metric_id not in [m["metric_id"] for m in review["metrics"]]):
                raise FinanceError("confirmation_integrity_error", 503)
            return receipt
        return None

    async def list_metrics(self, company_id):
        # Validates company scope even for an empty v2 database.
        await asyncio.to_thread(self.sources.companies.get, company_id)
        with self.store.tx() as db:
            ids = [row[0] for row in db.execute("SELECT id FROM fv2_metrics WHERE company_id=? ORDER BY id", (company_id,))]
        output = []
        for ref in ids:
            try:
                metrics, contexts = await self._selected([ref])
                metric = {**metrics[0], "source_status": "current_valid"}
                with self.store.tx(source=True) as db:
                    self._guard(db, contexts, metrics)
                    receipt = self._receipt(db, ref)
                if receipt and metric["status"] == "candidate":
                    metric.update(status="confirmed", confirmation_ref={"receipt_id": receipt["receipt_id"], "confirmation_kind": "local_operator"})
            except (FinanceError, SourceError) as exc:
                with self.store.tx() as db:
                    metric = self.store.decode(db.execute("SELECT * FROM fv2_metrics WHERE id=?", (ref,)).fetchone())
                metric = {**metric, "historical_value_decimal": metric["value_decimal"], "value_decimal": None,
                          "status": "unsupported", "source_status": "unavailable", "confirmation_ref": None,
                          "unsupported_reasons": [*metric["unsupported_reasons"], exc.code]}
            output.append(ExtendedMetricV2.model_validate(metric).model_dump(mode="json", exclude_unset=True))
        return {"schema_version": "extended-metric-list-v2", "company_id": company_id, "metrics": output,
                "limitations": ["Candidates and simulated_test receipts are not confirmed financial facts."]}

    async def review(self, request):
        async def work():
            metrics, contexts = await self._selected(request.metric_refs)
            review = {"schema_version": "extended-review-v2", "review_id": str(uuid4()), "metrics": metrics,
                      "acceptable": all(m["status"] == "candidate" for m in metrics), "created_at": now()}
            result = {**review, "review_sha256": digest(review)}
            with self.store.tx(source=True) as db:
                self._guard(db, contexts, metrics)
                db.execute("INSERT INTO fv2_reviews VALUES (?,?,?)", (review["review_id"], canonical(review), digest(review)))
                self.store.finish(db, request.operation_id, result)
            return result
        return await self._perform(request, "review", work)

    async def confirm(self, request, authorization=None):
        self._owner(authorization)
        async def work():
            with self.store.tx() as db:
                review = self.store.decode(db.execute("SELECT * FROM fv2_reviews WHERE id=?", (request.review_id,)).fetchone())
            if digest(review) != request.review_sha256 or not review["acceptable"]:
                raise FinanceError("review_not_acceptable")
            refs = [m["metric_id"] for m in review["metrics"]]
            metrics, contexts = await self._selected(refs)
            if metrics != review["metrics"]:
                raise FinanceError("review_changed")
            receipt = {"schema_version": "extended-confirmation-v2", "receipt_id": str(uuid4()),
                       "review_id": request.review_id, "review_sha256": request.review_sha256,
                       "metric_refs": refs, "confirmation_kind": self.confirmation_kind,
                       "actor": authorization.principal, "confirmed_at": now()}
            with self.store.tx(source=True) as db:
                self._guard(db, contexts, metrics)
                self._owner(authorization)
                db.execute("INSERT INTO fv2_receipts VALUES (?,?,?)", (receipt["receipt_id"], canonical(receipt), digest(receipt)))
                for ref in refs:
                    db.execute("INSERT INTO fv2_receipt_items VALUES (?,?)", (receipt["receipt_id"], ref))
                self.store.finish(db, request.operation_id, receipt)
            return receipt
        return await self._perform(request, "confirm", work)

    async def revoke(self, receipt_id, request, authorization=None):
        self._owner(authorization)
        async def work():
            with self.store.tx() as db:
                receipt = self.store.decode(db.execute("SELECT * FROM fv2_receipts WHERE id=?", (receipt_id,)).fetchone())
                if receipt["confirmation_kind"] != self.confirmation_kind:
                    raise FinanceError("confirmation_kind_mismatch")
                self._owner(authorization)
                prior = db.execute("SELECT * FROM fv2_revocations WHERE receipt_id=?", (receipt_id,)).fetchone()
                result = self.store.decode(prior) if prior else {"receipt_id": receipt_id, "reason": request.reason,
                    "revoked_at": now(), "actor": authorization.principal}
                db.execute("INSERT OR IGNORE INTO fv2_revocations VALUES (?,?,?)", (receipt_id, canonical(result), digest(result)))
                self.store.finish(db, request.operation_id, result)
            return result
        # Include route identity in the operation digest, not just the JSON body.
        return await self._perform(request, "revoke:" + receipt_id, work)

    async def analyse(self, request):
        # Replay also re-admits sources/receipts; a historical success is never a current fact grant.
        metrics, contexts = await self._selected(request.metric_refs)
        with self.store.tx(source=True) as db:
            self._guard(db, contexts, metrics)
            if any(m["status"] != "candidate" or not self._receipt(db, m["metric_id"]) for m in metrics):
                raise FinanceError("current_local_operator_confirmation_required", 403)
        async def work():
            value = debt_ratio(metrics)
            first = metrics[0]
            result = {**first, "metric_id": str(uuid4()), "metric_key": "debt_asset_ratio", "unit": "PERCENT",
                      "status": "confirmed", "value_decimal": value, "formula": "total_liabilities / total_assets * 100",
                      "input_refs": request.metric_refs, "evidence_refs": [ref for m in metrics for ref in m["evidence_refs"]],
                      "calculation_version": "debt-asset-ratio-v1;decimal;half-even;6dp", "confirmation_ref": None}
            with self.store.tx(source=True) as db:
                self._guard(db, contexts, metrics)
                receipts = [self._receipt(db, m["metric_id"]) for m in metrics]
                if any(r is None for r in receipts):
                    raise FinanceError("current_local_operator_confirmation_required", 403)
                result["confirmation_refs"] = [{"receipt_id": r["receipt_id"], "confirmation_kind": "local_operator"} for r in receipts]
                ExtendedMetricV2.model_validate(result)
                db.execute("INSERT INTO fv2_analyses VALUES (?,?,?)", (result["metric_id"], canonical(result), digest(result)))
                self.store.finish(db, request.operation_id, result)
            return result
        def replay_check(cached):
            refs = cached.get("confirmation_refs", [])
            if len(refs) != len(metrics):
                raise FinanceError("confirmation_integrity_error", 503)
            with self.store.tx(source=True) as db:
                self._guard(db, contexts, metrics)
                for metric, ref in zip(metrics, refs):
                    if not self._receipt(db, metric["metric_id"], receipt_id=ref.get("receipt_id")):
                        raise FinanceError("current_local_operator_confirmation_required", 403)
        return await self._perform(request, "analyse", work, replay_check=replay_check)

    def operation(self, operation_id):
        with self.store.tx() as db:
            row = db.execute("SELECT * FROM fv2_operations WHERE id=?", (operation_id,)).fetchone()
            if row is None:
                raise FinanceError("operation_not_found", 404)
            return {"operation_id": operation_id, "state": row["state"], "error_code": row["error_code"],
                    "historical_snapshot": True, "result": json.loads(row["result"]) if row["result"] else None}
