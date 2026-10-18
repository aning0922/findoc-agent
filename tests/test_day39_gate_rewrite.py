from math import sqrt

import pytest

from experiments.day39_gate_rewrite import cosine, top_k


def _gate_candidates():
    return [
        {
            "id": "z-first-in-input",
            "metadata": {"source": "first"},
            "vector": (2, 0, 0),
        },
        {
            "id": "a-second-in-input",
            "metadata": {"source": "second"},
            "vector": (7, 0, 0),
        },
        {
            "id": "middle",
            "metadata": {"source": "third"},
            "vector": (1, 1, 0),
        },
        {
            "id": "zero-score",
            "metadata": {"source": "fourth"},
            "vector": (0, 3, 0),
        },
        {
            "id": "negative",
            "metadata": {"source": "fifth"},
            "vector": (-4, 0, 0),
        },
    ]


def test_gate_cosine_handles_unseen_3d_scores():
    query = (1, 2, 2)

    assert cosine(query, (2, -1, 0)) == pytest.approx(0.0)
    assert cosine(query, (2, -1, 2)) == pytest.approx(4 / 9)
    assert cosine(query, (-1, -2, -2)) == pytest.approx(-1.0)


def test_gate_cosine_ignores_positive_magnitude_changes():
    assert cosine((1, 2, 2), (3, 6, 6)) == pytest.approx(1.0)


def test_gate_cosine_returns_float_within_mathematical_range():
    result = cosine((1, 5), (2, 10))

    assert isinstance(result, float)
    assert -1.0 <= result <= 1.0
    assert result == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("x", "y"),
    [
        ((), (1,)),
        ((1,), ()),
        ((1, 2), (1, 2, 3)),
        ((0, 0, 0), (1, 2, 3)),
        ((1, 2, 3), (0, 0, 0)),
    ],
)
def test_gate_cosine_rejects_invalid_vectors(x, y):
    with pytest.raises(ValueError):
        cosine(x, y)


def test_gate_top_k_ranks_new_records_and_preserves_input_ties():
    candidates = _gate_candidates()

    result = top_k((1, 0, 0), candidates, 3)

    assert [row["id"] for row in result] == [
        "z-first-in-input",
        "a-second-in-input",
        "middle",
    ]
    assert result[0] == {
        "id": "z-first-in-input",
        "metadata": {"source": "first"},
        "vector": (2, 0, 0),
        "score": 1.0,
    }
    assert result[2]["score"] == pytest.approx(1 / sqrt(2))


def test_gate_top_k_does_not_mutate_candidates():
    candidates = _gate_candidates()
    original_order = [row["id"] for row in candidates]

    result = top_k((1, 0, 0), candidates, 3)

    assert [row["id"] for row in candidates] == original_order
    assert all("score" not in row for row in candidates)
    assert result is not candidates
    assert all(result_row is not source_row for result_row in result for source_row in candidates)


def test_gate_top_k_returns_empty_for_empty_candidates():
    assert top_k((1, 0, 0), [], 2) == []


@pytest.mark.parametrize(
    ("k", "error_type"),
    [
        (0, ValueError),
        (-3, ValueError),
        (2.5, TypeError),
        ("2", TypeError),
    ],
)
def test_gate_top_k_rejects_invalid_k(k, error_type):
    with pytest.raises(error_type):
        top_k((1, 0, 0), _gate_candidates(), k)


def test_gate_top_k_returns_all_sorted_when_k_is_too_large():
    result = top_k((1, 0, 0), _gate_candidates(), 99)

    assert [row["id"] for row in result] == [
        "z-first-in-input",
        "a-second-in-input",
        "middle",
        "zero-score",
        "negative",
    ]


@pytest.mark.parametrize("bad_vector", [(1, 2), (0, 0, 0)])
def test_gate_top_k_rejects_an_invalid_candidate(bad_vector):
    candidates = _gate_candidates()
    candidates[2] = {
        "id": "broken",
        "metadata": {"source": "broken"},
        "vector": bad_vector,
    }

    with pytest.raises(ValueError):
        top_k((1, 0, 0), candidates, 2)
