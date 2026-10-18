# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
from typing import Any, cast
import re
from .models import DocChunk, PDFCell, PDFLayout
import pymupdf

SCANNED_CHAR_THRESHOLD = 20  # 一页文字少于这么多字符 -> 判扫描页(图片，没有文字层)


def page_body_text(page: pymupdf.Page, margin_frac: float = 0.07) -> str:
    """获取页面主体文本，排除页眉页脚"""
    r = page.rect
    body = pymupdf.Rect(
        r.x0,
        r.y0 + r.height * margin_frac,
        r.x1,
        r.y1 - r.height * margin_frac,
    )
    return cast(str, page.get_text(clip=body))


def page_text(page: pymupdf.Page) -> str:
    # get_text() 有多种返回(str/list/dict),默认取纯文本;cast 成 str 才能 .strip()
    return cast(str, page.get_text())


def is_scanned_page(page: pymupdf.Page) -> bool:
    return len(page_body_text(page).strip()) < SCANNED_CHAR_THRESHOLD


def extract_text_fast(path: str) -> list[str]:
    """逐页抽纯文本,返回每页文本组成的列表"""
    pages: list[str] = []
    with pymupdf.open(path) as doc:
        for i in range(doc.page_count):
            pages.append(page_body_text(doc[i]))
    return pages


def text_to_chunks(path: str) -> list[DocChunk]:
    """抽取文本并转换为DocChunk列表"""
    chunks: list[DocChunk] = []
    with pymupdf.open(path) as doc:
        for i in range(doc.page_count):
            page = doc[i]
            if is_scanned_page(page):
                continue
            txt = page_body_text(page).strip()
            if txt:
                chunks.append(
                    DocChunk(
                        text=txt,
                        page=i + 1,
                        type="paragraph",
                        source_file=path,
                        layout=page_layout(page),
                    )
                )
    return chunks


def page_layout(page: pymupdf.Page) -> PDFLayout:
    """Keep actual text lines and PDF point boxes, including borderless tables.

    Only co-baseline lines are grouped. No inferred numeric cells or OCR values.
    Full page geometry is retained separately from margin-clipped retrieval text.
    """
    data = cast(dict[str, Any], page.get_text("dict"))
    words = cast(list[tuple[Any, ...]], page.get_text("words"))
    cells: list[PDFCell] = []
    for block in data["blocks"]:
        for line in block.get("lines", []):
            text = "".join(span["text"] for span in line["spans"])
            if text.strip():
                # MuPDF sometimes joins notes and two amounts into a single line.
                # Split using real word boxes, never estimated substring coordinates.
                b = line["bbox"]
                matching = [
                    w
                    for w in words
                    if b[0] - 0.1 <= w[0]
                    and w[2] <= b[2] + 0.1
                    and b[1] - 0.1 <= w[1]
                    and w[3] <= b[3] + 0.1
                ]
                numeric = [w for w in matching if re.fullmatch(r"[()（）+\-\d,.]+", w[4])]
                if numeric and len(matching) > 1 and not re.fullmatch(r"\s*\d{4}\s*年度?\s*", text):
                    cells.extend(PDFCell(text=w[4], bbox=tuple(w[:4])) for w in matching)
                else:
                    cells.append(PDFCell(text=text, bbox=tuple(b)))
    rows: list[list[PDFCell]] = []
    for cell in sorted(
        cells, key=lambda c: ((c.bbox or (0, 0, 0, 0))[1], (c.bbox or (0, 0, 0, 0))[0])
    ):
        assert cell.bbox is not None
        center = (cell.bbox[1] + cell.bbox[3]) / 2
        anchor = rows[-1][0].bbox if rows else None
        if anchor is not None and abs(center - (anchor[1] + anchor[3]) / 2) <= 3:
            rows[-1].append(cell)
        else:
            rows.append([cell])
    for row in rows:
        row.sort(key=lambda c: (c.bbox or (0, 0, 0, 0))[0])
    return PDFLayout(strategy="text_geometry", rows=rows)


if __name__ == "__main__":
    path = "data/京东方A 2025年报.pdf"
    chunks = text_to_chunks(path)
    print(chunks)
    with pymupdf.open(path) as doc:
        for block in doc[11].get_text("blocks"):
            x0, y0, x1, y1, text, block_no, block_type = block
            if block_type == 0:
                print(block_no, repr(text[:30]))
