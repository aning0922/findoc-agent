import json
from pathlib import Path

from app.rag.embed import embed
from app.rag.store import get_client, ensure_collection, insert_rows, count_rows

files = sorted(Path("data").glob("*_chunks.jsonl"))
chunks: list[dict[str, object]] = []
for f in files:
    chunks += [json.loads(x) for x in f.read_text("utf-8").splitlines() if x.strip()]
print(f"共 {len(chunks)} 块（来自 {len(files)}）家")

vecs = embed([c["text"] for c in chunks if isinstance(c["text"], str)])
rows = [{"id": i, "vector": v, **c} for i, (c, v) in enumerate(zip(chunks, vecs))]

client = get_client()
ensure_collection(client, "findoc")
n = insert_rows(client, "findoc", rows)
print(f"写入：{n} 块")
print(f"库内行数：{count_rows(client, 'findoc')}")
