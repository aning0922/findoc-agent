from pathlib import Path
from collections.abc import Mapping
from typing import Any

import pytest

from scripts.evaluate_day42_retrieval import (
    check_result_metadata,
    evaluate_question,
    load_questions,
    run_warmup,
    summarize_latency,
)


QUESTION_PATH = Path("eval/day42_questions.jsonl")


def test_load_day42_questions() -> None:
    # 12题、10道可回答、2道无答案
    questions = load_questions(QUESTION_PATH)
    assert len(questions) == 12
    assert sum(q["answerable"] for q in questions) == 10
    assert sum(not q["answerable"] for q in questions) == 2

    for question in questions:
        assert question["ground_truth"]
        assert isinstance(question["expected_metadata"], dict)


def test_metadata_check_detects_section_mismatch() -> None:
    question = {
        "answerable": True,
        "relevant_chunk_ids": ["R1"],
        "source_file": None,
        "expected_metadata": {
            "R1": {
                "source_file": "data/贵州茅台2025年报.pdf",
                "page": 9,
                "type": "paragraph",
                "section": "四、报告期内核心竞争力分析",
            }
        },
    }

    hits = [
        {
            "chunk_id": "R1",
            "source_file": "data/贵州茅台2025年报.pdf",
            "page": 9,
            "type": "paragraph",
            "section": "贵州茅台酒股份有限公司2025 年年度报告",
        }
    ]

    actual = check_result_metadata(question=question, hits=hits, retrieval_succeeded=True)

    assert actual["filter_ok"] is None
    assert actual["relevant_metadata_status"] == "failed"
    assert actual["relevant_hit_checks"] == [
        {
            "chunk_id": "R1",
            "ok": False,
            "mismatches": {
                "section": {
                    "expected": "四、报告期内核心竞争力分析",
                    "actual": "贵州茅台酒股份有限公司2025 年年度报告",
                }
            },
        }
    ]


def test_metadata_check_passes_when_expected_fields_match() -> None:
    question = {
        "answerable": True,
        "relevant_chunk_ids": ["R1"],
        "source_file": None,
        "expected_metadata": {
            "R1": {
                "source_file": "data/贵州茅台2025年报.pdf",
                "page": 9,
                "type": "paragraph",
                "section": "四、报告期内核心竞争力分析",
            }
        },
    }

    hits = [
        {
            "chunk_id": "R1",
            "source_file": "data/贵州茅台2025年报.pdf",
            "page": 9,
            "type": "paragraph",
            "section": "四、报告期内核心竞争力分析",
        }
    ]

    actual = check_result_metadata(question=question, hits=hits, retrieval_succeeded=True)

    assert actual["filter_ok"] is None
    assert actual["relevant_metadata_status"] == "passed"
    assert actual["relevant_hit_checks"] == [
        {
            "chunk_id": "R1",
            "ok": True,
            "mismatches": {},
        }
    ]


def test_metadata_check_fails_when_expected_section_is_missing() -> None:
    question = {
        "answerable": True,
        "relevant_chunk_ids": ["R1"],
        "source_file": None,
        "expected_metadata": {
            "R1": {
                "source_file": "data/贵州茅台2025年报.pdf",
                "page": 9,
                "type": "paragraph",
                "section": "四、报告期内核心竞争力分析",
            }
        },
    }

    hits = [
        {
            "chunk_id": "R1",
            "source_file": "data/贵州茅台2025年报.pdf",
            "page": 9,
            "type": "paragraph",
        }
    ]

    actual = check_result_metadata(question=question, hits=hits, retrieval_succeeded=True)

    assert actual["filter_ok"] is None
    assert actual["relevant_metadata_status"] == "failed"
    assert actual["relevant_hit_checks"] == [
        {
            "chunk_id": "R1",
            "ok": False,
            "mismatches": {
                "section": {
                    "expected": "四、报告期内核心竞争力分析",
                    "actual": None,
                }
            },
        }
    ]


def test_source_filter_checks_every_hit() -> None:
    question = {
        "answerable": True,
        "relevant_chunk_ids": ["R1"],
        "source_file": "data/贵州茅台2025年报.pdf",
        "expected_metadata": {
            "R1": {
                "source_file": "data/贵州茅台2025年报.pdf",
                "page": 9,
                "type": "paragraph",
                "section": "四、报告期内核心竞争力分析",
            }
        },
    }

    hits = [
        {
            "chunk_id": "R1",
            "source_file": "data/贵州茅台2025年报.pdf",
            "page": 9,
            "type": "paragraph",
            "section": "四、报告期内核心竞争力分析",
        }
    ]

    actual = check_result_metadata(question=question, hits=hits, retrieval_succeeded=True)

    assert actual["filter_ok"] is True
    assert actual["relevant_metadata_status"] == "passed"
    assert actual["relevant_hit_checks"] == [
        {
            "chunk_id": "R1",
            "ok": True,
            "mismatches": {},
        }
    ]

    hits = [
        {
            "chunk_id": "R1",
            "source_file": "data/贵州茅台2025年报.pdf",
            "page": 9,
            "type": "paragraph",
            "section": "四、报告期内核心竞争力分析",
        },
        {
            "chunk_id": "X1",
            "source_file": "data/成都华微电子2025年报.pdf",
            "page": 20,
            "type": "paragraph",
            "section": "其他章节",
        },
    ]

    actual = check_result_metadata(
        question=question,
        hits=hits,
        retrieval_succeeded=True,
    )

    assert actual["filter_ok"] is False
    assert actual["relevant_metadata_status"] == "passed"


def test_latency_summary_excludes_system_error() -> None:
    results = [
        {
            "status": "normal",
            "latency_ms": 10.0,
        },
        {
            "status": "normal",
            "latency_ms": 20.0,
        },
        {
            "status": "recall_error",
            "latency_ms": 30.0,
        },
        {
            "status": "filtered_empty",
            "latency_ms": 40.0,
        },
        {
            "status": "system_error",
            "latency_ms": 9999.0,
        },
    ]

    actual = summarize_latency(results)
    assert actual["latency_sample_count"] == 4
    assert actual["exploratory_p50_ms"] == 25.0
    assert actual["exploratory_p95_ms"] == 38.5


RELEVANT_HIT: dict[str, Any] = {
    "score": 0.9,
    "chunk_id": "R1",
    "text": "相关正文",
    "page": 9,
    "source_file": "data/贵州茅台2025年报.pdf",
    "type": "paragraph",
    "section": "四、报告期内核心竞争力分析",
    "table_md": None,
}

UNRELATED_HIT: dict[str, Any] = {
    "score": 0.8,
    "chunk_id": "X1",
    "text": "无关正文",
    "page": 20,
    "source_file": "data/其他年报.pdf",
    "type": "paragraph",
    "section": "其他章节",
    "table_md": None,
}


class FakeStore:
    def __init__(
        self,
        *,
        hits: list[Mapping[str, Any]] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.hits = hits or []
        self.error = error
        self.seen_top_k: int | None = None
        self.seen_filter_expression: str | None = None

    def search(
        self,
        query_vector: list[float],
        *,
        top_k: int,
        filter_expression: str,
    ) -> list[Mapping[str, Any]]:
        self.seen_top_k = top_k
        self.seen_filter_expression = filter_expression

        if self.error is not None:
            raise self.error

        return self.hits


def fake_embedder(texts: list[str]) -> list[list[float]]:
    assert len(texts) == 1
    return [[0.1, 0.2]]


@pytest.mark.parametrize(
    (
        "answerable",
        "source_file",
        "hits",
        "store_error",
        "expected_status",
        "expected_rank",
        "expect_metric_case",
    ),
    [
        (
            True,
            None,
            [UNRELATED_HIT, RELEVANT_HIT],
            None,
            "normal",
            2,
            True,
        ),
        (
            True,
            "data/贵州茅台2025年报.pdf",
            [],
            None,
            "filtered_empty",
            None,
            True,
        ),
        (
            True,
            None,
            [UNRELATED_HIT],
            None,
            "recall_error",
            None,
            True,
        ),
        (
            True,
            "data/贵州茅台2025年报.pdf",
            [],
            RuntimeError("Milvus offline"),
            "system_error",
            None,
            True,
        ),
        (
            False,
            None,
            [UNRELATED_HIT],
            None,
            "normal",
            None,
            False,
        ),
    ],
)
def test_evaluate_question_with_fake_dependencies(
    answerable: bool,
    source_file: str | None,
    hits: list[Mapping[str, Any]],
    store_error: Exception | None,
    expected_status: str,
    expected_rank: int | None,
    expect_metric_case: bool,
) -> None:
    relevant_ids = ["R1"] if answerable else []

    question = {
        "case_id": "T1",
        "query": "测试问题",
        "category": "test",
        "answerable": answerable,
        "relevant_chunk_ids": relevant_ids,
        "source_file": source_file,
        "expected_metadata": (
            {
                "R1": {
                    "source_file": "data/贵州茅台2025年报.pdf",
                    "page": 9,
                    "type": "paragraph",
                    "section": "四、报告期内核心竞争力分析",
                }
            }
            if answerable
            else {}
        ),
    }

    store = FakeStore(
        hits=hits,
        error=store_error,
    )

    result, metric_case = evaluate_question(
        question,
        embedder=fake_embedder,
        store=store,
        top_k=3,
    )

    assert result["status"] == expected_status
    assert result["relevant_rank"] == expected_rank
    assert (metric_case is not None) is expect_metric_case

    # 证明函数没有忽略传入参数而使用全局 TOP_K。
    assert store.seen_top_k == 3

    if source_file is not None:
        assert source_file in str(store.seen_filter_expression)

    if expected_status == "system_error":
        assert result["error"] == "RuntimeError: Milvus offline"
        assert result["metadata_check"]["filter_ok"] is None

    if expected_status in {"filtered_empty", "recall_error"}:
        assert result["metadata_check"]["relevant_metadata_status"] == "not_observed"

    if not answerable:
        assert result["metadata_check"]["relevant_metadata_status"] == "not_applicable"


def test_warmup_forwards_top_k() -> None:
    question = {
        "query": "热身问题",
        "source_file": None,
    }
    store = FakeStore(hits=[])

    elapsed_ms = run_warmup(
        question=question,
        embedder=fake_embedder,
        store=store,
        top_k=3,
    )

    assert elapsed_ms >= 0
    assert store.seen_top_k == 3
