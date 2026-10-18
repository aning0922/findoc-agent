import pdfplumber
import re
from .models import DocChunk, PDFCell, PDFLayout
from .table_structure import project_table, render_structure


def table_to_md(table: list[list[str | None]]) -> str:
    """pdfplumber 的表格(行列嵌套 list)→ 合法 Markdown 表格。
    单元格里的换行 / 竖线会破坏表格,先清洗;各行列数不齐就补空。"""

    def clean(cell: str | None) -> str:
        return (cell or "").replace("\n", " ").replace("|", "\\|").strip()

    rows = [[clean(c) for c in row] for row in table]
    if not rows:
        return ""
    ncol = max(len(r) for r in rows)
    rows = [r + [""] * (ncol - len(r)) for r in rows]  # 补齐每行列数
    header = "| " + " | ".join(rows[0]) + " |"
    sep = "| " + " | ".join(["---"] * ncol) + " |"
    body = ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join([header, sep] + body)


def extract_table_chunks(path: str, page_no: int | None = None) -> list[DocChunk]:
    """抽取表格并转换为DocChunk列表，表格为table类型，table_md为表格的Markdown格式"""
    chunks: list[DocChunk] = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            if page_no is not None and i != page_no:
                continue
            # Ruled detection can crop away the metric labels and one year column
            # of a financial statement. Such a fragment still requires financial
            # geometry certification; it must never fall back to an ordinary table.
            page_text = "".join((page.extract_text() or "").split())
            financial_page = any(term in page_text for term in (
                "营业收入", "净利润", "现金流量净额", "资产负债表",
                "利润表", "现金流量表", "主要会计数据和财务指标",
            ))
            for table in page.find_tables():
                t = table.extract()
                layout = PDFLayout(
                    strategy="ruled",
                    rows=[
                        [PDFCell(text=text, bbox=box) for text, box in zip(cells, row.cells)]
                        for cells, row in zip(t, table.rows)
                    ],
                )
                boxes = [c.bbox for row in layout.rows for c in row if c.bbox]
                xs = sorted({v for b in boxes for v in (b[0], b[2])})
                ys = sorted({v for b in boxes for v in (b[1], b[3])})
                for row in layout.rows:
                    for cell in row:
                        if cell.bbox:
                            cell.column_span = xs.index(cell.bbox[2]) - xs.index(cell.bbox[0])
                            cell.row_span = ys.index(cell.bbox[3]) - ys.index(cell.bbox[1])
                monetary_fragment = financial_page and any(
                    re.search(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d{2}", cell.text or "")
                    for row in layout.rows for cell in row
                )
                layout.table_structure = project_table(layout, financial_page=monetary_fragment)
                md = (
                    render_structure(layout.table_structure)
                    if layout.table_structure
                    else table_to_md(t)
                )
                summary = f"第{i}页表格，{len(t)}行，{len(t[0])}列"
                chunks.append(
                    DocChunk(
                        text=summary,
                        page=i,
                        type="table",
                        source_file=path,
                        table_md=md,
                        layout=layout,
                    )
                )

    return chunks


if __name__ == "__main__":
    path = "data/京东方A 2025年报.pdf"
    chunks = extract_table_chunks(path, 29)
    for c in chunks:
        print(c.text)
        print(c.table_md)  # ⚠️ 直接打 table_md 才看得到真实换行;print(列表) 会把 \n 显示成转义符
        print("-" * 40)
