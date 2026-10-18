"""Single D11 application entry point over D10 durable, admitted facts."""

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import gettempdir
from typing import Any

from app.agent.finance_tools import financial_period_change_v1
from app.agent.metric_extraction import METRICS, parse_amount
from app.agent.revenue_confirmation import (
    ConfirmationKind,
    FinancialFactSet,
    RevenueConfirmationError,
    RevenueConfirmationService,
)


@dataclass(frozen=True)
class FinancialFactReference:
    fact_set_id: str
    fact_id: str
    period: int
    source_revision: str
    disclosure_version: str | None


@dataclass(frozen=True)
class IsolatedAnalysisTestConfig:
    """Server-only opt-in; bind the actual SQLite reader to a disposable root.

    The HTTP router never accepts this configuration, even when the review
    harness uses simulated_test. A production API cannot promote that kind.
    """

    runtime_root: Path

    def validate(self, storage_path: Path) -> None:
        root = self.runtime_root.resolve()
        if (
            not self.runtime_root.is_absolute()
            or not root.is_dir()
            or not root.name.startswith("findoc-d11-")
            or not root.is_relative_to(Path(gettempdir()).resolve())
            or root.is_relative_to(Path(__file__).resolve().parents[2])
            or not storage_path.resolve().is_relative_to(root)
        ):
            raise ValueError("An isolated findoc-d11-* SQLite runtime is required")


REASONS = {
    "same_company": "企业 A 与企业 B 必须为不同企业。",
    "period_mismatch": "双方必须为同一财务年度及期间起止，不能跨年比较。",
    "missing_current_fact": "缺少本期已确认事实，不能补零。",
    "missing_previous_fact": "缺少上期已确认事实，不能补零。",
    "version_selection_required": "请明确选择两个期间的披露版本；系统不会自动取值。",
    "selection_mismatch": "事实 ID、事实组、期间或来源与选择不一致。",
    "company_mismatch": "事实不属于所选企业，不能分析。",
    "metric_mismatch": "两条事实的指标必须相同并匹配所选指标。",
    "invalid_period": "首版仅支持具有有效起止日期的自然年度全年事实。",
    "invalid_period_order": "本期必须晚于上期。",
    "unit_conflict": "两期必须使用人民币及规范 CNY 元单位。",
    "scope_conflict": "两期必须采用一致的合并报表口径。",
    "basis_conflict": "两期必须采用一致的中国企业会计准则。",
    "facts_not_calculable": "事实、确认或来源状态无效，不能分析。",
    "production_calculable_required": "正式分析只允许当前有效的本地真人确认事实。",
    "non_adjacent_annual_periods": "两期不是可比的相邻年度，仅提供绝对差额。",
    "zero_base": "上期为零，同比百分比无定义，仅提供绝对差额。",
}


class FinancialAnalysisService:
    """Frontend, Agent and report consumers use this same facts-only service."""

    def __init__(
        self,
        *,
        facts: RevenueConfirmationService,
        workspace_id: str,
        isolated_test: IsolatedAnalysisTestConfig | None = None,
    ) -> None:
        if not isinstance(workspace_id, str) or not workspace_id.strip():
            raise ValueError("启用分析必须提供非空服务端 workspace")
        if isolated_test is not None:
            isolated_test.validate(facts.financial_storage_path)
        self._facts = facts
        self._workspace_id = workspace_id
        self._kind: ConfirmationKind = "simulated_test" if isolated_test else "local_operator"

    async def admit_reference(
        self, ref: FinancialFactReference, company_id: str, metric_key: str
    ) -> tuple[FinancialFactSet | None, dict[str, Any] | None, str | None]:
        """One D10 admission path shared by period analysis and company comparison."""
        group = await self._facts.read_financial_facts(
            workspace_id=self._workspace_id,
            receipt_id=ref.fact_set_id,
            confirmation_kind=self._kind,
        )
        p = group.to_payload()
        if group.receipt.review.workspace_id != self._workspace_id:
            raise RevenueConfirmationError("facts_not_found")
        if p["company_id"] != company_id:
            return None, None, ("company_mismatch")
        matches = [f for f in p["facts"] if f["fact_id"] == ref.fact_id]
        if (
            len(matches) != 1
            or ref.fact_set_id != p["fact_set_id"]
            or ref.disclosure_version != p["disclosure_version"]
            or ref.source_revision != p["source_revision"]
        ):
            return None, None, ("selection_mismatch")
        f = matches[0]
        if f["period"] != ref.period or f["source_revision"] != ref.source_revision:
            return None, None, ("selection_mismatch")
        if f["company_id"] != company_id:
            return None, None, ("company_mismatch")
        if f["metric_key"] != metric_key:
            return None, None, ("metric_mismatch")
        if (
            not p["current_valid"]
            or not p["calculable"]
            or (f["confirmation_status"] != "confirmed" or f["status"] != "candidate")
        ):
            return None, None, ("facts_not_calculable")
        if self._kind == "local_operator" and (
            not p["production_calculable"] or p["confirmation_kind"] != "local_operator"
        ):
            return None, None, ("production_calculable_required")
        if self._kind == "simulated_test" and p["confirmation_kind"] != "simulated_test":
            return None, None, ("facts_not_calculable")
        if f["currency"] != "CNY" or f["unit"] != "CNY_YUAN":
            return None, None, ("unit_conflict")
        if f["scope"] != "consolidated":
            return None, None, ("scope_conflict")
        if f["accounting_basis"] != "PRC_GAAP":
            return None, None, ("basis_conflict")
        try:
            start, end = (
                date.fromisoformat(f["period_start"]),
                date.fromisoformat(f["period_end"]),
            )
            if (
                f["period_type"] != "annual"
                or type(f["period"]) is not int
                or start != date(f["period"], 1, 1)
                or end != date(f["period"], 12, 31)
            ):
                return None, None, ("invalid_period")
            value = Decimal(f["value_cny_yuan"])
            if (
                not value.is_finite()
                or parse_amount(f["raw_value"], f["raw_unit"]) != value
                or not f["evidence"]
                or not f["basis_evidence"]
            ):
                raise ValueError("incomplete fact")
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise RevenueConfirmationError("confirmation_integrity_error") from exc
        return (
            group,
            dict(
                **f,
                disclosure_version=p["disclosure_version"],
                confirmation_kind=p["confirmation_kind"],
                production_calculable=p["production_calculable"],
                current_valid=p["current_valid"],
                calculable=p["calculable"],
                integrity=p["integrity"],
                source=p["review"]["source"],
                snapshot_id=p["snapshot_id"],
                accepted_at=p["accepted_at"],
            ),
            None,
        )

    async def analyze(
        self,
        *,
        company_id: str,
        metric_key: str,
        current: FinancialFactReference | None,
        previous: FinancialFactReference | None,
    ) -> dict[str, Any]:
        if metric_key not in METRICS:
            raise RevenueConfirmationError("invalid_financial_selection")
        result: dict[str, Any] = dict(
            schema="financial-analysis-v1",
            company_id=company_id,
            metric_key=metric_key,
            selection={
                "current": asdict(current) if current else None,
                "previous": asdict(previous) if previous else None,
            },
            status="blocked",
            reasons=[],
            current=None,
            previous=None,
            absolute_change=None,
            percentage_change=None,
            percentage_reason=None,
            absolute_change_unit="CNY_YUAN",
            percentage_change_unit="PERCENT",
            formula=dict(
                absolute_change_id="financial_absolute_change_v1",
                percentage_change_id="financial_yoy_signed_base_v1",
                version="1",
                absolute_expression="current - previous",
                percentage_expression="(current - previous) / previous * 100",
                decimal_places=2,
                rounding="ROUND_HALF_UP",
                precision="max(50, operand_span + 32, magnitude_gap + 32)",
                legacy_formula_id="revenue_growth_rate_v1",
            ),
            confirmation_kind=self._kind,
            production_calculable=False,
            automatic_selection=False,
            limitations=[],
            sign_transition=None,
        )

        def blocked(code: str) -> dict[str, Any]:
            result["reasons"] = [{"code": code, "message": REASONS[code]}]
            return result

        if current is None:
            return blocked("missing_current_fact")
        if previous is None:
            return blocked("missing_previous_fact")
        if not current.disclosure_version or not previous.disclosure_version:
            return blocked("version_selection_required")
        groups: list[FinancialFactSet] = []
        selected = []
        for ref in (current, previous):
            group, fact, reason = await self.admit_reference(ref, company_id, metric_key)
            if reason:
                return blocked(reason)
            assert group is not None and fact is not None
            groups.append(group)
            selected.append(fact)
        c, p = selected
        if c["period"] <= p["period"]:
            return blocked("invalid_period_order")
        arithmetic = financial_period_change_v1(
            Decimal(c["value_cny_yuan"]), Decimal(p["value_cny_yuan"])
        )
        if metric_key == "net_profit_parent":
            arithmetic["sign_transition"] = {
                "negative_to_positive": "loss_to_profit",
                "positive_to_negative": "profit_to_loss",
            }.get(str(arithmetic["sign_transition"]), arithmetic["sign_transition"])
        if c["period"] != p["period"] + 1:
            arithmetic.update(
                percentage_change=None, percentage_reason="non_adjacent_annual_periods"
            )
        result.update(
            **arithmetic,
            current=c,
            previous=p,
            company=groups[0].receipt.review.to_payload()["company"],
            currency="CNY",
            unit="CNY_YUAN",
            scope="consolidated",
            accounting_basis="PRC_GAAP",
            status="partial" if arithmetic["percentage_reason"] else "analyzed",
            production_calculable=self._kind == "local_operator",
        )
        if arithmetic["percentage_reason"]:
            code = str(arithmetic["percentage_reason"])
            result["reasons"] = [{"code": code, "message": REASONS[code]}]
        # This is the last await: bytes first, then both complete groups in one DB snapshot.
        await self._facts.recheck_financial_analysis_sources(
            workspace_id=self._workspace_id, groups=tuple(groups), confirmation_kind=self._kind
        )
        return result

    async def compare(
        self,
        *,
        company_a_id: str,
        company_b_id: str,
        period: int,
        selections: dict[str, tuple[FinancialFactReference | None, FinancialFactReference | None]],
    ) -> dict[str, Any]:
        """Limited D13 entry: identical admission, arithmetic and final DB snapshot."""
        if not selections or any(m not in METRICS for m in selections):
            raise RevenueConfirmationError("invalid_financial_selection")
        rows = []
        groups: list[FinancialFactSet] = []
        for metric, (a_ref, b_ref) in selections.items():
            row: dict[str, Any] = dict(
                metric_key=metric,
                selection=dict(
                    a=asdict(a_ref) if a_ref else None, b=asdict(b_ref) if b_ref else None
                ),
                a=None,
                b=None,
                status="blocked",
                reasons=[],
                limitations=[],
                absolute_change=None,
                percentage_change=None,
                percentage_reason=None,
                sign_transition=None,
            )
            reason = "same_company" if company_a_id == company_b_id else None
            if reason is None:
                for side, ref, company in (("a", a_ref, company_a_id), ("b", b_ref, company_b_id)):
                    if ref is None:
                        continue
                    if ref.period != period:
                        reason = "period_mismatch"
                        break
                    if not ref.disclosure_version:
                        reason = "version_selection_required"
                        break
                    group, fact, reason = await self.admit_reference(ref, company, metric)
                    if reason:
                        break
                    assert group is not None and fact is not None
                    groups.append(group)
                    row[side] = fact
            if reason:
                row.update(a=None, b=None, reasons=[dict(code=reason, message=REASONS[reason])])
            elif row["a"] is None or row["b"] is None:
                row.update(
                    status="incomplete",
                    reasons=[
                        dict(
                            code="missing_comparison_fact",
                            message="一方或双方缺少明确选定的有效事实；该指标不补零。",
                        )
                    ],
                )
            else:
                a, b = row["a"], row["b"]
                # Natural annual admission above makes equal year imply equal start/end.
                if (a["period_start"], a["period_end"]) != (b["period_start"], b["period_end"]):
                    row.update(
                        a=None,
                        b=None,
                        reasons=[dict(code="period_mismatch", message=REASONS["period_mismatch"])],
                    )
                else:
                    arithmetic = financial_period_change_v1(
                        Decimal(b["value_cny_yuan"]), Decimal(a["value_cny_yuan"])
                    )
                    # Reuse signed-base math; only the business interpretation differs.
                    arithmetic["limitations"] = (
                        [
                            dict(
                                code="negative_base",
                                message="企业 A 为负基数，使用带符号分母；百分比符号不能表示经营改善或恶化。",
                            )
                        ]
                        if Decimal(a["value_cny_yuan"]) < 0
                        else []
                    )
                    row.update(
                        **arithmetic,
                        status="partial" if arithmetic["percentage_reason"] else "compared",
                    )
                    if arithmetic["percentage_reason"]:
                        row["reasons"] = [
                            dict(
                                code="zero_base",
                                message="企业 A 为零，相对差异无定义；仅提供 B − A 差额。",
                            )
                        ]
            rows.append(row)
        # Recheck every admitted group, across both companies and all metrics, before publication.
        if groups:
            await self._facts.recheck_financial_analysis_sources(
                workspace_id=self._workspace_id, groups=tuple(groups), confirmation_kind=self._kind
            )
        return dict(
            schema="financial-company-comparison-v1",
            company_a_id=company_a_id,
            company_b_id=company_b_id,
            period=period,
            rows=rows,
            status="blocked"
            if all(r["status"] == "blocked" for r in rows)
            else "compared"
            if all(r["status"] == "compared" for r in rows)
            else "partial",
            confirmation_kind=self._kind,
            production_calculable=self._kind == "local_operator"
            and any(r["status"] in ("compared", "partial") for r in rows),
            automatic_selection=False,
            currency="CNY",
            unit="CNY_YUAN",
            scope="consolidated",
            accounting_basis="PRC_GAAP",
            formula=dict(
                absolute_change_id="financial_absolute_change_v1",
                percentage_change_id="financial_company_relative_signed_base_v1",
                version="1",
                absolute_expression="B - A",
                percentage_expression="(B - A) / A * 100",
                decimal_places=2,
                rounding="ROUND_HALF_UP",
                base="company_a",
                precision="max(50, operand_span + 32, magnitude_gap + 32)",
            ),
        )
