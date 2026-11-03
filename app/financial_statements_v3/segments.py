"""Read-only annual revenue composition candidates. No confirmation or DB writes."""

from decimal import Decimal, localcontext
import hashlib
import re
import pymupdf
from .extraction import sha

NUMBER = re.compile(r"-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d+")
SOURCE_KEYS = (
    "workspace_id",
    "company_id",
    "document_id",
    "source_revision",
    "content_sha256",
    "parser_version",
    "report_year",
    "basis",
)


def amount(value):
    value = (value or "").strip()
    return Decimal(value.replace(",", "")) if NUMBER.fullmatch(value) else None


def extract_segments(source, raw):
    """Extract only explicit 2-year 金额 columns under 营业收入构成 + 分产品/分地区.

    source is a server-owned identity, not a browser DTO. Header years define time;
    report_year is retained separately. Unit 元 without explicit人民币 leaves currency unknown.
    """
    identity = {key: source[key] for key in SOURCE_KEYS}
    if hashlib.sha256(raw).hexdigest() != source["content_sha256"]:
        raise ValueError("pdf_hash_changed")
    groups = []
    with pymupdf.open(stream=raw, filetype="pdf") as pdf:
        if len(pdf) > 3000:
            raise ValueError("segment_page_budget_exceeded")
        for page_number, page in enumerate(pdf, 1):
            if "营业收入构成" not in page.get_text().replace(" ", ""):
                continue
            for table in page.find_tables().tables:
                rows = table.extract()
                if len(rows) < 4 or rows[0][0] != "项目" or len(rows[0]) != len(rows[1]):
                    continue
                columns = []
                for col, label in enumerate(rows[0]):
                    match = re.fullmatch(r"(\d{4})\s*年", label or "")
                    if match and rows[1][col] == "金额":
                        columns.append((col, int(match[1])))
                if len(columns) != 2 or columns[0][1] == columns[1][1]:
                    continue
                context = page.get_text(
                    clip=pymupdf.Rect(
                        table.bbox[0], max(0, table.bbox[1] - 26), table.bbox[2], table.bbox[1]
                    )
                )
                units = re.findall(r"单位\s*[：:]\s*(人民币)?\s*(亿元|万元|千元|元)", context)
                if len(set(units)) != 1:
                    continue
                renminbi, unit = units[0]
                factor = {"元": 1, "千元": 1000, "万元": 10000, "亿元": 100000000}[unit]
                totals = [row for row in rows[2:] if row[0] == "营业收入合计"]
                if len(totals) != 1:
                    continue
                section = None
                buckets = {}
                for row_index, row in enumerate(rows[2:], 2):
                    label = (row[0] or "").replace("\n", "").strip()
                    if label.startswith("分"):
                        section = {"分产品": "product", "分地区": "region"}.get(label)
                        continue
                    if not section or not label:
                        continue
                    for col, year in columns:
                        value = amount(row[col])
                        total = amount(totals[0][col])
                        if value is None or total is None or total <= 0:
                            continue
                        key = (section, year)
                        bucket = buckets.setdefault(key, [])
                        bbox = table.rows[row_index].cells[col]
                        if bbox is None:
                            continue
                        with localcontext() as ctx:
                            ctx.prec = max(60, len(str(value)) + len(str(total)) + 20)
                            normalized = value * factor
                            ratio = format(value / total * 100, ".6f") if value >= 0 else None
                        bucket.append(
                            dict(
                                label=label,
                                raw_decimal=format(value, "f"),
                                normalized_decimal=format(normalized, "f"),
                                share_percent_decimal=ratio,
                                evidence=dict(
                                    physical_page=page_number,
                                    table_bbox=list(table.bbox),
                                    amount_bbox=list(bbox),
                                    raw_value=row[col],
                                    raw_label=row[0],
                                    header_year=year,
                                ),
                            )
                        )
                for (dimension, year), items in buckets.items():
                    col = next(c for c, y in columns if y == year)
                    total = amount(totals[0][col])
                    with localcontext() as ctx:
                        ctx.prec = 80
                        subtotal = sum((Decimal(i["raw_decimal"]) for i in items), Decimal(0))
                    group = dict(
                        schema_version="revenue-segment-candidates-v1",
                        source=identity,
                        dimension=dimension,
                        time=dict(
                            kind="duration",
                            period_start=f"{year}-01-01",
                            period_end=f"{year}-12-31",
                            period_type="annual",
                        ),
                        scope="unknown",
                        raw_unit=unit,
                        currency="CNY" if renminbi else "unknown",
                        raw_disclosed_total_decimal=format(total, "f"),
                        component_sum_decimal=format(subtotal, "f"),
                        sum_matches_disclosed_total=subtotal == total,
                        items=items,
                        extraction_status="candidate",
                        financial_review="unconfirmed",
                        source_status="snapshot_bytes_hash_matches",
                        formula_version="component-over-disclosed-revenue-v1;decimal;6dp",
                        limitations=[
                            "Exact annual heading only; no cross-page reconstruction or financial approval.",
                            "Shares use disclosed total, never normalize selected components to 100%.",
                            "Unit 元 alone does not independently establish currency or accounting/consolidation scope.",
                        ],
                    )
                    group["group_id"] = sha(group)
                    groups.append(group)
    return dict(
        schema_version="revenue-segment-extraction-v1",
        source=identity,
        groups=groups,
        human_approvals=0,
        limitations=[] if groups else ["supported_revenue_composition_table_not_found"],
    )
