"""Bounded consolidated balance-sheet extraction from immutable PDFLayout cells.

No PDF access, retrieval, model, invented date/column, or first-number matching.
Only exact total labels + explicit dated columns + CNY units + consolidated
statement title and accounting-basis evidence are eligible as candidates.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
import hashlib
import json
import re
from uuid import NAMESPACE_URL, uuid5

from app.finance_v2.contracts import FinanceError
from app.finance_v2.models import ExtendedMetricV2
from app.rag.parse.models import PDFLayout

DEFINITION = "consolidated-balance-sheet-instant-v1"
LABELS = {"total_assets": ("资产总计",), "total_liabilities": ("负债合计", "负债总计")}
FACTORS = {"元": Decimal(1), "千元": Decimal(1000), "万元": Decimal(10000), "亿元": Decimal(100000000)}
TITLE = re.compile(r"(?:\d{4}年度?)?合并资产负债表(?:[（(]续[）)])?")
DATE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
AMOUNT = re.compile(r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")
UNIT = re.compile(r"(?:单位[：:])?人民币(亿元|万元|千元|元)(?![\u4e00-\u9fff])")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def compact(text):
    return re.sub(r"\s+", "", text or "")


def amount(raw, unit):
    text = compact(raw).replace("，", ",").replace("−", "-").replace("－", "-")
    negative = text.startswith(("(", "（")) and text.endswith((")", "）"))
    if negative:
        text = text[1:-1]
    if not AMOUNT.fullmatch(text) or unit not in FACTORS or (negative and text.startswith(("+", "-"))):
        return None
    value = Decimal(text.replace(",", ""))
    with localcontext() as ctx:
        ctx.prec = max(40, len(value.as_tuple().digits) + 12)
        return format(value * FACTORS[unit] * (-1 if negative else 1), "f")


def cells_payload(cells):
    return [c.model_dump(mode="json") for c in cells]


def dated_columns(row):
    """Reassemble split date glyphs only, preserving every actual bounding box."""
    columns, i = [], 0
    while i < len(row):
        matched = False
        for end in range(i + 1, min(len(row), i + 6) + 1):
            text = compact("".join(c.text or "" for c in row[i:end]))
            match = DATE.fullmatch(text)
            if not match or any(c.bbox is None for c in row[i:end]):
                continue
            try:
                instant = date(*map(int, match.groups())).isoformat()
            except ValueError:
                continue
            cells = row[i:end]
            bbox = [min(c.bbox[0] for c in cells), min(c.bbox[1] for c in cells),
                    max(c.bbox[2] for c in cells), max(c.bbox[3] for c in cells)]
            columns.append({"as_of_date": instant, "bbox": bbox, "cells": cells_payload(cells)})
            i, matched = end, True
            break
        if not matched:
            i += 1
    return columns


def observed(record):
    if not record.get("layout"):
        return []
    layout = PDFLayout.model_validate(record["layout"])
    if layout.table_structure and layout.table_structure.status == "unsupported":
        return []
    rows = layout.rows
    titles = [(i, row) for i, row in enumerate(rows)
              if TITLE.fullmatch(compact("".join(c.text or "" for c in row)))]
    # Reject mixed parent/consolidated views and note tables, including nearby numeric labels.
    if len(titles) != 1 or any("母公司资产负债表" in compact(c.text) for row in rows for c in row):
        return []
    title_index, title = titles[0]
    headers = [(i, row, dated_columns(row)) for i, row in enumerate(rows)
               if i > title_index and any(compact(c.text) == "项目" for c in row)]
    headers = [(i, row, cols) for i, row, cols in headers if len(cols) >= 2]
    result = []
    for index, header, columns in headers:
        units = [row for row in rows[title_index:index]
                 if UNIT.search(compact("".join(c.text or "" for c in row)))]
        unit_set = {match for row in units for match in UNIT.findall(compact("".join(c.text or "" for c in row)))}
        unit = next(iter(unit_set)) if len(unit_set) == 1 else None
        columns.sort(key=lambda col: col["bbox"][0])
        centers = [(col["bbox"][0] + col["bbox"][2]) / 2 for col in columns]
        next_header = next((j for j, _, _ in headers if j > index), len(rows))
        for row in rows[index + 1:next_header]:
            label_cells = [c for c in row if c.bbox and c.bbox[2] < columns[0]["bbox"][0] - 1]
            label = compact("".join(c.text or "" for c in label_cells))
            key = next((key for key, labels in LABELS.items() if label in labels), None)
            if key is None:
                continue
            for k, col in enumerate(columns):
                left = (centers[k - 1] + centers[k]) / 2 if k else col["bbox"][0] - 15
                right = (centers[k] + centers[k + 1]) / 2 if k + 1 < len(columns) else float("inf")
                # Require the complete cell to fit its geometric column, never split a merged number.
                matches = [c for c in row if c.bbox and c.text and left < c.bbox[0] and c.bbox[2] < right]
                matches = list({(c.text, c.bbox): c for c in matches}.values())
                raw = matches[0].text if len(matches) == 1 else None
                value = amount(raw, unit) if raw is not None else None
                reason = ("duplicate_date_columns" if len({c["as_of_date"] for c in columns}) != len(columns)
                          else "unit_missing_or_ambiguous" if unit is None
                          else "amount_cell_missing_or_ambiguous" if len(matches) != 1
                          else "merged_amount_cell" if any(c.row_span not in (None, 1) or c.column_span not in (None, 1) for c in matches)
                          else "unsupported_amount" if value is None
                          else "negative_balance" if Decimal(value) < 0 else None)
                result.append({"metric_key": key, "as_of_date": col["as_of_date"], "value_decimal": value,
                               "reason": reason, "ref": {
                                   "evidence_id": record["evidence_id"], "chunk_id": record["evidence_id"],
                                   "physical_page": record["physical_page"], "text": " | ".join(c.text or "" for c in row),
                                   "raw_label": label, "raw_value": raw, "raw_unit": unit,
                                   "raw_cells": cells_payload(row), "period_header_cells": col["cells"],
                                   "scope_cells": cells_payload(title),
                                   "unit_cells": [cell for unit_row in units for cell in cells_payload(unit_row)],
                                   "scope": "consolidated", "layout_sha256": digest(record["layout"]),
                               }})
    return result


def extract(source, records):
    if any(r["source_revision"] != source["source_revision"] or r["evidence_id"] not in source["evidence_ids"]
           for r in records):
        raise FinanceError("evidence_source_mismatch")
    basis = [r for r in records if r["kind"] == "paragraph" and
             "遵循企业会计准则" in compact(r["text"]) and "财务报表符合企业会计准则" in compact(r["text"])]
    basis_refs = [{"evidence_id": r["evidence_id"], "physical_page": r["physical_page"], "text": r["text"]} for r in basis]
    groups = defaultdict(list)
    for record in records:
        for observation in observed(record):
            groups[observation["metric_key"], observation["as_of_date"]].append(observation)
    for key in LABELS:
        if not any(k == key for k, _ in groups):
            groups[key, None] = []
    metrics = []
    identity_verified = all(source.get("assessment", {}).get(key) == "matches_cover"
                            for key in ("company", "report_year", "report_type"))
    for (key, instant), observations in sorted(groups.items(), key=lambda item: (item[0][0], item[0][1] or "")):
        values = {o["value_decimal"] for o in observations if o["value_decimal"] is not None}
        reasons = {o["reason"] for o in observations if o["reason"]}
        if not observations:
            reasons.add("no_provable_dated_consolidated_total")
        if len({Decimal(v) for v in values}) != 1:
            reasons.add("amount_missing_or_conflicting")
        if instant and (not source.get("period_end") or instant > source["period_end"]):
            reasons.add("instant_after_report_period")
        if not identity_verified:
            reasons.add("report_identity_unverified")
        if source.get("basis") != "PRC_GAAP" or not basis:
            reasons.add("accounting_basis_unproven")
        if not source.get("parser_version", "").startswith("fast-pdf-"):
            reasons.add("unsupported_parser_requires_v2_identity_review")
        if source.get("report_type") != "annual":
            reasons.add("unsupported_report_type")
        refs = [{"document_id": source["document_id"], "company_id": source["company_id"],
                 "source_revision": source["source_revision"], "content_sha256": source["content_sha256"],
                 "parser_version": source["parser_version"], "transcription_review_status": "fast_extraction_unreviewed",
                 **o["ref"]} for o in observations]
        item = {"schema_version": "extended-metric-v2", "metric_id": "", **{k: source[k] for k in (
            "company_id", "document_id", "source_revision", "content_sha256", "report_year")},
            "period": int(instant[:4]) if instant else None, "period_kind": "instant", "as_of_date": instant,
            "period_start": None, "period_end": None, "metric_definition_version": DEFINITION,
            "metric_key": key, "value_decimal": sorted(values)[0] if values and not reasons else None,
            "unit": "CNY_YUAN", "scope": "consolidated", "basis": source.get("basis"),
            "status": "unsupported" if reasons else "candidate", "evidence_refs": refs, "basis_refs": basis_refs,
            "unsupported_reasons": sorted(reasons), "confirmation_ref": None, "formula": None, "input_refs": []}
        item["metric_id"] = str(uuid5(NAMESPACE_URL, digest(item)))
        metrics.append(ExtendedMetricV2.model_validate(item).model_dump(mode="json", exclude_unset=True))
    return metrics


def debt_ratio(metrics):
    """Deterministic arithmetic after caller admits authority/currentness. No client amounts."""
    if len(metrics) != 2 or {m["metric_key"] for m in metrics} != {"total_assets", "total_liabilities"}:
        raise FinanceError("assets_and_liabilities_required")
    for key in ("company_id", "document_id", "source_revision", "content_sha256", "as_of_date", "basis", "scope", "metric_definition_version"):
        if len({m[key] for m in metrics}) != 1:
            raise FinanceError("incomparable_" + key)
    if any(m["period_kind"] != "instant" or m["unit"] != "CNY_YUAN" or not m["as_of_date"] or
           m["scope"] != "consolidated" or m["value_decimal"] is None for m in metrics):
        raise FinanceError("unsupported_metric_inputs")
    by_key = {m["metric_key"]: m for m in metrics}
    assets, liabilities = Decimal(by_key["total_assets"]["value_decimal"]), Decimal(by_key["total_liabilities"]["value_decimal"])
    if not assets.is_finite() or not liabilities.is_finite() or assets <= 0 or liabilities < 0:
        raise FinanceError("zero_or_negative_balance")
    with localcontext() as ctx:
        ctx.prec = max(50, len(assets.as_tuple().digits) + len(liabilities.as_tuple().digits) + 12)
        ctx.rounding = ROUND_HALF_EVEN
        value = (liabilities / assets * 100).quantize(Decimal("0.000001"))
    return format(value, "f")
