"""Decimal-only ratios from the caller's explicitly selected current points."""

from decimal import Decimal, localcontext


def debt_asset_ratios(points):
    groups = {}
    for point in points:
        if point["time"]["kind"] == "instant" and point["metric_key"] in (
            "total_assets",
            "total_liabilities",
        ):
            groups.setdefault((point["company_id"], point["time"]["as_of_date"]), {})[
                point["metric_key"]
            ] = point
    result = []
    for (company, date), cells in sorted(groups.items()):
        selected = [cells[k] for k in ("total_assets", "total_liabilities") if k in cells]
        reason = None
        percent = None
        if len(selected) != 2:
            reason = "missing_selected_input"
        else:
            assets, liabilities = selected
            axes = ("basis", "scope", "currency", "normalized_unit")
            if any(
                assets.get(k) in (None, "", "unknown") or assets.get(k) != liabilities.get(k)
                for k in axes
            ):
                reason = "incomparable_or_unknown_basis"
            elif Decimal(assets["normalized_decimal"]) <= 0:
                reason = "nonpositive_assets"
            else:
                with localcontext() as ctx:
                    ctx.prec = max(60, sum(len(p["normalized_decimal"]) for p in selected) + 20)
                    percent = format(
                        Decimal(liabilities["normalized_decimal"])
                        / Decimal(assets["normalized_decimal"])
                        * 100,
                        ".6f",
                    )
        result.append(
            {
                "metric_key": "debt_asset_ratio",
                "company_id": company,
                "time": {"kind": "instant", "as_of_date": date},
                "percent_decimal": percent,
                "input_refs": [p["cell_id"] for p in selected],
                "reason": reason,
                "financial_review": "local_operator_confirmed"
                if selected and all(p.get("receipt_ref") for p in selected)
                else "unconfirmed",
                "formula_version": "debt-assets-v1;decimal;6dp",
                "authority_basis": "computed_from_selected_cells",
            }
        )
    return result
