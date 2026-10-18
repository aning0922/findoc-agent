import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from app.rag.ingest import load_versioned_jsonl
from experiments.day43_build_v2 import DocumentJsonlBuildResult
from experiments.day43_load_v2_collection import (
    DocumentCollectionLoadResult,
    V2CollectionBuildResult,
)


@dataclass(frozen=True)
class ManifestWriteResult:
    """记录版本化 manifest 原子写入后的文件审计结果。

    Attributes:
        path: 实际发布的 manifest 文件路径。
        byte_size: 最终 manifest 的 UTF-8 字节数。
        sha256: 最终 manifest 文件字节的 SHA-256 摘要。
    """

    path: Path
    byte_size: int
    sha256: str


def _require_manifest_dict(
    container: dict[str, Any],
    field_name: str,
    *,
    manifest_path: Path,
) -> dict[str, Any]:
    """读取 manifest 中必须为字典的字段。

    Args:
        container: 当前包含目标字段的父级字典。
        field_name: 要读取的字段名称。
        manifest_path: 当前 manifest 文件路径，仅用于错误定位。

    Returns:
        通过类型检查的字段字典。

    Raises:
        ValueError: 字段缺失或者字段值不是字典。

    Limitations:
        本函数只检查一层容器类型，不验证字典内部业务字段。
    """
    value = container.get(field_name)

    if not isinstance(value, dict):
        raise ValueError(f"{manifest_path} 的 {field_name} 必须是字典")

    return value


def _require_nonnegative_int(
    value: object,
    field_path: str,
    *,
    manifest_path: Path,
) -> int:
    """验证 manifest 中的计数值是非负整数。

    Args:
        value: 待验证的计数值。
        field_path: 字段在 manifest 中的可读路径，用于错误定位。
        manifest_path: 当前 manifest 文件路径。

    Returns:
        通过检查的整数值。

    Raises:
        ValueError: 值是 bool、不是 int 或者小于零。

    Limitations:
        本函数只检查整数合同，不判断多个计数之间是否守恒。
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{manifest_path} 的 {field_path} 必须是非负整数")

    return value


def _serialize_manifest_path(
    path: str | Path,
    *,
    project_root: Path | None,
) -> str:
    """把项目内路径转换成稳定的仓库相对 POSIX 字符串。

    Args:
        path: 待写入 manifest 的绝对路径或仓库相对路径。
        project_root: 仓库根目录；转换绝对路径时必须提供。

    Returns:
        使用正斜杠的仓库相对路径字符串。

    Raises:
        ValueError: 绝对路径不在项目内、缺少 project_root，
            或相对路径尝试通过 `..` 越出项目目录。

    Limitations:
        本函数不检查目标文件是否存在，也不读取文件内容。
    """
    manifest_path = Path(path)

    if manifest_path.is_absolute():
        if project_root is None:
            raise ValueError("序列化绝对路径时必须提供 project_root")

        resolved_root = project_root.resolve()

        try:
            relative_path = manifest_path.resolve().relative_to(resolved_root)
        except ValueError as exc:
            raise ValueError(f"path={manifest_path} 不在 project_root={resolved_root} 内") from exc
    else:
        relative_path = manifest_path

    if ".." in relative_path.parts:
        raise ValueError(f"path={manifest_path} 不能通过 '..' 越出项目目录")

    return relative_path.as_posix()


def _aggregate_quality_checks(
    smoke_by_source_file: dict[str, dict[str, object]],
    *,
    global_chunk_id_count: int,
    expected_total_row_count: int,
) -> dict[str, Any]:
    """验证并汇总所有真实文档的表格与 section 质量统计。

    Args:
        smoke_by_source_file: 以 source_file 为键的真实数据 smoke 报告。
        global_chunk_id_count: 批次预检得到的全局唯一 chunk_id 数量。
        expected_total_row_count: 三份 JSONL 的预期总行数。

    Returns:
        可以直接写入 manifest 的质量检查结果。

    Raises:
        ValueError: smoke 未通过、缺陷计数不是非负整数、
            全局唯一 ID 数与总行数不一致，或者仍存在质量缺陷。

    Limitations:
        本函数不重新扫描 MinerU 文件，也不读取 JSONL 或 Milvus。
    """
    if (
        isinstance(global_chunk_id_count, bool)
        or not isinstance(global_chunk_id_count, int)
        or global_chunk_id_count < 0
    ):
        raise ValueError("global_chunk_id_count 必须是非负整数")

    if global_chunk_id_count != expected_total_row_count:
        raise ValueError(
            "全局唯一 chunk_id 数与预期总行数不一致："
            f"chunk_ids={global_chunk_id_count}, "
            f"expected_rows={expected_total_row_count}"
        )

    quality_field_names = (
        "degraded_table_text_count",
        "html_in_table_text_count",
        "missing_table_md_count",
        "table_md_mismatch_count",
        "section_pollution_count",
    )
    totals = {field_name: 0 for field_name in quality_field_names}

    for source_file, report in smoke_by_source_file.items():
        if report.get("passed") is not True:
            raise ValueError(f"smoke_report[{source_file}] 的 passed 必须严格为 True")

        for field_name in quality_field_names:
            value = report.get(field_name)

            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"smoke_report[{source_file}] 的 {field_name} 必须是非负整数")

            totals[field_name] += value

    nonzero_defects = {field_name: value for field_name, value in totals.items() if value != 0}
    if nonzero_defects:
        raise ValueError(f"真实数据 smoke 仍存在质量缺陷：{nonzero_defects}")

    return {
        "global_chunk_ids_unique": True,
        "document_ids_unique": True,
        **totals,
    }


def _index_smoke_reports_by_source_file(
    smoke_reports: list[dict[str, object]],
    expected_source_files: set[str],
) -> dict[str, dict[str, object]]:
    """按 source_file 建立唯一的真实数据 smoke 报告索引。

    Args:
        smoke_reports: 每份真实源文档的 smoke 质量报告。
        expected_source_files: JSONL 构建结果中的完整源文件集合。

    Returns:
        以 source_file 为键的 smoke 报告字典。

    Raises:
        ValueError: 报告为空、报告结构错误、source_file 重复，
            或报告中的源文件集合与 JSONL 构建结果不一致。

    Limitations:
        本函数不执行真实 smoke，只验证已有报告的身份集合。
    """
    if not smoke_reports:
        raise ValueError("smoke_reports 不能为空")

    smoke_by_source_file: dict[str, dict[str, object]] = {}

    for index, smoke_report in enumerate(smoke_reports):
        if not isinstance(smoke_report, dict):
            raise ValueError(f"smoke_reports[{index}] 必须是字典")

        source_file = smoke_report.get("source_file")

        if not isinstance(source_file, str) or not source_file.strip():
            raise ValueError(f"smoke_reports[{index}] 的 source_file 必须是非空字符串")

        if source_file in smoke_by_source_file:
            raise ValueError(f"smoke_reports 中 source_file 重复：{source_file}")

        smoke_by_source_file[source_file] = smoke_report

    actual_source_files = set(smoke_by_source_file)

    if actual_source_files != expected_source_files:
        missing_reports = sorted(expected_source_files - actual_source_files)
        unexpected_reports = sorted(actual_source_files - expected_source_files)
        raise ValueError(
            "smoke 报告的 source_file 集合与 JSONL 结果不一致："
            f"missing={missing_reports}, "
            f"unexpected={unexpected_reports}"
        )

    return smoke_by_source_file


def _validate_sha256(
    value: object,
    document_id: str,
) -> str:
    """验证并返回合法的 JSONL SHA-256 字符串。

    Args:
        value: 待验证的 JSONL 摘要。
        document_id: 当前文档身份，仅用于错误定位。

    Returns:
        通过验证的 64 位小写十六进制摘要。

    Raises:
        ValueError: 摘要不是合法的小写 SHA-256 字符串。

    Limitations:
        本函数只检查摘要格式，不读取文件，也不重新计算摘要。
    """
    if not isinstance(value, str):
        raise ValueError(f"document_id={document_id} 的 jsonl_sha256 必须是字符串")

    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(
            f"document_id={document_id} 的 jsonl_sha256 必须是 64 位小写十六进制字符串"
        )

    return value


def _build_manifest_document(
    jsonl_result: DocumentJsonlBuildResult,
    collection_document_result: DocumentCollectionLoadResult,
    *,
    project_root: Path | None,
) -> dict[str, Any]:
    """合并并校验同一 document_id 的 JSONL 和 Milvus 构建结果。

    Args:
        jsonl_result: 单文档 JSONL 构建审计结果。
        collection_document_result: 同一文档写入 collection 后的审计结果。
        project_root: 用于把绝对路径转换成仓库相对路径。

    Returns:
        一条可写入 manifest documents 数组的文档记录。

    Raises:
        ValueError: 文档身份、源文件、JSONL 路径、四阶段行数、
            文件字节数或 SHA-256 不符合合同。

    Limitations:
        本函数不读取 JSONL 文件，也不访问 Milvus。
    """
    if jsonl_result.document_id != collection_document_result.document_id:
        raise ValueError(
            "关联后的 document_id 不一致："
            f"jsonl={jsonl_result.document_id}, "
            f"collection={collection_document_result.document_id}"
        )

    if jsonl_result.source_file != collection_document_result.source_file:
        raise ValueError(
            "关联后的 source_file 不一致："
            f"document_id={jsonl_result.document_id}, "
            f"jsonl={jsonl_result.source_file}, "
            f"collection={collection_document_result.source_file}"
        )

    jsonl_output_path = _serialize_manifest_path(
        jsonl_result.output_jsonl,
        project_root=project_root,
    )
    collection_jsonl_path = _serialize_manifest_path(
        collection_document_result.jsonl_path,
        project_root=project_root,
    )

    if jsonl_output_path != collection_jsonl_path:
        raise ValueError(
            "关联后的 JSONL 路径不一致："
            f"document_id={jsonl_result.document_id}, "
            f"jsonl={jsonl_output_path}, "
            f"collection={collection_jsonl_path}"
        )

    final_chunk_count = jsonl_result.final_chunk_count
    jsonl_row_count = collection_document_result.jsonl_row_count
    embedded_row_count = collection_document_result.embedded_row_count
    final_document_row_count = collection_document_result.final_document_row_count

    row_counts = {
        "final_chunk_count": final_chunk_count,
        "jsonl_row_count": jsonl_row_count,
        "embedded_row_count": embedded_row_count,
        "final_document_row_count": final_document_row_count,
    }

    for field_name, value in row_counts.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(
                f"document_id={jsonl_result.document_id} 的 {field_name} 必须是非负整数"
            )

    if len(set(row_counts.values())) != 1:
        raise ValueError(
            "文档行数不守恒："
            f"document_id={jsonl_result.document_id}, "
            f"final_chunk_count={final_chunk_count}, "
            f"jsonl_row_count={jsonl_row_count}, "
            f"embedded_row_count={embedded_row_count}, "
            f"final_document_row_count={final_document_row_count}"
        )

    if (
        isinstance(jsonl_result.byte_size, bool)
        or not isinstance(jsonl_result.byte_size, int)
        or jsonl_result.byte_size <= 0
    ):
        raise ValueError(f"document_id={jsonl_result.document_id} 的 jsonl_byte_size 必须是正整数")

    validated_sha256 = _validate_sha256(
        jsonl_result.sha256,
        jsonl_result.document_id,
    )

    return {
        "source_file": jsonl_result.source_file,
        "content_list_file": _serialize_manifest_path(
            jsonl_result.content_list_file,
            project_root=project_root,
        ),
        "output_jsonl": jsonl_output_path,
        "document_id": jsonl_result.document_id,
        "jsonl_row_count": jsonl_row_count,
        "embedded_row_count": embedded_row_count,
        "final_document_row_count": final_document_row_count,
        "jsonl_byte_size": jsonl_result.byte_size,
        "jsonl_sha256": validated_sha256,
    }


def _validate_collection_totals(
    collection_result: V2CollectionBuildResult, expected_document_count: int
) -> None:
    """验证 collection 构建结果的合同合规性。

    Args:
        collection_result: collection 构建结果。
        expected_document_count: JSONL 文档数。

    Raises:
        ValueError: 合同违规、行数不守恒、文档数不一致、或 legacy 行数变化。

    Limitations:
        本函数不读取 Milvus，只验证合同合规性。
    """
    if not collection_result.collection_name.strip():
        raise ValueError("collection_result.collection_name 是空字符串")
    if not collection_result.embedding_model.strip():
        raise ValueError("collection_result.embedding_model 是空字符串")
    if (
        isinstance(collection_result.vector_dim, bool)
        or not isinstance(collection_result.vector_dim, int)
        or collection_result.vector_dim <= 0
    ):
        raise ValueError("collection_result.vector_dim 必须是正整数")
    if (
        not collection_result.metric_type.strip()
        or collection_result.metric_type.strip().upper() != "COSINE"
    ):
        raise ValueError("collection_result.metric_type 必须是 COSINE")
    if (
        isinstance(collection_result.expected_total_row_count, bool)
        or not isinstance(collection_result.expected_total_row_count, int)
        or collection_result.expected_total_row_count < 0
    ):
        raise ValueError("collection_result.expected_total_row_count 必须是非负整数")
    if (
        isinstance(collection_result.actual_collection_row_count, bool)
        or not isinstance(collection_result.actual_collection_row_count, int)
        or collection_result.actual_collection_row_count < 0
    ):
        raise ValueError("collection_result.actual_collection_row_count 必须是非负整数")

    if (
        isinstance(collection_result.global_chunk_id_count, bool)
        or not isinstance(collection_result.global_chunk_id_count, int)
        or collection_result.global_chunk_id_count < 0
    ):
        raise ValueError("collection_result.global_chunk_id_count 必须是非负整数")

    if collection_result.global_chunk_id_count != collection_result.expected_total_row_count:
        raise ValueError(
            "全局唯一 chunk_id 数与预期总行数不一致："
            f"chunk_ids={collection_result.global_chunk_id_count}, "
            "expected_rows="
            f"{collection_result.expected_total_row_count}"
        )

    if collection_result.actual_collection_row_count != collection_result.expected_total_row_count:
        raise ValueError(
            f"collection_result.actual_collection_row_count 和 collection_result.expected_total_row_count 不一致：expected={collection_result.expected_total_row_count}, actual={collection_result.actual_collection_row_count}"
        )
    if len(collection_result.document_results) != expected_document_count:
        raise ValueError("collection 文档结果数与 JSONL 文档数不一致")

    if (
        isinstance(collection_result.legacy_row_count_before, bool)
        or not isinstance(collection_result.legacy_row_count_before, int)
        or collection_result.legacy_row_count_before < 0
    ):
        raise ValueError("collection_result.legacy_row_count_before 必须是非负整数")
    if (
        isinstance(collection_result.legacy_row_count_after, bool)
        or not isinstance(collection_result.legacy_row_count_after, int)
        or collection_result.legacy_row_count_after < 0
    ):
        raise ValueError("collection_result.legacy_row_count_after 必须是非负整数")

    if collection_result.legacy_row_count_before != collection_result.legacy_row_count_after:
        raise ValueError(
            f"legacy collection 在 v2 构建期间发生变化 before={collection_result.legacy_row_count_before}, after={collection_result.legacy_row_count_after}"
        )

    document_final_total = sum(
        result.final_document_row_count for result in collection_result.document_results
    )
    if document_final_total != collection_result.actual_collection_row_count:
        raise ValueError("各 document 最终行数之和与 collection 实际总行数不一致")


def _index_unique_by_document_id(results: list[Any], result_label: str) -> dict[str, Any]:
    """
    将一个列表中的元素按 document_id 索引，确保 document_id 唯一且不为空。
    """
    results_by_document_id: dict[str, Any] = {}
    for index, result in enumerate(results):
        document_id = result.document_id
        if not isinstance(document_id, str):
            raise ValueError(f"{result_label}[{index}] 的 document_id 必须是字符串")
        if document_id.strip() == "":
            raise ValueError(f"{result_label}[{index}] 的 document_id 不能为空")
        if document_id in results_by_document_id:
            raise ValueError(f"{result_label} 中 document_id 重复：{document_id}")
        results_by_document_id[document_id] = result
    return results_by_document_id


def build_v2_manifest(
    jsonl_results: list[DocumentJsonlBuildResult],
    collection_result: V2CollectionBuildResult,
    smoke_reports: list[dict[str, object]],
    build_id: str,
    workspace_id: str,
    database_path: Path,
    legacy_collection_name: str,
    *,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """组装并验证 Day43 v2 数据发布 manifest。

    Args:
        jsonl_results: 每份文档的版本化 JSONL 构建结果。
        collection_result: 整个 v2 collection 的构建审计结果。
        smoke_reports: 每份真实源文档的只读质量检查报告。
        build_id: 本次数据构建版本。
        workspace_id: 三份演示文档共用的固定 workspace 身份。
        database_path: Milvus Lite 数据库路径。
        legacy_collection_name: 本次构建明确保护的旧 collection 名。
        project_root: 仓库根目录，用于把绝对路径转成仓库相对路径。

    Returns:
        经过身份、行数、文件指纹和质量合同验证的 manifest 字典。

    Raises:
        ValueError: 顶层参数、文档身份、路径、行数、文件指纹、
            legacy 保护结果或真实数据质量不符合合同。

    Limitations:
        本函数不写 manifest 文件、不读取 JSONL、不生成 embedding，
        也不访问 Milvus。
    """
    if not jsonl_results:
        raise ValueError("jsonl_results 不能为空")

    if not isinstance(build_id, str) or not build_id.strip():
        raise ValueError("build_id 必须是非空字符串")

    if not isinstance(workspace_id, str) or not workspace_id.strip():
        raise ValueError("workspace_id 必须是非空字符串")

    if not isinstance(legacy_collection_name, str) or not legacy_collection_name.strip():
        raise ValueError("legacy_collection_name 必须是非空字符串")

    jsonl_by_document_id = _index_unique_by_document_id(
        jsonl_results,
        "jsonl_results",
    )
    collection_by_document_id = _index_unique_by_document_id(
        list(collection_result.document_results),
        "collection_result.document_results",
    )

    jsonl_ids = set(jsonl_by_document_id)
    collection_ids = set(collection_by_document_id)

    if jsonl_ids != collection_ids:
        missing_in_collection = sorted(jsonl_ids - collection_ids)
        unexpected_in_collection = sorted(collection_ids - jsonl_ids)

        raise ValueError(
            "JSONL 与 collection 的 document_id 集合不一致："
            f"missing_in_collection={missing_in_collection}, "
            "unexpected_in_collection="
            f"{unexpected_in_collection}"
        )

    _validate_collection_totals(
        collection_result,
        expected_document_count=len(jsonl_by_document_id),
    )

    source_files = [result.source_file for result in jsonl_results]
    if len(source_files) != len(set(source_files)):
        raise ValueError("不同 document_id 不能共用同一个 source_file")

    smoke_by_source_file = _index_smoke_reports_by_source_file(
        smoke_reports,
        expected_source_files=set(source_files),
    )

    documents: list[dict[str, Any]] = []

    for jsonl_result in jsonl_results:
        collection_document_result = collection_by_document_id[jsonl_result.document_id]

        documents.append(
            _build_manifest_document(
                jsonl_result,
                collection_document_result,
                project_root=project_root,
            )
        )

    quality_checks = _aggregate_quality_checks(
        smoke_by_source_file,
        global_chunk_id_count=(collection_result.global_chunk_id_count),
        expected_total_row_count=(collection_result.expected_total_row_count),
    )

    document_row_total = sum(document["final_document_row_count"] for document in documents)
    if document_row_total != collection_result.actual_collection_row_count:
        raise ValueError(
            "manifest documents 行数之和与 collection 实际总行数不一致："
            f"documents={document_row_total}, "
            "collection="
            f"{collection_result.actual_collection_row_count}"
        )

    return {
        "manifest_schema_version": "1.0",
        "build_id": build_id,
        "workspace_id": workspace_id,
        "embedding": {
            "model_name": collection_result.embedding_model,
            "vector_dim": collection_result.vector_dim,
        },
        "retrieval_contract": {
            "metric_type": collection_result.metric_type,
        },
        "collection": {
            "database_path": _serialize_manifest_path(
                database_path,
                project_root=project_root,
            ),
            "collection_name": collection_result.collection_name,
            "expected_row_count": (collection_result.expected_total_row_count),
            "actual_row_count": (collection_result.actual_collection_row_count),
        },
        "legacy_preservation": {
            "collection_name": legacy_collection_name,
            "row_count_before": (collection_result.legacy_row_count_before),
            "row_count_after": (collection_result.legacy_row_count_after),
            "preserved": (
                collection_result.legacy_row_count_before
                == collection_result.legacy_row_count_after
            ),
        },
        "documents": documents,
        "quality_checks": quality_checks,
    }


def write_v2_manifest(
    path: Path,
    manifest: dict[str, Any],
) -> ManifestWriteResult:
    """把已验证的 v2 manifest 确定性地原子发布为 UTF-8 JSON。

    Args:
        path: manifest 的最终输出路径。
        manifest: 已由 build_v2_manifest 验证和组装的内存对象。

    Returns:
        最终文件的路径、字节数和 SHA-256 摘要。

    Raises:
        TypeError: manifest 包含不能序列化为 JSON 的对象。
        ValueError: manifest 包含 JSON 不允许的 NaN 或 Infinity。
        OSError: 创建目录、写入、同步或替换文件失败。

    Failure behavior:
        JSON 序列化在创建临时文件之前完成；如果序列化失败，
        已存在的目标文件保持不变。临时文件写入失败时会清理残留文件。
    """
    serialized_text = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    )
    payload = (serialized_text + "\n").encode("utf-8")

    path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path: Path | None = None

    try:
        with NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)

            # 把完整 JSON 字节写入同目录临时文件。
            temporary_file.write(payload)
            temporary_file.flush()

            # 要求操作系统同步当前临时文件的内容。
            os.fsync(temporary_file.fileno())

        # 退出 with 后文件已经关闭，此时再原子替换最终 manifest。
        temporary_path.replace(path)
    except BaseException:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise

    return ManifestWriteResult(
        path=path,
        byte_size=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def load_v2_manifest(
    path: Path,
    *,
    project_root: Path,
    expected_build_id: str,
    expected_workspace_id: str,
    expected_collection_name: str,
    expected_document_ids: set[str],
) -> dict[str, Any]:
    """读取并复查已发布的 Day43 v2 manifest 和对应 JSONL。

    Args:
        path: 已发布 manifest.json 的路径。
        project_root: 仓库根目录，用于解析 manifest 中的相对路径。
        expected_build_id: 调用方冻结的数据版本。
        expected_workspace_id: 调用方冻结的 workspace 身份。
        expected_collection_name: 调用方预期的 v2 collection 名。
        expected_document_ids: 调用方冻结的完整 document_id 集合。

    Returns:
        通过结构、身份、行数、字节数、SHA-256 和 JSONL 合同复查的
        manifest 字典。

    Raises:
        FileNotFoundError: manifest 或某份 JSONL 不存在。
        ValueError: manifest JSON 无效，或者版本、身份、路径、行数、
            文件摘要、legacy 保护和质量检查不符合冻结合同。

    Limitations:
        本函数只读 manifest 和 JSONL，不访问 Milvus、不生成 embedding，
        也不修改任何文件。
    """
    if not path.is_file():
        raise FileNotFoundError(f"manifest 文件不存在：{path}")

    if not project_root.is_dir():
        raise ValueError(f"project_root 不是有效目录：{project_root}")

    if not isinstance(expected_build_id, str) or not expected_build_id.strip():
        raise ValueError("expected_build_id 必须是非空字符串")

    if not isinstance(expected_workspace_id, str) or not expected_workspace_id.strip():
        raise ValueError("expected_workspace_id 必须是非空字符串")

    if not isinstance(expected_collection_name, str) or not expected_collection_name.strip():
        raise ValueError("expected_collection_name 必须是非空字符串")

    if not expected_document_ids:
        raise ValueError("expected_document_ids 不能为空")

    for expected_document_id in expected_document_ids:
        if not isinstance(expected_document_id, str) or not expected_document_id.strip():
            raise ValueError("expected_document_ids 中的身份必须是非空字符串")

    try:
        manifest_text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"manifest 不是合法 UTF-8 文件：{path}") from exc

    try:
        raw_manifest = json.loads(manifest_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"manifest 不是合法 JSON：{path}：{exc}") from exc

    if not isinstance(raw_manifest, dict):
        raise ValueError(f"manifest JSON 顶层必须是字典：{path}")

    manifest: dict[str, Any] = raw_manifest

    schema_version = manifest.get("manifest_schema_version")
    if schema_version != "1.0":
        raise ValueError(
            f"{path} 的 manifest_schema_version 不匹配：expected='1.0', actual={schema_version!r}"
        )

    actual_build_id = manifest.get("build_id")
    if actual_build_id != expected_build_id:
        raise ValueError(
            f"{path} 的 build_id 不匹配：expected={expected_build_id!r}, actual={actual_build_id!r}"
        )

    actual_workspace_id = manifest.get("workspace_id")
    if actual_workspace_id != expected_workspace_id:
        raise ValueError(
            f"{path} 的 workspace_id 不匹配："
            f"expected={expected_workspace_id!r}, "
            f"actual={actual_workspace_id!r}"
        )

    collection = _require_manifest_dict(
        manifest,
        "collection",
        manifest_path=path,
    )

    actual_collection_name = collection.get("collection_name")
    if actual_collection_name != expected_collection_name:
        raise ValueError(
            f"{path} 的 collection.collection_name 不匹配："
            f"expected={expected_collection_name!r}, "
            f"actual={actual_collection_name!r}"
        )

    expected_collection_row_count = _require_nonnegative_int(
        collection.get("expected_row_count"),
        "collection.expected_row_count",
        manifest_path=path,
    )
    actual_collection_row_count = _require_nonnegative_int(
        collection.get("actual_row_count"),
        "collection.actual_row_count",
        manifest_path=path,
    )

    if expected_collection_row_count != actual_collection_row_count:
        raise ValueError(
            f"{path} 的 collection 行数不守恒："
            f"expected={expected_collection_row_count}, "
            f"actual={actual_collection_row_count}"
        )

    legacy_preservation = _require_manifest_dict(
        manifest,
        "legacy_preservation",
        manifest_path=path,
    )

    if legacy_preservation.get("preserved") is not True:
        raise ValueError(f"{path} 的 legacy_preservation.preserved 必须严格为 True")

    legacy_row_count_before = _require_nonnegative_int(
        legacy_preservation.get("row_count_before"),
        "legacy_preservation.row_count_before",
        manifest_path=path,
    )
    legacy_row_count_after = _require_nonnegative_int(
        legacy_preservation.get("row_count_after"),
        "legacy_preservation.row_count_after",
        manifest_path=path,
    )

    if legacy_row_count_before != legacy_row_count_after:
        raise ValueError(
            f"{path} 的 legacy collection 行数发生变化："
            f"before={legacy_row_count_before}, "
            f"after={legacy_row_count_after}"
        )

    quality_checks = _require_manifest_dict(
        manifest,
        "quality_checks",
        manifest_path=path,
    )

    if quality_checks.get("global_chunk_ids_unique") is not True:
        raise ValueError(f"{path} 的 quality_checks.global_chunk_ids_unique 必须严格为 True")

    if quality_checks.get("document_ids_unique") is not True:
        raise ValueError(f"{path} 的 quality_checks.document_ids_unique 必须严格为 True")

    quality_count_fields = (
        "degraded_table_text_count",
        "html_in_table_text_count",
        "missing_table_md_count",
        "table_md_mismatch_count",
        "section_pollution_count",
    )

    for field_name in quality_count_fields:
        defect_count = _require_nonnegative_int(
            quality_checks.get(field_name),
            f"quality_checks.{field_name}",
            manifest_path=path,
        )

        if defect_count != 0:
            raise ValueError(
                f"{path} 的 quality_checks.{field_name} 必须为 0，actual={defect_count}"
            )

    documents_value = manifest.get("documents")
    if not isinstance(documents_value, list) or not documents_value:
        raise ValueError(f"{path} 的 documents 必须是非空列表")

    resolved_project_root = project_root.resolve()
    document_ids: set[str] = set()
    total_jsonl_row_count = 0

    for index, document_value in enumerate(documents_value):
        if not isinstance(document_value, dict):
            raise ValueError(f"{path} 的 documents[{index}] 必须是字典")

        document: dict[str, Any] = document_value

        document_id = document.get("document_id")
        if not isinstance(document_id, str) or not document_id.strip():
            raise ValueError(f"{path} 的 documents[{index}].document_id 必须是非空字符串")

        if document_id in document_ids:
            raise ValueError(f"{path} 的 document_id 重复：{document_id}")

        document_ids.add(document_id)

        source_file = document.get("source_file")
        if not isinstance(source_file, str) or not source_file.strip():
            raise ValueError(f"{path} 的 documents[{index}].source_file 必须是非空字符串")

        output_jsonl_value = document.get("output_jsonl")
        if not isinstance(output_jsonl_value, str) or not output_jsonl_value.strip():
            raise ValueError(f"{path} 的 documents[{index}].output_jsonl 必须是非空字符串")

        output_jsonl = Path(output_jsonl_value)

        if output_jsonl.is_absolute():
            raise ValueError(
                f"{path} 的 document_id={document_id} 的 "
                f"output_jsonl 不能是绝对路径：{output_jsonl}"
            )

        if ".." in output_jsonl.parts:
            raise ValueError(
                f"{path} 的 document_id={document_id} 的 output_jsonl 不能包含 '..'：{output_jsonl}"
            )

        jsonl_path = (resolved_project_root / output_jsonl).resolve()

        try:
            jsonl_path.relative_to(resolved_project_root)
        except ValueError as exc:
            raise ValueError(
                f"{path} 的 document_id={document_id} 的 "
                f"output_jsonl 越出 project_root：{jsonl_path}"
            ) from exc

        if not jsonl_path.is_file():
            raise FileNotFoundError(
                f"document_id={document_id} 的 output_jsonl 文件不存在：{jsonl_path}"
            )

        expected_byte_size = _require_nonnegative_int(
            document.get("jsonl_byte_size"),
            f"documents[{index}].jsonl_byte_size",
            manifest_path=path,
        )

        if expected_byte_size == 0:
            raise ValueError(f"{path} 的 document_id={document_id} 的 jsonl_byte_size 必须大于 0")

        expected_sha256 = _validate_sha256(
            document.get("jsonl_sha256"),
            document_id,
        )

        assert isinstance(expected_sha256, str)

        current_bytes = jsonl_path.read_bytes()
        actual_byte_size = len(current_bytes)

        if actual_byte_size != expected_byte_size:
            raise ValueError(
                f"document_id={document_id} 的 JSONL 字节数不一致："
                f"path={jsonl_path}, "
                f"expected={expected_byte_size}, "
                f"actual={actual_byte_size}"
            )

        actual_sha256 = hashlib.sha256(current_bytes).hexdigest()

        if actual_sha256 != expected_sha256:
            raise ValueError(
                f"document_id={document_id} 的 JSONL SHA-256 不一致："
                f"path={jsonl_path}, "
                f"expected={expected_sha256}, "
                f"actual={actual_sha256}"
            )

        jsonl_row_count = _require_nonnegative_int(
            document.get("jsonl_row_count"),
            f"documents[{index}].jsonl_row_count",
            manifest_path=path,
        )
        embedded_row_count = _require_nonnegative_int(
            document.get("embedded_row_count"),
            f"documents[{index}].embedded_row_count",
            manifest_path=path,
        )
        final_document_row_count = _require_nonnegative_int(
            document.get("final_document_row_count"),
            f"documents[{index}].final_document_row_count",
            manifest_path=path,
        )

        if not (jsonl_row_count == embedded_row_count == final_document_row_count):
            raise ValueError(
                f"document_id={document_id} 的发布行数不守恒："
                f"jsonl={jsonl_row_count}, "
                f"embedded={embedded_row_count}, "
                f"final={final_document_row_count}"
            )

        rows = load_versioned_jsonl(
            jsonl_path,
            expected_workspace_id=expected_workspace_id,
            expected_document_id=document_id,
            expected_source_file=source_file,
            expected_data_version=expected_build_id,
        )

        if len(rows) != jsonl_row_count:
            raise ValueError(
                f"document_id={document_id} 的 JSONL 行数不一致："
                f"path={jsonl_path}, "
                f"manifest={jsonl_row_count}, "
                f"actual={len(rows)}"
            )

        total_jsonl_row_count += jsonl_row_count

    if document_ids != expected_document_ids:
        missing_document_ids = sorted(expected_document_ids - document_ids)
        unexpected_document_ids = sorted(document_ids - expected_document_ids)
        raise ValueError(
            f"{path} 的 document_id 集合不一致："
            f"missing={missing_document_ids}, "
            f"unexpected={unexpected_document_ids}"
        )

    if total_jsonl_row_count != expected_collection_row_count:
        raise ValueError(
            f"{path} 的 documents 行数之和与 collection 不一致："
            f"documents={total_jsonl_row_count}, "
            f"collection={expected_collection_row_count}"
        )

    return manifest
