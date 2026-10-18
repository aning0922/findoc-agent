import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from time import perf_counter
from typing import Any, cast

from app.rag.evaluation import classify_result_status, first_relevant_rank
from app.rag.metrics import (
    RankingCase,
    mean_hit_at_k,
    mean_reciprocal_rank,
)
from app.rag.retriever import (
    Retriever,
    SearchFilters,
    SearchHit,
    SearchStore,
    TrustedContext,
)
from scripts.evaluate_day42_retrieval import (
    check_result_metadata,
    summarize_latency,
)


def adapt_filter_for_legacy(
    filter_expression: str,
    *,
    expected_workspace_id: str,
) -> str:
    """把 Retriever 生成的过滤表达式转换成 legacy collection 支持的形式。

    Args:
        filter_expression:
            Retriever 已生成的可信过滤表达式。只允许包含预期 workspace_id，
            以及可选的 source_file 等值条件。

        expected_workspace_id:
            本次实验固定的可信 workspace_id。输入表达式中的 workspace_id
            必须与它完全一致。

    Returns:
        legacy collection 可执行的过滤表达式。没有 source_file 时返回空字符串；
        存在 source_file 时返回完整的 source_file 等值条件。

    Raises:
        TypeError:
            filter_expression 或 expected_workspace_id 不是字符串。

        ValueError:
            参数为空、workspace_id 不匹配、source_file 不是非空字符串，
            或者表达式包含 legacy 兼容层不允许处理的未知条件。
    """
    if not isinstance(filter_expression, str):
        raise TypeError("filter_expression 必须是字符串")
    if not filter_expression:
        raise ValueError("filter_expression 不能为空")

    if not isinstance(expected_workspace_id, str):
        raise TypeError("expected_workspace_id 必须是字符串")
    if not expected_workspace_id.strip():
        raise ValueError("expected_workspace_id 不能为空字符串")

    expected_workspace_clause = (
        f"workspace_id == {json.dumps(expected_workspace_id, ensure_ascii=False)}"
    )

    if filter_expression == expected_workspace_clause:
        return ""

    expected_prefix = f"{expected_workspace_clause} and "
    if not filter_expression.startswith(expected_prefix):
        raise ValueError(
            f"过滤表达式中的 workspace_id 与预期不一致，或者表达式格式不受支持：{filter_expression}"
        )

    source_file_clause = filter_expression[len(expected_prefix) :]
    source_file_prefix = "source_file == "

    if not source_file_clause.startswith(source_file_prefix):
        raise ValueError(
            f"legacy 兼容层只允许保留 source_file 条件，不支持当前过滤表达式：{filter_expression}"
        )

    encoded_source_file = source_file_clause[len(source_file_prefix) :]

    try:
        source_file = json.loads(encoded_source_file)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "source_file 条件不是单个合法的 JSON 字符串，"
            "可能包含额外或未知过滤条件："
            f"{filter_expression}"
        ) from exc

    if not isinstance(source_file, str) or not source_file.strip():
        raise ValueError("source_file 过滤值必须是非空字符串")

    canonical_source_file_clause = f"source_file == {json.dumps(source_file, ensure_ascii=False)}"

    if source_file_clause != canonical_source_file_clause:
        raise ValueError(f"source_file 条件格式不符合 Retriever 的规范输出：{filter_expression}")

    return canonical_source_file_clause


class LegacyComparisonStore:
    """让 legacy collection 接入当前 Retriever 的 Day43 实验适配器。

    该类只解决 legacy collection 缺少 workspace_id 的历史兼容问题。
    它验证并移除 workspace_id 条件，保留 source_file 条件，然后把查询
    原样委托给真实 SearchStore。

    该类不会修改查询向量、top_k、命中顺序、分数或命中内容，也不能用于
    v2 生产检索。
    """

    def __init__(
        self,
        delegate: SearchStore,
        *,
        expected_workspace_id: str,
    ) -> None:
        """绑定真实检索存储和本次实验预期的 workspace_id。

        Args:
            delegate:
                实际执行检索的 SearchStore。真实评测时传入绑定 legacy
                collection 的 MilvusSearchStore。

            expected_workspace_id:
                Retriever 必须使用的固定可信 workspace_id。

        Raises:
            TypeError:
                expected_workspace_id 不是字符串。

            ValueError:
                expected_workspace_id 是空字符串。
        """
        if not isinstance(expected_workspace_id, str):
            raise TypeError("expected_workspace_id 必须是字符串")
        if not expected_workspace_id.strip():
            raise ValueError("expected_workspace_id 不能为空字符串")

        self._delegate = delegate
        self._expected_workspace_id = expected_workspace_id

    def search(
        self,
        query_vector: list[float],
        *,
        top_k: int,
        filter_expression: str,
    ) -> list[Mapping[str, Any]]:
        """转换 legacy 不支持的 workspace 条件并委托真实存储执行检索。

        Args:
            query_vector:
                Retriever 生成的查询向量，本方法不修改它。

            top_k:
                Retriever 要求的最大命中数量，本方法不修改它。

            filter_expression:
                Retriever 生成的 workspace_id 和可选 source_file 条件。

        Returns:
            delegate 返回的原始命中列表，不修改命中内容和顺序。

        Raises:
            TypeError:
                过滤表达式参数类型错误。

            ValueError:
                过滤表达式不符合 legacy 兼容合同。

            Exception:
                delegate 的检索异常原样向上传递，不在这里吞掉。
        """
        adapted_filter = adapt_filter_for_legacy(
            filter_expression,
            expected_workspace_id=self._expected_workspace_id,
        )

        return self._delegate.search(
            query_vector,
            top_k=top_k,
            filter_expression=adapted_filter,
        )


def evaluate_question_with_retriever(
    question: Mapping[str, Any],
    *,
    retriever: Retriever,
    context: TrustedContext,
    top_k: int,
) -> tuple[dict[str, Any], RankingCase | None]:
    """通过统一 Retriever 执行一道题并返回逐题结果和可选指标样本。

    Args:
        question:
            已通过题集加载合同校验的一道问题，包含 query、answerable、
            relevant_chunk_ids、expected_metadata 和可选 source_file。

        retriever:
            当前数据版本使用的 Retriever。legacy 和 v2 使用同一个类，
            只允许底层绑定的 collection 或兼容 store 不同。

        context:
            服务端可信检索上下文。本次固定使用
            workspace_id="demo-financial-reports"。

        top_k:
            最大召回数量。本次 legacy 和 v2 都必须固定为 5。

    Returns:
        二元组：
        1. 可序列化的逐题评测结果；
        2. 可回答问题对应的 RankingCase；无答案题返回 None。

    Failure:
        Retriever 抛出的异常会被记录为 system_error，使后续问题能够继续执行；
        异常不会被伪装成普通的 recall_error。
    """
    question_start = perf_counter()

    query = cast(str, question["query"])
    answerable = cast(bool, question["answerable"])
    source_file = cast(str | None, question.get("source_file"))
    relevant_ids = frozenset(cast(list[str], question.get("relevant_chunk_ids", [])))

    filters = None if source_file is None else SearchFilters(source_file=source_file)

    hits: list[SearchHit] = []
    hit_rows: list[dict[str, Any]] = []
    retrieved_ids: list[str] = []
    relevant_rank: int | None = None
    error: Exception | None = None

    try:
        hits = retriever.retrieve(
            query,
            context=context,
            top_k=top_k,
            filters=filters,
        )

        hit_rows = [asdict(hit) for hit in hits]
        retrieved_ids = [hit.chunk_id for hit in hits]
        relevant_rank = first_relevant_rank(
            retrieved_ids=retrieved_ids,
            relevant_ids=relevant_ids,
        )
    except Exception as caught_error:
        error = caught_error
        hits = []
        hit_rows = []
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
        question=question,
        hits=hit_rows,
        retrieval_succeeded=error is None,
    )

    serialized_hits: list[dict[str, Any]] = []

    for rank, hit in enumerate(hits, start=1):
        serialized_hits.append(
            {
                "rank": rank,
                "chunk_id": hit.chunk_id,
                "score": hit.score,
                "page": hit.page,
                "source_file": hit.source_file,
                "type": hit.type,
                "section": hit.section,
                "text_preview": hit.text[:120],
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


def run_retriever_warmup(
    *,
    question: Mapping[str, Any],
    retriever: Retriever,
    context: TrustedContext,
    top_k: int,
) -> float:
    """通过统一 Retriever 执行一次预热并返回预热耗时。

    Args:
        question:
            用于预热的第一道已校验问题。

        retriever:
            当前数据版本绑定完成的 Retriever。

        context:
            本次评测固定使用的可信 workspace 上下文。

        top_k:
            与正式评测完全相同的召回数量。

    Returns:
        包含 query embedding 和向量检索的预热耗时，单位为毫秒。

    Failure:
        预热失败时异常直接向上传递。本次数据版本不能在预热失败的情况下
        继续生成看似正常的评测报告。
    """
    query = cast(str, question["query"])
    source_file = cast(str | None, question.get("source_file"))

    filters = None if source_file is None else SearchFilters(source_file=source_file)

    start = perf_counter()

    retriever.retrieve(
        query,
        context=context,
        top_k=top_k,
        filters=filters,
    )

    return (perf_counter() - start) * 1000


def evaluate_question_set_with_retriever(
    questions: Sequence[Mapping[str, Any]],
    *,
    retriever: Retriever,
    context: TrustedContext,
    top_k: int,
) -> dict[str, Any]:
    """通过统一 Retriever 评测一套问题并汇总排名指标与探索性延迟。

    Args:
        questions:
            已经过题集合同校验的问题序列。第一题同时用于一次预热。

        retriever:
            当前数据版本绑定完成的 Retriever。

        context:
            本次评测固定使用的可信 workspace 上下文。

        top_k:
            每道题最大召回数量。legacy 和 v2 必须使用相同值。

    Returns:
        包含 warmup_ms、metrics 和逐题 results 的可序列化字典。
        warm-up 不进入正式逐题结果，也不进入 P50/P95。

    Raises:
        ValueError:
            题集为空，或者题集中没有任何可回答问题，无法计算排名指标。
    """
    if not questions:
        raise ValueError("questions 不能为空，无法执行检索评测")

    warmup_ms = run_retriever_warmup(
        question=questions[0],
        retriever=retriever,
        context=context,
        top_k=top_k,
    )

    results: list[dict[str, Any]] = []
    metric_cases: list[RankingCase] = []

    for question in questions:
        result, metric_case = evaluate_question_with_retriever(
            question,
            retriever=retriever,
            context=context,
            top_k=top_k,
        )
        results.append(result)

        if metric_case is not None:
            metric_cases.append(metric_case)

    if not metric_cases:
        raise ValueError("questions 中没有可回答问题，无法计算 Hit@K 和 MRR")

    metrics: dict[str, int | float | None] = {
        "question_count": len(questions),
        "answerable_count": len(metric_cases),
        "hit_at_1": mean_hit_at_k(metric_cases, 1),
        "hit_at_5": mean_hit_at_k(metric_cases, 5),
        "mrr": mean_reciprocal_rank(metric_cases),
        **summarize_latency(results),
    }

    return {
        "warmup_ms": warmup_ms,
        "metrics": metrics,
        "results": results,
    }
