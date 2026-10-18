import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, ".")
from app.rag.chunk import CHUNK_SIZE, count_tokens


def inspect(path: str = "chunks.jsonl") -> None:
    """
    检查分块结果
    统计块数、token 数量、缺失字段、唯一性、超长块
    Args:
        path: 分块结果文件路径
    """
    print(f"检查文件：{path}")
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    chunks = [json.loads(x) for x in lines if x.strip()]
    toks = [count_tokens(c["text"]) for c in chunks]
    print(f"块数：{len(chunks)}")
    print(f"token: min={min(toks)}, median={int(statistics.median(toks))}, max={max(toks)}")
    for k in ("source_file", "page", "section", "chunk_id"):
        miss = sum(1 for c in chunks if c.get(k) in (None, ""))
        print(f" {k}: 缺失 {miss} 个")
    ids = [c["chunk_id"] for c in chunks]
    print(f"chunk_id 唯一： {len(ids) == len(set(ids))}")
    print(f"超长块(>1.3 X {CHUNK_SIZE}): {sum(1 for t in toks if t > 1.3 * CHUNK_SIZE)}")

if __name__ == "__main__":
    inspect("./data/京东方A 2025年报_chunks.jsonl")