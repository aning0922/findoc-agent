# pyright: reportUnknownMemberType=false
from pathlib import Path
import pymupdf
from app.rag.parse import parse_pdf

def _make_text_pdf(path: str) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Annual report test paragraph.")
    doc.save(path)
    doc.close()

def test_parse_pdf_retruns_paragraph_chunks(tmp_path: Path) -> None:
    pdf = tmp_path / "t.pdf"
    _make_text_pdf(str(pdf))
    chunks = parse_pdf(str(pdf))
    assert len(chunks) > 0
    assert any(c.type == "paragraph" for c in chunks)
    assert all(c.page >= 1 for c in chunks)
