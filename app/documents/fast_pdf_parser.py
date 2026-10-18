from pathlib import Path
from tempfile import NamedTemporaryFile

from app.rag.parse import parse_pdf
from app.rag.parse.models import DocChunk


def parse_fast_pdf_bytes(
    content: bytes,
    source_file: str,
) -> list[DocChunk]:
    """通过临时物理PDF调用fast parser，并恢复逻辑source_file。

    Args:
        content: 需要解析的原始PDF bytes。
        source_file: 写入返回chunks的逻辑展示文件名。

    Returns:
        source_file已经修正、尚未生成稳定chunk_id的解析块。

    Raises:
        OSError: 临时文件创建、写入或删除失败。
        Exception: fast parser无法解析PDF；由上层worker转换为安全失败。
    """
    temporary_path: Path | None = None

    try:
        with NamedTemporaryFile(delete=False, suffix=".pdf") as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(content)
            temporary_file.flush()

        chunks = parse_pdf(str(temporary_path), backend="fast")
        for chunk in chunks:
            chunk.source_file = source_file
        return chunks
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
