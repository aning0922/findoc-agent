import inspect
from decimal import Decimal, localcontext
import time
from uuid import uuid4
from app.retrieval_v2.service import resolve, sha
from app.retrieval_v2.models import RetrievalError
from .store import Store


class PeerComparisonService:
    def __init__(
        self,
        runtime_root,
        *,
        statements,
        identity_validator,
        publication_guard,
        memory=None,
        commit_check=None,
    ):
        if statements.root.resolve() != runtime_root.resolve():
            raise ValueError("peer_runtime_mismatch")
        self.statements, self.validator, self.guard, self.memory = (
            statements,
            identity_validator,
            publication_guard,
            memory,
        )
        self.commit_check = commit_check
        self.store = Store(runtime_root, "peer-compare")

    async def owner(self, identity):
        if (
            self.validator is None
            or identity.expires_at <= time.time()
            or identity.workspace_id != self.statements.sources.documents.workspace_id
        ):
            raise RetrievalError("trusted_identity_required", 403)
        if await resolve(self.validator(identity)) is False:
            raise RetrievalError("identity_rejected", 403)
        return sha(identity.model_dump())

    async def compare(self, body, identity):
        owner = await self.owner(identity)
        if not self.store.reserve(body["operation_id"], owner, body):
            return self.store.operation(body["operation_id"], owner)
        if self.guard is None or self.commit_check is None:
            raise RetrievalError("publication_guard_required", 503)
        companies = body["company_ids"]
        refs = body["collection_refs"]
        candidate = body.get("candidate_view", False)
        if (
            not 2 <= len(companies) <= 3
            or len(set(companies)) != len(companies)
            or any(not isinstance(r, dict) or not r.get("cell_ids") for r in refs)
        ):
            raise RetrievalError("explicit_company_cells_required", 422)
        collections, contexts = await self.statements.selected(refs)
        if {c["source"]["company_id"] for c in collections} != set(companies):
            raise RetrievalError("selected_company_mismatch", 422)
        generation = None
        if self.memory is not None:
            with self.memory.tx() as db:
                generation = self.memory._generation(db)
        points = []
        with self.statements.tx(source=True) as db:
            self.statements.guard(db, contexts)
            for collection in collections:
                for cell in collection["cells"]:
                    receipt = self.statements.admitted(db, cell)
                    available = (
                        cell["extraction_status"] == "candidate"
                        and cell.get("normalized_decimal") is not None
                        and (receipt is not None or candidate)
                    )
                    points.append(
                        dict(
                            cell,
                            receipt_ref=receipt,
                            financial_review="local_operator_confirmed"
                            if receipt
                            else "unconfirmed",
                            available=available,
                            unavailable_reason=None
                            if available
                            else "unsupported_or_confirmation_missing",
                        )
                    )
        groups = {}
        for p in points:
            groups.setdefault(p["metric_key"], []).append(p)
        comparisons = []
        for key, rows in groups.items():
            selected = []
            reason = None
            for company in companies:
                matches = [p for p in rows if p["company_id"] == company]
                if len(matches) != 1:
                    reason = "missing_or_ambiguous_period_selection"
                    break
                selected.append(matches[0])
            if not reason and not all(p["available"] for p in selected):
                reason = "unsupported_or_confirmation_missing"
            dimensions = ("time", "basis", "scope", "currency", "normalized_unit")
            if not reason and any(
                any(p.get(k) != selected[0].get(k) for k in dimensions) for p in selected[1:]
            ):
                reason = "incomparable_period_unit_basis_scope_currency"
            deltas = []
            if not reason:
                with localcontext() as ctx:
                    ctx.prec = max(60, sum(len(p["normalized_decimal"]) for p in selected) + 20)
                    baseline = Decimal(selected[0]["normalized_decimal"])
                    for p in selected[1:]:
                        value = Decimal(p["normalized_decimal"])
                        if not value.is_finite() or not baseline.is_finite():
                            raise RetrievalError("nonfinite_decimal")
                        deltas.append(
                            dict(
                                left_company_id=selected[0]["company_id"],
                                right_company_id=p["company_id"],
                                delta_decimal=format(value - baseline, "f"),
                                input_cell_ids=[selected[0]["cell_id"], p["cell_id"]],
                                formula_version="peer-difference-decimal-v1",
                            )
                        )
            comparisons.append(
                dict(
                    metric_key=key,
                    state="incomparable"
                    if reason
                    else "candidate_observation"
                    if any(not p["receipt_ref"] for p in selected)
                    else "confirmed_comparison",
                    reason=reason,
                    points=selected,
                    differences=deltas,
                )
            )
        payload = dict(
            schema_version="peer-comparison-v1",
            result_id=str(uuid4()),
            company_ids=companies,
            collection_refs=refs,
            candidate_view=candidate,
            comparisons=comparisons,
            memory_generation=generation,
            industry_status="user_selected_not_industry_certified",
            limitations=[
                "用户明确选择比较对象不代表已认证同行。",
                "仅在同期间、单位、口径及合并范围下比较；缺值不补零。",
                "候选差额只是待核对观察，不授予财务确认资格。",
            ],
        )
        payload["payload_sha256"] = sha(payload)
        await self.owner(identity)
        fence = dict(
            selected_sources=[c["source"] for c in collections],
            collection_refs=refs,
            memory_generation=generation,
        )
        with self.guard(identity, fence):
            with self.statements.tx(source=True) as db:
                self.statements.guard(db, contexts)
                if db.execute("PRAGMA main.journal_mode").fetchone()[0].lower() == "wal":
                    raise RetrievalError("wal_receipt_fence_unsupported", 503)
                for p in points:
                    if self.statements.admitted(db, p) != p["receipt_ref"]:
                        raise RetrievalError("receipt_changed")
                if self.memory is not None:
                    self.memory.check_generation(generation)
                # Both statement receipt/source read locks remain held through peer COMMIT.
                with self.store.tx(
                    before_commit=lambda: self.before_commit(identity, fence)
                ) as output:
                    self.store.finish(
                        output, payload["result_id"], owner, body["operation_id"], payload
                    )
        return self.store.operation(body["operation_id"], owner)

    def before_commit(self, identity, fence):
        if identity.expires_at <= time.time():
            raise RetrievalError("identity_expired_before_commit", 403)
        value = self.commit_check(identity, fence)
        if inspect.isawaitable(value):
            if inspect.iscoroutine(value):
                value.close()
            raise RetrievalError("synchronous_commit_check_required", 503)
        if value is False or identity.expires_at <= time.time():
            raise RetrievalError("identity_rejected_before_commit", 403)

    async def read(self, key, identity):
        value = self.store.read(key, await self.owner(identity))
        status = "current"
        try:
            collections, contexts = await self.statements.selected(value["collection_refs"])
            with self.statements.tx(source=True) as db:
                self.statements.guard(db, contexts)
                for group in value["comparisons"]:
                    for p in group["points"]:
                        if self.statements.admitted(db, p) != p["receipt_ref"]:
                            raise RetrievalError("receipt_changed")
        except Exception:
            status = "stale_or_receipt_changed"
        return {**value, "historical_snapshot": True, "current_source_status": status}
