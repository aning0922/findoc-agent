import pytest
from app.rag.metrics import (
    RankingCase,
    hit_at_k,
    reciprocal_rank,
    mean_hit_at_k,
    mean_reciprocal_rank,
)


def test_single_query_hit_at_k_and_reciprocal_rank() -> None:
    """想关结果首次位于第二名的时候，hit@1 hit@5 和 RR 应该符合定义"""
    retrieved_ids = [
        "C-INTRO",
        "R-TABLE",
        "C-PROFIT",
        "R-REV",
        "C-RISK",
    ]
    relevant_ids = {"R-REV", "R-TABLE"}

    assert hit_at_k(retrieved_ids, relevant_ids, 1) == 0
    assert hit_at_k(retrieved_ids, relevant_ids, 5) == 1
    assert reciprocal_rank(retrieved_ids, relevant_ids) == 0.5


def test_aggregate_hit_at_k_and_mrr() -> None:
    """三个问题的平均 hit@1 hit@5和 mrr 应符合人工标注的结果"""
    cases: list[RankingCase] = [
        (["X", "R1"], {"R1"}),  # 第一个相关结果在第2名
        (["R2", "X"], {"R2"}),  # 第一个相关结果在第1名
        (["X", "Y", "Z"], {"R3"}),  # 未命中
    ]

    assert mean_hit_at_k(cases, 1) == pytest.approx(1 / 3)
    assert mean_hit_at_k(cases, 5) == pytest.approx(2 / 3)
    assert mean_reciprocal_rank(cases) == pytest.approx(0.5)


def test_empty_relevant_ids_are_rejected() -> None:
    """没有相关 chunk 的无答案题不能混入 hit@k 或 mrr"""
    with pytest.raises(ValueError, match="relevant"):
        hit_at_k(["C-1"], set(), 1)

    with pytest.raises(ValueError, match="relevant"):
        reciprocal_rank(["C-1"], set())

    with pytest.raises(ValueError, match="K 必须大于等于 1"):
        hit_at_k(["C-1"], {"R-1"}, 0)


def test_invalid_metric_collection_inputs_are_rejected() -> None:
    """布尔 K 和空问题集不应该进入平均指标计算"""
    with pytest.raises(TypeError, match="K 必须是整数"):
        hit_at_k(["C-1"], {"R-1"}, True)

    with pytest.raises(ValueError, match="cases 不能为空，无法计算平均检索指标"):
        mean_hit_at_k([], 1)

    with pytest.raises(ValueError, match="cases 不能为空，无法计算平均检索指标"):
        mean_reciprocal_rank([])
