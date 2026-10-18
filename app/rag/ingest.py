import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from pymilvus import MilvusClient

from app.rag.parse.models import DocChunk

Embedder = Callable[[list[str]], list[list[float]]]

VERSIONED_EXPORT_FIELDS = frozenset(
    {
        "text",
        "page",
        "type",
        "source_file",
        "table_md",
        "section",
        "chunk_id",
        "workspace_id",
        "document_id",
        "data_version",
    }
)


@dataclass(frozen=True)
class JsonlWriteResult:
    """写入 JSONL 文件的结果。"""

    path: Path
    """写入的文件路径。"""
    row_count: int
    """写入的行数。"""
    byte_size: int
    """写入的文件大小。"""
    sha256: str
    """写入的文件 SHA-256 哈希。"""


def write_versioned_jsonl(path: Path, rows: list[dict[str, Any]]) -> JsonlWriteResult:
    """写入版本化的 JSONL 文件。

     Args:
         path: 写入的文件路径。
         rows: 要写入的行列表。

    Raises:
         ValueError: 输出路径或 rows 输入不符合合同。
         TypeError: 某个 row 包含不能序列化为 JSON 的值。
         OSError: 创建、同步或发布文件失败。
    """
    if not isinstance(path, Path):
        raise ValueError("path 必须是 Path")
    if path.exists() and not path.is_file():
        raise ValueError("path 已存在但不是普通文件")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("rows 必须是一个列表，且列表中的每个元素必须是字典")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None

    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            for row in rows:
                temporary_file.write(
                    json.dumps(row, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
                    + "\n"
                )
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        temporary_path.replace(path)
    finally:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)
    published_bytes = path.read_bytes()
    return JsonlWriteResult(
        path=path,
        row_count=len(rows),
        byte_size=len(published_bytes),
        sha256=hashlib.sha256(published_bytes).hexdigest(),
    )


def build_versioned_export_rows(
    chunks: list[DocChunk], *, workspace_id: str, document_id: str, data_version: str
) -> list[dict[str, Any]]:
    """把分块结果转换成带可信构建身份的 JSONL 行。

    Args:
        chunks: 已完成分块并具有稳定 chunk_id 的文档块。
        workspace_id: 当前构建使用的可信 workspace 身份。
        document_id: 当前源文档的稳定身份。
        data_version: 当前数据构建版本。

    Returns:
        不含 vector 的 JSONL 可序列化字典列表。

    Raises:
        ValueError: 构建身份为空，或者 chunk_id 为空或重复。
    """
    seen_chunk_ids: set[str] = set()
    if not isinstance(workspace_id, str) or not workspace_id.strip():
        raise ValueError("workspace_id 必须是非空字符串")
    if not isinstance(document_id, str) or not document_id.strip():
        raise ValueError("document_id 必须是非空字符串")
    if not isinstance(data_version, str) or not data_version.strip():
        raise ValueError("data_version 必须是非空字符串")
    rows = []
    for index, chunk in enumerate(chunks):
        if not chunk.chunk_id.strip():
            raise ValueError(f"chunks[{index}] 缺少有效 chunk_id")
        if chunk.chunk_id in seen_chunk_ids:
            raise ValueError(f"chunks[{index}] 的 chunk_id: {chunk.chunk_id} 重复")
        seen_chunk_ids.add(chunk.chunk_id)
        row = {
            "text": chunk.text,
            "page": chunk.page,
            "type": chunk.type,
            "source_file": chunk.source_file,
            "table_md": chunk.table_md,
            "section": chunk.section,
            "chunk_id": chunk.chunk_id,
            "workspace_id": workspace_id,
            "document_id": document_id,
            "data_version": data_version,
        }
        rows.append(row)
    return rows


@dataclass(frozen=True)
class ReplaceResult:
    inserted: int
    updated: int
    skipped: int
    final_ids: frozenset[str]


def build_aligned_rows(
    raw_chunks: list[dict[str, Any]],
    embedder: Embedder,
) -> list[dict[str, Any]]:
    """
    执行 adapter、chunk、可信 metadata 注入和向量对齐，返回 chunks 与 rows

    Args:
        raw_chunks: 原始分块结果。
        embedder: 向量嵌入器。

    Returns:
        list[dict[str, Any]]: 行列表。
    """
    legal_chunks: list[dict[str, Any]] = []
    for index, chunk in enumerate(raw_chunks):
        if "text" not in chunk:
            raise ValueError(f"raw_chunks[{index}] 缺少 text 字段")
        if chunk["text"] is None:
            raise ValueError(f"raw_chunks[{index}] 的 text 为空")
        text = chunk["text"]
        if not isinstance(text, str):
            raise ValueError(f"raw_chunks[{index}] 的 text 类型错误")
        if text.strip() == "":
            continue
        chunk_id = chunk.get("chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id.strip():
            raise ValueError(f"raw_chunks[{index}] 缺少有效 chunk_id")
        legal_chunks.append(chunk)

    texts = [chunk["text"] for chunk in legal_chunks]
    vectors = embedder(texts)

    if len(vectors) != len(legal_chunks):
        raise ValueError("vectors 长度与 legal_chunks 长度不一致")

    rows = [{**chunk, "vector": vector} for chunk, vector in zip(legal_chunks, vectors)]
    return rows


def load_versioned_jsonl(
    path: Path,
    *,
    expected_workspace_id: str,
    expected_document_id: str,
    expected_source_file: str,
    expected_data_version: str,
) -> list[dict[str, Any]]:
    """读取并验证已发布的 v2 JSONL，不修改磁盘行。

    Args:
        path: 已发布的 v2 JSONL 正式路径。
        expected_workspace_id: 当前可信 workspace 配置。
        expected_document_id: 当前文档固定身份。
        expected_source_file: 当前文档稳定源路径。
        expected_data_version: 当前冻结数据版本。

    Returns:
        按磁盘顺序排列、通过十字段和身份合同验证的行。

    Raises:
        FileNotFoundError: 正式 JSONL 文件不存在。
        ValueError: JSON 语法、字段、类型、身份、表格职责或 chunk_id 不符合合同。
    """
    if not isinstance(path, Path):
        raise ValueError("path 必须是 Path")
    if not path.is_file():
        raise FileNotFoundError(f"v2 JSONL 文件不存在: {path}")

    expected_identities = {
        "workspace_id": expected_workspace_id,
        "document_id": expected_document_id,
        "source_file": expected_source_file,
        "data_version": expected_data_version,
    }
    for field_name, expected_value in expected_identities.items():
        if not isinstance(expected_value, str) or not expected_value.strip():
            raise ValueError(f"expected_{field_name} 必须是非空字符串")
    rows: list[dict[str, Any]] = []
    seen_chunk_ids: set[str] = set()
    lines = path.read_text(encoding="utf-8").splitlines()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
            if not isinstance(parsed, dict):
                raise ValueError(f"{path} 第 {line_number} 行必须是 JSON Object")
            row: dict[str, Any] = parsed
            actual_fields = set(row)
            missing_fields = sorted(VERSIONED_EXPORT_FIELDS - actual_fields)
            extra_fields = sorted(actual_fields - VERSIONED_EXPORT_FIELDS)
            if missing_fields or extra_fields:
                raise ValueError(
                    f"{path} 第 {line_number} 行字段不符合 v2 合同：missing={missing_fields}, extra={extra_fields}"
                )
            text = row["text"]
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"{path} 第 {line_number} 行 text 必须是非空字符串")

            page = row["page"]
            if isinstance(page, bool) or not isinstance(page, int) or page < 1:
                raise ValueError(f"{path} 第 {line_number} 行 page 必须是正整数")

            row_type = row["type"]
            if not isinstance(row_type, str) or row_type not in {"paragraph", "table"}:
                raise ValueError(
                    f"{path} 第 {line_number} 行 type 必须是 paragraph 或 table，"
                    f"actual={row_type!r}"
                )

            if not isinstance(row["section"], str):
                raise ValueError(f"{path} 第 {line_number} 行 section 必须是字符串")

            chunk_id = row["chunk_id"]
            if not isinstance(chunk_id, str) or not chunk_id.strip():
                raise ValueError(f"{path} 第 {line_number} 行 chunk_id 必须是非空字符串")
            if chunk_id in seen_chunk_ids:
                raise ValueError(f"{path} 第 {line_number} 行 chunk_id 重复：{chunk_id}")

            seen_chunk_ids.add(chunk_id)

            if row_type == "table":
                table_md = row["table_md"]

                if not isinstance(table_md, str) or not table_md.strip():
                    raise ValueError(
                        f"{path} 第 {line_number} 行 table 的 table_md 必须是非空字符串"
                    )

                text_lower = text.lower()
                table_tags = (
                    "<table",
                    "<tr",
                    "<td",
                    "<th",
                    "</table>",
                    "</tr>",
                    "</td>",
                    "</th>",
                )

                if any(tag in text_lower for tag in table_tags):
                    raise ValueError(f"{path} 第 {line_number} 行 table 的 text 包含 HTML 标签")
            elif row["table_md"] is not None:
                raise ValueError(f"{path} 第 {line_number} 行 paragraph 的 table_md 必须是 null")

            for field_name, expected_value in expected_identities.items():
                actual_value = row[field_name]

                if actual_value != expected_value:
                    raise ValueError(
                        f"{path} 第 {line_number} 行 {field_name} 不一致："
                        f"expected={expected_value!r}, actual={actual_value!r}"
                    )

            rows.append(row)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path} 第 {line_number} 行不是合法 JSON: {exc}") from exc

    if not rows:
        raise ValueError(f"v2 JSONL 文件没有有效数据行：{path}")

    return rows


def replace_document_rows(
    client: MilvusClient, collection_name: str, document_id: str, rows: list[dict[str, Any]]
) -> ReplaceResult:
    """把一份已经通过预检的 JSONL rows 按一个稳定 document_id 替换进指定 collection
    Args:
        client: Milvus 客户端
        collection_name: 目标 collection 名称
        document_id: 目标文档固定身份
        rows: 已经通过预检的 JSONL rows
    Returns:
        ReplaceResult: 替换结果
    """
    if not isinstance(document_id, str) or not document_id.strip():
        raise ValueError("document_id 必须是非空字符串")

    expected_ids: set[str] = set()
    for row in rows:
        if row.get("chunk_id") is None:
            raise ValueError("row 缺少有效 chunk_id")

        chunk_id = row.get("chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id.strip():
            raise ValueError("row 的 chunk_id 类型错误")
        if chunk_id in expected_ids:
            raise ValueError("row 的 chunk_id 重复")
        expected_ids.add(chunk_id)

    new_rows = [{**row, "document_id": document_id} for row in rows]

    document_filter = f"document_id == {json.dumps(document_id)}"
    old_rows = client.query(
        collection_name=collection_name,
        filter=document_filter,
        output_fields=["chunk_id"],
    )
    old_ids = {row["chunk_id"] for row in old_rows}
    client.delete(
        collection_name=collection_name,
        filter=document_filter,
    )

    if new_rows:
        client.insert(
            collection_name=collection_name,
            data=new_rows,
        )

    actual_rows = client.query(
        collection_name=collection_name,
        filter=document_filter,
        output_fields=["chunk_id"],
    )
    actual_ids = {row["chunk_id"] for row in actual_rows}

    if actual_ids != expected_ids:
        raise RuntimeError(f"document最终ID集合错误：expected={expected_ids}, actual={actual_ids}")

    if len(actual_rows) != len(expected_ids):
        raise RuntimeError(
            f"document最终行数错误：expected={len(expected_ids)}, actual={len(actual_rows)}"
        )

    stale_ids = old_ids - expected_ids

    if stale_ids:
        leftovers = client.get(
            collection_name=collection_name,
            ids=list(stale_ids),
            output_fields=["chunk_id"],
        )
        if leftovers:
            raise RuntimeError(f"旧chunk仍然存在：{stale_ids}")

    return ReplaceResult(
        inserted=len(new_rows),
        updated=0,
        skipped=0,
        final_ids=frozenset(actual_ids),
    )
