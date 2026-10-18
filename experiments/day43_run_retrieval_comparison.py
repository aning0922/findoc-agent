"""运行 Day43 legacy/v2 同配置检索对照并保留逐题原始结果。

职责：
1. 重新验证已发布的 v2 manifest 和三份 JSONL。
2. 验证 legacy/v2 两份题集的问题语义完全一致。
3. 验证两个 collection 的行数和 COSINE 合同。
4. 通过同一个 Retriever、embedding 模型和 top_k 分别运行两套题。
5. 原子写入 legacy、v2 和汇总对照报告。
6. 再次确认 legacy collection 和 Day42 baseline 没有被修改。

限制：
不生成 RAG 答案，不调整 top_k，不更换 embedding 模型，
不覆盖 Day42 baseline，也不根据本次指标重新调参。
"""

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import perf_counter
from typing import Any, cast

from pymilvus import MilvusClient

from app.rag.retriever import Retriever, TrustedContext
from app.rag.store import MilvusSearchStore, count_rows, get_client
from experiments.day43_compare_retrieval import (
    LegacyComparisonStore,
    evaluate_question_set_with_retriever,
)
from experiments.day43_config import (
    BUILD_ID,
    DEMO_WORKSPACE_ID,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_VECTOR_DIM,
    EXPECTED_LEGACY_ROW_COUNT,
    LEGACY_COLLECTION_NAME,
    MANIFEST_PATH,
    METRIC_TYPE,
    MILVUS_DB_PATH,
    PROJECT_ROOT,
    REAL_DOCUMENTS,
    V2_COLLECTION_NAME,
)
from experiments.day43_manifest import load_v2_manifest
from scripts.evaluate_day42_retrieval import (
    get_git_state,
    load_questions,
    print_question_result,
)


# legacy/v2 共同使用的固定召回数量。
TOP_K = 5

# 冻结的 Day42 legacy 问题集，只读使用。
LEGACY_QUESTION_PATH = PROJECT_ROOT / "eval/day42_questions.jsonl"

# 已迁移到 v2 稳定 chunk_id 的问题集。
V2_QUESTION_PATH = PROJECT_ROOT / "eval/day43_questions_v2.jsonl"

# 冻结的 Day42 原始 baseline，只用于保护和审计，不允许覆盖。
DAY42_BASELINE_PATH = PROJECT_ROOT / "eval/day42_baseline.json"

# 本次使用统一 Retriever 重跑 legacy 后的独立原始结果。
LEGACY_RESULT_PATH = PROJECT_ROOT / "eval/day43_legacy_comparison.json"

# 本次 v2 的独立逐题原始结果。
V2_RESULT_PATH = PROJECT_ROOT / "eval/day43_v2_comparison.json"

# legacy/v2 指标和逐题排名的汇总对照。
COMPARISON_RESULT_PATH = PROJECT_ROOT / "eval/day43_legacy_v2_comparison.json"

# 两份题集必须逐题保持不变的语义字段。
SEMANTIC_QUESTION_FIELDS = (
    "case_id",
    "query",
    "category",
    "answerable",
    "source_file",
    "ground_truth",
)

# Day43 冻结题集合同。
EXPECTED_QUESTION_COUNT = 12
EXPECTED_ANSWERABLE_COUNT = 10
EXPECTED_UNANSWERABLE_COUNT = 2


def calculate_file_sha256(path: Path) -> str:
    """计算现有文件的 SHA-256，用于确认输入和旧 baseline 未变化。

    Args:
        path:
            必须存在的普通文件。

    Returns:
        文件原始字节的64位小写 SHA-256。

    Raises:
        FileNotFoundError:
            文件不存在或不是普通文件。

        OSError:
            文件读取失败。
    """
    if not path.is_file():
        raise FileNotFoundError(f"审计文件不存在：{path}")

    return hashlib.sha256(path.read_bytes()).hexdigest()


def ensure_result_paths_are_new(paths: Sequence[Path]) -> None:
    """确认本次三个输出路径都不存在，避免覆盖第一次原始对照结果。

    Args:
        paths:
            本次准备写入的全部结果文件路径。

    Raises:
        ValueError:
            输出路径重复。

        FileExistsError:
            任意目标文件已经存在。

    Limitations:
        本函数只检查目标路径，不创建、删除或修改文件。
    """
    if len(set(paths)) != len(paths):
        raise ValueError("评测输出路径不能重复")

    existing_paths = [path for path in paths if path.exists()]

    if existing_paths:
        raise FileExistsError(
            f"Day43 原始对照结果已存在，拒绝覆盖：{[str(path) for path in existing_paths]}"
        )


def write_evaluation_report(
    path: Path,
    report: Mapping[str, Any],
) -> dict[str, Any]:
    """将评测报告确定性地原子写入一个此前不存在的 JSON 文件。

    Args:
        path:
            最终输出路径。为了保留第一次原始结果，该路径必须不存在。

        report:
            已完成评测的可序列化报告。

    Returns:
        包含最终路径、字节数和 SHA-256 的审计字典。

    Raises:
        FileExistsError:
            目标路径已经存在。

        TypeError:
            report 包含不能序列化为 JSON 的对象。

        ValueError:
            report 包含 NaN 或 Infinity。

        OSError:
            创建目录、写入、同步或发布文件失败。

    Failure:
        完整 JSON 在创建临时文件前完成序列化。临时文件写入失败时会清理，
        已存在的结果文件绝不会被覆盖。
    """
    if path.exists():
        raise FileExistsError(f"评测结果已存在，拒绝覆盖：{path}")

    serialized_text = json.dumps(
        report,
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

            # 把完整报告写入同目录临时文件并同步到操作系统。
            temporary_file.write(payload)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        # os.link 只有在最终路径不存在时才会成功，因此不会覆盖原始结果。
        os.link(temporary_path, path)
        temporary_path.unlink()
        temporary_path = None
    except BaseException:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise

    return {
        "path": str(path),
        "byte_size": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _metadata_value_fingerprints(
    question: Mapping[str, Any],
) -> list[str]:
    """忽略 chunk_id 键，生成一道题的证据元数据值指纹列表。

    Args:
        question:
            包含 expected_metadata 的已校验问题。

    Returns:
        按稳定顺序排列的元数据 JSON 字符串列表。

    Raises:
        ValueError:
            expected_metadata 不是字典，或者某个元数据值不是字典。
    """
    expected_metadata = question.get("expected_metadata")

    if not isinstance(expected_metadata, dict):
        raise ValueError(f"问题 {question.get('case_id')} 的 expected_metadata 必须是字典")

    fingerprints: list[str] = []

    for chunk_id, metadata in expected_metadata.items():
        if not isinstance(chunk_id, str) or not chunk_id.strip():
            raise ValueError("expected_metadata 的 chunk_id 键必须是非空字符串")

        if not isinstance(metadata, dict):
            raise ValueError(f"expected_metadata[{chunk_id}] 必须是字典")

        fingerprints.append(
            json.dumps(
                metadata,
                ensure_ascii=False,
                sort_keys=True,
                allow_nan=False,
            )
        )

    return sorted(fingerprints)


def validate_comparable_question_sets(
    legacy_questions: Sequence[Mapping[str, Any]],
    v2_questions: Sequence[Mapping[str, Any]],
) -> None:
    """验证 legacy/v2 题集只改变证据身份，不改变问题语义和证据位置。

    Args:
        legacy_questions:
            使用 legacy UUID chunk_id 的冻结题集。

        v2_questions:
            使用 v2 稳定 SHA-256 chunk_id 的迁移题集。

    Raises:
        ValueError:
            题目数量、顺序、语义字段、可回答性、证据数量或证据元数据不一致；
            可回答题仍复用 legacy ID；或者无答案题出现相关证据。

    Limitations:
        本函数不访问 collection。证据原文等价性已经由
        day43_migrate_ground_truth 负责验证。
    """
    if len(legacy_questions) != EXPECTED_QUESTION_COUNT:
        raise ValueError(
            "legacy 题目数量不符合冻结合同："
            f"expected={EXPECTED_QUESTION_COUNT}, "
            f"actual={len(legacy_questions)}"
        )

    if len(v2_questions) != EXPECTED_QUESTION_COUNT:
        raise ValueError(
            "v2 题目数量不符合冻结合同："
            f"expected={EXPECTED_QUESTION_COUNT}, "
            f"actual={len(v2_questions)}"
        )

    legacy_answerable_count = sum(
        question.get("answerable") is True for question in legacy_questions
    )
    v2_answerable_count = sum(question.get("answerable") is True for question in v2_questions)

    if (
        legacy_answerable_count != EXPECTED_ANSWERABLE_COUNT
        or v2_answerable_count != EXPECTED_ANSWERABLE_COUNT
    ):
        raise ValueError(
            "可回答题数量不符合冻结合同："
            f"legacy={legacy_answerable_count}, "
            f"v2={v2_answerable_count}"
        )

    legacy_unanswerable_count = len(legacy_questions) - legacy_answerable_count
    v2_unanswerable_count = len(v2_questions) - v2_answerable_count

    if (
        legacy_unanswerable_count != EXPECTED_UNANSWERABLE_COUNT
        or v2_unanswerable_count != EXPECTED_UNANSWERABLE_COUNT
    ):
        raise ValueError(
            "无答案题数量不符合冻结合同："
            f"legacy={legacy_unanswerable_count}, "
            f"v2={v2_unanswerable_count}"
        )

    seen_case_ids: set[str] = set()

    for index, (legacy_question, v2_question) in enumerate(
        zip(legacy_questions, v2_questions, strict=True),
        start=1,
    ):
        case_id = legacy_question.get("case_id")

        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"第 {index} 题缺少合法 case_id")

        if case_id in seen_case_ids:
            raise ValueError(f"题集中 case_id 重复：{case_id}")

        seen_case_ids.add(case_id)

        for field_name in SEMANTIC_QUESTION_FIELDS:
            legacy_value = legacy_question.get(field_name)
            v2_value = v2_question.get(field_name)

            if legacy_value != v2_value:
                raise ValueError(
                    f"第 {index} 题 {case_id} 的语义字段发生变化："
                    f"field={field_name}, "
                    f"legacy={legacy_value!r}, "
                    f"v2={v2_value!r}"
                )

        legacy_ids = legacy_question.get("relevant_chunk_ids")
        v2_ids = v2_question.get("relevant_chunk_ids")

        if not isinstance(legacy_ids, list) or not isinstance(v2_ids, list):
            raise ValueError(f"第 {index} 题 {case_id} 的 relevant_chunk_ids 必须是列表")

        answerable = legacy_question.get("answerable") is True

        if answerable:
            if not legacy_ids or not v2_ids:
                raise ValueError(f"可回答题 {case_id} 必须在两个版本中都有相关证据")

            if len(legacy_ids) != len(v2_ids):
                raise ValueError(
                    f"题目 {case_id} 迁移前后的相关证据数量不一致："
                    f"legacy={len(legacy_ids)}, v2={len(v2_ids)}"
                )

            if set(legacy_ids) & set(v2_ids):
                raise ValueError(f"题目 {case_id} 的 v2 证据仍复用了 legacy chunk_id")
        elif legacy_ids or v2_ids:
            raise ValueError(f"无答案题 {case_id} 的 relevant_chunk_ids 必须保持为空")

        legacy_metadata = _metadata_value_fingerprints(legacy_question)
        v2_metadata = _metadata_value_fingerprints(v2_question)

        if legacy_metadata != v2_metadata:
            raise ValueError(f"题目 {case_id} 迁移前后的证据元数据值不一致")


def validate_collection_metric(
    client: MilvusClient,
    collection_name: str,
    *,
    expected_metric_type: str,
) -> None:
    """验证 collection 的 vector 索引使用冻结的距离度量。

    Args:
        client:
            已连接 Milvus Lite 的客户端。

        collection_name:
            目标 collection 名称。

        expected_metric_type:
            本次对照冻结的距离度量，Day43 固定为 COSINE。

    Raises:
        RuntimeError:
            collection 不存在、缺少 vector 索引，
            或者 metric_type 不符合冻结合同。
    """
    if not client.has_collection(collection_name):
        raise RuntimeError(f"collection 不存在：{collection_name}")

    # 第三方 pymilvus 调用：返回当前 collection 已创建的索引名称。
    index_names = client.list_indexes(
        collection_name=collection_name,
    )

    if "vector" not in index_names:
        raise RuntimeError(
            f"collection {collection_name} 缺少 vector 索引：actual_indexes={index_names}"
        )

    # 第三方 pymilvus 调用：读取 vector 索引的 metric、类型和构建状态。
    description = cast(
        dict[str, Any],
        client.describe_index(
            collection_name=collection_name,
            index_name="vector",
        ),
    )

    actual_metric_type = description.get("metric_type")

    if actual_metric_type != expected_metric_type:
        raise RuntimeError(
            f"collection {collection_name} 的 metric_type 不一致："
            f"expected={expected_metric_type}, "
            f"actual={actual_metric_type}"
        )

    index_state = description.get("state")

    if index_state != "Finished":
        raise RuntimeError(
            f"collection {collection_name} 的 vector 索引尚未完成：state={index_state!r}"
        )

    total_rows = description.get("total_rows")
    indexed_rows = description.get("indexed_rows")

    if isinstance(total_rows, bool) or not isinstance(total_rows, int) or total_rows < 0:
        raise RuntimeError(f"collection {collection_name} 的索引 total_rows 无效：{total_rows!r}")

    if isinstance(indexed_rows, bool) or not isinstance(indexed_rows, int) or indexed_rows < 0:
        raise RuntimeError(
            f"collection {collection_name} 的索引 indexed_rows 无效：{indexed_rows!r}"
        )

    if indexed_rows != total_rows:
        raise RuntimeError(
            f"collection {collection_name} 的 vector 索引行数未收敛："
            f"total_rows={total_rows}, indexed_rows={indexed_rows}"
        )


def build_target_report(
    *,
    data_version: str,
    question_path: Path,
    collection_name: str,
    collection_row_count: int,
    workspace_filter_supported: bool,
    store_adapter: str,
    run_order: int,
    model_load_ms: float,
    evaluation_run: Mapping[str, Any],
    question_sha256: str,
    manifest_sha256: str | None,
    known_data_limitations: Sequence[str],
    git_state: Mapping[str, str | bool],
) -> dict[str, Any]:
    """为单个数据版本组装包含完整配置和逐题结果的评测报告。

    Args:
        data_version:
            当前被评测的数据版本。

        question_path:
            当前版本对应的题集路径。

        collection_name:
            当前版本使用的 collection。

        collection_row_count:
            开始与结束均已验证的 collection 行数。

        workspace_filter_supported:
            collection 是否真实存储 workspace_id。

        store_adapter:
            Retriever 下方实际使用的 store 适配器说明。

        run_order:
            本次进程中的实际执行顺序。

        model_load_ms:
            两个版本共用模型的一次加载耗时。

        evaluation_run:
            evaluate_question_set_with_retriever 的完整返回结果。

        question_sha256:
            当前题集文件指纹。

        manifest_sha256:
            v2 manifest 指纹；legacy 没有该文件时为 None。

        known_data_limitations:
            当前版本已经确认的限制。

        git_state:
            当前 git commit 和工作区状态。

    Returns:
        可以原子写入 JSON 的完整单版本报告。
    """
    return {
        "model_load_ms": model_load_ms,
        "warmup_ms": evaluation_run["warmup_ms"],
        "scope": {
            "data_version": data_version,
            "question_set": str(question_path),
            "question_set_sha256": question_sha256,
            "model": EMBEDDING_MODEL_NAME,
            "vector_dim": EMBEDDING_VECTOR_DIM,
            "collection": collection_name,
            "row_count": collection_row_count,
            "top_k": TOP_K,
            "metric_type": METRIC_TYPE,
            "retriever": "app.rag.retriever.Retriever",
            "store_adapter": store_adapter,
            "trusted_workspace_id": DEMO_WORKSPACE_ID,
            "real_workspace_filter_supported": (workspace_filter_supported),
            "manifest_sha256": manifest_sha256,
            "run_order": run_order,
            "latency_scope": (
                "各版本单独 warm-up 后的非 system_error 单题；"
                "包含 query 校验、query embedding、filter 构造、"
                "Milvus search 和 SearchHit 合同转换"
            ),
            "known_data_limitations": list(known_data_limitations),
            **git_state,
        },
        "metrics": evaluation_run["metrics"],
        "results": evaluation_run["results"],
    }


def _rank_change(
    legacy_rank: object,
    v2_rank: object,
) -> str:
    """把一道题的 legacy/v2 相关证据排名变化转换成可读分类。

    Args:
        legacy_rank:
            legacy 第一个相关证据排名；未命中时为 None。

        v2_rank:
            v2 第一个相关证据排名；未命中时为 None。

    Returns:
        improved:
            v2 排名数字更小，或者 legacy 未命中而 v2 命中。

        unchanged:
            两个版本排名相同，包含两边都未命中。

        regressed:
            v2 排名数字更大，或者 legacy 命中而 v2 未命中。

    Limitations:
        bool 虽然是 Python 的 int 子类，但不是合法排名，因此显式拒绝。
        其他未知类型不会参与数值比较，统一返回 unchanged。
    """
    if isinstance(legacy_rank, int) and not isinstance(legacy_rank, bool):
        if isinstance(v2_rank, int) and not isinstance(v2_rank, bool):
            if v2_rank < legacy_rank:
                return "improved"

            if v2_rank > legacy_rank:
                return "regressed"

            return "unchanged"

        if v2_rank is None:
            return "regressed"

        return "unchanged"

    if legacy_rank is None:
        if isinstance(v2_rank, int) and not isinstance(v2_rank, bool):
            return "improved"

        return "unchanged"

    return "unchanged"


def build_comparison_report(
    *,
    legacy_report: Mapping[str, Any],
    v2_report: Mapping[str, Any],
    day42_baseline_sha256: str,
    manifest_sha256: str,
) -> dict[str, Any]:
    """组装 legacy/v2 指标差值和逐题排名对照，不自动判定指标好坏。

    Args:
        legacy_report:
            本次统一 Retriever 重跑得到的 legacy 原始报告。

        v2_report:
            本次统一 Retriever 得到的 v2 原始报告。

        day42_baseline_sha256:
            只读保护的原 Day42 baseline 文件指纹。

        manifest_sha256:
            已重新加载验证的 v2 manifest 文件指纹。

    Returns:
        包含冻结配置、两侧指标、指标差值和12题逐题差异的汇总报告。

    Raises:
        ValueError:
            两侧结果数量或 case_id 顺序不一致。
    """
    legacy_metrics = cast(
        Mapping[str, Any],
        legacy_report["metrics"],
    )
    v2_metrics = cast(
        Mapping[str, Any],
        v2_report["metrics"],
    )
    legacy_results = cast(
        list[dict[str, Any]],
        legacy_report["results"],
    )
    v2_results = cast(
        list[dict[str, Any]],
        v2_report["results"],
    )

    if len(legacy_results) != len(v2_results):
        raise ValueError(
            f"legacy/v2 逐题结果数量不一致：legacy={len(legacy_results)}, v2={len(v2_results)}"
        )

    metric_names = (
        "hit_at_1",
        "hit_at_5",
        "mrr",
    )
    metric_deltas: dict[str, float] = {}

    for metric_name in metric_names:
        legacy_value = legacy_metrics.get(metric_name)
        v2_value = v2_metrics.get(metric_name)

        if not isinstance(legacy_value, (int, float)):
            raise ValueError(f"legacy metrics.{metric_name} 不是数值")
        if not isinstance(v2_value, (int, float)):
            raise ValueError(f"v2 metrics.{metric_name} 不是数值")

        metric_deltas[f"{metric_name}_delta_v2_minus_legacy"] = float(v2_value) - float(
            legacy_value
        )

    per_question: list[dict[str, Any]] = []

    for legacy_result, v2_result in zip(
        legacy_results,
        v2_results,
        strict=True,
    ):
        legacy_case_id = legacy_result.get("case_id")
        v2_case_id = v2_result.get("case_id")

        if legacy_case_id != v2_case_id:
            raise ValueError(
                f"legacy/v2 逐题结果顺序不一致：legacy={legacy_case_id!r}, v2={v2_case_id!r}"
            )

        legacy_hits = cast(
            list[dict[str, Any]],
            legacy_result.get("hits", []),
        )
        v2_hits = cast(
            list[dict[str, Any]],
            v2_result.get("hits", []),
        )

        legacy_rank = legacy_result.get("relevant_rank")
        v2_rank = v2_result.get("relevant_rank")

        per_question.append(
            {
                "case_id": legacy_case_id,
                "query": legacy_result.get("query"),
                "answerable": legacy_result.get("answerable"),
                "legacy_status": legacy_result.get("status"),
                "v2_status": v2_result.get("status"),
                "legacy_relevant_rank": legacy_rank,
                "v2_relevant_rank": v2_rank,
                "rank_change": _rank_change(
                    legacy_rank,
                    v2_rank,
                ),
                "legacy_top_chunk_ids": [hit.get("chunk_id") for hit in legacy_hits],
                "v2_top_chunk_ids": [hit.get("chunk_id") for hit in v2_hits],
            }
        )

    return {
        "comparison_contract": {
            "same_query_text": True,
            "same_embedding_model": EMBEDDING_MODEL_NAME,
            "same_vector_dim": EMBEDDING_VECTOR_DIM,
            "same_metric_type": METRIC_TYPE,
            "same_top_k": TOP_K,
            "same_retriever": "app.rag.retriever.Retriever",
            "same_evaluation_functions": True,
            "same_warmup_policy": True,
            "legacy_workspace_compatibility": (
                "legacy collection 不含 workspace_id；"
                "LegacyComparisonStore 只移除已验证的固定 workspace 条件，"
                "并保留 source_file 条件"
            ),
        },
        "protected_inputs": {
            "day42_baseline_path": str(DAY42_BASELINE_PATH),
            "day42_baseline_sha256": day42_baseline_sha256,
            "v2_manifest_path": str(MANIFEST_PATH),
            "v2_manifest_sha256": manifest_sha256,
        },
        "legacy": {
            "result_path": str(LEGACY_RESULT_PATH),
            "metrics": legacy_metrics,
        },
        "v2": {
            "result_path": str(V2_RESULT_PATH),
            "metrics": v2_metrics,
        },
        "metric_deltas": metric_deltas,
        "per_question": per_question,
        "interpretation_limitations": [
            "指标没有提升不代表 Day43 数据修复失败",
            "本次不因结果好坏调整模型、top_k、chunk 参数或阈值",
            "延迟仅为本机单次探索性结果，不是正式性能基准",
            "本报告只记录差异；Day43 只人工分析一个代表性差异",
        ],
    }


def _print_target_results(
    label: str,
    report: Mapping[str, Any],
) -> None:
    """打印一个数据版本的逐题结果和汇总指标。"""
    print()
    print(f"=== {label} ===")

    results = cast(list[dict[str, Any]], report["results"])

    for result in results:
        print_question_result(result)

    metrics = cast(Mapping[str, Any], report["metrics"])

    print(
        f"{label}: "
        f"Hit@1={float(metrics['hit_at_1']):.4f} "
        f"Hit@5={float(metrics['hit_at_5']):.4f} "
        f"MRR={float(metrics['mrr']):.4f}"
    )
    print(f"{label}: P50={metrics['exploratory_p50_ms']} ms P95={metrics['exploratory_p95_ms']} ms")


def main() -> int:
    """执行真实 legacy/v2 同配置检索对照并发布三份新报告。"""
    result_paths = (
        LEGACY_RESULT_PATH,
        V2_RESULT_PATH,
        COMPARISON_RESULT_PATH,
    )
    ensure_result_paths_are_new(result_paths)

    day42_baseline_sha256_before = calculate_file_sha256(DAY42_BASELINE_PATH)
    manifest_sha256 = calculate_file_sha256(MANIFEST_PATH)
    legacy_question_sha256 = calculate_file_sha256(LEGACY_QUESTION_PATH)
    v2_question_sha256 = calculate_file_sha256(V2_QUESTION_PATH)

    expected_document_ids = {document["document_id"] for document in REAL_DOCUMENTS}

    manifest = load_v2_manifest(
        MANIFEST_PATH,
        project_root=PROJECT_ROOT,
        expected_build_id=BUILD_ID,
        expected_workspace_id=DEMO_WORKSPACE_ID,
        expected_collection_name=V2_COLLECTION_NAME,
        expected_document_ids=expected_document_ids,
    )

    manifest_collection = manifest.get("collection")
    if not isinstance(manifest_collection, dict):
        raise RuntimeError("已验证 manifest 缺少 collection 字典")

    expected_v2_row_count = manifest_collection.get("actual_row_count")
    if (
        isinstance(expected_v2_row_count, bool)
        or not isinstance(expected_v2_row_count, int)
        or expected_v2_row_count < 1
    ):
        raise RuntimeError("manifest.collection.actual_row_count 必须是正整数")

    legacy_questions = load_questions(LEGACY_QUESTION_PATH)
    v2_questions = load_questions(V2_QUESTION_PATH)

    validate_comparable_question_sets(
        legacy_questions,
        v2_questions,
    )

    model_load_start = perf_counter()

    # 这一导入会初始化冻结的 BAAI/bge-m3 embedding 模型。
    from app.rag.embed import embed

    model_load_ms = (perf_counter() - model_load_start) * 1000

    legacy_run: dict[str, Any]
    v2_run: dict[str, Any]
    legacy_row_count_before: int
    legacy_row_count_after: int
    v2_row_count_before: int
    v2_row_count_after: int

    client = get_client(str(MILVUS_DB_PATH))

    try:
        if not client.has_collection(LEGACY_COLLECTION_NAME):
            raise RuntimeError(f"legacy collection 不存在：{LEGACY_COLLECTION_NAME}")
        if not client.has_collection(V2_COLLECTION_NAME):
            raise RuntimeError(f"v2 collection 不存在：{V2_COLLECTION_NAME}")

        client.load_collection(LEGACY_COLLECTION_NAME)
        client.load_collection(V2_COLLECTION_NAME)

        legacy_row_count_before = count_rows(
            client,
            LEGACY_COLLECTION_NAME,
        )
        v2_row_count_before = count_rows(
            client,
            V2_COLLECTION_NAME,
        )

        if legacy_row_count_before != EXPECTED_LEGACY_ROW_COUNT:
            raise RuntimeError(
                "legacy collection 行数偏离冻结起点："
                f"expected={EXPECTED_LEGACY_ROW_COUNT}, "
                f"actual={legacy_row_count_before}"
            )

        if v2_row_count_before != expected_v2_row_count:
            raise RuntimeError(
                "v2 collection 行数与 manifest 不一致："
                f"expected={expected_v2_row_count}, "
                f"actual={v2_row_count_before}"
            )

        validate_collection_metric(
            client,
            LEGACY_COLLECTION_NAME,
            expected_metric_type=METRIC_TYPE,
        )
        validate_collection_metric(
            client,
            V2_COLLECTION_NAME,
            expected_metric_type=METRIC_TYPE,
        )

        context = TrustedContext(DEMO_WORKSPACE_ID)

        legacy_store = LegacyComparisonStore(
            MilvusSearchStore(
                client,
                LEGACY_COLLECTION_NAME,
            ),
            expected_workspace_id=DEMO_WORKSPACE_ID,
        )
        legacy_retriever = Retriever(
            embed,
            legacy_store,
        )

        v2_store = MilvusSearchStore(
            client,
            V2_COLLECTION_NAME,
        )
        v2_retriever = Retriever(
            embed,
            v2_store,
        )

        legacy_run = evaluate_question_set_with_retriever(
            legacy_questions,
            retriever=legacy_retriever,
            context=context,
            top_k=TOP_K,
        )

        v2_run = evaluate_question_set_with_retriever(
            v2_questions,
            retriever=v2_retriever,
            context=context,
            top_k=TOP_K,
        )

        legacy_row_count_after = count_rows(
            client,
            LEGACY_COLLECTION_NAME,
        )
        v2_row_count_after = count_rows(
            client,
            V2_COLLECTION_NAME,
        )

        if legacy_row_count_after != legacy_row_count_before:
            raise RuntimeError(
                "评测期间 legacy collection 行数发生变化："
                f"before={legacy_row_count_before}, "
                f"after={legacy_row_count_after}"
            )

        if v2_row_count_after != v2_row_count_before:
            raise RuntimeError(
                "评测期间 v2 collection 行数发生变化："
                f"before={v2_row_count_before}, "
                f"after={v2_row_count_after}"
            )
    finally:
        client.close()

    day42_baseline_sha256_after = calculate_file_sha256(DAY42_BASELINE_PATH)

    if day42_baseline_sha256_after != day42_baseline_sha256_before:
        raise RuntimeError("Day42 baseline 在评测期间发生变化，拒绝发布对照结果")

    git_state = get_git_state()

    legacy_report = build_target_report(
        data_version="legacy_7451_day41",
        question_path=LEGACY_QUESTION_PATH,
        collection_name=LEGACY_COLLECTION_NAME,
        collection_row_count=legacy_row_count_after,
        workspace_filter_supported=False,
        store_adapter=("LegacyComparisonStore(MilvusSearchStore)"),
        run_order=1,
        model_load_ms=model_load_ms,
        evaluation_run=legacy_run,
        question_sha256=legacy_question_sha256,
        manifest_sha256=None,
        known_data_limitations=[
            "旧表格 embedding text 大量退化为第N页表格",
            "旧表体主要只存在于 table_md",
            "旧 section 可能与真实章节不一致",
            "旧 chunk_id 不是当前稳定 ID 构建流程的产物",
            "旧 collection 没有 workspace_id 和 document_id",
        ],
        git_state=git_state,
    )

    v2_report = build_target_report(
        data_version=BUILD_ID,
        question_path=V2_QUESTION_PATH,
        collection_name=V2_COLLECTION_NAME,
        collection_row_count=v2_row_count_after,
        workspace_filter_supported=True,
        store_adapter="MilvusSearchStore",
        run_order=2,
        model_load_ms=model_load_ms,
        evaluation_run=v2_run,
        question_sha256=v2_question_sha256,
        manifest_sha256=manifest_sha256,
        known_data_limitations=[
            "当前只有固定 demo workspace，不是完整多用户系统",
            "本次只验证检索，不生成 RAG 答案",
            "本次不做 hybrid、rerank 或阈值调优",
        ],
        git_state=git_state,
    )

    comparison_report = build_comparison_report(
        legacy_report=legacy_report,
        v2_report=v2_report,
        day42_baseline_sha256=day42_baseline_sha256_before,
        manifest_sha256=manifest_sha256,
    )

    legacy_write_result = write_evaluation_report(
        LEGACY_RESULT_PATH,
        legacy_report,
    )
    v2_write_result = write_evaluation_report(
        V2_RESULT_PATH,
        v2_report,
    )
    comparison_write_result = write_evaluation_report(
        COMPARISON_RESULT_PATH,
        comparison_report,
    )

    _print_target_results("legacy", legacy_report)
    _print_target_results("v2", v2_report)

    print()
    print(
        json.dumps(
            {
                "legacy_result": legacy_write_result,
                "v2_result": v2_write_result,
                "comparison_result": comparison_write_result,
                "legacy_row_count": legacy_row_count_after,
                "v2_row_count": v2_row_count_after,
                "day42_baseline_preserved": True,
                "manifest_revalidated": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    all_results = [
        *cast(list[dict[str, Any]], legacy_report["results"]),
        *cast(list[dict[str, Any]], v2_report["results"]),
    ]
    system_errors = [result for result in all_results if result.get("status") == "system_error"]

    if system_errors:
        print(f"评测报告已保留，但存在 {len(system_errors)} 个 system_error")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
