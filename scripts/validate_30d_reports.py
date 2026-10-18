"""D1-D3 isolated real-PDF experiment. Never writes facts or invokes RAG/LLM.

Run with a Python environment containing the repository dependencies:
  PYTHONPATH=. python scripts/validate_30d_reports.py
PDF bytes stay unchanged under ignored data/; expected values live separately.
"""

from decimal import Decimal
import argparse
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.request

import pdfplumber
import pymupdf

from app.agent.revenue_extraction import extract_revenue_candidates
from app.documents.preparation import PreparedDocumentTask
from app.rag.parse import parse_pdf
from app.rag.retriever import SearchFilters, SearchHit, TrustedContext

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "product/validation"
ALIASES = {
    "revenue": "营业收入",
    "net_profit_parent": "归属于上市公司股东的净利润",
    "operating_cash_flow": "经营活动产生的现金流量净额",
}


def compact(value: str) -> str:
    return re.sub(r"\s+", "", value)


def summary_candidates(path: Path) -> tuple[list[dict], list[dict]]:
    """Conservative ruled summary-table probe, not a production extractor.

    Finds pages by content; maps explicit year headers by x coordinates rather
    than column ordinal. Unknown labels/units or ambiguous cells are skipped.
    Scope/accounting basis still requires a separate statement cross-check.
    """
    candidates, diagnostics = [], []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            if "主要会计数据和财务指标" not in compact(page.extract_text() or ""):
                continue
            tables = page.find_tables()
            diagnostics.append({"page": page.page_number, "table_count": len(tables)})
            for table in tables:
                rows = table.extract()
                years = {}
                year_header_cells = []
                for row_idx, cells in enumerate(rows):
                    for col_idx, cell in enumerate(cells):
                        match = re.fullmatch(r"(\d{4})年", compact(cell or ""))
                        box = table.rows[row_idx].cells[col_idx]
                        if match and box:
                            years[int(match[1])] = (box[0] + box[2]) / 2
                            year_header_cells.append(cell)
                    label = compact("".join(c or "" for c in cells))
                    for metric, alias in ALIASES.items():
                        if not label.startswith(alias):
                            continue
                        unit_match = re.search(r"[（(](千元|万元|亿元|元)[）)]", label)
                        if not unit_match:
                            continue
                        unit = unit_match[1]
                        factor = {"元": 1, "千元": 1000, "万元": 10000, "亿元": 100000000}[unit]
                        for year, x in years.items():
                            matches = []
                            for col_idx, cell in enumerate(cells):
                                box = table.rows[row_idx].cells[col_idx]
                                if box and box[0] <= x <= box[2]:
                                    raw = compact(cell or "")
                                    if re.fullmatch(r"-?\d[\d,]*(?:\.\d+)?", raw):
                                        matches.append((raw, box))
                            if len(matches) != 1:
                                continue
                            raw, box = matches[0]
                            candidates.append({
                                "metric": metric, "period": year, "raw_value": raw,
                                "raw_unit": unit,
                                "value_cny_yuan": format(Decimal(raw.replace(",", "")) * factor, "f"),
                                "physical_page": page.page_number,
                                "bbox_pdf_points": list(box), "label": alias,
                                "raw_row_cells": cells,
                                "year_header_cells": list(year_header_cells),
                                "scope": "unverified_summary", "status": "candidate_only",
                            })
    return candidates, diagnostics


def main() -> None:
    sources = json.loads((OUT / "sources.json").read_text())
    truth = json.loads((OUT / "manual-benchmark.json").read_text())
    output = {"boundary": "offline PDF parser and isolated table probe; no model/vector/HTTP/human confirmation", "documents": [], "facts": []}
    for source in sources:
        path = ROOT / source["path"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != source["sha256"]:
            raise ValueError(f"source_changed: {source['id']}")
        started = time.monotonic()
        chunks = parse_pdf(str(path), backend="fast")
        prepared = PreparedDocumentTask(
            query="查询2024和2025年度营业收入",
            context=TrustedContext(workspace_id="offline-validation"),
            filters=SearchFilters(document_id=source["id"]), source_file=str(path),
        )
        # All parsed chunks supplied as controlled inputs: upper bound on the old
        # rule's coverage, not actual top-k retrieval or ready/source validation.
        hits = tuple(SearchHit(score=1.0, chunk_id=f"{source['id']}:{i}",
            text=c.text, page=c.page, source_file=c.source_file, type=c.type,
            table_md=c.table_md, workspace_id="offline-validation", document_id=source["id"])
            for i, c in enumerate(chunks))
        old = extract_revenue_candidates(prepared=prepared, hits=hits)
        candidates, diagnostics = summary_candidates(path)
        doc = pymupdf.open(path)
        output["documents"].append({
            "id": source["id"], "sha256": digest, "page_count": len(doc),
            "paragraph_chunks": sum(c.type == "paragraph" for c in chunks),
            "table_chunks": sum(c.type == "table" for c in chunks),
            "legacy_revenue_candidates": len(old.state.candidates),
            "legacy_failure": old.state.failure_code.value if old.state.failure_code else None,
            "probe_candidates": candidates, "diagnostics": diagnostics,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        })
        for expected in truth["facts"]:
            if expected["document_id"] != source["id"]:
                continue
            matched = [c for c in candidates if c["metric"] == expected["metric"] and c["period"] == expected["period"]]
            result = matched[0] if len(matched) == 1 else None
            passed = result is not None and all(result[key] == expected[key] for key in ("value_cny_yuan", "physical_page", "raw_unit"))
            page_text = doc[expected["statement_page"] - 1].get_text()
            statement_text_contains_value = expected["raw_value"] in page_text
            output["facts"].append({**expected, "system_result": result,
                "probe_pass": passed, "statement_text_contains_value": statement_text_contains_value,
                "failure_reason": None if passed else "summary_label_split_or_unit_not_in_same_row",
                "production_status": "unsupported_by_legacy_extractor"})
        doc.close()
        print(source["id"], "legacy", len(old.state.candidates), "probe", len(candidates), flush=True)
    output["summary"] = {"benchmark_count": len(output["facts"]),
        "probe_pass": sum(f["probe_pass"] for f in output["facts"]),
        "statement_value_crosschecks": sum(f["statement_text_contains_value"] for f in output["facts"])}
    (OUT / "real-pdf-results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(output["summary"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Fetch pinned public sources and verify SHA256")
    args = parser.parse_args()
    if args.download:
        for source in json.loads((OUT / "sources.json").read_text()):
            target = ROOT / source["path"]
            if not target.exists():
                content = urllib.request.urlopen(source["url"], timeout=45).read()
                if hashlib.sha256(content).hexdigest() != source["sha256"]:
                    raise ValueError(f"download source_changed: {source['id']}")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
    main()
