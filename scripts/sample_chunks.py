import json
import random
import sys
from pathlib import Path

sys.path.insert(0, ".")


def sample(path: str = "chunks.jsonl", n: int = 20) -> None:
    """
    抽样分块结果
    Args:
        path: 分块结果文件路径
        n: 抽样块数
    """
    print(f"抽样文件：{path}")
    print(f"抽样块数：{n}")
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    chunks = [json.loads(x) for x in lines if x.strip()]
    for c in random.sample(chunks, min(n, len(chunks))):
        print(f"[{c['type']}] p{c['page']} 章节={c['section']}")
        print(f"   头：{c['text'][:25]}")
        print(f"   尾：{c['text'][-25:]}")
        print("-" * 40)

if __name__ == "__main__":
    sample("./data/京东方A 2025年报_chunks.jsonl", 20)