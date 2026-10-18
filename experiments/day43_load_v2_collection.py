import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

from pymilvus import DataType, MilvusClient

from experiments.day43_config import (
    BUILD_ID,
    DEMO_WORKSPACE_ID,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_VECTOR_DIM,
    EXPECTED_LEGACY_ROW_COUNT,
    LEGACY_COLLECTION_NAME,
    METRIC_TYPE,
    MILVUS_DB_PATH,
    REAL_DOCUMENTS,
    V2_COLLECTION_NAME,
    RealDocumentConfig,
)

from app.rag.ingest import (
    Embedder,
    build_aligned_rows,
    load_versioned_jsonl,
    replace_document_rows,
)

from app.rag.store import (
    count_rows,
    ensure_document_collection,
    get_client,
)


@dataclass(frozen=True)
class DocumentCollectionLoadResult:
    """文档集合加载结果"""

    source_file: str
    """源文件"""
    document_id: str
    """文档ID"""
    jsonl_path: Path
    """JSONL文件路径"""
    jsonl_row_count: int
    """通过 loader Gate 的磁盘行数"""
    embedded_row_count: int
    """增加 vector 后的 row 数"""
    final_document_row_count: int
    """按该 document_id 从 Milvus 查询到的最终行数"""


@dataclass(frozen=True)
class V2CollectionBuildResult:
    """记录三份 v2 JSONL 构建新 collection 后的可审计结果。"""

    collection_name: str
    """collection 名称"""
    embedding_model: str
    """embedding 模型"""
    vector_dim: int
    """向量维度"""
    metric_type: str
    """距离度量类型"""
    expected_total_row_count: int
    """预期总行数"""
    actual_collection_row_count: int
    """实际 collection 行数"""
    global_chunk_id_count: int
    """全局 chunk_id 数量"""
    legacy_row_count_before: int
    """legacy collection 行数 before"""
    legacy_row_count_after: int
    """legacy collection 行数 after"""
    document_results: tuple[DocumentCollectionLoadResult, ...]
    """document 结果"""


def load_all_versioned_jsonls() -> list[tuple[RealDocumentConfig, list[dict[str, Any]]]]:
    """在加载模型和创建 collection 前，验证三份冻结 v2 JSONL 的完整批次。

    Returns:
        按 REAL_DOCUMENTS 顺序排列的文档配置及已验证 JSONL rows。

    Raises:
        ValueError: document_id 或 chunk_id 在批次内重复，或者 JSONL 不符合合同。
        RuntimeError: 配置文档数量、总行数或全局 ID 数量不守恒。

    Limitations:
        本函数只读磁盘，不加载 embedding 模型，也不访问 Milvus。
    """
    prepared_documents: list[tuple[RealDocumentConfig, list[dict[str, Any]]]] = []
    seen_document_ids: set[str] = set()
    global_chunk_ids: set[str] = set()
    for document in REAL_DOCUMENTS:
        document_id = document["document_id"]
        if document_id in seen_document_ids:
            raise ValueError(f"REAL_DOCUMENTS 中 document_id 重复：{document_id}")
        seen_document_ids.add(document_id)
        rows = load_versioned_jsonl(
            Path(document["output_jsonl"]),
            expected_workspace_id=DEMO_WORKSPACE_ID,
            expected_document_id=document["document_id"],
            expected_source_file=document["source_file"],
            expected_data_version=BUILD_ID,
        )
        for index, row in enumerate(rows, start=1):
            chunk_id = row["chunk_id"]
            if chunk_id in global_chunk_ids:
                raise ValueError(
                    f"{document['output_jsonl']} 第 {index} 行 chunk_id 在批次内重复：{chunk_id}"
                )
            global_chunk_ids.add(chunk_id)
        prepared_documents.append((document, rows))
    if len(prepared_documents) != len(REAL_DOCUMENTS):
        raise RuntimeError(
            f"准备好的文档数与实际文档数不一致：{len(prepared_documents)} != {len(REAL_DOCUMENTS)}"
        )
    total_row_count = sum(len(rows) for _, rows in prepared_documents)
    if total_row_count != len(global_chunk_ids):
        raise RuntimeError(
            f"通过 loader Gate 的磁盘行数与 chunk_id 数不一致：{total_row_count} != {len(global_chunk_ids)}"
        )
    return prepared_documents


def load_document_into_collection(
    *,
    client: MilvusClient,
    collection_name: str,
    document_config: RealDocumentConfig,
    jsonl_rows: list[dict[str, Any]],
    embedder: Embedder,
    expected_vector_dim: int,
) -> DocumentCollectionLoadResult:
    """把一份通过预检的 JSONL rows 向量化并按 document_id 写入 collection。

    Args:
        client: 已连接目标数据库的 Milvus 客户端。
        collection_name: 已存在且维度匹配的目标 collection。
        document_config: 当前文档的冻结身份和路径配置。
        jsonl_rows: 已通过 v2 JSONL Gate 的行。
        embedder: 保持输入输出顺序一致的向量化函数。
        expected_vector_dim: 目标 collection 要求的向量维度。

    Returns:
        当前文档从 JSONL 到 Milvus 的行数和身份审计结果。

    Raises:
        ValueError: 输入行、向量数量、类型或维度不符合合同。
        RuntimeError: document 替换后的行数或 ID 集合与 JSONL 不一致。
    """
    jsonl_row_count = len(jsonl_rows)
    if not jsonl_rows:
        raise ValueError("jsonl_rows 不能为空")

    if (
        isinstance(expected_vector_dim, bool)
        or not isinstance(expected_vector_dim, int)
        or expected_vector_dim < 1
    ):
        raise ValueError("expected_vector_dim 必须是正整数")
    embedded_rows = build_aligned_rows(jsonl_rows, embedder)
    if len(embedded_rows) != jsonl_row_count:
        raise ValueError(
            f"向量化后的行数与原始行数不一致：{len(embedded_rows)} != {jsonl_row_count}"
        )
    for index, row in enumerate(embedded_rows):
        vector = row["vector"]
        if not isinstance(vector, list):
            raise ValueError(
                f"embedded_rows[{index}] 的 vector 必须是 list，actual={type(vector).__name__}"
            )
        if len(vector) != expected_vector_dim:
            raise ValueError(
                f"embedded_rows[{index}] 的 vector 维度错误："
                f"expected={expected_vector_dim}, actual={len(vector)}"
            )
        for value_index, value in enumerate(vector):
            if isinstance(value, bool) or not isinstance(
                value,
                (int, float),
            ):
                raise ValueError(
                    f"embedded_rows[{index}] 的 vector[{value_index}] "
                    f"必须是数值，actual={type(value).__name__}"
                )

    replace_result = replace_document_rows(
        client,
        collection_name,
        document_config["document_id"],
        embedded_rows,
    )

    document_filter = "document_id == " + json.dumps(
        document_config["document_id"],
        ensure_ascii=False,
    )

    final_document_rows = client.query(
        collection_name=collection_name,
        filter=document_filter,
        output_fields=["chunk_id"],
    )

    final_document_row_count = len(final_document_rows)
    expected_chunk_ids = {row["chunk_id"] for row in jsonl_rows}
    actual_chunk_ids = {row["chunk_id"] for row in final_document_rows}

    if replace_result.final_ids != frozenset(expected_chunk_ids):
        raise RuntimeError("document 替换结果 ID 集合与 JSONL 不一致")

    if actual_chunk_ids != expected_chunk_ids:
        raise RuntimeError("Milvus 最终 document ID 集合与 JSONL 不一致")
    if final_document_row_count != jsonl_row_count:
        raise RuntimeError(
            "Milvus 最终 document 行数与 JSONL 行数不一致："
            f"expected={jsonl_row_count}, "
            f"actual={final_document_row_count}"
        )
    return DocumentCollectionLoadResult(
        source_file=document_config["source_file"],
        document_id=document_config["document_id"],
        jsonl_path=Path(document_config["output_jsonl"]),
        jsonl_row_count=jsonl_row_count,
        embedded_row_count=len(embedded_rows),
        final_document_row_count=final_document_row_count,
    )


def validate_v2_collection_contract(
    client: MilvusClient,
    collection_name: str,
    *,
    expected_vector_dim: int,
    expected_metric_type: str,
) -> None:
    """验证 v2 collection 的主键、向量字段、动态 metadata 和索引合同。

    Args:
        client: 已连接目标数据库的 Milvus 客户端。
        collection_name: 已存在的 v2 collection 名。
        expected_vector_dim: embedding 模型要求的向量维度。
        expected_metric_type: legacy/v2 对照共同使用的距离度量。

    Raises:
        RuntimeError: collection schema 或向量索引不符合冻结合同。
    """
    description = cast(dict[str, Any], client.describe_collection(collection_name))
    raw_fields = description.get("fields")

    if not isinstance(raw_fields, list):
        raise RuntimeError(f"collection {collection_name} 的 fields 不是列表")
    fields: dict[str, dict[str, Any]] = {}
    for index, raw_field in enumerate(raw_fields):
        if not isinstance(raw_field, dict):
            raise RuntimeError(f"collection {collection_name} 的 fields[{index}] 不是字典")
        field_name = raw_field.get("name")
        if not isinstance(field_name, str) or not field_name:
            raise RuntimeError(f"collection {collection_name} 的 fields[{index}] 缺少有效 name")
        fields[field_name] = raw_field

    chunk_id_field = fields.get("chunk_id")
    if (
        chunk_id_field is None
        or chunk_id_field.get("type") != DataType.VARCHAR
        or chunk_id_field.get("is_primary") is not True
    ):
        raise RuntimeError(f"collection {collection_name} 的 chunk_id 必须是 VARCHAR 主键")

    vector_field = fields.get("vector")
    if vector_field is None or vector_field.get("type") != DataType.FLOAT_VECTOR:
        raise RuntimeError(f"collection {collection_name} 的 vector 必须是 FLOAT_VECTOR")
    actual_vector_dim = vector_field.get("params", {}).get("dim")
    try:
        actual_vector_dim = int(actual_vector_dim)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            f"collection {collection_name} 的 vector dim 无效：{actual_vector_dim!r}"
        ) from exc

    if actual_vector_dim != expected_vector_dim:
        raise RuntimeError(
            f"collection {collection_name} 的 vector dim 不一致："
            f"expected={expected_vector_dim}, "
            f"actual={actual_vector_dim}"
        )

    if description.get("enable_dynamic_field") is not True:
        raise RuntimeError(
            f"collection {collection_name} 必须启用动态字段，"
            "以保存 workspace/document/source 等 metadata"
        )

    index_names = client.list_indexes(collection_name)

    if "vector" not in index_names:
        raise RuntimeError(f"collection {collection_name} 缺少 vector 索引")

    index_description = cast(dict[str, Any], client.describe_index(collection_name, "vector"))
    actual_metric_type = index_description.get("metric_type")

    if actual_metric_type != expected_metric_type:
        raise RuntimeError(
            f"collection {collection_name} 的 metric_type 不一致："
            f"expected={expected_metric_type}, "
            f"actual={actual_metric_type}"
        )


def build_v2_collection() -> V2CollectionBuildResult:
    prepared_documents = load_all_versioned_jsonls()
    expected_total_row_count = sum(len(rows) for _, rows in prepared_documents)

    if V2_COLLECTION_NAME == LEGACY_COLLECTION_NAME:
        raise RuntimeError("v2 collection 不能与 legacy collection 同名")
    from app.rag.embed import embed

    client = get_client(str(MILVUS_DB_PATH))

    try:
        if not client.has_collection(LEGACY_COLLECTION_NAME):
            raise RuntimeError(f"legacy collection 不存在：{LEGACY_COLLECTION_NAME}")
        client.load_collection(
            LEGACY_COLLECTION_NAME,
        )
        legacy_row_count_before = count_rows(
            client,
            LEGACY_COLLECTION_NAME,
        )

        if legacy_row_count_before != EXPECTED_LEGACY_ROW_COUNT:
            raise RuntimeError(
                "legacy collection 行数与 Day43 冻结起点不一致："
                f"expected={EXPECTED_LEGACY_ROW_COUNT}, "
                f"actual={legacy_row_count_before}"
            )

        ensure_document_collection(
            client,
            V2_COLLECTION_NAME,
            dim=EMBEDDING_VECTOR_DIM,
        )

        client.load_collection(
            V2_COLLECTION_NAME,
        )

        validate_v2_collection_contract(
            client,
            V2_COLLECTION_NAME,
            expected_vector_dim=EMBEDDING_VECTOR_DIM,
            expected_metric_type=METRIC_TYPE,
        )

        document_results: list[DocumentCollectionLoadResult] = []

        for document_config, jsonl_rows in prepared_documents:
            result = load_document_into_collection(
                client=client,
                collection_name=V2_COLLECTION_NAME,
                document_config=document_config,
                jsonl_rows=jsonl_rows,
                embedder=embed,
                expected_vector_dim=EMBEDDING_VECTOR_DIM,
            )
            document_results.append(result)
        document_total_row_count = sum(
            result.final_document_row_count for result in document_results
        )

        actual_collection_row_count = count_rows(
            client,
            V2_COLLECTION_NAME,
        )

        if document_total_row_count != expected_total_row_count:
            raise RuntimeError(
                "三个 document 最终行数之和与 JSONL 总行数不一致："
                f"expected={expected_total_row_count}, "
                f"actual={document_total_row_count}"
            )

        if actual_collection_row_count != expected_total_row_count:
            raise RuntimeError(
                "v2 collection 总行数与 JSONL 总行数不一致："
                f"expected={expected_total_row_count}, "
                f"actual={actual_collection_row_count}"
            )

        legacy_row_count_after = count_rows(
            client,
            LEGACY_COLLECTION_NAME,
        )

        if legacy_row_count_after != legacy_row_count_before:
            raise RuntimeError(
                "构建 v2 collection 时 legacy 行数发生变化："
                f"before={legacy_row_count_before}, "
                f"after={legacy_row_count_after}"
            )
    finally:
        client.close()

    return V2CollectionBuildResult(
        collection_name=V2_COLLECTION_NAME,
        embedding_model=EMBEDDING_MODEL_NAME,
        vector_dim=EMBEDDING_VECTOR_DIM,
        metric_type=METRIC_TYPE,
        expected_total_row_count=expected_total_row_count,
        actual_collection_row_count=actual_collection_row_count,
        legacy_row_count_before=legacy_row_count_before,
        legacy_row_count_after=legacy_row_count_after,
        document_results=tuple(document_results),
        global_chunk_id_count=expected_total_row_count,
    )


def main() -> int:
    """构建并验证真实 v2 collection，打印审计结果，成功后返回退出码 0。"""

    result = build_v2_collection()

    print(
        json.dumps(
            asdict(result),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
