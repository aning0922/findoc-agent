"""Read-only, finite raw-cell projection. Never author an answer or a financial fact.

Values come exclusively from digest-checked captured geometry, reprojected with the
unchanged table verifier. Missing/ambiguous targets fail closed. No cache is shared
between questions, even when complete historical answers have identical hashes.
"""

from collections.abc import Callable
import re
from typing import Any

from app.agent.metric_extraction import compact, parse_amount
from app.rag.calculation_intent import requires_financial_analysis
from app.rag.parse.models import PDFLayout
from app.rag.parse.table_structure import project_table, render_structure
from app.research.models import Citation, Envelope, canonical, sha

VERSION = "trusted-answer-focus-v1"
METRICS = {
    "revenue": ("营业收入",),
    "total_revenue": ("营业总收入",),
    "net_profit_parent": ("归属于上市公司股东的净利润", "归属于母公司股东的净利润", "归母净利润"),
    "net_profit_excluding_nonrecurring": (
        "归属于上市公司股东的扣除非经常性损益的净利润",
        "归属于母公司股东的扣除非经常性损益的净利润",
        "扣非净利润",
    ),
    "operating_cash_flow": ("经营活动产生的现金流量净额", "经营现金流量净额"),
}
UNIT_LABEL = re.compile(r"(.+)[（(](元|千元|万元|亿元)[）)]")
NEGATIVE_TAIL = re.compile(
    r"[，,；;](?:不计算同比|不要计算同比|不做同比|不要做同比|无需计算同比|仅摘录)$"
)


def target(query: str, companies: dict[str, str]) -> tuple[str, int, str] | None:
    """A deliberately closed grammar for one company/year/raw metric request."""
    if requires_financial_analysis(query):
        return None
    text = NEGATIVE_TAIL.sub("", compact(query).rstrip("。.!！"))
    names = "|".join(re.escape(name) for name in sorted(companies.values(), key=len, reverse=True))
    aliases = "|".join(re.escape(a) for values in METRICS.values() for a in values)
    match = re.fullmatch(
        rf"(?:请)?(?:仅|只)?(?:摘录|列出|列|提供|读取)?(?P<company>{names})?"
        rf"(?P<year>\d{{4}})年(?:度)?(?:年报)?(?P<metric>{aliases})"
        r"(?:原值|原始金额)(?:及原单位|和原单位)?",
        text,
    )
    if match is None:
        return None
    candidates = [cid for cid, name in companies.items() if name == match["company"]]
    if match["company"] is None and len(companies) == 1:
        candidates = list(companies)
    if len(candidates) != 1:
        return None
    metric = next(k for k, aliases in METRICS.items() if match["metric"] in aliases)
    return candidates[0], int(match["year"]), metric


def project_focus(
    run: Envelope,
    companies: dict[str, str],
    read_page: Callable[[Citation], list[dict[str, Any]]],
) -> dict[str, Any]:
    base = dict(
        projection_version=VERSION,
        run_id=run.run_id,
        query_sha256=sha(run.query),
        run_integrity_sha256=sha(canonical(run.model_dump())),
        answer_sha256=sha(run.result.content if run.result else ""),
    )

    def finish(status: str, reason: str | None, focus: dict[str, Any] | None = None):
        value = dict(**base, status=status, reason=reason, focus=focus)
        return dict(**value, projection_sha256=sha(canonical(value)))

    if run.status != "answered" or run.result is None:
        return finish("unlocated", "non_answer")
    requested = target(run.query, companies)
    if requested is None:
        return finish("unlocated", "unsupported_or_ambiguous_question")
    company, year, metric = requested
    found = []
    for citation in run.result.citations:
        if citation.company_id != company:
            continue
        if not citation.parser_version.startswith("fast-pdf-v4;table-geometry-v2;"):
            return finish("unlocated", "unverified_parser")
        records = read_page(citation)
        # Match the whole stored page snapshot, not a numerical substring from a model.
        if (
            not records
            or any(
                r["source_revision"] != citation.source_revision
                or r["physical_page"] != citation.physical_page
                for r in records
            )
            or "\n".join(r["text"] for r in records) != citation.text
        ):
            return finish("unlocated", "page_snapshot_mismatch")
        if "主要会计数据和财务指标" not in compact(citation.text):
            continue  # C1 covers annual summary excerpts only, not statement scope inference.
        for record in records:
            if record["kind"] != "table" or not record.get("layout"):
                continue
            layout = PDFLayout.model_validate(record["layout"])
            structure = layout.table_structure
            if structure is None:
                if any(a in compact(record["text"]) for a in METRICS[metric]):
                    return finish("unlocated", "unreliable_table")
                continue
            if structure.status != "verified":
                return finish("unlocated", "unreliable_table")
            checked = project_table(layout, financial_page=True)
            if checked != structure or render_structure(structure) != record["text"]:
                return finish("unlocated", "table_geometry_mismatch")
            rows = [
                [c for c in structure.cells if c.row == ri] for ri in range(len(structure.rows) - 1)
            ]
            header_index = None
            for ri, row in enumerate(rows):
                if row[0].is_header:
                    header_index = ri
                    continue
                if header_index is None:
                    continue
                first_year_column = min(c.column for c in row if c.actual_year is not None)
                labels = [
                    (ci, c, UNIT_LABEL.fullmatch(compact(c.text)))
                    for ci, c in enumerate(row)
                    if ci < first_year_column and c.text
                ]
                matching = [(ci, c, m) for ci, c, m in labels if m and m[1] in METRICS[metric]]
                # A recognised target without an explicit row unit is not publishable.
                bare_target = any(compact(c.text) in METRICS[metric] for _, c, _ in labels)
                if bare_target:
                    return finish("unlocated", "unit_missing")
                if not matching:
                    continue
                if len(labels) != 1 or len(matching) != 1:
                    return finish("unlocated", "ambiguous_metric_row")
                label_column, label, unit_match = matching[0]
                assert unit_match is not None
                amounts = [c for c in row if c.actual_year == year]
                if len(amounts) != 1:
                    continue
                cell = amounts[0]
                header = rows[header_index][cell.column]
                if re.fullmatch(rf"{year}年(?:度)?", compact(header.text)) is None:
                    continue
                raw = [
                    layout.rows[r][c]
                    for r, c in cell.raw_cells
                    if layout.rows[r][c].text and layout.rows[r][c].text.strip()
                ]
                if len(raw) != 1 or compact(raw[0].text) != compact(cell.text):
                    return finish("unlocated", "ambiguous_original_cell")
                unit, value = unit_match[2], raw[0].text
                if value is None or parse_amount(value, unit) is None:
                    return finish("unlocated", "unsupported_amount")
                table_sha = sha(
                    canonical(
                        dict(
                            evidence_id=record["evidence_id"],
                            source_revision=record["source_revision"],
                            physical_page=record["physical_page"],
                            text=record["text"],
                            layout=record["layout"],
                        )
                    )
                )
                found.append(
                    dict(
                        **{
                            k: getattr(citation, k)
                            for k in (
                                "workspace_id",
                                "document_id",
                                "company_id",
                                "report_year",
                                "source_revision",
                                "content_sha256",
                                "attempt",
                                "parser_version",
                                "chunk_id",
                                "source_file",
                                "physical_page",
                            )
                        },
                        company_name=companies[company],
                        financial_year=year,
                        metric_key=metric,
                        citation_number=citation.number,
                        citation_sha256=sha(citation.text),
                        table_id=record["evidence_id"],
                        table_sha256=table_sha,
                        table_text=record["text"],
                        table_text_sha256=sha(record["text"]),
                        row_index=ri,
                        column_index=cell.column,
                        header_row_index=header_index,
                        metric_column_index=label_column,
                        row_label=label.text,
                        year_header=header.text,
                        raw_value=value,
                        raw_unit=unit,
                        original_row=[c.text for c in row],
                        original_header=[c.text for c in rows[header_index]],
                        raw_cells=cell.raw_cells,
                        # Strings retain authoritative coordinates and give Python/JS
                        # the same canonical bytes (e.g. 100.0 must not become 100).
                        bbox=[str(n) for n in cell.bbox],
                        unit_raw_cells=label.raw_cells,
                        year_raw_cells=header.raw_cells,
                    )
                )
    if len(found) != 1:
        return finish("unlocated", "missing_or_ambiguous_cell")
    return finish("located", None, found[0])
