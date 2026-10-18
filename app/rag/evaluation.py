from collections.abc import Collection, Sequence
from typing import Literal

EvaluationStatus = Literal[
    "normal",
    "filtered_empty",
    "system_error",
    "recall_error",
]


def first_relevant_rank(retrieved_ids: Sequence[str], relevant_ids: Collection[str]) -> int | None:
    """返回第一个相关 chunk 的排名，没有就返回 None"""
    for i, retrieved_id in enumerate(retrieved_ids):
        if retrieved_id in relevant_ids:
            return i + 1
    return None


def classify_result_status(
    *,
    answerable: bool,
    relevant_rank: int | None,
    hit_count: int,
    has_filter: bool,
    system_error: Exception | None = None,
) -> EvaluationStatus:
    """根据答案标注 命中 过滤 和异常确定一次检索的结果状态

    Args:
        answerable: 答案标注
        relevant_rank: 第一个相关 chunk 的排名
        hit_count: 命中 chunk 数量
        has_filter: 是否存在过滤
        system_error: 系统异常
    """
    if system_error is not None:
        return "system_error"
    if hit_count == 0 and has_filter:
        return "filtered_empty"
    if answerable and relevant_rank is None:
        return "recall_error"
    return "normal"
