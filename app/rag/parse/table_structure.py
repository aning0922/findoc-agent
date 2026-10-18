"""Geometry-only projection of ruled financial tables; no gold, LLM or amounts.

PDFs often draw padding rectangles inside a column. A sparse extract indexes the
header in a padding subcolumn and the amount at its spanning cell's left edge.
Only boundaries continuous through every physical strip may define a flat column
or row. The original grid, including null placeholders, remains in PDFLayout.rows.
Multi-level, intersecting or ambiguous structures fail closed rather than flatten.
"""

import re
from typing import cast
from app.rag.parse.models import PDFLayout, PDFCell, TableStructure, TableCell

YEAR = re.compile(r"(\d{4})年(?:度|末)?")


def project_table(layout: PDFLayout, *, financial_page: bool = False) -> TableStructure | None:
    cells = [
        (r, c, cell)
        for r, row in enumerate(layout.rows)
        for c, cell in enumerate(row)
        if cell.bbox is not None
    ]
    all_cells = [cell for row in layout.rows for cell in row]
    years = [cell for cell in all_cells if YEAR.fullmatch((cell.text or "").strip())]
    financial = financial_page or len(years) >= 2 or any(
        term in (cell.text or "")
        for cell in all_cells
        for term in ("营业收入", "净利润", "现金流量净额")
    )
    if not financial:
        return None

    def unsupported(reason: str) -> TableStructure:
        return TableStructure(status="unsupported", reason=reason)

    if not cells or any(cell.text and cell.bbox is None for row in layout.rows for cell in row):
        return unsupported("missing_cell_geometry")
    boxes = [cell.bbox for _, _, cell in cells]
    assert all(b is not None for b in boxes)
    # table.find_tables uses shared, exact edge coordinates. No fuzzy amount matching.
    xs = sorted({x for b in boxes if b for x in (b[0], b[2])})
    ys = sorted({y for b in boxes if b for y in (b[1], b[3])})
    if any(b and (b[0] >= b[2] or b[1] >= b[3]) for b in boxes):
        return unsupported("invalid_cell_rectangle")

    # Each strip must be tiled exactly once. Holes and overlapping rectangles
    # cannot be certified by matching their outer envelope alone.
    for top, bottom in zip(ys, ys[1:]):
        mid = (top + bottom) / 2
        intervals = sorted((b[0], b[2]) for b in boxes if b and b[1] < mid < b[3])
        edge = xs[0]
        for left, right in intervals:
            if left != edge:
                return unsupported("incomplete_or_overlapping_grid")
            edge = right
        if edge != xs[-1]:
            return unsupported("incomplete_or_overlapping_grid")

    def continuous(axis: int, strips: list[float]) -> list[float]:
        edges = None
        other = 1 - axis
        for a, b in zip(strips, strips[1:]):
            mid = (a + b) / 2
            active = [box for box in boxes if box and box[other] < mid < box[other + 2]]
            found = {v for box in active for v in (box[axis], box[axis + 2])}
            edges = found if edges is None else edges & found
        return sorted(edges or [])

    columns, rows = continuous(0, ys), continuous(1, xs)
    if len(columns) < 3 or len(rows) < 2:
        return unsupported("no_unique_flat_grid")
    if columns[0] != xs[0] or columns[-1] != xs[-1] or rows[0] != ys[0] or rows[-1] != ys[-1]:
        return unsupported("incomplete_table_envelope")
    grid: list[list[list[tuple[int, int, PDFCell]]]] = [[[] for _ in columns[1:]] for _ in rows[1:]]
    for r, c, cell in cells:
        assert cell.bbox is not None
        b = cell.bbox
        cx = [
            i
            for i, (left, right) in enumerate(zip(columns, columns[1:]))
            if left <= b[0] and b[2] <= right
        ]
        cy = [
            i
            for i, (top, bottom) in enumerate(zip(rows, rows[1:]))
            if top <= b[1] and b[3] <= bottom
        ]
        if len(cx) != 1 or len(cy) != 1:
            return unsupported("cell_crosses_logical_boundary")
        grid[cy[0]][cx[0]].append((r, c, cell))
    result = []
    current_years: dict[int, int] = {}
    for ri, row in enumerate(grid):
        texts = []
        refs = []
        for group in row:
            # Keep physical reading order and all original cell references, including padding.
            ordered = sorted(
                group,
                key=lambda v: (
                    cast(tuple[float, float, float, float], v[2].bbox)[1],
                    cast(tuple[float, float, float, float], v[2].bbox)[0],
                ),
            )
            visible = [v for v in ordered if v[2].text and v[2].text.strip()]
            for first, second in zip(visible, visible[1:]):
                if (
                    cast(tuple[float, float, float, float], first[2].bbox)[3]
                    > cast(tuple[float, float, float, float], second[2].bbox)[1] + 0.01
                ):
                    return unsupported("overlapping_visible_cells")
            texts.append(" ".join((v[2].text or "").replace("\n", " ").strip() for v in visible))
            refs.append([[r, c] for r, c, _ in ordered])
        header = {
            ci: int(m.group(1)) for ci, text in enumerate(texts) if (m := YEAR.fullmatch(text))
        }
        if header:
            if len(header) < 2 or len(set(header.values())) != len(header):
                return unsupported("ambiguous_year_header")
            current_years = header
        elif not current_years:
            return unsupported("missing_year_header")
        for ci, (text, group) in enumerate(zip(texts, row)):
            if (
                ci in current_years
                and not header
                and sum(bool(v[2].text and v[2].text.strip()) for v in group) > 1
            ):
                return unsupported("multiple_values_in_year_cell")
            result.append(
                TableCell(
                    row=ri,
                    column=ci,
                    text=text,
                    bbox=(columns[ci], rows[ri], columns[ci + 1], rows[ri + 1]),
                    raw_cells=refs[ci],
                    actual_year=current_years.get(ci),
                    is_header=bool(header),
                )
            )
    return TableStructure(status="verified", columns=columns, rows=rows, cells=result)


def render_structure(structure: TableStructure) -> str:
    if structure.status != "verified":
        return "表格列关系待核验（unsupported）；请打开原 PDF 核对，未发布结构化金额。"

    def clean(text: str) -> str:
        return text.replace("|", "\\|").replace("\n", " ")

    lines = []
    ncols = len(structure.columns) - 1
    for ri in range(len(structure.rows) - 1):
        row = [c for c in structure.cells if c.row == ri]
        lines.append("| " + " | ".join(clean(c.text) for c in row) + " |")
        if row[0].is_header:
            if ri:
                lines.insert(len(lines) - 1, "")
            lines.append("| " + " | ".join(["---"] * ncols) + " |")
    return "\n".join(lines)
