import json
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from statistics import median, quantiles
from time import perf_counter
from typing import Any, cast

from app.rag.evaluation import classify_result_status, first_relevant_rank
from app.rag.metrics import RankingCase, mean_hit_at_k, mean_reciprocal_rank
from app.rag.retriever import SearchStore
from app.rag.store import MilvusSearchStore, get_client

Embedder = Callable[[list[str]], list[list[float]]]

QUESTION_PATH = Path("eval/day42_questions.jsonl")
OUTPUT_PATH = Path("eval/day42_baseline.json")
DB_PATH = "./data/milvus.db"
COLLECTION = "findoc"
MODEL_NAME = "BAAI/bge-m3"
TOP_K = 5
ROW_COUNT = 7451


def load_questions(path: Path) -> list[dict[str, Any]]:
    """从 json 加载 Day42 检索问题和人工相关性标注"""
    questions: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        question = cast(dict[str, Any], json.loads(line))

        if not question.get("case_id", "").strip():
            raise ValueError(f"第 {line_number} 行问题 JSON 格式错误: {line}")
        if not question.get("query", "").strip():
            raise ValueError(f"第 {line_number} 行问题 JSON 格式错误: {line}")
        if not question.get("category", "").strip():
            raise ValueError(f"第 {line_number} 行问题 JSON 格式错误: {line}")
        answerable = question.get("answerable", None)
        if answerable is None:
            raise ValueError(f"第 {line_number} 行问题 JSON 格式错误: {line}")
        if not isinstance(answerable, bool):
            raise ValueError(f"第 {line_number} 行问题 JSON 格式错误: {line}")
        relevant_chunk_ids = question.get("relevant_chunk_ids")
        if relevant_chunk_ids is None:
            raise ValueError(f"第 {line_number} 行问题 JSON 格式错误: {line}")
        if answerable:
            if len(relevant_chunk_ids) < 1:
                raise ValueError(f"第 {line_number} 行问题 JSON 格式错误: {line}")
        else:
            if len(relevant_chunk_ids) > 0:
                raise ValueError(f"第 {line_number} 行问题 JSON 格式错误: {line}")

        if question.get("ground_truth") is None:
            raise ValueError(f"第 {line_number} 行问题 JSON 格式错误: {line}")
        if question.get("expected_metadata") is None:
            raise ValueError(f"第 {line_number} 行问题 JSON 格式错误: {line}")
        if not isinstance(relevant_chunk_ids, list) or not all(
            isinstance(chunk_id, str) and chunk_id.strip() for chunk_id in relevant_chunk_ids
        ):
            raise ValueError(f"第 {line_number} 行问题 JSON 格式错误: {line}")

        ground_truth = question.get("ground_truth")
        if not isinstance(ground_truth, str) or not ground_truth.strip():
            raise ValueError(f"第 {line_number} 行问题 JSON 格式错误: {line}")

        expected_metadata = question.get("expected_metadata")
        if not isinstance(expected_metadata, dict):
            raise ValueError(f"第 {line_number} 行问题 JSON 格式错误: {line}")
        if answerable and not set(relevant_chunk_ids).issubset(expected_metadata):
            raise ValueError(f"第 {line_number} 行问题 JSON 格式错误: {line}")
        questions.append(question)
    return questions


def build_legacy_source_filter(source_file: str | None) -> str:
    """为旧 collection 构造当前 schema 支持的 source_file 过滤"""
    if source_file is None:
        return ""

    return f"source_file == {json.dumps(source_file, ensure_ascii=False)}"


def check_result_metadata(
    *, question: Mapping[str, Any], hits: Sequence[Mapping[str, Any]], retrieval_succeeded: bool
) -> dict[str, Any]:
    """检查结果元数据并返回结果字典
    Args:
        question: 检索问题
        hits: 检索结果
    Returns:
        dict[str, Any]: 结果字典
    """
    source_file_filter = cast(str | None, question.get("source_file"))
    answerable = cast(bool, question.get("answerable"))
    relevant_ids = set(cast(list[str], question.get("relevant_chunk_ids", [])))
    expected_metadata = cast(dict[str, dict[str, Any]], question.get("expected_metadata", {}))

    # 1.检查过滤后的所有 hits， 而不只是相关 hit
    if not retrieval_succeeded:
        filter_ok = None
    elif source_file_filter is None:
        filter_ok = None
    else:
        filter_ok = all(hit.get("source_file") == source_file_filter for hit in hits)

    relevant_hit_checks: list[dict[str, Any]] = []

    for hit in hits:
        chunk_id = str(hit.get("chunk_id", ""))
        if chunk_id not in relevant_ids:
            continue

        expected = expected_metadata.get(chunk_id, {})
        mismatches: dict[str, dict[str, Any]] = {}
        for key, expected_value in expected.items():
            actual_value = hit.get(key)
            if key not in hit or actual_value != expected_value:
                mismatches[key] = {
                    "expected": expected_value,
                    "actual": actual_value,
                }

        relevant_hit_checks.append(
            {
                "chunk_id": chunk_id,
                "ok": not mismatches,
                "mismatches": mismatches,
            }
        )

    if not answerable:
        status = "not_applicable"
    elif not relevant_hit_checks:
        status = "not_observed"
    elif all(check["ok"] for check in relevant_hit_checks):
        status = "passed"
    else:
        status = "failed"

    return {
        "filter_ok": filter_ok,
        "relevant_metadata_status": status,
        "relevant_hit_checks": relevant_hit_checks,
    }


def evaluate_question(
    question: dict[str, Any], *, embedder: Embedder, store: SearchStore, top_k: int
) -> tuple[dict[str, Any], RankingCase | None]:
    """运行一道真实检索题并返回逐题记录及可选指标样本"""
    question_start = perf_counter()

    query = cast(str, question["query"])
    answerable = cast(bool, question["answerable"])
    source_file = cast(str | None, question.get("source_file"))
    relevant_ids = frozenset(cast(list[str], question.get("relevant_chunk_ids", [])))

    hits: list[Mapping[str, Any]] = []
    retrieved_ids: list[str] = []
    relevant_rank: int | None = None
    error: Exception | None = None

    try:
        query_vectors = embedder([query])
        if len(query_vectors) != 1 or not query_vectors[0]:
            raise ValueError("embedder必须返回恰好一个非空查询向量")

        filter_expression = build_legacy_source_filter(source_file)

        hits = store.search(query_vectors[0], top_k=top_k, filter_expression=filter_expression)

        retrieved_ids = [str(hit["chunk_id"]) for hit in hits]

        relevant_rank = first_relevant_rank(retrieved_ids=retrieved_ids, relevant_ids=relevant_ids)

    except Exception as caught_error:
        error = caught_error
        hits = []
        retrieved_ids = []
        relevant_rank = None

    latency_ms = (perf_counter() - question_start) * 1000

    status = classify_result_status(
        answerable=answerable,
        relevant_rank=relevant_rank,
        hit_count=len(hits),
        has_filter=source_file is not None,
        system_error=error,
    )

    metadata_check = check_result_metadata(
        question=question, hits=hits, retrieval_succeeded=error is None
    )

    serialized_hits: list[dict[str, Any]] = []

    for rank, hit in enumerate(hits, start=1):
        text = str(hit.get("text", ""))
        serialized_hits.append(
            {
                "rank": rank,
                "chunk_id": str(hit["chunk_id"]),
                "score": float(hit["score"]),
                "page": hit.get("page"),
                "source_file": hit.get("source_file"),
                "type": hit.get("type"),
                "section": hit.get("section"),
                "text_preview": text[:120],
            }
        )

    result: dict[str, Any] = {
        "case_id": question["case_id"],
        "query": query,
        "category": question["category"],
        "answerable": answerable,
        "source_file_filter": source_file,
        "status": status,
        "relevant_rank": relevant_rank,
        "latency_ms": latency_ms,
        "hits": serialized_hits,
        "metadata_check": metadata_check,
        "error": (None if error is None else f"{type(error).__name__}: {error}"),
    }
    metric_case: RankingCase | None = None

    if answerable:
        metric_case = (
            tuple(retrieved_ids),
            relevant_ids,
        )

    return result, metric_case


def run_warmup(
    *, question: Mapping[str, Any], embedder: Embedder, store: SearchStore, top_k: int
) -> float:
    """运行一次检索题的预加载热身，返回实际执行时间（毫秒）"""
    start = perf_counter()

    query = cast(str, question["query"])
    source_file = cast(str | None, question.get("source_file"))

    vectors = embedder([query])
    if len(vectors) != 1 or not vectors[0]:
        raise ValueError("warm-up embedder必须返回恰好一个非空查询向量")

    store.search(vectors[0], top_k=top_k, filter_expression=build_legacy_source_filter(source_file))

    return (perf_counter() - start) * 1000


def summarize_latency(results: Sequence[Mapping[str, Any]]) -> dict[str, int | float | None]:
    """汇总并总结检索题执行时间统计"""
    latencies = [
        float(result["latency_ms"]) for result in results if result["status"] != "system_error"
    ]

    if not latencies:
        return {
            "latency_sample_count": 0,
            "exploratory_p50_ms": None,
            "exploratory_p95_ms": None,
        }

    p50 = median(latencies)

    p95: float | None
    if len(latencies) < 2:
        p95 = None
    else:
        p95 = quantiles(latencies, n=100, method="inclusive")[94]

    return {
        "latency_sample_count": len(latencies),
        "exploratory_p50_ms": p50,
        "exploratory_p95_ms": p95,
    }


def print_question_result(result: Mapping[str, Any]) -> None:
    """打印逐题结果到控制台"""
    print(
        f"{result['case_id']} | "
        f"{result['status']} | "
        f"relevant_rank={result['relevant_rank']} | "
        f"latency={float(result['latency_ms']):.2f} ms"
    )

    hits = cast(list[dict[str, Any]], result["hits"])

    for hit in hits:
        print(
            f"  {hit['rank']}. "
            f"chunk_id={hit['chunk_id']} "
            f"score={float(hit['score']):.6f} "
            f"source={hit['source_file']} "
            f"page={hit['page']} "
            f"type={hit['type']}"
        )

    metadata = cast(dict[str, Any], result["metadata_check"])

    print(f"  metadata={metadata['relevant_metadata_status']} filter_ok={metadata['filter_ok']}")

    if result["error"] is not None:
        print(f"  error={result['error']}")


def get_git_state() -> dict[str, str | bool]:
    """获取 git 状态"""
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    status_output = subprocess.run(
        ["git", "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    return {
        "git_commit": commit,
        "working_tree_dirty": bool(status_output.strip()),
    }


def main() -> None:
    """主函数"""
    model_start = perf_counter()
    from app.rag.embed import embed

    model_load_ms = (perf_counter() - model_start) * 1000

    questions = load_questions(QUESTION_PATH)

    client = get_client(DB_PATH)
    results: list[dict[str, Any]] = []
    metric_cases: list[RankingCase] = []

    try:
        client.load_collection(COLLECTION)
        store = MilvusSearchStore(client, COLLECTION)

        warmup_ms = run_warmup(question=questions[0], embedder=embed, store=store, top_k=TOP_K)

        for question in questions:
            result, metric_case = evaluate_question(
                question=question, embedder=embed, store=store, top_k=TOP_K
            )
            results.append(result)
            print_question_result(result)
            if metric_case is not None:
                metric_cases.append(metric_case)

    finally:
        client.close()

    metrics = {
        "question_count": len(questions),
        "answerable_count": len(metric_cases),
        "hit_at_1": mean_hit_at_k(metric_cases, 1),
        "hit_at_5": mean_hit_at_k(metric_cases, 5),
        "mrr": mean_reciprocal_rank(metric_cases),
    }

    latency = summarize_latency(results)
    git_state = get_git_state()

    report = {
        "model_load_ms": model_load_ms,
        "warmup_ms": warmup_ms,
        "scope": {
            "data_version": "legacy_7451_day41",
            "question_set": str(QUESTION_PATH),
            "question_count": len(questions),
            "model": MODEL_NAME,
            "collection": COLLECTION,
            "row_count": ROW_COUNT,
            "top_k": TOP_K,
            "metric_type": "COSINE",
            "real_workspace_filter_supported": False,
            "real_filter_fields": ["source_file"],
            "latency_scope": (
                "warm-up后的非system_error单题，包含query embedding、filter构造和Milvus search"
            ),
            "known_data_limitations": [
                "旧表格embedding text多为第N页表格，表体只在table_md",
                "旧section可能与源文档真实章节不一致",
                "旧chunk_id不是当前稳定ID流程的迁移产物",
                "旧collection没有workspace_id",
            ],
            **git_state,
        },
        "metrics": {**metrics, **latency},
        "results": results,
    }

    OUTPUT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print()
    print(
        f"Hit@1={metrics['hit_at_1']:.4f} Hit@5={metrics['hit_at_5']:.4f} MRR={metrics['mrr']:.4f}"
    )
    print(
        f"探索性P50={latency['exploratory_p50_ms']} ms 探索性P95={latency['exploratory_p95_ms']} ms"
    )


if __name__ == "__main__":
    main()
