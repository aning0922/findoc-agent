"""Deterministic financial candidate core over D6 captured PDF evidence.

Adapters provide ruled cells or text geometry; this module never opens a PDF,
retrieves, confirms, calculates, or reads benchmark data.
"""

from dataclasses import asdict, dataclass
from decimal import Decimal, localcontext
import hashlib
import json
import re
from typing import Any

from app.rag.parse.models import PDFCell, PDFLayout

EXTRACTION_METHOD = "financial_table_rule"
EXTRACTION_VERSION = "v2"
METRICS: dict[str, tuple[str, ...]] = {
    "revenue": ("营业收入",),
    "net_profit_parent": ("归属于母公司股东的净利润", "归属于上市公司股东的净利润"),
    "operating_cash_flow": (
        "经营活动产生的现金流量净额",
        "经营活动产生/(使用)的现金流量净额",
        "经营活动产生/（使用）的现金流量净额",
    ),
}
UNIT_FACTORS = {
    "元": Decimal(1),
    "千元": Decimal(1000),
    "万元": Decimal(10000),
    "亿元": Decimal(100000000),
}
AMOUNT = re.compile(r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")
YEAR = re.compile(r"(\d{4})年(?:度)?")
UNIT = re.compile(r"(?:人民币|[（(：:])(千元|万元|亿元|元)(?![\u4e00-\u9fff])")
STATEMENT_TITLE = re.compile(r"(?:\d{4}年度)?合并(?:及公司)?(?:利润表|现金流量表)(?:[（(]续[）)])?")


def compact(text: str | None) -> str:
    return re.sub(r"\s+", "", text or "")


def parse_amount(raw: str, unit: str) -> Decimal | None:
    text = compact(raw).replace("，", ",").replace("−", "-").replace("－", "-")
    negative = text.startswith(("(", "（")) and text.endswith((")", "）"))
    if negative:
        text = text[1:-1]
    if not AMOUNT.fullmatch(text) or unit not in UNIT_FACTORS:
        return None
    amount = Decimal(text.replace(",", ""))
    if negative and text.startswith(("-", "+")):
        return None
    with localcontext() as ctx:
        ctx.prec = max(28, len(amount.as_tuple().digits) + 10)
        return amount * UNIT_FACTORS[unit] * (-1 if negative else 1)


def metric_for(label: str) -> str | None:
    text = compact(label)
    # Remove only recognised row prefixes, units and loss annotations.
    text = re.sub(r"^(?:[一二三四五六七八九十\d]+[、.．]|其中[：:])", "", text)
    text = re.sub(r"[（(](?:千元|万元|亿元|元)[）)]$", "", text)
    text = re.sub(r"[（(]净亏损以[“\"‘']?[-－][”\"’']?号填(?:列[）)]?)?$", "", text)
    return next((key for key, aliases in METRICS.items() if text in aliases), None)


def box(cell: PDFCell) -> tuple[float, float, float, float]:
    if cell.bbox is None:
        raise ValueError("missing geometry")
    return cell.bbox


def center(cell: PDFCell) -> float:
    b = box(cell)
    return (b[0] + b[2]) / 2


@dataclass(frozen=True)
class Observation:
    metric_key: str
    period: int
    role: str
    raw_value: str | None
    raw_unit: str | None
    value: str | None
    currency: str | None
    evidence_id: str
    physical_page: int
    label: str
    raw_cells: list[dict[str, Any]]
    year_header: list[dict[str, Any]]
    scope_header: list[dict[str, Any]]
    unit_excerpt: str
    scope_excerpt: str
    bbox: tuple[float, float, float, float] | None
    failure_reason: str | None = None


def cells_payload(cells: list[PDFCell]) -> list[dict[str, Any]]:
    return [c.model_dump(mode="json") for c in cells]


def _headers(rows: list[list[PDFCell]]) -> list[tuple[int, list[PDFCell]]]:
    return [
        (i, [c for c in row if c.bbox and YEAR.fullmatch(compact(c.text))])
        for i, row in enumerate(rows)
        if len([c for c in row if c.bbox and YEAR.fullmatch(compact(c.text))]) >= 2
    ]


def _row_groups(
    rows: list[list[PDFCell]], first_x: float, strategy: str, label_limit: float
) -> list[tuple[str, list[PDFCell]]]:
    """Merge adjacent label continuations, never across another amount-bearing row.

    Ruled rows contain true merged-cell boxes. Borderless rows can merge an
    incomplete recognised label prefix with the immediately following suffix.
    """
    groups: list[tuple[str, list[PDFCell]]] = []
    i = 0
    aliases = [alias for values in METRICS.values() for alias in values]
    while i < len(rows):
        row = list(rows[i])
        label_cells = [c for c in row if c.bbox and box(c)[2] <= label_limit]
        label = "".join(compact(c.text) for c in label_cells)
        if strategy == "ruled":
            j = i + 1
            while j < len(rows) and j <= i + 3:
                following = [c for c in rows[j] if c.text]
                if not following or any(c.bbox and box(c)[0] >= first_x for c in following):
                    break
                # A new complete label cannot become a continuation.
                suffix = "".join(compact(c.text) for c in following)
                if metric_for(suffix) is not None:
                    break
                row += rows[j]
                label += suffix
                j += 1
            i = j
        else:
            base = re.sub(r"^(?:\d+[、.]|其中[：:])", "", label)
            partial = any(
                (alias.startswith(base) and alias != base)
                or base.startswith(alias + "（净亏损以")
                or base.startswith(alias + "(净亏损以")
                for alias in aliases
            )
            if base and metric_for(label) is None and partial:
                if i + 1 < len(rows):
                    following = rows[i + 1]
                    suffix = "".join(
                        compact(c.text) for c in following if c.bbox and box(c)[2] < label_limit
                    )
                    # Physical proximity and exact resulting identity are both required.
                    y_gap = min(box(c)[1] for c in following) - max(box(c)[3] for c in row)
                    if y_gap <= 8 and metric_for(label + suffix) is not None:
                        label += suffix
                        row += following
                        i += 1
            i += 1
        groups.append((label, row))
    return groups


def observations(record: dict[str, Any], page_text: str) -> list[Observation]:
    if record.get("layout") is None:
        return []
    layout = PDFLayout.model_validate(record["layout"])
    if layout.table_structure and layout.table_structure.status == "unsupported":
        return []
    text = compact(
        page_text
        if record["kind"] == "table"
        else "".join(c.text or "" for row in layout.rows for c in row)
    )
    summary = record["kind"] == "table" and "主要会计数据和财务指标" in text
    titles = [
        "".join(c.text or "" for c in row)
        for row in layout.rows
        if STATEMENT_TITLE.fullmatch(compact("".join(c.text or "" for c in row)))
    ]
    statement = record["kind"] == "paragraph" and bool(titles)
    # Parent-only statements or note tables cannot prove consolidated facts.
    if not summary and not statement:
        return []
    headers = _headers(layout.rows)
    result = []
    for header_index, years in headers:
        if summary:
            scope_cells: list[PDFCell] = []
            scopes = ["summary"] * len(years)
        else:
            scope_cells = [
                c
                for row in layout.rows[header_index + 1 : header_index + 3]
                for c in row
                if compact(c.text) in ("合并", "公司", "母公司") and c.bbox
            ]
            if "合并及公司" in text or scope_cells:
                if len(scope_cells) != len(years):
                    continue
                scopes = []
                for year in years:
                    matches = [c for c in scope_cells if abs(box(c)[2] - box(year)[2]) < 12]
                    scopes.append(
                        "consolidated"
                        if len(matches) == 1 and compact(matches[0].text) == "合并"
                        else "parent"
                    )
            elif "母公司利润表" in text or "母公司现金流量表" in text:
                continue
            else:
                scopes = ["consolidated"] * len(years)
        first_x = min(box(c)[0] for c in years)
        notes = [
            c
            for r in layout.rows[header_index : header_index + 2]
            for c in r
            if compact(c.text) == "附注" and c.bbox
        ]
        label_limit = min(box(c)[0] for c in notes) if notes else first_x
        # Restrict this header to rows before the next explicit header.
        next_header = next((i for i, _ in headers if i > header_index), len(layout.rows))
        body = layout.rows[header_index + 1 : next_header]
        for label, row in _row_groups(body, first_x, layout.strategy, label_limit):
            key = metric_for(label)
            if key is None:
                continue
            label_unit = re.search(r"[（(](千元|万元|亿元|元)[）)]", label)
            unit_rows = [
                "".join(c.text or "" for c in r)
                for r in layout.rows[:header_index]
                if "人民币" in compact("".join(c.text or "" for c in r))
                and UNIT.search(compact("".join(c.text or "" for c in r)))
            ]
            unit_excerpt = "\n".join(([label] if label_unit else []) + unit_rows)
            units = {
                unit
                for excerpt in ([label] if label_unit else []) + unit_rows
                for unit in UNIT.findall(compact(excerpt))
            }
            unit = next(iter(units)) if len(units) == 1 else None
            currency = "CNY" if "人民币" in compact(unit_excerpt) else None
            for year_cell, scope in zip(years, scopes):
                if scope == "parent":
                    continue
                period = int(compact(year_cell.text)[:4])
                same_year = sum(
                    compact(c.text)[:4] == str(period) and s == scope for c, s in zip(years, scopes)
                )
                matches = []
                for cell in row:
                    if not cell.bbox or not cell.text or box(cell)[2] < first_x:
                        continue
                    if layout.strategy == "ruled":
                        belongs = box(cell)[0] <= center(year_cell) <= box(cell)[2]
                    else:
                        # Right-aligned amount and year headers in bounded annual statements.
                        # Partition using header right edges; reject cells crossing partitions.
                        ordered = sorted(years, key=lambda c: box(c)[2])
                        idx = ordered.index(year_cell)
                        right = box(year_cell)[2]
                        left_bound = (box(ordered[idx - 1])[2] + right) / 2 if idx else first_x - 30
                        right_bound = (
                            (box(ordered[idx + 1])[2] + right) / 2
                            if idx + 1 < len(ordered)
                            else right + 30
                        )
                        belongs = left_bound < box(cell)[2] < right_bound
                    if belongs:
                        matches.append(cell)
                # Merged ruled cells can repeat in the physical rows; dedupe exact cells only.
                matches = list({(c.text, c.bbox): c for c in matches}.values())
                raw = matches[0].text if len(matches) == 1 else None
                value = parse_amount(raw or "", unit or "")
                failure = (
                    "year_column_conflict"
                    if same_year != 1
                    else "missing_or_ambiguous_cell"
                    if len(matches) != 1
                    else "unit_missing_or_conflict"
                    if unit is None
                    else "unsupported_amount"
                    if value is None
                    else None
                )
                result.append(
                    Observation(
                        key,
                        period,
                        "summary" if summary else "statement",
                        raw,
                        unit,
                        format(value, "f") if value is not None else None,
                        currency,
                        record["evidence_id"],
                        record["physical_page"],
                        label,
                        cells_payload(row),
                        cells_payload(years),
                        cells_payload(scope_cells),
                        unit_excerpt,
                        "主要会计数据和财务指标" if summary else titles[0],
                        matches[0].bbox if len(matches) == 1 else None,
                        failure,
                    )
                )
    return result


def extract_metrics(
    *,
    source: dict[str, Any],
    records: list[dict[str, Any]],
    metric_keys: tuple[str, ...],
    periods: tuple[int, ...],
) -> dict[str, Any]:
    """Every requested metric/period yields one explicit outcome, never a guessed amount."""
    if (
        not metric_keys
        or len(set(metric_keys)) != len(metric_keys)
        or any(k not in METRICS for k in metric_keys)
    ):
        raise ValueError("invalid metric selection")
    if (
        not periods
        or len(set(periods)) != len(periods)
        or any(type(y) is not int or not 1 <= y <= 9999 for y in periods)
    ):
        raise ValueError("invalid period selection")
    if any(
        r["source_revision"] != source["source_revision"]
        or r["evidence_id"] not in source["evidence_ids"]
        for r in records
    ):
        raise ValueError("evidence source mismatch")
    pages = {r["physical_page"]: r["text"] for r in records if r["kind"] == "paragraph"}
    found = [
        obs
        for record in records
        for obs in observations(record, pages.get(record["physical_page"], ""))
    ]
    basis = [
        r
        for r in records
        if r["kind"] == "paragraph"
        and "遵循企业会计准则" in compact(r["text"])
        and "财务报表符合企业会计准则的要求" in compact(r["text"])
    ]
    items = []
    annual = (
        source["report_type"] == "annual"
        and source["period_start"] == f"{source['report_year']:04d}-01-01"
        and source["period_end"] == f"{source['report_year']:04d}-12-31"
    )
    for key in metric_keys:
        for period in periods:
            observations_for_key = [o for o in found if o.metric_key == key and o.period == period]
            summaries = [o for o in observations_for_key if o.role == "summary"]
            statements = [o for o in observations_for_key if o.role == "statement"]
            values = {Decimal(o.value) for o in observations_for_key if o.value is not None}
            failures = {o.failure_reason for o in observations_for_key if o.failure_reason}
            currencies = {o.currency for o in statements}
            status, reason = "candidate", None
            if len(values) > 1:
                status, reason = "conflict", "disclosure_value_conflict"
            elif failures:
                status, reason = "unsupported", ",".join(sorted(failures))
            elif not observations_for_key:
                status, reason = "unsupported", "metric_or_period_missing"
            elif not statements:
                status, reason = "needs_manual_review", "consolidated_statement_missing"
            elif currencies != {"CNY"}:
                status, reason = "needs_manual_review", "currency_missing_or_conflict"
            elif not annual:
                status, reason = "unsupported", "annual_period_not_verified"
            elif source["basis"] != "PRC_GAAP" or not basis:
                status, reason = "needs_manual_review", "accounting_basis_not_verified"
            elif any(
                source["assessment"][k] != "matches_cover"
                for k in ("company", "report_year", "report_type")
            ):
                status, reason = "needs_manual_review", "report_identity_needs_review"
            primary: Observation | None = (
                (summaries or statements)[0] if summaries or statements else None
            )
            evidence = [
                {**asdict(o), "bbox": list(o.bbox) if o.bbox else None}
                for o in observations_for_key
            ]
            basis_refs = [
                dict(
                    evidence_id=r["evidence_id"],
                    physical_page=r["physical_page"],
                    excerpt=r["text"],
                )
                for r in basis
            ]
            identity = [
                source["company_id"],
                source["document_id"],
                source["source_revision"],
                key,
                period,
                EXTRACTION_VERSION,
                evidence,
                basis_refs,
            ]
            cid = hashlib.sha256(
                json.dumps(identity, ensure_ascii=False, sort_keys=True).encode()
            ).hexdigest()
            items.append(
                dict(
                    candidate_id=cid,
                    company_id=source["company_id"],
                    document_id=source["document_id"],
                    source_revision=source["source_revision"],
                    content_sha256=source["content_sha256"],
                    attempt=source["attempt"],
                    parser_version=source["parser_version"],
                    extraction_method=EXTRACTION_METHOD,
                    extraction_version=EXTRACTION_VERSION,
                    metric_key=key,
                    period=period,
                    period_start=f"{period:04d}-01-01",
                    period_end=f"{period:04d}-12-31",
                    period_type="annual",
                    raw_value=primary.raw_value if primary else None,
                    raw_unit=primary.raw_unit if primary else None,
                    multiplier=str(UNIT_FACTORS[primary.raw_unit])
                    if primary and primary.raw_unit in UNIT_FACTORS
                    else None,
                    value_cny_yuan=primary.value if primary and status == "candidate" else None,
                    currency="CNY" if currencies == {"CNY"} else None,
                    scope="consolidated" if statements else "unverified_summary",
                    accounting_basis="PRC_GAAP"
                    if basis and source["basis"] == "PRC_GAAP"
                    else "unverified",
                    physical_page=primary.physical_page if primary else None,
                    evidence_id=primary.evidence_id if primary else None,
                    evidence=evidence,
                    basis_evidence=basis_refs,
                    status=status,
                    failure_reason=reason,
                    confirmation_status="pending",
                    requires_human_confirmation=True,
                )
            )
    return dict(schema="financial-candidates-v1", source=source, candidates=items)
