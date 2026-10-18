"""从只读的单模型缓存准备容器缓存；仅复制白名单公开文件，不复制登录令牌。

通过 compose run 将本文件传给容器内 Python 的标准输入执行。
输入：/model-source 中的 BGE-M3 hub 缓存及 HF_HOME 指定的目标缓存根。
输出：逐文件摘要；已有同内容文件复用，冲突或缺文件直接失败，不覆盖旧文件。
"""

import hashlib
import json
import os
from pathlib import Path
import shutil


MODEL_FILES = (
    "config.json", "config_sentence_transformers.json", "modules.json",
    "sentence_bert_config.json", "tokenizer_config.json", "special_tokens_map.json",
    "sentencepiece.bpe.model", "tokenizer.json", "pytorch_model.bin",
    "colbert_linear.pt", "sparse_linear.pt", "1_Pooling/config.json",
)


def file_digest(path: Path) -> str:
    """流式读取文件并返回 SHA-256，避免把大型模型权重整体放入内存。"""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> None:
    """核对 snapshot 和既有文件后准备缓存；不加载模型或访问业务库。"""
    source = Path("/model-source")
    revision = (source / "refs/main").read_text().strip()
    if len(revision) != 40 or any(char not in "0123456789abcdef" for char in revision):
        raise ValueError("BGE main 引用必须是 40 位十六进制 snapshot ID")
    cache_root = Path(os.environ["HF_HOME"])
    if not cache_root.is_absolute():
        raise ValueError("HF_HOME 必须是容器内绝对路径")
    model_root = cache_root / "hub/models--BAAI--bge-m3"
    target = model_root / "snapshots" / revision
    manifest = []
    for name in MODEL_FILES:
        original = source / "snapshots" / revision / name
        copied = target / name
        expected = file_digest(original)
        copied.parent.mkdir(parents=True, exist_ok=True)
        if not copied.exists():
            # xb 禁止覆盖；复制失败移除本次未完成文件，允许之后安全重试。
            with original.open("rb") as input_stream:
                with copied.open("xb") as output_stream:
                    try:
                        shutil.copyfileobj(input_stream, output_stream)
                    except BaseException:
                        copied.unlink()
                        raise
        if file_digest(copied) != expected:
            raise ValueError(f"缓存内容冲突：{name}")
        manifest.append({"file": name, "bytes": copied.stat().st_size, "sha256": expected})
    ref = model_root / "refs/main"
    ref.parent.mkdir(parents=True, exist_ok=True)
    if ref.exists():
        if ref.read_text().strip() != revision:
            raise ValueError("已有 BGE main 引用不同；拒绝覆盖")
    else:
        with ref.open("x") as stream:
            stream.write(revision)
    print(json.dumps({"revision": revision, "files": manifest}, indent=2))


if __name__ == "__main__":
    main()
