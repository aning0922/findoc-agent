from tests.day36_fixed_lab import fixed_split
import pytest

def test_empty_text():
    assert fixed_split("", 5, 2) == []


def test_short_text():
    assert fixed_split("年度利润增长。", 14, 4) == ["年度利润增长。"]


def test_equal_length():
    assert fixed_split("季度报告显示，公司收入持续增", 14, 4) == ["季度报告显示，公司收入持续增"]


def test_long_text():
    assert fixed_split(
        "季度报告显示，公司收入持续增长，但海外订单波动明显。管理层计划优化库存，并增加研发投入，以应对需求变化。",
        14,
        4,
    ) == [
        "季度报告显示，公司收入持续增",
        "入持续增长，但海外订单波动明",
        "单波动明显。管理层计划优化库",
        "划优化库存，并增加研发投入，",
        "发投入，以应对需求变化。",
    ]

def test_size_zero():
    with pytest.raises(ValueError, match="size必须大于 0"):
        fixed_split("财务报告", 0, 0)

def test_size_equal_overlap():
    with pytest.raises(ValueError, match="size必须大于 overlap"):
        fixed_split("ABCDEFGHIJ", 8, 8)


def test_overlap_greater_than_size():
    with pytest.raises(ValueError, match="size必须大于 overlap"):
        fixed_split("ABCDEFGHIJ", 8, 9)

def test_overlap_negative():
    with pytest.raises(ValueError, match="overlap必须大于等于 0"):
        fixed_split("ABCDEFGHIJ", 8, -1)

def test_overlap_zero():
    assert fixed_split("ABCDEFGHIJ", 4, 0) == ["ABCD", "EFGH", "IJ"]

def test_size_less_than_zero():
    with pytest.raises(ValueError, match="size必须大于 0"):
        fixed_split("ABCDEFGHIJ", -1, 0)