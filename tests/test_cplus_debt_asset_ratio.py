from decimal import Decimal
from app.financial_statements_v3.ratios import debt_asset_ratios


def points():
    return [
        dict(
            company_id="c",
            time={"kind": "instant", "as_of_date": "2025-12-31"},
            metric_key=metric,
            cell_id=metric,
            normalized_decimal=value,
            basis="PRC_GAAP",
            scope="consolidated",
            currency="CNY",
            normalized_unit="CNY_YUAN",
            receipt_ref=None,
        )
        for metric, value in [
            ("total_assets", "391371999819.49"),
            ("total_liabilities", "241580719144.79"),
        ]
    ]


def test_ratio_decimal_exact_selected_refs_and_candidate_status():
    selected = points()
    ratio = debt_asset_ratios(selected)[0]
    assert ratio["percent_decimal"] == format(
        Decimal("241580719144.79") / Decimal("391371999819.49") * 100, ".6f"
    )
    assert ratio["financial_review"] == "unconfirmed"
    assert ratio["input_refs"] == ["total_assets", "total_liabilities"]
    # Caller data remains unchanged; ratios are not signed financial cells.
    assert all(p["receipt_ref"] is None for p in selected)
    selected[0]["receipt_ref"] = "receipt-a"
    selected[1]["receipt_ref"] = "receipt-l"
    assert debt_asset_ratios(selected)[0]["financial_review"] == "local_operator_confirmed"


def test_missing_cross_time_unknown_basis_and_invalid_denominator_not_guessed():
    selected = points()
    assert debt_asset_ratios(selected[:1])[0]["reason"] == "missing_selected_input"
    selected[1]["time"] = {"kind": "instant", "as_of_date": "2024-12-31"}
    assert all(p["percent_decimal"] is None for p in debt_asset_ratios(selected))
    selected = points()
    selected[0]["basis"] = "unknown"
    assert debt_asset_ratios(selected)[0]["reason"] == "incomparable_or_unknown_basis"
    selected = points()
    selected[0]["normalized_decimal"] = "0"
    assert debt_asset_ratios(selected)[0]["reason"] == "nonpositive_assets"
