import pytest
from tests.day36_recursive_lab import recursive_split


def test_recursive_split():
    text = """摘要完整。

收入增长
成本下降。海外订单ABCDEFGHIJKLMNO"""
    separators = ["\n\n", "\n", "。", ""]
    assert recursive_split(text, 12, separators) == [
        "摘要完整。\n\n",
        "收入增长\n",
        "成本下降。",
        "海外订单ABCDEFGH",
        "IJKLMNO",
    ]


def test_recursive_separators_empty():
    """分隔符列表为空"""
    with pytest.raises(ValueError, match="分隔符列表不能为空"):
        recursive_split("ABCDEFGHIJ", 4, [])


def test_recursive_fixed_length():
    """只有 size 一个切割点"""
    assert recursive_split("ABCDEFGHIJ", 4, [""]) == ["ABCD", "EFGH", "IJ"]


def test_recursive_split_falls_back_when_separator_missing():
    """分隔符列表中没有分隔符"""
    assert recursive_split("ABCDEFGHIJ", 4, ["\n", ""]) == ["ABCD", "EFGH", "IJ"]


def test_recursive_split_keeps_existing_separator():
    assert recursive_split("甲乙丙。丁戊己。", 4, ["。", ""]) == ["甲乙丙。", "丁戊己。"]


def test_recursive_split_counts_kept_separator_in_size():
    """分隔符列表中包含分隔符"""
    assert recursive_split("甲乙丙丁。戊。", 4, ["。", ""]) == ["甲乙丙丁", "。", "戊。"]
