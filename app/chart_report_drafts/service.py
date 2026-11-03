"""Explicit copy of an immutable server trend into one draft revision, no browser values."""

from uuid import uuid4
from app.peer_compare.store import Store
from app.retrieval_v2.models import RetrievalError
from app.research_templates_v1.shared import (
    check_receipts,
    commit_check,
    now,
    owner,
    selected_points,
    source_ref,
    validate_point_snapshot,
)


class ChartReportDraftService:
    def __init__(self, root, *, statements, identity_validator, publication_guard, commit_check):
        if statements.root != root.resolve():
            raise ValueError("chart_report_runtime_mismatch")
        self.statements, self.validator, self.guard, self.commit_check = (
            statements,
            identity_validator,
            publication_guard,
            commit_check,
        )
        self.store = Store(root, "chart-report-drafts")

    async def owner(self, i):
        return await owner(i, self.validator, self.statements.sources.documents.workspace_id)

    async def reload(self, trend_id, metrics):
        trend = self.statements.read(trend_id, "trend")
        if trend.get("schema_version") != "statement-trend-v3":
            raise RetrievalError("chart_requires_statement_trend_v3", 422)
        saved = [p for p in trend["points"] if p["metric_key"] in metrics]
        if not saved or len(saved) > 64 or set(metrics) - {p["metric_key"] for p in saved}:
            raise RetrievalError("chart_selected_metrics_unavailable", 422)
        collections, contexts, points = await selected_points(
            self.statements, trend["collection_refs"]
        )
        ids = {p["cell_id"] for p in saved}
        current = [p for p in points if p["cell_id"] in ids]
        validate_point_snapshot(saved, current)
        refs = [
            dict(
                collection_id=c["id"],
                cell_ids=[p["cell_id"] for p in c["cells"] if p["cell_id"] in ids],
            )
            for c in collections
        ]
        refs = [r for r in refs if r["cell_ids"]]
        sources = [
            source_ref(self.statements, c["source"])
            for c in collections
            if any(p["cell_id"] in ids for p in c["cells"])
        ]
        return trend, contexts, current, refs, sources

    async def create(self, request, i):
        who = await self.owner(i)
        if self.guard is None or self.commit_check is None:
            raise RetrievalError("publication_hooks_required", 503)
        if not self.store.reserve(request.operation_id, who, request.model_dump()):
            return self.store.operation(request.operation_id, who)
        if len(set(request.metric_keys)) != len(request.metric_keys):
            raise RetrievalError("duplicate_chart_metric", 422)
        trend, contexts, points, refs, sources = await self.reload(
            request.trend_id, request.metric_keys
        )
        result = dict(
            schema_version="chart-report-v1",
            report_id=str(uuid4()),
            revision=1,
            status="draft",
            trend_id=trend["id"],
            selected_sources=sources,
            collection_refs=refs,
            financial_points=points,
            chart={
                "kind": request.chart_kind,
                "metric_keys": request.metric_keys,
                "record_refs": [
                    {k: p[k] for k in ("cell_id", "cell_revision", "payload_sha256")}
                    for p in points
                ],
            },
            financial_authority=False,
            created_at=now(),
            limitations=["这是从明确选择的服务器数据复制的报告草稿版本1；候选金额待核对。"],
        )
        await self.owner(i)
        with self.guard(i, result):
            with self.statements.tx(source=True) as source_db:
                self.statements.guard(source_db, contexts)
                check_receipts(self.statements, source_db, points)
                with self.store.tx(
                    before_commit=lambda: commit_check(self.commit_check, i, result)
                ) as db:
                    self.store.finish(db, result["report_id"], who, request.operation_id, result)
        return self.store.operation(request.operation_id, who)

    async def read(self, identifier, i):
        value = self.store.read(identifier, await self.owner(i))
        status = "current"
        try:
            _, _, points, _, _ = await self.reload(value["trend_id"], value["chart"]["metric_keys"])
            validate_point_snapshot(value["financial_points"], points)
            with self.guard(i, value):
                pass
        except Exception:
            status = "stale_or_unavailable"
        await self.owner(i)
        return {**value, "historical_snapshot": True, "current_source_status": status}

    async def operation(self, op, i):
        return self.store.operation(op, await self.owner(i))
