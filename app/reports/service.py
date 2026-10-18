"""Re-admission and field identity checks; never runs D21, retrieval or arithmetic."""

from contextlib import closing
from pathlib import Path
from typing import Any
from pydantic import ValidationError
from app.agent.financial_analysis import IsolatedAnalysisTestConfig
from app.agent.revenue_confirmation import RevenueConfirmationError, ConfirmationKind
from app.agent.sqlite_financial_facts import SQLiteRevenueConfirmationRepository
from app.documents.source_models import SourceError
from app.documents.source_service import DocumentSourceService
from app.research.models import canonical
from app.research.repository import HistoryError
from app.research.task_contracts import TaskRecordV2
from app.research.task_repository import TaskRepository
from app.reports.builder import ReportBuilder
from app.reports.contracts import GenerateDraft, ReportDraft


class ReportService:
    def __init__(
        self,
        tasks: TaskRepository,
        sources: DocumentSourceService,
        *,
        isolated_test: IsolatedAnalysisTestConfig | None = None,
    ):
        self.tasks, self.sources = tasks, sources
        if isolated_test:
            isolated_test.validate(Path(tasks.registry._database_path))
        self.kind: ConfirmationKind = "simulated_test" if isolated_test else "local_operator"
        self.reader = SQLiteRevenueConfirmationRepository(
            tasks.registry._database_path, initialize=False
        )
        self.builder = ReportBuilder()

    def admission(self, conn: Any, request: GenerateDraft) -> dict[str, Any]:
        task = self.tasks.decode(self.tasks.row(conn, request.task_id))
        if task["revision"] != request.expected_revision:
            raise HistoryError("report_task_revision_conflict", 409)
        if (
            task["graph_version"] != "d21-operating-graph-v2"
            or task["status"] != "completed"
            or task["execution_status"] != "idle"
            or task["error_code"]
        ):
            raise HistoryError("report_research_not_completed", 409)
        TaskRecordV2.model_validate(task)
        # The task's qualification is checked on this same caller-owned DB snapshot.
        try:
            self.sources.repository.verify_selection_in(conn, tuple(task["snapshot"]["documents"]))
            self.reader.recheck_financial_fact_sets_in(
                conn,
                workspace_id=self.tasks.workspace,
                receipt_ids=tuple(sorted({f["receipt_id"] for f in task["snapshot"]["facts"]})),
                confirmation_kind="simulated_test"
                if task["snapshot"]["test_mode"]
                else "local_operator",
            )
        except (SourceError, RevenueConfirmationError) as exc:
            raise HistoryError("report_publication_eligibility_invalidated", 409) from exc
        c = task["final_research_content"]
        if (c["test_mode"] == "simulated_test") != (self.kind == "simulated_test"):
            raise HistoryError("report_production_confirmation_required", 409)
        if (
            c["selected_reports"] != task["snapshot"]["documents"]
            or c["deterministic_analysis"] != task["snapshot"]["analysis_results"]
        ):
            raise HistoryError("report_snapshot_mismatch", 409)
        self.sources.repository.verify_selection_in(conn, tuple(c["selected_reports"]))
        groups = self.reader.recheck_financial_fact_sets_in(
            conn,
            workspace_id=self.tasks.workspace,
            receipt_ids=tuple(sorted({f["receipt_id"] for f in c["financial_facts"]})),
            confirmation_kind=self.kind,
        )
        current = {g.receipt.receipt_id: g.to_payload() for g in groups}
        slots = set()
        for item in c["financial_facts"]:
            f = item["fact"]
            group = current[item["receipt_id"]]
            actual = next((v for v in group["facts"] if v["fact_id"] == f["fact_id"]), None)
            side = c["input"][item["side"]]
            if (
                actual != f
                or item["fact_set_id"] != group["fact_set_id"]
                or item["disclosure_version"] != group["disclosure_version"]
                or item["confirmation_kind"] != self.kind
                or item["production_calculable"] != group["production_calculable"]
                or f["company_id"] != side["company_id"]
                or f["period"] != side["period"]["year"]
                or (f["currency"], f["unit"], f["scope"], f["accounting_basis"])
                != ("CNY", "CNY_YUAN", "consolidated", "PRC_GAAP")
            ):
                raise HistoryError("report_fact_identity_mismatch", 409)
            slots.add((item["side"], f["metric_key"]))
        if len(slots) != 6:
            raise HistoryError("report_incomplete_facts", 409)
        comparison = c["template"] == "company_same_period_comparison"
        metrics = set()
        for result in c["deterministic_analysis"]:
            if any(
                result.get(k) != v
                for k, v in {
                    "schema": "financial-company-comparison-v1"
                    if comparison
                    else "financial-analysis-v1",
                    "currency": "CNY",
                    "unit": "CNY_YUAN",
                    "scope": "consolidated",
                    "accounting_basis": "PRC_GAAP",
                }.items()
            ):
                raise HistoryError("report_analysis_basis_mismatch", 409)
            if comparison:
                if (result["company_a_id"], result["company_b_id"], result["period"]) != (
                    c["input"]["first"]["company_id"],
                    c["input"]["second"]["company_id"],
                    c["input"]["first"]["period"]["year"],
                ):
                    raise HistoryError("report_comparison_scope_mismatch", 409)
            elif (
                result["company_id"] != c["input"]["first"]["company_id"]
                or result["absolute_change_unit"] != "CNY_YUAN"
                or result["percentage_change_unit"] != "PERCENT"
            ):
                raise HistoryError("report_analysis_scope_mismatch", 409)
            if result["confirmation_kind"] != self.kind or result["production_calculable"] != (
                self.kind == "local_operator"
            ):
                raise HistoryError("report_analysis_kind_mismatch", 409)
            row = result["rows"][0] if comparison and len(result["rows"]) == 1 else result
            metric = row["metric_key"]
            metrics.add(metric)
            if (
                row["status"] not in ("analyzed", "compared", "partial")
                or row["absolute_change"] is None
            ):
                raise HistoryError("report_analysis_incomplete", 409)
            for side, key in (
                ("first", "a" if comparison else "current"),
                ("second", "b" if comparison else "previous"),
            ):
                operand = row[key]
                frozen = next(
                    v["fact"]
                    for v in c["financial_facts"]
                    if v["side"] == side and v["fact"]["metric_key"] == metric
                )
                if any(operand.get(k) != v for k, v in frozen.items()):
                    raise HistoryError("report_analysis_operand_mismatch", 409)
                selected = c["input"][side]
                selection = row["selection"][key]
                if (
                    any(
                        selection[k] != frozen[k]
                        for k in ("fact_id", "fact_set_id", "period", "source_revision")
                    )
                    or selection["disclosure_version"] != operand["disclosure_version"]
                ):
                    raise HistoryError("report_analysis_selection_mismatch", 409)
                if operand["company_id"] != selected["company_id"]:
                    raise HistoryError("report_analysis_company_mismatch", 409)
            formula = result["formula"]
            if formula["absolute_change_id"] != "financial_absolute_change_v1" or formula[
                "percentage_change_id"
            ] != (
                "financial_company_relative_signed_base_v1"
                if comparison
                else "financial_yoy_signed_base_v1"
            ):
                raise HistoryError("report_formula_mismatch", 409)
            if (
                formula["absolute_expression"],
                formula["percentage_expression"],
                formula["version"],
            ) != (
                ("B - A", "(B - A) / A * 100", "1")
                if comparison
                else ("current - previous", "(current - previous) / previous * 100", "1")
            ):
                raise HistoryError("report_formula_expression_mismatch", 409)
        if len(metrics) != 3:
            raise HistoryError("report_incomplete_analysis", 409)
        return task

    async def pdf_evidence(self, task: dict[str, Any]) -> None:
        c = task["final_research_content"]
        batches = {}
        for report in c["selected_reports"]:
            source, records = await self.sources.parsed_evidence(
                report["document_id"],
                company_id=report["company_id"],
                source_revision=report["source_revision"],
            )
            if any(
                source[k] != report[k]
                for k in (
                    "content_sha256",
                    "attempt",
                    "parser_version",
                    "report_year",
                    "company_id",
                )
            ):
                raise HistoryError("report_pdf_identity_mismatch", 409)
            batches[report["document_id"]] = records
        appendix = c["evidence_appendix"]
        for d in c["operating_descriptions"]:
            cit = d["citation"]
            report = next(
                r for r in c["selected_reports"] if r["document_id"] == cit["document_id"]
            )
            if cit["workspace_id"] != self.tasks.workspace or any(
                cit[k] != report[k]
                for k in (
                    "company_id",
                    "report_year",
                    "report_type",
                    "period_start",
                    "period_end",
                    "basis",
                    "source_revision",
                    "content_sha256",
                    "attempt",
                    "parser_version",
                )
            ):
                raise HistoryError("report_citation_identity_mismatch", 409)
            hits = [
                h
                for h in appendix["retrieval_hits"]
                if h["chunk_id"] == cit["chunk_id"]
                and h["document_id"] == cit["document_id"]
                and h["source_revision"] == cit["source_revision"]
                and h["page"] == cit["physical_page"]
                and h["workspace_id"] == self.tasks.workspace
            ]
            page = [
                e for e in batches[cit["document_id"]] if e["physical_page"] == cit["physical_page"]
            ]
            original = d["text"]
            if (
                not hits
                or not any(
                    (
                        h["text"] in original
                        if cit["kind"] == "paragraph"
                        else h["table_md"] and h["table_md"] in original
                    )
                    for h in hits
                )
                or appendix["originals"].get(str(cit["number"])) != original
                or original != cit["text"]
                or not (
                    any(original in e["text"] for e in page)
                    or "\n".join(e["text"] for e in page) == original
                )
            ):
                raise HistoryError("report_pdf_excerpt_mismatch", 409)

    async def generate(self, request: GenerateDraft) -> ReportDraft:
        try:
            with closing(self.tasks.registry._connect()) as conn, conn:
                conn.execute("BEGIN")
                task = self.admission(conn, request)
            await self.pdf_evidence(task)
            draft = self.builder.build(task)
            await self.pdf_evidence(task)
            # One shared DB snapshot after the last external read, with revision/content fence.
            with closing(self.tasks.registry._connect()) as conn, conn:
                conn.execute("BEGIN IMMEDIATE")
                final = self.admission(conn, request)
                if canonical(final) != canonical(task):
                    raise HistoryError("report_task_changed", 409)
            return draft
        except (SourceError, RevenueConfirmationError) as exc:
            raise HistoryError(exc.code, 409) from exc
        except (ValidationError, KeyError, TypeError, ValueError, StopIteration) as exc:
            raise HistoryError("report_content_integrity_error", 409) from exc
