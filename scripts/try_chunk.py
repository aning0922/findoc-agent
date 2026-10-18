from app.rag.parse import parse_pdf
from app.rag.chunk import chunk_docment, save_chunks

file_name = "贵州茅台2025年报"
blocaks = parse_pdf(f"data/{file_name}.pdf", backend="mineru", mineru_out=f"./mineru_out/{file_name}")
chunks = chunk_docment(blocaks)
print(f"粗块数: {len(blocaks)} + 精块数: {len(chunks)}")
save_chunks(chunks, f"./data/{file_name}_chunks.jsonl")