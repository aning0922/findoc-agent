"""Snapshot counts and facts-only charts. Never migrate, confirm, or call a model."""

import asyncio
import json

from collections import Counter, defaultdict
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
import sqlite3
from typing import Any
from urllib.parse import urlencode

from app.agent.financial_analysis import FinancialAnalysisService, FinancialFactReference
from app.agent.revenue_confirmation import RevenueConfirmationError, RevenueConfirmationService
from app.memory.service import MemoryService
from app.research.task_repository import TaskRepository

METRICS = {
    "revenue": "营业收入",
    "net_profit_parent": "归母净利润",
    "operating_cash_flow": "经营现金流",
}


class DashboardError(Exception):
    def __init__(self, code: str, status: int = 503):
        self.code, self.status = code, status
        super().__init__(code)


class DashboardService:
    def __init__(
        self,
        *,
        runtime_root: Path,
        workspace_id: str,
        tasks: TaskRepository,
        facts: RevenueConfirmationService | None = None,
        memory: MemoryService | None = None,
        lease_generation: int | None = None,
        seed_version: str | None = None,
        preset_task_ids: frozenset[str] = frozenset(),
    ):
        self.path = runtime_root.resolve() / "documents.db"
        if not workspace_id.strip() or tasks.workspace != workspace_id:
            raise ValueError("dashboard_workspace_mismatch")
        if tasks.registry._database_path.resolve() != self.path:
            raise ValueError("dashboard_task_database_mismatch")
        if facts is not None and facts.financial_storage_path.resolve() != self.path:
            raise ValueError("dashboard_fact_database_mismatch")
        # Existing MemoryRepository is explicitly scoped to demo/local_operator.
        if memory is not None and workspace_id != "demo":
            raise ValueError("dashboard_memory_scope_mismatch")
        if memory is not None:
            owner = getattr(memory.repository._connect, "__self__", None)
            if owner is None or owner._database_path.resolve() != self.path:
                raise ValueError("dashboard_memory_database_mismatch")
        self.workspace, self.tasks, self.facts, self.memory = workspace_id, tasks, facts, memory
        self.generation, self.seed = lease_generation, seed_version
        self.preset_task_ids = frozenset(preset_task_ids)
        self.archive = self.research = self.showcase_reports = None

    def _connect(self):
        connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        return connection

    def _metadata(self):
        return dict(
            lease_generation=self.generation,
            seed_version=self.seed,
            snapshot_at=datetime.now(UTC).isoformat(),
        )

    def overview(self) -> dict[str, Any]:
        with closing(self._connect()) as conn:
            stamp = self._metadata()
            companies = [
                dict(r)
                for r in conn.execute(
                    "SELECT company_id,name,security_code FROM companies WHERE workspace_id=? "
                    "ORDER BY name,company_id",
                    (self.workspace,),
                )
            ]
            ready = conn.execute(
                "SELECT count(*) FROM documents d JOIN report_document_metadata m "
                "ON m.workspace_id=d.workspace_id AND m.document_id=d.document_id "
                "WHERE d.workspace_id=? AND d.status='ready'",
                (self.workspace,),
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM template_tasks WHERE workspace_id=? ORDER BY sequence DESC",
                (self.workspace,),
            ).fetchall()
            # Decode verifies canonical payload, hashes, identity and budget integrity.
            tasks = [self.tasks.decode(row) for row in rows]
            reports = conn.execute(
                "SELECT count(*) FROM reports WHERE workspace_id=?", (self.workspace,)
            ).fetchone()[0]
        statuses = ["running" if t["execution_status"] == "running" else t["status"] for t in tasks]
        counts = Counter(statuses)
        recent = []
        for task, status in list(zip(tasks, statuses))[:5]:
            # Historical completion is not a claim of current source qualification.
            recent.append(
                dict(
                    id=task["task_id"],
                    title="企业经营研究",
                    status=status,
                    href="/research?" + urlencode({"task": task["task_id"], "mode": "operating"}),
                    origin="preset_demo"
                    if task["task_id"] in self.preset_task_ids
                    else "local_runtime",
                    review_status="source_recheck_required",
                )
            )
        preferences = self._preferences()
        return dict(
            schema_version="dashboard-overview-v1",
            generated_at=stamp["snapshot_at"],
            **stamp,
            data_origin="local_runtime",
            kpis=dict(
                companies=len(companies),
                reports_ready=ready,
                research_completed=counts["completed"],
                reports=reports,
            ),
            task_distribution=[dict(status=s, count=n) for s, n in sorted(counts.items())],
            recent_research=recent,
            suggested_questions=self._suggestions(preferences),
            display_preferences=preferences,
            companies=companies,
            limitations=[
                "研究完成数为已保存历史状态；阅读结果时仍需重新核验来源。",
                "仅统计旧研究Task；尚未混入独立v2 jobs。",
            ],
        )

    async def overview_enriched(self):
        value = await asyncio.to_thread(self.overview)
        counts = Counter({item["status"]: item["count"] for item in value["task_distribution"]})
        recent = list(value["recent_research"])
        if self.research is not None:
            with closing(sqlite3.connect(self.research.store.path.as_uri() + "?mode=ro", uri=True)) as db:
                rows = db.execute("SELECT id,conversation_id,mode,state,created_at,result FROM sr_jobs ORDER BY created_at DESC").fetchall()
            for job_id, cid, mode, state, created, result in rows:
                counts[state] += 1
                if result:
                    saved = json.loads(result)
                    if self.research.store.get(job_id, "job-result") != saved:
                        raise DashboardError("research_snapshot_unverified")
                else:
                    saved = {}
                recent.append(dict(id=job_id, title=saved.get("goal", "正在进行的企业研究"), status=state,
                    href="/conversations?" + urlencode({"conversation": cid, "job": job_id, "research_mode": mode}),
                    origin="local_runtime", review_status="source_recheck_required", saved_at=created))
                value["kpis"]["research_completed"] += state == "completed"
        if self.showcase_reports is not None:
            value["kpis"]["reports"] += len(await asyncio.to_thread(self.showcase_reports.list))
        if self.archive is not None:
            jobs = (await self.archive.list(kind="job"))["items"]
            reports = (await self.archive.list(kind="report"))["items"]
            value["kpis"]["research_completed"] += len({item["original_id"] for item in jobs})
            value["kpis"]["reports"] += len({item["original_id"] for item in reports})
            counts["completed"] += len(jobs)
            for item in jobs:
                recent.append(dict(id=item["archive_id"], title=item["title"], status="completed",
                    href="/tasks?" + urlencode({"case": item["archive_id"]}), origin="preset_demo",
                    review_status=item["current_source_status"], saved_at=item["saved_at"]))
        value["task_distribution"] = [dict(status=status, count=count) for status, count in sorted(counts.items())]
        value["recent_research"] = sorted(recent, key=lambda item: item.get("saved_at", ""), reverse=True)[:5]
        if self.research is not None or self.archive is not None:
            value["limitations"] = ["完成研究和报告包含已保存历史与明确标记的预置案例；当前查看不会重新调用模型。",
                                    "首页图表只显示已核准财务数据，或明确开启的虚构界面示意。"]
        return value

    def _preferences(self):
        values = ({m.key: m.value for m in self.memory.recall_context().items}
                  if self.memory is not None else {})
        return {key: values.get(key, default) for key, default in (
            ("analysis_focus", "balanced"), ("display_unit", "CNY_HUNDRED_MILLION"),
            ("research_habit", "evidence_first"),
        )}

    def _suggestions(self, preferences=None):
        order = list(METRICS)
        if preferences is not None or self.memory is not None:
            focus = (preferences or self._preferences())["analysis_focus"]
            preferred = {
                "cash_flow": "operating_cash_flow",
                "profitability": "net_profit_parent",
                "revenue": "revenue",
            }.get(focus)
            if preferred:
                order.remove(preferred)
                order.insert(0, preferred)
        return [
            dict(
                id=metric,
                text=f"近年{METRICS[metric]}如何变化？",
                href="/conversations?"
                + urlencode({"question": f"近年{METRICS[metric]}如何变化？"}),
            )
            for metric in order
        ]

    async def charts(self, *, company_id: str, metric_key: str, sample_mode: bool):
        if metric_key not in METRICS:
            raise DashboardError("unsupported_metric", 422)
        result = dict(
            schema_version="dashboard-charts-v1",
            **self._metadata(),
            company_id=company_id,
            metric_key=metric_key,
            unit="CNY_YUAN",
            origin="illustrative" if sample_mode else "confirmed_financial",
            points=[],
            comparison=[],
            empty_reason=None,
            limitations=[],
        )
        if sample_mode:
            result["company_id"] = "illustrative-company-a"
            result["limitations"] = ["界面示意数据：虚构企业，不参与财务计算。"]
            result["points"] = [
                dict(
                    period=y,
                    report_year=y + 1,
                    value_decimal=v,
                    source_revision=None,
                    document_id=None,
                    source_state="illustrative",
                )
                for y, v in ((2023, "100000000"), (2024, "120000000"), (2025, "110000000"))
            ]
            return result
        with closing(self._connect()) as conn:
            if not conn.execute(
                "SELECT 1 FROM companies WHERE workspace_id=? AND company_id=?",
                (self.workspace, company_id),
            ).fetchone():
                raise DashboardError("company_not_found", 404)
            exists = conn.execute(
                "SELECT 1 FROM financial_fact_sets WHERE workspace_id=? AND company_id=? LIMIT 1",
                (self.workspace, company_id),
            ).fetchone()
        if not exists:
            result["empty_reason"] = "no_confirmed_facts"
            return result
        if self.facts is None:
            raise DashboardError("financial_service_unavailable")
        query = await self.facts.query_financial_facts(
            workspace_id=self.workspace,
            confirmation_kind="local_operator",
            company_id=company_id,
            metric_key=metric_key,
        )
        analysis = FinancialAnalysisService(facts=self.facts, workspace_id=self.workspace)
        candidates = defaultdict(dict)
        groups = {}
        for fact in query["facts"]:
            if not (
                fact["current_valid"]
                and fact["calculable"]
                and fact["production_calculable"]
                and fact["confirmation_kind"] == "local_operator"
                and fact.get("disclosure_version")
            ):
                continue
            ref = FinancialFactReference(
                fact["fact_set_id"],
                fact["fact_id"],
                fact["period"],
                fact["source_revision"],
                fact["disclosure_version"],
            )
            try:
                group, admitted, reason = await analysis.admit_reference(
                    ref, company_id, metric_key
                )
            except RevenueConfirmationError as exc:
                if exc.code in {"source_changed", "facts_not_calculable", "source_invalid"}:
                    result["limitations"].append(exc.code)
                    continue
                raise
            if reason or group is None or admitted is None:
                result["limitations"].append(reason or "fact_not_admitted")
                continue
            source = group.receipt.review.to_payload()["source"]
            point = dict(
                period=ref.period,
                report_year=source["report_year"],
                value_decimal=admitted["value_cny_yuan"],
                source_revision=ref.source_revision,
                document_id=source["document_id"],
                source_state="current",
                fact_ref=dict(
                    fact_set_id=ref.fact_set_id,
                    fact_id=ref.fact_id,
                    period=ref.period,
                    receipt_id=group.receipt.receipt_id,
                    disclosure_version=ref.disclosure_version,
                    source_revision=ref.source_revision,
                ),
            )
            candidates[ref.period][(ref.fact_set_id, ref.fact_id)] = point
            groups[group.fact_set_id] = group
        for period, points in sorted(candidates.items()):
            if len(points) != 1:
                result["limitations"].append(f"version_selection_required:{period}")
            else:
                result["points"].extend(points.values())
        # Recheck complete source groups after assembling all points; no stale success on race.
        await self.facts.recheck_financial_analysis_sources(
            workspace_id=self.workspace,
            groups=tuple(groups.values()),
            confirmation_kind="local_operator",
        )
        result["empty_reason"] = None if result["points"] else "no_eligible_facts"
        return result
