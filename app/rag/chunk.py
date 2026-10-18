from langchain_text_splitters import RecursiveCharacterTextSplitter
import tiktoken
from pathlib import Path
from .parse.models import DocChunk
import hashlib
import json

CHUNK_SIZE = 400
CHUNK_OVERLAP = 60
CHINESE_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", "，", "、", " ", ""]

_enc = tiktoken.get_encoding("cl100k_base")
_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
    encoding_name="cl100k_base",
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=CHINESE_SEPARATORS,
)


def count_tokens(text: str) -> int:
    """
    计算文本 token 数量
    Args:
        text: 文本
    Returns:
        int: token 数量
    """
    return len(_enc.encode(text))


def recursive_chunk(text: str) -> list[str]:
    """
    递归按中文分隔符分块， 用 token 计数保证分块大小
    Args:
        text: 文本
    Returns:
        list[str]: 分块列表
    """
    return _splitter.split_text(text)


def recursive_chunk_char(text: str, size: int = 500, overlap: int = 80) -> list[str]:
    """
    递归按中文分隔符分块，一定程度上保证语义完整
    Args:
        text: 文本
        size: 分块大小
        overlap: 重叠部分大小
    Returns:
        list[str]: 分块列表
    """
    sp = RecursiveCharacterTextSplitter(
        chunk_size=size,
        chunk_overlap=overlap,
        separators=CHINESE_SEPARATORS,
    )
    return sp.split_text(text)


def fixed_chunk(text: str, size: int = 500, overlap: int = 80) -> list[str]:
    """
    固定大小分块，不保证语义完整
    Args:
        text: 文本
        size: 分块大小
        overlap: 重叠部分大小
    Returns:
        list[str]: 分块列表
    """
    if size <= overlap:
        raise ValueError("size 必须 > overlap，否则死循环")
    chunks: list[str] = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + size])
        start += size - overlap
    return chunks

def build_stable_chunk_id(chunk: DocChunk, source_locator: str) -> str:
    """
    根据chunk和source_locator生成稳定ID
    """
    data_dict = {
        "source_locator": source_locator,
        "source_file": chunk.source_file,
        "page": chunk.page,
        "text": chunk.text,
        "section": chunk.section,
        "type": chunk.type,
        "table_md": chunk.table_md,
    }
    json_data = json.dumps(data_dict, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(json_data.encode("utf-8")).hexdigest()

def chunk_docment(blocks: list[DocChunk]) -> list[DocChunk]:
    """
    将文档块分块 按标题、表格、段落分块
    标题、表格、段落块直接使用，其他块使用递归分块
    Args:
        blocks: 文档块列表
    Returns:
        list[DocChunk]: 分块后的文档块列表
    """
    chunk_payload_map: dict[str, int] = {}

    def build_chunk_payload(chunk: DocChunk) -> str:
        """
        构建chunk的唯一标识payload
        """
        data = {
            "text": chunk.text,
            "page": chunk.page,
            "section": chunk.section,
            "type": chunk.type,
            "source_file": chunk.source_file,
            "table_md": chunk.table_md,
        }
        json_data = json.dumps(data, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(json_data.encode("utf-8")).hexdigest()

    def get_chunk_payload_idx(payload: str) -> int:
        """
        获取chunk的唯一标识payload的索引
        """
        if payload in chunk_payload_map:
            idx = chunk_payload_map[payload]
            chunk_payload_map[payload] += 1
            return idx
        chunk_payload_map[payload] = 1
        return 0

    out: list[DocChunk] = []
    for b in blocks:
        if b.type == "title":
            continue
        if b.type == "table":
            pieces = [b.text]
        else:
            pieces = recursive_chunk(b.text)
        for piece in pieces:
            chunk = DocChunk(
                text=piece,
                page=b.page,
                type=b.type,
                source_file=b.source_file,
                table_md=b.table_md,
                section=b.section or "未分节",
            )
            payload = build_chunk_payload(chunk)
            idx = get_chunk_payload_idx(payload)
            chunk_id = build_stable_chunk_id(chunk, str(idx))
            chunk.chunk_id = chunk_id
            out.append(chunk)
    return out


def save_chunks(chunks: list[DocChunk], path: str = "chunks.jsonl") -> None:
    """
    保存分块结果到 jsonl 文件
    Args:
        chunks: 文档块列表
        path: 保存路径
    """
    with Path(path).open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(c.model_dump_json() + "\n")
