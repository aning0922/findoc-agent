from app.rag.parse import parse_pdf

chunks = parse_pdf("data/京东方A 2025年报.pdf", backend="mineru", mineru_out="./mineru_out")
print(f"总块数：{len(chunks)}")
print(f"表格块：{sum(1 for c in chunks if c.type == 'table')}")
print(f"段落块：{sum(1 for c in chunks if c.type == 'paragraph')}")
for c in chunks[:10]:
    print(f"    [{c.type}] p{c.page}: {c.text[:40]}...")
