# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportOptionalMemberAccess=false
import pdfplumber
# import pymupdf
from app.rag.parse.tables import table_to_md

path, pno = "data/京东方A 2025年报.pdf", 63
with pdfplumber.open(path) as pdf:
    for t in pdf.pages[pno].extract_tables():
        print("pdfplumber: ", table_to_md(t))
# with pymupdf.open(path) as doc:
#     for t in doc[pno].find_tables().tables:
#         print("pymupdf: ", t.extract())
