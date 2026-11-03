"""Read-only deterministic signals over server-admitted instant balances; no candidates."""
from datetime import date
from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from app.finance_v2.contracts import FinanceError

KEYS = ("total_assets", "total_liabilities")
VERSION = "instant-balance-signals-v1;decimal;half-even;6dp-rates"


def build_signals(source, metrics):
    """Internal input only: service re-admits receipts and sources in its read transaction."""
    admitted = []
    for metric in metrics:
        if any(metric[k] != source[k] for k in ("company_id", "document_id", "source_revision", "content_sha256")):
            raise FinanceError("signal_source_mismatch")
        if (metric["metric_key"] in KEYS and metric["status"] == "confirmed"
                and metric.get("source_status") == "current_valid"
                and (metric.get("confirmation_ref") or {}).get("confirmation_kind") == "local_operator"
                and metric.get("value_decimal") is not None and metric.get("as_of_date")):
            instant = date.fromisoformat(metric["as_of_date"])
            if instant.isoformat() != metric["as_of_date"] or metric.get("period") != instant.year:
                raise FinanceError("signal_date_invalid")
            admitted.append(metric)
    by_key = {key: {} for key in KEYS}
    for metric in admitted:
        values = by_key[metric["metric_key"]]
        if metric["as_of_date"] in values:
            raise FinanceError("ambiguous_signal_metric_date")
        values[metric["as_of_date"]] = metric
    if any(len(values) > 2 for values in by_key.values()):
        raise FinanceError("ambiguous_signal_date_pair")

    def ref(metric):
        return {key: metric[key] for key in ("metric_id", "as_of_date", "value_decimal", "unit",
                                            "confirmation_ref", "evidence_refs")}

    def fixed(value):
        rounded = value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
        return format(abs(rounded) if rounded == 0 else rounded, "f")

    output, balances = [], {}
    # Precision accommodates exact subtraction of all accepted fixed-point input digits.
    precision = max(80, sum(len(m["value_decimal"]) for m in admitted) + 30)
    with localcontext() as context:
        context.prec = precision
        for key, values in by_key.items():
            if len(values) != 2:
                output.append({"metric_key": key, "status": "missing", "reason": "two_confirmed_dates_required"})
                continue
            before, after = [values[d] for d in sorted(values)]
            old, new = Decimal(before["value_decimal"]), Decimal(after["value_decimal"])
            delta = new - old
            valid_rate = old > 0 and new >= 0
            output.append({"metric_key": key, "status": "available", "from_date": before["as_of_date"],
                           "to_date": after["as_of_date"], "delta_decimal": format(delta, "f"), "unit": "CNY_YUAN",
                           "change_percent_decimal": fixed(delta / old * 100) if valid_rate else None,
                           "percent_unavailable_reason": None if valid_rate else "zero_baseline" if old == 0 else "negative_balance",
                           "input_refs": [ref(before), ref(after)]})
            balances[key] = (before, after)
        ratio = {"metric_key": "debt_asset_ratio", "status": "missing", "reason": "matched_confirmed_dates_required"}
        if all(key in balances for key in KEYS):
            assets, liabilities = balances["total_assets"], balances["total_liabilities"]
            if [m["as_of_date"] for m in assets] == [m["as_of_date"] for m in liabilities]:
                asset_values = [Decimal(m["value_decimal"]) for m in assets]
                liability_values = [Decimal(m["value_decimal"]) for m in liabilities]
                if min(asset_values) > 0 and min(liability_values) >= 0:
                    rates = [Decimal(fixed(liability_values[i] / asset_values[i] * 100)) for i in (0, 1)]
                    ratio = {"metric_key": "debt_asset_ratio", "status": "available", "from_date": assets[0]["as_of_date"],
                             "to_date": assets[1]["as_of_date"], "from_percent_decimal": fixed(rates[0]),
                             "to_percent_decimal": fixed(rates[1]), "delta_percentage_points_decimal": fixed(rates[1] - rates[0]),
                             "unit": "PERCENTAGE_POINTS", "input_refs": [ref(m) for m in (*assets, *liabilities)]}
                else:
                    ratio["reason"] = "assets_must_be_positive_liabilities_nonnegative"
        output.append(ratio)
    ready = {s["metric_key"]: s for s in output if s["status"] == "available"}
    notices = []
    if ratio["status"] == "available":
        signs = [Decimal(ready[key]["delta_decimal"]) for key in KEYS]
        notices.append({"kind": "balance_combination", "text": "按所列实际时点比较：资产" + ("增加" if signs[0] > 0 else "减少" if signs[0] < 0 else "不变")
                        + "，负债" + ("增加" if signs[1] > 0 else "减少" if signs[1] < 0 else "不变")
                        + "；资产负债率变化见百分点字段。此为算术描述，原因需核对原文。"})
    return {"schema_version": "extended-signals-v1", "source": source, "source_status": "current_valid", "calculation_version": VERSION,
            "signals": output, "notices": notices,
            "limitations": ["仅当前来源、current_valid、confirmed、local_operator原始余额参与计算；candidate及simulated_test不参与。",
                            "按实际as_of_date较早到较晚比较；同年期初不是上年年末，不自动称同比。",
                            "差额=后值-前值；百分比=差额/前值*100，仅前值>0且后值>=0计算；零分母或负值保留差额并省略百分比。",
                            "资产负债率要求资产>0且负债>=0；各时点比率四舍六入五成双保留6位，再相减得百分点变化。",
                            "多于两个确认日期或同指标同日期重复拒绝自动选择；组合提示不构成风险评分或投资建议。"]}
