from math import sqrt

import pytest

from experiments.day39_vector_lab import cosine, top_k


def _make_candidates():
    """每次返回一份新的候选记录，避免测试之间共享被修改的数据。"""
    return [
        {"id": "d1", "metadata": "A", "vector": (4, 6)},
        {"id": "d2", "metadata": "B", "vector": (6, 9)},
        {"id": "d3", "metadata": "C", "vector": (-3, 2)},
        {"id": "d4", "metadata": "D", "vector": (-3, -1)},
    ]


def test_cosine_zero_score():
    """两个非零正交向量的 COSINE 应为 0。"""

    x = (1, 1)
    y = (-1, 1)
    expected = 0.0

    actual = cosine(x, y)
    assert actual == pytest.approx(expected)


def test_cosine_positive_non_extreme():
    """两个向量夹角为锐角且不完全同向时，COSINE 应严格介于 0 和 1 之间。"""

    x = (1, 1)
    y = (0, 1)
    expected = 1 / sqrt(2)

    actual = cosine(x, y)
    assert actual == pytest.approx(expected)


def test_cosine_negative_non_extreme():
    """两个向量夹角为钝角且不完全反向时，COSINE 应严格介于 -1 和 0 之间。"""

    x = (1, 1)
    y = (-1, 0)
    expected = -1 / sqrt(2)

    actual = cosine(x, y)
    assert actual == pytest.approx(expected)


def test_cosine_same_direction_different_magnitudes():
    """两个正比例同向向量即使模长不同，COSINE 也应为 1。"""

    x = (1, 1)
    y = (2, 2)
    expected = 1.0

    actual = cosine(x, y)
    assert actual == pytest.approx(expected)


def test_cosine_raises_for_zero_x():
    """x 为零向量导致分母为零时，应抛出 ValueError。"""

    x = (0, 0)
    y = (1, 1)

    with pytest.raises(ValueError):
        cosine(x, y)


def test_cosine_raises_for_zero_y():
    """y 为零向量导致分母为零时，应抛出 ValueError。"""

    x = (1, 1)
    y = (0, 0)

    with pytest.raises(ValueError):
        cosine(x, y)


def test_cosine_raises_for_dimension_mismatch():
    """两个向量维度不一致时，应抛出 ValueError。"""
    x = (1, 1)
    y = (1, 1, 1)

    with pytest.raises(ValueError):
        cosine(x, y)


def test_cosine_raises_for_empty_x():
    """x 为空向量时，应抛出 ValueError。"""
    x = ()
    y = (1, 1)

    with pytest.raises(ValueError):
        cosine(x, y)


def test_cosine_raises_for_empty_y():
    """y 为空向量时，应抛出 ValueError。"""
    x = (1, 1)
    y = ()

    with pytest.raises(ValueError):
        cosine(x, y)


def test_top_k_returns_ranked_complete_records():
    """返回按分数排列的前 k 条新记录，并保留完整必需字段。"""
    candidates = _make_candidates()
    query = (2, 3)
    k = 3
    expected = [
        {"id": "d1", "metadata": "A", "vector": (4, 6), "score": 1},
        {"id": "d2", "metadata": "B", "vector": (6, 9), "score": 1},
        {"id": "d3", "metadata": "C", "vector": (-3, 2), "score": 0},
    ]

    actual = top_k(query, candidates, k)

    assert actual == expected


def test_top_k_preserves_input_order_for_tied_scores():
    """候选同分时，应保留它们在输入列表中的相对顺序。"""
    candidates = _make_candidates()
    d1 = candidates[0]
    d2 = candidates[1]
    candidates[0] = d2
    candidates[1] = d1
    query = (2, 3)
    k = 3
    expected = [
        {"id": "d2", "metadata": "B", "vector": (6, 9), "score": 1},
        {"id": "d1", "metadata": "A", "vector": (4, 6), "score": 1},
        {"id": "d3", "metadata": "C", "vector": (-3, 2), "score": 0},
    ]

    actual = top_k(query, candidates, k)

    assert actual == expected


def test_top_k_does_not_mutate_candidates():
    """top-k 应返回新列表，且不改变原 candidates 的顺序或字段。"""
    candidates = _make_candidates()
    expected_original = _make_candidates()
    query = (2, 3)
    k = 3
    result = top_k(query, candidates, k)

    assert candidates == expected_original
    assert all("score" not in item for item in candidates)
    assert result is not candidates


def test_top_k_returns_empty_list_for_empty_candidates():
    """候选列表为空且 k 合法时，应返回空列表。"""
    candidates = []
    query = (2, 3)
    k = 2
    expected = []

    result = top_k(query, candidates, k)

    assert result == expected


def test_top_k_raises_for_zero_k():
    """k 为 0 时，应抛出 ValueError。"""
    candidates = _make_candidates()
    query = (2, 3)
    k = 0

    with pytest.raises(ValueError):
        top_k(query, candidates, k)


def test_top_k_raises_for_negative_k():
    """k 为负数时，应抛出 ValueError。"""
    candidates = _make_candidates()
    query = (2, 3)
    k = -1

    with pytest.raises(ValueError):
        top_k(query, candidates, k)


def test_top_k_raises_type_error_for_non_integer_k():
    """k 不是整数时，应抛出 TypeError。"""
    candidates = _make_candidates()
    query = (2, 3)
    k = 2.5

    with pytest.raises(TypeError):
        top_k(query, candidates, k)


def test_top_k_returns_all_when_k_exceeds_candidate_count():
    """k 大于候选数量时，应返回全部候选并保持正确排序。"""
    candidates = _make_candidates()
    query = (2, 3)
    k = 10

    result = top_k(query, candidates, k)

    assert len(result) == len(candidates)
    assert [item["id"] for item in result] == ["d1", "d2", "d3", "d4"]


def test_top_k_raises_for_candidate_dimension_mismatch():
    """任一候选向量与 query 维度不一致时，整体应抛出 ValueError。"""
    candidates = _make_candidates()
    candidates[2]["vector"] = (-3, 2, 3)
    query = (2, 3)
    k = 3

    with pytest.raises(ValueError):
        top_k(query, candidates, k)


def test_top_k_raises_for_zero_candidate_vector():
    """任一候选向量为零向量时，整体应抛出 ValueError。"""
    candidates = _make_candidates()
    candidates[2]["vector"] = (0, 0)
    query = (2, 3)
    k = 3

    with pytest.raises(ValueError):
        top_k(query, candidates, k)


def test_cosine_raises_for_three_dimensional_zero_vector():
    """任一更高维零向量也应按统一契约抛出 ValueError。"""
    x = (0, 0, 0)
    y = (1, 2, 3)

    with pytest.raises(ValueError):
        cosine(x, y)


def test_cosine_accepts_valid_vectors_despite_floating_roundoff():
    """合法同向向量不应因极小浮点越界而被误判为非法输入。"""
    x = (1, 5)
    y = (2, 10)
    expected = 1.0

    actual = cosine(x, y)

    assert -1.0 <= actual <= 1.0
    assert isinstance(actual, float)
    assert actual == pytest.approx(expected)


def test_top_k_raises_type_error_for_zero_float_k():
    """k 为数值等于零的 float 时，仍应优先按类型错误抛出 TypeError。"""
    candidates = _make_candidates()
    query = (2, 3)
    k = 0.0

    with pytest.raises(TypeError):
        top_k(query, candidates, k)
