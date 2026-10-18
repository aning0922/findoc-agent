"""Day43 数据 v2 的真实重建、收敛验证和 manifest 发布入口。

职责：
1. 对三份真实 MinerU 输入执行生产 smoke。
2. 重建三份版本化 JSONL，并确认文件 SHA-256 与上次构建一致。
3. 使用冻结 embedding 合同按 document_id 重建 v2 collection。
4. 生成、原子写入并重新加载 manifest。
5. 确认 legacy collection 未被修改。

限制：
不做 RAG 答案生成，不修改检索参数，不运行 12 题评测。
"""

import hashlib
import json
from pathlib import Path
from typing import Any

from experiments.day43_build_v2 import (
    DocumentJsonlBuildResult,
    build_all_document_jsonls,
)
from experiments.day43_config import (
    BUILD_ID,
    DEMO_WORKSPACE_ID,
    LEGACY_COLLECTION_NAME,
    MANIFEST_PATH,
    MILVUS_DB_PATH,
    PROJECT_ROOT,
    REAL_DOCUMENTS,
    V2_COLLECTION_NAME,
)
from experiments.day43_load_v2_collection import (
    V2CollectionBuildResult,
    build_v2_collection,
)
from experiments.day43_manifest import (
    ManifestWriteResult,
    build_v2_manifest,
    load_v2_manifest,
    write_v2_manifest,
)
from experiments.day43_real_data_smoke import (
    build_document_smoke_report,
)


def _calculate_file_sha256(path: Path) -> str:
    """计算现有文件的 SHA-256 摘要。

    Args:
        path: 必须已经存在的普通文件。

    Returns:
        文件全部字节的 64 位小写 SHA-256 摘要。

    Raises:
        FileNotFoundError: 文件不存在或不是普通文件。
        OSError: 文件读取失败。

    Limitations:
        本函数只读文件，不修改文件内容。
    """
    if not path.is_file():
        raise FileNotFoundError(f"收敛验证要求已有版本化 JSONL：{path}")

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot_existing_jsonl_sha256() -> dict[str, str]:
    """记录第二次重建前的三份版本化 JSONL 摘要。

    Returns:
        以 document_id 为键、当前 JSONL SHA-256 为值的字典。

    Raises:
        ValueError: REAL_DOCUMENTS 中 document_id 重复。
        FileNotFoundError: 任意已发布 JSONL 不存在。

    Limitations:
        本函数不解析 JSONL，只记录重建前的文件字节摘要。
    """
    sha256_by_document_id: dict[str, str] = {}

    for document in REAL_DOCUMENTS:
        document_id = document["document_id"]

        if document_id in sha256_by_document_id:
            raise ValueError(f"REAL_DOCUMENTS 中 document_id 重复：{document_id}")

        sha256_by_document_id[document_id] = _calculate_file_sha256(document["output_jsonl"])

    return sha256_by_document_id


def _validate_jsonl_rebuild_convergence(
    before_sha256: dict[str, str],
    jsonl_results: list[DocumentJsonlBuildResult],
) -> None:
    """验证相同真实输入重建后，三份 JSONL 的字节摘要没有变化。

    Args:
        before_sha256: 重建前按 document_id 记录的文件摘要。
        jsonl_results: 本次真实重建产生的单文档结果。

    Raises:
        RuntimeError: 文档身份集合发生变化，或者任意 JSONL 摘要变化。

    Limitations:
        本函数只比较构建前后的结果，不写文件、不访问 Milvus。
    """
    after_sha256: dict[str, str] = {}

    for result in jsonl_results:
        if result.document_id in after_sha256:
            raise RuntimeError(f"JSONL 重建结果中 document_id 重复：{result.document_id}")

        after_sha256[result.document_id] = result.sha256

    before_document_ids = set(before_sha256)
    after_document_ids = set(after_sha256)

    if before_document_ids != after_document_ids:
        raise RuntimeError(
            "JSONL 重建前后的 document_id 集合不一致："
            f"missing_after="
            f"{sorted(before_document_ids - after_document_ids)}, "
            f"unexpected_after="
            f"{sorted(after_document_ids - before_document_ids)}"
        )

    changed_documents = {
        document_id: {
            "before": before_sha256[document_id],
            "after": after_sha256[document_id],
        }
        for document_id in sorted(before_document_ids)
        if (before_sha256[document_id] != after_sha256[document_id])
    }

    if changed_documents:
        raise RuntimeError(f"相同输入重建后的 JSONL SHA-256 发生变化：{changed_documents}")


def _run_real_smoke_reports() -> list[dict[str, object]]:
    """执行三份真实 MinerU 输入的只读质量检查。

    Returns:
        按 REAL_DOCUMENTS 顺序排列的真实 smoke 报告。

    Raises:
        RuntimeError: 任意真实文档 smoke 未通过。
        原始文件读取或生产解析异常直接向上抛出。

    Limitations:
        本函数不写 JSONL、不生成 embedding，也不访问 Milvus。
    """
    reports: list[dict[str, object]] = []

    for document in REAL_DOCUMENTS:
        report = build_document_smoke_report(
            document["source_file"],
            document["content_list_file"],
        )

        if report.get("passed") is not True:
            raise RuntimeError(
                "真实数据 smoke 未通过："
                f"source_file={document['source_file']}, "
                f"failure_reasons="
                f"{report.get('failure_reasons')}"
            )

        reports.append(report)

    return reports


def publish_day43_v2() -> dict[str, Any]:
    """重建 Day43 v2 数据并发布可重新验证的 manifest。

    Returns:
        本次真实发布的收敛、collection 和 manifest 摘要。

    Raises:
        RuntimeError: smoke、JSONL 收敛、collection 构建或 manifest
            重新加载结果不符合冻结合同。
        其他输入、文件、embedding 或 Milvus 异常直接向上抛出。

    Failure behavior:
        manifest 是最后一步发布；此前任何步骤失败都不会覆盖已有
        manifest。JSONL 使用原子替换，collection 使用 document 级替换。
    """
    before_sha256 = _snapshot_existing_jsonl_sha256()

    smoke_reports = _run_real_smoke_reports()

    jsonl_results = build_all_document_jsonls()

    _validate_jsonl_rebuild_convergence(
        before_sha256,
        jsonl_results,
    )

    collection_result: V2CollectionBuildResult = build_v2_collection()

    manifest = build_v2_manifest(
        jsonl_results=jsonl_results,
        collection_result=collection_result,
        smoke_reports=smoke_reports,
        build_id=BUILD_ID,
        workspace_id=DEMO_WORKSPACE_ID,
        database_path=MILVUS_DB_PATH,
        legacy_collection_name=LEGACY_COLLECTION_NAME,
        project_root=PROJECT_ROOT,
    )

    manifest_write_result: ManifestWriteResult = write_v2_manifest(
        MANIFEST_PATH,
        manifest,
    )

    expected_document_ids = {document["document_id"] for document in REAL_DOCUMENTS}

    loaded_manifest = load_v2_manifest(
        MANIFEST_PATH,
        project_root=PROJECT_ROOT,
        expected_build_id=BUILD_ID,
        expected_workspace_id=DEMO_WORKSPACE_ID,
        expected_collection_name=V2_COLLECTION_NAME,
        expected_document_ids=expected_document_ids,
    )

    if loaded_manifest != manifest:
        raise RuntimeError("重新加载的 manifest 与发布前内存对象不一致")

    return {
        "build_id": BUILD_ID,
        "workspace_id": DEMO_WORKSPACE_ID,
        "jsonl_rebuild_converged": True,
        "document_count": len(jsonl_results),
        "jsonl_row_count": sum(result.final_chunk_count for result in jsonl_results),
        "collection_name": (collection_result.collection_name),
        "collection_row_count": (collection_result.actual_collection_row_count),
        "legacy_row_count_before": (collection_result.legacy_row_count_before),
        "legacy_row_count_after": (collection_result.legacy_row_count_after),
        "manifest_path": str(manifest_write_result.path),
        "manifest_byte_size": (manifest_write_result.byte_size),
        "manifest_sha256": (manifest_write_result.sha256),
        "manifest_reloaded": True,
    }


def main() -> int:
    """执行真实 v2 发布并打印最终审计摘要。"""
    result = publish_day43_v2()

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
