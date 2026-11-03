"""Finite fast-text statement candidates, with exact PDF word geometry; no OCR or approval."""

import hashlib
import json
import re
from decimal import Decimal, localcontext
from uuid import NAMESPACE_URL, uuid5
import pymupdf
from .models import time_adapter


def canonical(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(x):
    return hashlib.sha256(canonical(x).encode()).hexdigest()


LABELS = {
    "balance_sheet": {
        "货币资金": "cash",
        "应收账款": "accounts_receivable",
        "存货": "inventory",
        "流动资产合计": "current_assets",
        "资产总计": "total_assets",
        "流动负债合计": "current_liabilities",
        "负债合计": "total_liabilities",
    },
    "income_statement": {
        "其中：营业收入": "revenue",
        "其中：营业成本": "cost_of_revenue",
        "销售费用": "selling_expenses",
        "管理费用": "administrative_expenses",
        "研发费用": "research_expenses",
        "财务费用": "finance_expenses",
        "归属于母公司股东的净利润": "net_profit_parent",
        "1.归属于母公司股东的净利润": "net_profit_parent",
    },
    "cash_flow_statement": {
        "经营活动现金流入小计": "operating_inflows",
        "经营活动现金流出小计": "operating_outflows",
        "经营活动产生的现金流量净额": "operating_cash_flow",
        "投资活动产生的现金流量净额": "investing_cash_flow",
        "筹资活动产生的现金流量净额": "financing_cash_flow",
    },
}
TITLES = {
    "合并资产负债表": "balance_sheet",
    "合并利润表": "income_statement",
    "合并现金流量表": "cash_flow_statement",
}


def extract(source, raw):
    if hashlib.sha256(raw).hexdigest() != source["content_sha256"]:
        raise ValueError("pdf_hash_changed")
    output = []
    with pymupdf.open(stream=raw, filetype="pdf") as pdf:
        for page_index, page in enumerate(pdf):
            words = page.get_text("words")
            rows = []
            for w in sorted(words, key=lambda w: (round(w[1] / 3), w[0])):
                row = next((r for r in rows if abs(r[0][1] - w[1]) < 3), None)
                if row is None:
                    rows.append([w])
                else:
                    row.append(w)
            rows = [sorted(r, key=lambda w: w[0]) for r in rows]
            texts = ["".join(w[4] for w in r).replace(" ", "") for r in rows]
            output.extend(_combined_core_cells(source, page_index + 1, rows, texts))
            headings = [
                (i, TITLES[re.sub(r"[（(]续[）)]$", "", t)])
                for i, t in enumerate(texts)
                if re.sub(r"[（(]续[）)]$", "", t) in TITLES
            ]
            if len(headings) != 1:
                continue
            start, kind = headings[0]
            header = next(
                (
                    i
                    for i in range(start + 1, min(start + 12, len(rows)))
                    if texts[i].startswith("项目")
                ),
                None,
            )
            if header is None:
                continue
            units = [
                u
                for t in texts[start : header + 1]
                for u in re.findall(r"单位[：:]人民币(亿元|万元|千元|元)", t)
            ]
            if len(set(units)) != 1:
                continue
            unit = units[0]
            factor = {"元": 1, "千元": 1000, "万元": 10000, "亿元": 100000000}[unit]
            columns = []
            pattern = (
                r"(\d{4})年(\d{1,2})月(\d{1,2})日" if kind == "balance_sheet" else r"(\d{4})年度"
            )
            # Header words may be split by embedded spacing; use geometric groups below.
            header_words = rows[header]
            groups = []
            for w in header_words:
                if groups and w[0] - groups[-1][-1][2] < 8:
                    groups[-1].append(w)
                else:
                    groups.append([w])
            for group in groups:
                t = "".join(w[4] for w in group)
                match = re.fullmatch(pattern, t)
                if match:
                    year = int(match[1])
                    time = (
                        {
                            "kind": "instant",
                            "as_of_date": f"{year:04d}-{int(match[2]):02d}-{int(match[3]):02d}",
                        }
                        if kind == "balance_sheet"
                        else {
                            "kind": "duration",
                            "period_start": f"{year:04d}-01-01",
                            "period_end": f"{year:04d}-12-31",
                            "period_type": "annual",
                        }
                    )
                    time_adapter.validate_python(time)
                    columns.append(
                        (sum((w[0] + w[2]) / 2 for w in group) / len(group), time, group)
                    )
            if len(columns) != 2 or columns[0][1] == columns[1][1]:
                continue
            for row, text in zip(rows[header + 1 :], texts[header + 1 :]):
                left = [w for w in row if w[2] < columns[0][0] - 50]
                label = "".join(w[4] for w in left)
                label = re.sub(r"五[、,].*", "", label)
                clean_label = re.sub(r"^[1-9][、.]", "", re.sub(r"[（(].*", "", label))
                key = LABELS[kind].get(clean_label)
                if key is None:
                    continue
                numeric = [
                    w
                    for w in row
                    if re.fullmatch(r"-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d+", w[4])
                    and w[0] > columns[0][0] - 80
                ]
                for col, (center, time, header_cells) in enumerate(columns):
                    midpoint = (columns[0][0] + columns[1][0]) / 2
                    hits = (
                        [w for w in numeric if (w[0] + w[2]) / 2 < midpoint]
                        if col == 0
                        else [w for w in numeric if (w[0] + w[2]) / 2 > midpoint]
                    )
                    if len(hits) != 1:
                        continue
                    value = hits[0][4].replace(",", "")
                    with localcontext() as ctx:
                        ctx.prec = max(50, len(value) + 15)
                        normalized = format(Decimal(value) * factor, "f")
                    ref = {
                        "document_id": source["document_id"],
                        "source_revision": source["source_revision"],
                        "content_sha256": source["content_sha256"],
                        "parser_version": source["parser_version"],
                        "physical_page": page_index + 1,
                        "raw_label": label,
                        "raw_value": hits[0][4],
                        "bbox": list(hits[0][:4]),
                        "row_words": [list(w[:5]) for w in row],
                        "header_words": [list(w[:5]) for w in header_cells],
                    }
                    cell = {
                        "schema_version": "statement-cell-v3",
                        "cell_revision": 1,
                        **{
                            k: source[k]
                            for k in (
                                "company_id",
                                "document_id",
                                "source_revision",
                                "content_sha256",
                                "parser_version",
                                "report_year",
                                "basis",
                            )
                        },
                        "metadata_hash": sha(source),
                        "disclosure_version": source["source_revision"],
                        "statement_kind": kind,
                        "metric_key": key,
                        "raw_label": label,
                        "time": time,
                        "scope": "consolidated",
                        "currency": "CNY",
                        "raw_decimal": value,
                        "raw_unit": unit,
                        "normalized_unit": "CNY_YUAN",
                        "normalized_decimal": normalized,
                        "evidence_refs": [ref],
                        "source_kind": "fast_text",
                        "extraction_status": "candidate",
                        "financial_review": "unconfirmed",
                        "transcription_review": "unreviewed",
                        "interpretation_review": "not_applicable",
                        "metric_definition_version": "consolidated-statements-v3.1",
                        "extraction_version": "pdf-words-columns-v1",
                        "limitation_codes": [],
                    }
                    cell["cell_id"] = str(uuid5(NAMESPACE_URL, sha(cell)))
                    cell["payload_sha256"] = sha(cell)
                    output.append(cell)
    groups = {}
    for c in output:
        groups.setdefault((c["metric_key"], canonical(c["time"])), []).append(c)
    for values in groups.values():
        if len(values) > 1:
            for c in values:
                c.update(
                    extraction_status="unsupported",
                    normalized_decimal=None,
                    limitation_codes=["ambiguous_metric_time"],
                )
                c["payload_sha256"] = sha({k: v for k, v in c.items() if k != "payload_sha256"})
    return output


# Combined consolidated/parent-company four-column layouts. Core five only.
def _combined_core_cells(source, physical_page, rows, texts):
    titles = []
    for i, text in enumerate(texts):
        for name, kind in (
            ("资产负债表", "balance_sheet"),
            ("利润表", "income_statement"),
            ("现金流量表", "cash_flow_statement"),
        ):
            if re.fullmatch(r"(?:\d{4}年度)?合并及公司" + name + r"(?:[（(]续[）)])?", text):
                titles.append((i, kind))
    if len(titles) != 1:
        return []
    start, kind = titles[0]
    scope_rows = [
        (i, [w for w in row if w[4] in ("合并", "公司")])
        for i, row in enumerate(rows[start + 1 : start + 15], start + 1)
    ]
    scope_rows = [
        (i, w) for i, w in scope_rows if [v[4] for v in w] == ["合并", "合并", "公司", "公司"]
    ]
    if len(scope_rows) != 1:
        return []
    scope_index, scope_words = scope_rows[0]
    units = [
        u
        for t in texts[start : scope_index + 1]
        for u in re.findall(r"(?:单位[：:]|金额单位为)人民币(亿元|万元|千元|元)", t)
    ]
    if len(set(units)) != 1:
        return []
    unit = units[0]
    factor = {"元": 1, "千元": 1000, "万元": 10000, "亿元": 100000000}[unit]
    edges = [w[2] for w in scope_words]
    gaps = [b - a for a, b in zip(edges, edges[1:])]
    if min(gaps) < 30 or max(gaps) - min(gaps) > 8:
        return []
    columns = []
    for col, edge in enumerate(edges):
        header_words = [
            w
            for row in rows[start + 1 : scope_index]
            for w in row
            if edge - min(gaps) + 3 < w[0] and w[2] <= edge + 3 and w[1] > scope_words[0][1] - 45
        ]
        header_text = "".join(
            w[4] for w in sorted(header_words, key=lambda w: (round(w[1] / 3), w[0]))
        )
        pattern = r"(\d{4})年(\d{1,2})月(\d{1,2})日" if kind == "balance_sheet" else r"(\d{4})年度"
        match = re.fullmatch(pattern, header_text)
        if match is None:
            return []
        year = int(match[1])
        time = (
            {"kind": "instant", "as_of_date": f"{year:04d}-{int(match[2]):02d}-{int(match[3]):02d}"}
            if kind == "balance_sheet"
            else {
                "kind": "duration",
                "period_start": f"{year}-01-01",
                "period_end": f"{year}-12-31",
                "period_type": "annual",
            }
        )
        time_adapter.validate_python(time)
        columns.append((time, header_words))
    if (
        columns[0][0] != columns[2][0]
        or columns[1][0] != columns[3][0]
        or columns[0][0] == columns[1][0]
    ):
        return []
    core = {
        "资产总计": "total_assets",
        "负债合计": "total_liabilities",
        "其中：营业收入": "revenue",
        "归属于母公司股东的净利润": "net_profit_parent",
        "经营活动产生/(使用)的现金流量净额": "operating_cash_flow",
    }
    result = []
    previous_label = ""
    previous_row = []
    for row in rows[scope_index + 1 :]:
        label_words = [w for w in row if w[2] < edges[0] - min(gaps) - 6]
        label = "".join(w[4] for w in label_words)
        evidence_row = row
        if (
            label == "净利润"
            and previous_label == "归属于母公司股东的"
            and row[0][1] - previous_row[0][1] < 20
        ):
            label = previous_label + label
            evidence_row = previous_row + row
        previous_label, previous_row = label, row
        key = core.get(label)
        if (
            key is None
            or key
            not in {
                "balance_sheet": {"total_assets", "total_liabilities"},
                "income_statement": {"revenue", "net_profit_parent"},
                "cash_flow_statement": {"operating_cash_flow"},
            }[kind]
        ):
            continue
        for col in (0, 1):
            edge = edges[col]
            hits = [
                w
                for w in row
                if abs(w[2] - edge) < 3
                and re.fullmatch(r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?", w[4])
            ]
            if len(hits) != 1:
                continue
            number = hits[0]
            value = number[4].replace(",", "")
            with localcontext() as context:
                context.prec = max(50, len(value) + 15)
                normalized = format(Decimal(value) * factor, "f")
            time, headers = columns[col]
            ref = {
                "document_id": source["document_id"],
                "source_revision": source["source_revision"],
                "content_sha256": source["content_sha256"],
                "parser_version": source["parser_version"],
                "physical_page": physical_page,
                "raw_label": label,
                "raw_value": number[4],
                "bbox": list(number[:4]),
                "row_words": [list(w[:5]) for w in evidence_row],
                "header_words": [list(w[:5]) for w in headers + scope_words],
                "column_index": col,
                "column_scope": "consolidated",
            }
            cell = {
                "schema_version": "statement-cell-v3",
                "cell_revision": 1,
                **{
                    k: source[k]
                    for k in (
                        "company_id",
                        "document_id",
                        "source_revision",
                        "content_sha256",
                        "parser_version",
                        "report_year",
                        "basis",
                    )
                },
                "metadata_hash": sha(source),
                "disclosure_version": source["source_revision"],
                "statement_kind": kind,
                "metric_key": key,
                "raw_label": label,
                "time": time,
                "scope": "consolidated",
                "currency": "CNY",
                "raw_decimal": value,
                "raw_unit": unit,
                "normalized_unit": "CNY_YUAN",
                "normalized_decimal": normalized,
                "evidence_refs": [ref],
                "source_kind": "fast_text",
                "extraction_status": "candidate",
                "financial_review": "unconfirmed",
                "transcription_review": "unreviewed",
                "interpretation_review": "not_applicable",
                "metric_definition_version": "consolidated-statements-v3.1",
                "extraction_version": "pdf-words-combined-columns-v1",
                "limitation_codes": [],
            }
            cell["cell_id"] = str(uuid5(NAMESPACE_URL, sha(cell)))
            cell["payload_sha256"] = sha(cell)
            result.append(cell)
    return result
