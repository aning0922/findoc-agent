from experiments.day37_structure_lab import LabDocChunk
from experiments.day37_stable_id_lab import build_stable_chunk_id
import pytest


def test_identical_input_produces_same_nonempty_id() -> None:
    """
    测试相同内容、相同源定位器，是否产生相同的非空ID。
    """
    chunk1 = LabDocChunk(
        text="Hello, world!",
        page=1,
        type="paragraph",
        source_file="demo.pdf",
        table_md="",
        section="",
        chunk_id="",
    )
    chunk2 = LabDocChunk(
        text="Hello, world!",
        page=1,
        type="paragraph",
        source_file="demo.pdf",
        table_md="",
        section="",
        chunk_id="",
    )

    id1 = build_stable_chunk_id(chunk1, "page-1:block-3")
    id2 = build_stable_chunk_id(chunk2, "page-1:block-3")
    assert id1 is not None
    assert id1 != ""
    assert id2 is not None
    assert id2 != ""
    assert id1 == id2


def test_duplicate_content_with_different_source_locators_has_distinct_ids() -> None:
    """
    测试相同内容、不同源定位器，是否产生不同的ID。
    """
    chunk1 = LabDocChunk(
        text="Hello, world!",
        page=1,
        type="paragraph",
        source_file="demo.pdf",
        table_md="",
        section="",
        chunk_id="",
    )
    chunk2 = LabDocChunk(
        text="Hello, world!",
        page=1,
        type="paragraph",
        source_file="demo.pdf",
        table_md="",
        section="",
        chunk_id="",
    )

    id1 = build_stable_chunk_id(chunk1, "page-1:block-3")
    id2 = build_stable_chunk_id(chunk2, "page-1:block-4")
    assert id1 is not None
    assert id1 != ""
    assert id2 is not None
    assert id2 != ""
    assert id1 != id2


def test_one_character_text_change_changes_id() -> None:
    """
    测试一个字符的文本变化，是否产生不同的ID。
    """
    chunk1 = LabDocChunk(
        text="Hello, world!",
        page=1,
        type="paragraph",
        source_file="demo.pdf",
        table_md="",
        section="",
        chunk_id="",
    )
    chunk2 = LabDocChunk(
        text="Hello, world!2",
        page=1,
        type="paragraph",
        source_file="demo.pdf",
        table_md="",
        section="",
        chunk_id="",
    )
    id1 = build_stable_chunk_id(chunk1, "page-1:block-3")
    id2 = build_stable_chunk_id(chunk2, "page-1:block-3")
    assert id1 is not None
    assert id1 != ""
    assert id2 is not None
    assert id2 != ""
    assert id1 != id2


def test_page_change_changes_id() -> None:
    """
    测试页码变化，是否产生不同的ID。
    """
    chunk1 = LabDocChunk(
        text="Hello, world!",
        page=1,
        type="paragraph",
        source_file="demo.pdf",
        table_md="",
        section="",
        chunk_id="",
    )
    chunk2 = LabDocChunk(
        text="Hello, world!",
        page=2,
        type="paragraph",
        source_file="demo.pdf",
        table_md="",
        section="",
        chunk_id="",
    )
    id1 = build_stable_chunk_id(chunk1, "element-3")
    id2 = build_stable_chunk_id(chunk2, "element-3")
    assert id1 is not None
    assert id1 != ""
    assert id2 is not None
    assert id2 != ""
    assert id1 != id2


def test_section_change_changes_id() -> None:
    """
    测试章节变化，是否产生不同的ID。
    """
    chunk1 = LabDocChunk(
        text="Hello, world!",
        page=1,
        type="paragraph",
        source_file="demo.pdf",
        table_md="",
        section="section-1",
        chunk_id="",
    )
    chunk2 = LabDocChunk(
        text="Hello, world!",
        page=1,
        type="paragraph",
        source_file="demo.pdf",
        table_md="",
        section="section-2",
        chunk_id="",
    )
    id1 = build_stable_chunk_id(chunk1, "element-3")
    id2 = build_stable_chunk_id(chunk2, "element-3")
    assert id1 is not None
    assert id1 != ""
    assert id2 is not None
    assert id2 != ""
    assert id1 != id2


def test_same_content_in_different_documents_has_distinct_ids() -> None:
    """
    测试相同内容、不同文档，是否产生不同的ID。
    """
    chunk1 = LabDocChunk(
        text="Hello, world!",
        page=1,
        type="paragraph",
        source_file="demo.pdf",
        table_md="",
        section="",
        chunk_id="",
    )
    chunk2 = LabDocChunk(
        text="Hello, world!",
        page=1,
        type="paragraph",
        source_file="demo2.pdf",
        table_md="",
        section="",
        chunk_id="",
    )
    id1 = build_stable_chunk_id(chunk1, "element-3")
    id2 = build_stable_chunk_id(chunk2, "element-3")
    assert id1 is not None
    assert id1 != ""
    assert id2 is not None
    assert id2 != ""
    assert id1 != id2


def test_reordering_chunks_keeps_each_logical_id() -> None:
    """
    测试重新排序chunks，是否保持每个逻辑ID不变。
    """
    a_first = LabDocChunk(
        text="Hello, world!",
        page=1,
        type="paragraph",
        source_file="demo.pdf",
        table_md="",
        section="",
        chunk_id="",
    )
    b_first = LabDocChunk(
        text="Hello, world!",
        page=1,
        type="paragraph",
        source_file="demo.pdf",
        table_md="",
        section="",
        chunk_id="",
    )
    a_second = LabDocChunk(
        text="Hello, world!",
        page=1,
        type="paragraph",
        source_file="demo.pdf",
        table_md="",
        section="",
        chunk_id="",
    )
    b_second = LabDocChunk(
        text="Hello, world!",
        page=1,
        type="paragraph",
        source_file="demo.pdf",
        table_md="",
        section="",
        chunk_id="",
    )
    a_id_first = build_stable_chunk_id(a_first, "element-a")
    b_id_first = build_stable_chunk_id(b_first, "element-b")
    b_id_second = build_stable_chunk_id(b_second, "element-b")
    a_id_second = build_stable_chunk_id(a_second, "element-a")
    assert a_id_first is not None
    assert a_id_first != ""
    assert b_id_first is not None
    assert b_id_first != ""
    assert a_id_second is not None
    assert a_id_second != ""
    assert b_id_second is not None
    assert b_id_second != ""
    assert a_id_first == a_id_second
    assert b_id_first == b_id_second


def test_deleting_middle_chunk_keeps_remaining_ids() -> None:
    """
    测试删除中间chunk，是否保持剩余chunk的ID不变。
    """
    a_first = LabDocChunk(
        text="Hello, world!",
        page=1,
        type="paragraph",
        source_file="demo.pdf",
        table_md="",
        section="",
        chunk_id="",
    )
    b_first = LabDocChunk(
        text="Hello, world!",
        page=1,
        type="paragraph",
        source_file="demo.pdf",
        table_md="",
        section="",
        chunk_id="",
    )
    c_first = LabDocChunk(
        text="Hello, world!",
        page=1,
        type="paragraph",
        source_file="demo.pdf",
        table_md="",
        section="",
        chunk_id="",
    )
    a_second = LabDocChunk(
        text="Hello, world!",
        page=1,
        type="paragraph",
        source_file="demo.pdf",
        table_md="",
        section="",
        chunk_id="",
    )
    c_second = LabDocChunk(
        text="Hello, world!",
        page=1,
        type="paragraph",
        source_file="demo.pdf",
        table_md="",
        section="",
        chunk_id="",
    )
    a1_id = build_stable_chunk_id(a_first, "element-a")
    b1_id = build_stable_chunk_id(b_first, "element-b")
    c1_id = build_stable_chunk_id(c_first, "element-c")

    a2_id = build_stable_chunk_id(a_second, "element-a")
    c2_id = build_stable_chunk_id(c_second, "element-c")

    assert a1_id is not None
    assert a1_id != ""
    assert b1_id is not None
    assert b1_id != ""
    assert c1_id is not None
    assert c1_id != ""
    assert a2_id is not None
    assert a2_id != ""
    assert c2_id is not None
    assert c2_id != ""
    assert a1_id == a2_id
    assert c1_id == c2_id


def test_missing_source_file_is_rejected_before_id_generation() -> None:
    """
    测试缺失源文件的chunk，是否在生成ID之前被拒绝。
    """
    missing_source_file_chunk = LabDocChunk(
        text="Hello, world!",
        page=1,
        type="paragraph",
        source_file="",
        table_md="",
        section="",
        chunk_id="",
    )
    with pytest.raises(ValueError, match="source_file 丢失"):
        build_stable_chunk_id(missing_source_file_chunk, "element-a")


def test_missing_source_locator_is_rejected_before_id_generation() -> None:
    chunk = LabDocChunk(
        text="Hello, world!",
        page=1,
        type="paragraph",
        source_file="demo.pdf",
        table_md="",
        section="",
        chunk_id="",
    )
    with pytest.raises(ValueError, match="source_locator 丢失"):
        build_stable_chunk_id(chunk, "")

def test_existing_chunk_id_does_not_change_stable_id() -> None:
    """
    测试已存在的chunk_id，是否不会改变稳定ID。
    """
    chunk1 = LabDocChunk(
        text="Hello, world!",
        page=1,
        type="paragraph",
        source_file="demo.pdf",
        table_md="",
        section="",
        chunk_id="",
    )
    chunk2 = LabDocChunk(
        text="Hello, world!",
        page=1,
        type="paragraph",
        source_file="demo.pdf",
        table_md="",
        section="",
        chunk_id="existing-id",
    )
    id1 = build_stable_chunk_id(chunk1, "element-a")
    id2 = build_stable_chunk_id(chunk2, "element-a")
    assert id1 is not None
    assert id1 != ""
    assert id2 is not None
    assert id2 != ""
    assert id1 == id2