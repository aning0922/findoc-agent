from typing import Literal
from .models import DocChunk
from .mineru_adapter import parse_mineru_output
from .quick_text import text_to_chunks
from .tables import extract_table_chunks


def parse_pdf(
    path: str, backend: Literal["fast", "mineru"] = "fast", mineru_out: str | None = None
) -> list[DocChunk]:
    if backend == "mineru":
        if mineru_out is None:
            raise ValueError("backend='mineru' 时，mineru_out 不能为空")
        return parse_mineru_output(mineru_out, path).chunks

    chunks = text_to_chunks(path)  # 段落块 pymupdf 解析
    chunks += extract_table_chunks(path)  # 表格块 pdfplumber 解析
    return chunks


__all__ = ["parse_pdf", "parse_mineru_output", "DocChunk"]
