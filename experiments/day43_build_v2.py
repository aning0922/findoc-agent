from pathlib import Path
from pydantic import BaseModel

from app.rag.chunk import chunk_docment
from app.rag.ingest import build_versioned_export_rows, write_versioned_jsonl
from app.rag.parse.mineru_adapter import parse_mineru_output
import json

from experiments.day43_config import (
    BUILD_ID,
    DEMO_WORKSPACE_ID,
    REAL_DOCUMENTS,
)


class DocumentJsonlBuildResult(BaseModel):
    """记录单份文档从 MinerU 输入到版本化 JSONL 的可审计构建结果。"""

    source_file: str
    document_id: str
    content_list_file: Path
    output_jsonl: Path
    parsed_block_count: int
    final_chunk_count: int
    skipped_element_count: int
    byte_size: int
    sha256: str


def build_document_jsonl(
    *,
    source_file: str,
    document_id: str,
    content_list_file: Path,
    output_jsonl: Path,
    workspace_id: str,
    data_version: str,
) -> DocumentJsonlBuildResult:
    """
    完成一份文档的解析、分块、导出为 JSONL 文件的完整流程
    Args:
        source_file: 源文件路径
        document_id: 文档ID
        content_list_file: 内容列表文件路径
        output_jsonl: 输出JSONL文件路径
        workspace_id: 工作空间ID
        data_version: 数据版本
    Returns:
        DocumentJsonlBuildResult: 构建结果
    """
    if not content_list_file.is_file():
        raise FileNotFoundError(f"MinerU content_list 文件不存在：{content_list_file}")

    if not content_list_file.name.endswith("_content_list.json"):
        raise ValueError("content_list_file 必须指向 *_content_list.json 文件")

    matches = sorted(content_list_file.parent.rglob("*_content_list.json"))
    if len(matches) != 1 or matches[0] != content_list_file:
        raise ValueError(
            "content_list_file 所在目录必须能唯一定位当前 MinerU 输入："
            f"expected={content_list_file}, matches={matches}"
        )

    parsed_result = parse_mineru_output(str(content_list_file.parent), source_file)
    final_chunks = chunk_docment(parsed_result.chunks)
    export_rows = build_versioned_export_rows(
        final_chunks,
        workspace_id=workspace_id,
        document_id=document_id,
        data_version=data_version,
    )

    final_chunk_count = len(final_chunks)
    if final_chunk_count != len(export_rows):
        raise RuntimeError("最终块数与导出行数不一致")

    jsonl_result = write_versioned_jsonl(path=output_jsonl, rows=export_rows)

    if final_chunk_count != jsonl_result.row_count:
        raise RuntimeError("最终块数与写入行数不一致")
    return DocumentJsonlBuildResult(
        source_file=source_file,
        document_id=document_id,
        content_list_file=content_list_file,
        output_jsonl=output_jsonl,
        parsed_block_count=len(parsed_result.chunks),
        final_chunk_count=final_chunk_count,
        skipped_element_count=parsed_result.stats.skipped_element_count,
        byte_size=jsonl_result.byte_size,
        sha256=jsonl_result.sha256,
    )


def build_all_document_jsonls() -> list[DocumentJsonlBuildResult]:
    """按照冻结配置依次构建三份真实文档的 v2 JSONL。

    Returns:
        按 REAL_DOCUMENTS 配置顺序排列的单文档构建结果。

    Raises:
        原始解析、分块、身份注入或文件写入异常直接向上抛出。
        RuntimeError: 构建结果数量与配置文档数量不一致。

    Limitations:
        本函数不生成 embedding、不写 manifest，也不访问 Milvus。
    """
    results: list[DocumentJsonlBuildResult] = []
    for document in REAL_DOCUMENTS:
        result = build_document_jsonl(
            source_file=document["source_file"],
            document_id=document["document_id"],
            content_list_file=document["content_list_file"],
            output_jsonl=document["output_jsonl"],
            workspace_id=DEMO_WORKSPACE_ID,
            data_version=BUILD_ID,
        )
        results.append(result)
    if len(results) != len(REAL_DOCUMENTS):
        raise RuntimeError(
            "批次构建结果数与配置文档数不一致："
            f"expected={len(REAL_DOCUMENTS)}, actual={len(results)}"
        )
    return results


def main() -> int:
    """构建三份真实 v2 JSONL，打印可审计结果，并在全部成功后返回退出码 0。"""
    results = build_all_document_jsonls()

    print(
        json.dumps(
            [result.model_dump(mode="json") for result in results], ensure_ascii=False, indent=2
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
