"""Dynamic financial selections and adversarial table geometry (no gold amounts)."""

from copy import deepcopy
from decimal import Decimal

import pytest

from app.agent.metric_extraction import METRICS, extract_metrics, metric_for, parse_amount
from app.rag.parse.models import PDFCell, PDFLayout


def cell(text, x, y, width=80):
    return PDFCell(text=text, bbox=(x, y, x + width, y + 12))


def fixture_records(unit="元", combined=False, strategy="ruled", year=2031):
    header = [cell(f"{year}年度", 200, 60), cell(f"{year - 1}年度", 300, 60)]
    scope = [cell("合并", 260, 75, 20), cell("合并", 360, 75, 20)]
    if combined:
        header += [cell(f"{year}年度", 400, 60), cell(f"{year - 1}年度", 500, 60)]
        scope += [cell("公司", 460, 75, 20), cell("公司", 560, 75, 20)]
    labels = {
        "revenue": "营业收入",
        "net_profit_parent": "归属于母公司股东的净利润",
        "operating_cash_flow": "经营活动产生的现金流量净额",
    }
    values = {
        "revenue": "1,234.50",
        "net_profit_parent": "(12.75)",
        "operating_cash_flow": "-41.25",
    }
    records = []
    for key, label in labels.items():
        title = "合并及公司" if combined else "合并"
        title += "现金流量表" if key == "operating_cash_flow" else "利润表"
        rows = [
            [cell(title, 0, 10, 180)],
            [cell(f"单位：人民币{unit}", 0, 30, 180)],
            header,
            scope,
            [cell(label, 0, 100, 180), cell(values[key], 200, 100), cell("25.00", 300, 100)],
        ]
        if combined:
            rows[-1] += [cell("999999", 400, 100), cell("888888", 500, 100)]
        layout = PDFLayout(strategy=strategy, rows=rows)
        records.append(
            dict(
                evidence_id=key,
                source_revision="rev",
                kind="paragraph",
                physical_page=len(records) + 1,
                text=title,
                layout=layout.model_dump(mode="json"),
            )
        )
    records.append(
        dict(
            evidence_id="basis",
            source_revision="rev",
            kind="paragraph",
            physical_page=4,
            text="遵循企业会计准则的声明：本公司财务报表符合企业会计准则的要求",
            layout=None,
        )
    )
    source = dict(
        company_id="third-company",
        document_id="third-annual",
        source_revision="rev",
        content_sha256="a" * 64,
        attempt=3,
        parser_version="fast-pdf-v2",
        evidence_ids=[r["evidence_id"] for r in records],
        report_year=year,
        report_type="annual",
        period_start=f"{year}-01-01",
        period_end=f"{year}-12-31",
        basis="PRC_GAAP",
        assessment={k: "matches_cover" for k in ("company", "report_year", "report_type")},
    )
    return source, records


def extract(source, records, keys=tuple(METRICS), periods=(2031,)):
    return extract_metrics(source=source, records=records, metric_keys=keys, periods=periods)[
        "candidates"
    ]


@pytest.mark.parametrize(
    "unit,factor", [("元", 1), ("千元", 1000), ("万元", 10000), ("亿元", 100000000)]
)
@pytest.mark.parametrize("combined", [False, True])
@pytest.mark.parametrize("strategy", ["ruled", "text_geometry"])
def test_dynamic_year_third_company_unit_negative_and_scope(unit, factor, combined, strategy):
    source, records = fixture_records(unit, combined, strategy)
    result = extract(source, records, periods=(2030, 2031))
    assert len(result) == 6 and all(r["status"] == "candidate" for r in result)
    assert all(r["company_id"] == "third-company" and r["attempt"] == 3 for r in result)
    expected = {
        "revenue": "1234.50",
        "net_profit_parent": "-12.75",
        "operating_cash_flow": "-41.25",
    }
    for r in result:
        value = expected[r["metric_key"]] if r["period"] == 2031 else "25.00"
        assert Decimal(r["value_cny_yuan"]) == Decimal(value) * factor
        assert r["scope"] == "consolidated" and r["confirmation_status"] == "pending"
        assert r["evidence"][0]["year_header"] and r["evidence"][0]["unit_excerpt"]


@pytest.mark.parametrize(
    "label",
    [
        "营业总收入",
        "集团净利润",
        "净利润",
        "母公司净利润",
        "归属于上市公司股东的扣除非经常性损益的净利润",
        "扣非归母净利润",
        "经营活动现金流入小计",
        "经营活动现金流出小计",
        "投资活动产生的现金流量净额",
        "筹资活动产生的现金流量净额",
        "营业收入增长率",
    ],
)
def test_strict_metric_identity(label):
    assert metric_for(label) is None


@pytest.mark.parametrize("bad", ["--1", "12,34", "1e6", "NaN", "∞", "12%", "-", "", "(－12)"])
def test_bad_amount_never_becomes_zero_or_neighbor(bad):
    assert parse_amount(bad, "元") is None


def test_decimal_no_precision_loss_and_fullwidth_negative():
    assert parse_amount("（1，234.567890123456789012345678901）", "亿元") == Decimal(
        "-123456789012.3456789012345678901"
    )


@pytest.mark.parametrize(
    "failure", ["unit", "year", "missing", "duplicate", "parent", "currency", "basis", "fiscal"]
)
def test_missing_ambiguous_or_wrong_scope_fails_closed(failure):
    source, records = fixture_records(combined=True)
    row = records[0]["layout"]["rows"][-1]
    if failure == "unit":
        records[0]["layout"]["rows"][1][0]["text"] = "单位：人民币美元"
    if failure == "year":
        records[0]["layout"]["rows"][2][1]["text"] = "2031年度"
    if failure == "missing":
        row[1]["text"] = "-"
    if failure == "duplicate":
        row.append(deepcopy(row[1]))
        row[-1]["text"] = "999"
    if failure == "parent":
        records[0]["layout"]["rows"][3][0]["text"] = "公司"
    if failure == "currency":
        records[0]["layout"]["rows"][1][0]["text"] = "单位：美元元"
    if failure == "basis":
        source["basis"] = "IFRS"
    if failure == "fiscal":
        source["period_start"] = "2031-04-01"
    result = extract(source, records, keys=("revenue",))[0]
    assert result["status"] != "candidate" and result["value_cny_yuan"] is None
    assert result["failure_reason"]


def test_repeat_disclosures_merge_evidence_and_conflicting_disclosures_block():
    source, records = fixture_records()
    duplicate = deepcopy(records[0])
    duplicate["evidence_id"] = "duplicate"
    source["evidence_ids"].append("duplicate")
    records.append(duplicate)
    assert len(extract(source, records, keys=("revenue",))[0]["evidence"]) == 2
    duplicate["layout"]["rows"][-1][1]["text"] = "777"
    result = extract(source, records, keys=("revenue",))[0]
    assert result["status"] == "conflict" and result["value_cny_yuan"] is None


def test_cross_source_evidence_refused_and_candidate_id_binds_report_version():
    source, records = fixture_records()
    a = extract(source, records)[0]["candidate_id"]
    other = deepcopy(source)
    other["document_id"] = "different-report"
    assert extract(other, records)[0]["candidate_id"] != a
    records[0]["source_revision"] = "foreign"
    with pytest.raises(ValueError, match="source mismatch"):
        extract(source, records)


@pytest.mark.parametrize(
    "keys,periods",
    [
        ((), (2031,)),
        (("bad",), (2031,)),
        (("revenue",), (True,)),
        (("revenue",), (0,)),
        (("revenue",), (2031, 2031)),
        (("revenue", "revenue"), (2031,)),
    ],
)
def test_selection_validation(keys, periods):
    source, records = fixture_records()
    with pytest.raises(ValueError):
        extract(source, records, keys, periods)


def test_summary_only_equal_number_elsewhere_is_manual_review():
    source, records = fixture_records()
    revenue = records[0]
    revenue["kind"] = "table"
    revenue["layout"]["rows"][-1][0]["text"] = "营业收入（元）"
    records[1]["text"] = "主要会计数据和财务指标"
    records[1]["physical_page"] = 1
    records[1]["layout"] = None
    result = extract(source, records, keys=("revenue",))[0]
    assert result["status"] == "needs_manual_review"
    assert result["failure_reason"] == "consolidated_statement_missing"


def test_safe_ruled_label_continuation_does_not_merge_deducted_profit():
    source, records = fixture_records()
    paragraph = dict(records[1], evidence_id="page", text="主要会计数据和财务指标", layout=None)
    table = records[1]
    table["kind"] = "table"
    table["layout"]["rows"][-1][0]["text"] = "归属于母公司股东的"
    table["layout"]["rows"].append([cell("净利润（元）", 0, 112, 180)])
    records.append(paragraph)
    source["evidence_ids"].append("page")
    # A distinct amount row with a deducted-profit continuation stays excluded.
    table["layout"]["rows"] += [
        [cell("归属于上市公司股东的", 0, 130, 180), cell("999", 200, 130), cell("888", 300, 130)],
        [cell("扣除非经常性损益的", 0, 142, 180)],
        [cell("净利润（元）", 0, 154, 180)],
    ]
    result = extract(source, records, keys=("net_profit_parent",))[0]
    assert result["status"] == "needs_manual_review"
    assert len(result["evidence"]) == 1
    assert result["evidence"][0]["value"] == "-12.75"


def test_conflicting_statement_units_and_parent_headers_block():
    source, records = fixture_records()
    records[0]["layout"]["rows"][3][0]["text"] = "公司"
    assert extract(source, records, keys=("revenue",))[0]["status"] != "candidate"
    source, records = fixture_records()
    records[0]["layout"]["rows"].insert(2, [cell("单位：人民币千元", 0, 45, 180)])
    result = extract(source, records, keys=("revenue",))[0]
    assert (
        result["status"] == "unsupported" and result["failure_reason"] == "unit_missing_or_conflict"
    )


def test_narrative_mention_of_consolidated_statement_cannot_authorize_note_table():
    source, records = fixture_records()
    records[0]["layout"]["rows"][0][0]["text"] = "关于合并利润表的补充说明"
    result = extract(source, records, keys=("revenue",))[0]
    assert result["status"] == "unsupported" and result["value_cny_yuan"] is None


def test_ruled_boundary_and_equivalent_amount_formats_keep_all_disclosures():
    source, records = fixture_records()
    records[0]["layout"]["rows"][-1][0]["bbox"][2] = 200
    first = records[0]
    first["kind"] = "table"
    first["layout"]["rows"][-1][0]["text"] = "营业收入（元）"
    page = dict(
        first,
        evidence_id="summary-page",
        kind="paragraph",
        layout=None,
        text="主要会计数据和财务指标",
    )
    statement = deepcopy(first)
    statement["evidence_id"] = "statement"
    statement["kind"] = "paragraph"
    statement["physical_page"] = 5
    statement["layout"]["rows"][-1][1]["text"] = "1234.5"
    records += [page, statement]
    source["evidence_ids"] += ["summary-page", "statement"]
    result = extract(source, records, keys=("revenue",))[0]
    assert result["status"] == "candidate" and len(result["evidence"]) == 2
    assert result["value_cny_yuan"] == "1234.50"
