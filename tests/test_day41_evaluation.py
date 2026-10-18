import pytest

from app.rag.evaluation import first_relevant_rank, classify_result_status


def test_first_relevant_rank_returns_one_based_rank_or_none() -> None:
    """相关 chunk 应返回一基排名 没有就返回 None"""
    assert first_relevant_rank(retrieved_ids=["X", "R1", "R2"], relevant_ids={"R1", "R2"}) == 2
    assert first_relevant_rank(["X", "Y"], {"R1"}) is None
    assert first_relevant_rank(["X", "Y"], set()) is None


@pytest.mark.parametrize(
    (
        "answerable",
        "relevant_rank",
        "hit_count",
        "has_filter",
        "system_error",
        "expected",
    ),
    [
        (True, 1, 5, False, None, "normal"),
        (True, None, 0, True, None, "filtered_empty"),
        (True, None, 5, False, None, "recall_error"),
        (True, None, 0, False, ConnectionError("offline"), "system_error"),
        (False, None, 5, False, None, "normal"),
    ],
)
def test_classify_result_status_uses_explicit_priority(
    answerable: bool,
    relevant_rank: int | None,
    hit_count: int,
    has_filter: bool,
    system_error: Exception | None,
    expected: str,
) -> None:
    """结果状态应按照系统错误，过滤为空，召回错误和正常的优先级分类"""
    actual = classify_result_status(
        answerable=answerable,
        relevant_rank=relevant_rank,
        hit_count=hit_count,
        has_filter=has_filter,
        system_error=system_error,
    )
    assert actual == expected
