"""Pure projection from the one admitted, persisted D21 content; no execution services."""

from typing import Any
from app.research.models import canonical, sha
from app.research.task_repository import now
from app.reports.contracts import ReportDraft

LABELS = {
    "revenue": "营业收入",
    "net_profit_parent": "归母净利润",
    "operating_cash_flow": "经营活动现金流量净额",
}


class ReportBuilder:
    def business_fields(self, task: dict[str, Any]) -> dict[str, Any]:
        c = task["final_research_content"]
        names: dict[str, str] = {}
        for analysis in c["deterministic_analysis"]:
            row = analysis["rows"][0] if "rows" in analysis else analysis
            for key in ("current", "previous", "a", "b"):
                if key not in row:
                    continue
                operand = row[key]
                detected = operand["source"]["assessment"]["detected_companies"]
                name = detected[0] if len(detected) == 1 else operand["company_id"]
                if operand["company_id"] in names and names[operand["company_id"]] != name:
                    raise ValueError("frozen_company_name_conflict")
                names[operand["company_id"]] = name
        scope = c["input"]
        comparison = c["template"] == "company_same_period_comparison"
        first, second = scope["first"], scope["second"]
        a, b = names[first["company_id"]], names[second["company_id"]]
        labels = dict(
            first=f"企业 A · {a}" if comparison else f"本期 · {first['period']['year']}",
            second=f"企业 B · {b}" if comparison else f"上期 · {second['period']['year']}",
        )
        title = (
            f"{a} vs {b} · {first['period']['year']} 年经营对比研究"
            if comparison
            else f"{a} · {second['period']['year']}→{first['period']['year']} 经营变化研究"
        )
        facts, analyses, fields, summary = [], [], [], []

        def verified(
            path: str, origin: str, identity: str, snapshot: Any, pending: bool = False
        ) -> None:
            fields.append(
                dict(
                    path=path,
                    origin=origin,
                    identity=identity,
                    snapshot_sha256=sha(canonical(snapshot)),
                    status="pending_semantic_review" if pending else "verified_snapshot",
                )
            )

        for i, item in enumerate(c["financial_facts"]):
            f = item["fact"]
            row = {
                k: f[k]
                for k in (
                    "company_id",
                    "period",
                    "metric_key",
                    "raw_value",
                    "raw_unit",
                    "value_cny_yuan",
                    "unit",
                    "currency",
                    "scope",
                    "accounting_basis",
                    "fact_id",
                    "fact_set_id",
                    "document_id",
                    "source_revision",
                    "content_sha256",
                    "physical_page",
                )
            }
            row.update(
                side=item["side"],
                company_name=names[f["company_id"]],
                receipt_id=item["receipt_id"],
                disclosure_version=item["disclosure_version"],
                confirmation_kind=item["confirmation_kind"],
            )
            facts.append(row)
            for k in row:
                if k == "company_name":
                    verified(
                        f"financial_facts/{i}/{k}",
                        "D11_D13",
                        f["company_id"],
                        c["deterministic_analysis"],
                    )
                else:
                    verified(f"financial_facts/{i}/{k}", "D10", f["fact_id"], item)
        for i, result in enumerate(c["deterministic_analysis"]):
            r = result["rows"][0] if comparison else result
            formula = result["formula"]
            left, right = (r["a"], r["b"]) if comparison else (r["current"], r["previous"])
            row = dict(
                metric_key=r["metric_key"],
                direction="B_minus_A" if comparison else "current_minus_previous",
                first_fact_id=left["fact_id"],
                second_fact_id=right["fact_id"],
                absolute_change=r["absolute_change"],
                percentage_change=r["percentage_change"],
                percentage_reason=r["percentage_reason"],
                absolute_change_unit="CNY_YUAN",
                percentage_change_unit="PERCENT",
                absolute_formula_id=formula["absolute_change_id"],
                percentage_formula_id=formula["percentage_change_id"],
                absolute_expression=formula["absolute_expression"],
                percentage_expression=formula["percentage_expression"],
                limitations=r["limitations"],
            )
            analyses.append(row)
            text = f"{LABELS[r['metric_key']]}：{'B−A 差额' if comparison else '本期−上期差额'} {r['absolute_change']} CNY 元；"
            text += (
                f"{'以 A 为基准的相对差异' if comparison else '同比'} {r['percentage_change']}%。"
                if r["percentage_change"] is not None
                else f"百分比未定义（{r['percentage_reason']}）。"
            )
            summary.append(text)
            for k in row:
                verified(
                    f"financial_analysis/{i}/{k}", "D11_D13", row["percentage_formula_id"], result
                )
            verified(f"executive_summary/{i}", "D11_D13", row["percentage_formula_id"], result)
        for i, d in enumerate(c["operating_descriptions"]):
            verified(f"operating_information/{i}", "D21_PDF", d["citation"]["chunk_id"], d)
        for i, item in enumerate(c["model_interpretations"]):
            verified(
                f"model_interpretations/{i}",
                "D21_pending",
                ",".join(map(str, item["citations"])),
                item,
                True,
            )
        for i, text in enumerate(c["unresolved_questions"]):
            verified(f"unresolved_questions/{i}", "D21_pending", task["task_id"], text, True)
        for i, text in enumerate(c["limitations"]):
            verified(f"limitations/{i}", "D21_scope", task["task_id"], text)
        for key in ("title", "research_question", "research_scope", "side_labels"):
            verified(key, "D21_scope", task["task_id"], scope)
        data = dict(
            task_id=task["task_id"],
            task_revision=task["revision"],
            source_content_sha256=sha(canonical(c)),
            title=title,
            report_type=c["template"],
            research_question=f"在已确认财务事实与选定年报原文范围内，整理{title}。",
            research_scope=scope,
            executive_summary=summary,
            side_labels=labels,
            financial_facts=facts,
            financial_analysis=analyses,
            operating_information=c["operating_descriptions"],
            model_interpretations=c["model_interpretations"],
            unresolved_questions=c["unresolved_questions"],
            limitations=c["limitations"]
            + [
                "草稿尚未保存；当前资格仅在生成复验时有效。",
                "经营原文及模型判断需要人工审阅，引用有效不证明因果。",
            ],
            evidence_appendix=dict(
                selected_reports=c["selected_reports"],
                financial_facts=c["financial_facts"],
                deterministic_analysis=c["deterministic_analysis"],
                operating_evidence=c["evidence_appendix"],
                citations=[d["citation"] for d in c["operating_descriptions"]],
            ),
            field_verification=fields,
            status="simulated_draft" if c["test_mode"] else "qualified_draft",
            test_mode=c["test_mode"],
            watermark="simulated_test · 模拟接受 / 无真人确认 / 非生产可信报告"
            if c["test_mode"]
            else None,
        )
        return data

    def build(self, task: dict[str, Any]) -> ReportDraft:
        data = self.business_fields(task)
        return ReportDraft.model_validate(
            dict(**data, business_content_sha256=sha(canonical(data)), generated_at=now())
        )
