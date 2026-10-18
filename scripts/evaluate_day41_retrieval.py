import json
from collections.abc import Callable, Mapping
from pathlib import Path
from time import perf_counter
from typing import Any, cast


from app.rag.evaluation import classify_result_status, first_relevant_rank
from app.rag.metrics import RankingCase, mean_hit_at_k, mean_reciprocal_rank
from app.rag.store import MilvusSearchStore, get_client

Embedder = Callable[[list[str]], list[list[float]]]


def load_questions(path: Path) -> list[dict[str, Any]]:
    """从 JSONL 加载 Day41 检索问题和人工相关性标注"""
    questions: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        question = cast(dict[str, Any], json.loads(line))
        questions.append(question)
    return questions


def build_legacy_source_filter(source_file: str | None) -> str:
    """为旧collection 构造当前 schema 支持的 source_file 过滤"""
    if source_file is None:
        return ""
    return f"source_file == {json.dumps(source_file, ensure_ascii=False)}"


def evaluate_question(
    question: dict[str, Any], *, embedder: Embedder, store: MilvusSearchStore, top_k: int
) -> tuple[dict[str, Any], RankingCase | None]:
    """运行一道真实检索题并返回逐题记录及可选指标样本"""
    question_start = perf_counter()

    query = cast(str, question["query"])
    answerable = cast(bool, question.get("answerable", False))
    source_file = cast(str | None, question.get("source_file"))
    relevant_ids = frozenset(cast(list[str], question.get("relevant_chunk_ids", [])))

    hits: list[Mapping[str, Any]] = []
    retrieved_ids: list[str] = []
    relevant_rank: int | None = None
    error: Exception | None = None
    try:
        query_vectors = embedder([query])
        if len(query_vectors) != 1 or not query_vectors[0]:
            raise ValueError("embedder 必须返回恰好一个非空查询向量")
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
                "text_preview": text[:80],
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
        "error": (None if error is None else f"{type(error).__name__}: {error}"),
    }

    metric_case: RankingCase | None = None
    if answerable:
        metric_case = (tuple(retrieved_ids), relevant_ids)

    return result, metric_case


def main() -> None:
    """运行六题真实检索 baseline，输出逐题结果和汇总指标"""
    model_start = perf_counter()
    from app.rag.embed import embed

    model_load_time = (perf_counter() - model_start) * 1000
    print(f"模型加载时间: {model_load_time:.2f} ms")

    questions = load_questions(Path("eval/day41_questions.jsonl"))
    client = get_client("./data/milvus.db")
    results: list[dict[str, Any]] = []
    metric_cases: list[RankingCase] = []

    try:
        client.load_collection("findoc")
        store = MilvusSearchStore(client, "findoc")
        for question in questions:
            result, metric_case = evaluate_question(question, embedder=embed, store=store, top_k=5)
            results.append(result)
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

    report = {
        "model_load_ms": model_load_time,
        "scope": {
            "collection": "findoc",
            "row_count": 7451,
            "top_k": 5,
            "real_workspace_filter_supported": False,
            "real_filter_fields": ["source_file"],
            "table_embedding_limitation": (
                "旧数据的表格 embedding text 多为页码标签，表体只在 table_md"
            ),
        },
        "metrics": metrics,
        "results": results,
    }

    output_path = Path("eval/day41_baseline.json")
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
