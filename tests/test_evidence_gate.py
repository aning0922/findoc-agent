from typing import cast
import pytest

from app.rag.evidence_gate import ConservativeScoreEvidenceGate
from app.rag.retriever import SearchHit


@pytest.mark.parametrize(
    ("score", "text", "expected"),
    [
        (0.54, "低相关证据", False),
        (0.6081732511520386, "。", True),
        (
            0.7282137870788574,
            "成都华微电子科技股份有限公司2025年年度报告",
            True,
        ),
    ],
    ids=[
        "below-conservative-floor",
        "answerable-q11-score",
        "unanswerable-q12-score",
    ],
)
def test_conservative_score_gate_is_only_a_first_layer_filter(
    score: float, text: str, expected: bool
) -> None:
    """输入为冻结阈值0.55，以及低分、Q11近似分和Q12近似分的有序证据；
    预期只有低于阈值的证据被第一层拒绝，而Q11和Q12都进入模型第二层；
    若Gate把高分等同于可回答、拒绝Q11或直接判断Q12不可回答，
    说明第一层最低资格闸门越权承担了语义充分性分类。
    """
    gate = ConservativeScoreEvidenceGate(min_top_score=0.55)
    hit = SearchHit(
        score=score,
        chunk_id="test-chunk",
        text=text,
        page=1,
        source_file="test.pdf",
        type="paragraph",
        section="测试章节",
        table_md=None,
    )
    hits = [hit]
    original_hits = list(hits)
    actual = gate.allows("测试问题", hits)
    assert actual is expected
    assert hits == original_hits


@pytest.mark.parametrize(
    ("threshold", "expected_error"),
    [
        (True, TypeError),
        ("0.55", TypeError),
        (float("nan"), ValueError),
        (float("inf"), ValueError),
        (-1.01, ValueError),
        (1.01, ValueError),
    ],
    ids=[
        "bool-is-not-a-score",
        "string-is-not-a-score",
        "nan-is-not-finite",
        "positive-infinity-is-not-finite",
        "below-cosine-range",
        "above-cosine-range",
    ],
)
def test_conservative_score_gate_rejects_invalid_threshold(
    threshold: object,
    expected_error: type[Exception],
) -> None:
    """输入为 bool、字符串、非有限数和超出 cosine 范围的阈值；
    预期构造阶段分别抛出 TypeError 或 ValueError；
    若非法配置被接受并延迟到请求阶段，
    说明 Gate 无法在 baseline 冻结前快速发现配置错误。
    """
    # cast只跨过静态类型边界，不改变运行时对象；
    # 本测试需要确认构造器能拒绝来自配置层的非法实际值。
    invalid_threshold = cast(float, threshold)

    with pytest.raises(expected_error):
        ConservativeScoreEvidenceGate(min_top_score=invalid_threshold)


@pytest.mark.parametrize(
    "threshold",
    [-1.0, 0.0, 1.0],
)
def test_conservative_score_gate_accepts_cosine_range_boundaries(
    threshold: float,
) -> None:
    """输入为 cosine 合法范围的下界、中点和上界；
    预期 Gate 可成功冻结这些阈值；
    若构造失败，说明配置校验把策略选择误当成非法数值。
    """
    gate = ConservativeScoreEvidenceGate(min_top_score=threshold)
    assert gate.min_top_score == threshold
