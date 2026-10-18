from app.rag.parse.models import DocChunk
from app.rag.chunk import chunk_docment
import pytest


def test_chunk_document_skips_titles_and_preserves_coarse_section_on_pieces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    测试分块器跳过标题，保留粗粒度段落
    """
    splitter_calls: list[str] = []

    def fake_splitter(text: str) -> list[str]:
        splitter_calls.append(text)
        return ["甲", "乙"]

    monkeypatch.setattr("app.rag.chunk.recursive_chunk", fake_splitter)

    chunks = []
    chunks.append(
        DocChunk(
            text="第一章",
            type="title",
            source_file="dummy.pdf",
            page=1,
            section="第一章",
            table_md="",
            chunk_id="",
        )
    )
    chunks.append(
        DocChunk(
            text="甲乙",
            type="paragraph",
            source_file="dummy.pdf",
            page=1,
            section="第一章/1.1 业务",
            table_md="",
            chunk_id="",
        )
    )

    result = chunk_docment(chunks)
    assert len([chunk.type for chunk in result if chunk.type == "title"]) == 0
    assert len(result) == 2
    assert [chunk.type for chunk in result] == ["paragraph", "paragraph"]
    assert result[0].text == "甲"
    assert result[1].text == "乙"
    assert result[0].section == "第一章/1.1 业务"
    assert result[1].section == "第一章/1.1 业务"
    assert result[0].source_file == "dummy.pdf"
    assert result[1].source_file == "dummy.pdf"
    assert result[0].page == 1
    assert result[1].page == 1
    assert result[0].table_md == ""
    assert result[1].table_md == ""
    assert splitter_calls == ["甲乙"]


def test_chunk_document_preserves_searchable_table_text_and_original_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    测试分块器保留可搜索的表格文本和原始负载
    """

    def fake_splitter(text: str) -> list[str]:
        raise AssertionError("Should not be called")

    monkeypatch.setattr("app.rag.chunk.recursive_chunk", fake_splitter)

    chunks = []
    text = "测试表 列1 列2 行1 行2"
    table_md = """
    | 列1 | 列2 |
    | ---- | ---- |
    | 行1 | 行2 |
    """
    chunks.append(
        DocChunk(
            text=text,
            type="table",
            source_file="dummy.pdf",
            page=1,
            section="第一章",
            table_md=table_md,
            chunk_id="",
        )
    )
    result = chunk_docment(chunks)
    assert len(result) == 1
    assert result[0].text == text
    assert result[0].type == "table"
    assert result[0].source_file == "dummy.pdf"
    assert result[0].page == 1
    assert result[0].section == "第一章"
    assert result[0].table_md == table_md


def test_chunk_document_same_input_twice_produces_same_nonempty_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    测试分块器相同输入两次，产生相同的非空ID
    """
    def fake_splitter(text: str) -> list[str]:
        return [text]

    monkeypatch.setattr("app.rag.chunk.recursive_chunk", fake_splitter)

    def generate_chunks() -> list[DocChunk]:
        return [
            DocChunk(
                text="测试文本",
                type="paragraph",
                source_file="dummy.pdf",
                page=1,
                section="第一章",
                table_md="",
                chunk_id="",
            ),
            DocChunk(
                text="测试文本2",
                type="paragraph",
                source_file="dummy.pdf",
                page=1,
                section="第一章",
                table_md="",
                chunk_id="",
            ),
        ]

    chunks1 = generate_chunks()
    chunks2 = generate_chunks()
    result1 = chunk_docment(chunks1)
    result2 = chunk_docment(chunks2)
    assert len(result1) == len(result2) == 2
    assert [chunk.text for chunk in result1] == [chunk.text for chunk in result2]
    assert all([chunk.chunk_id != "" for chunk in result1])
    assert all([chunk.chunk_id != "" for chunk in result2])
    assert [chunk.chunk_id for chunk in result1] == [chunk.chunk_id for chunk in result2]

def test_chunk_document_duplicate_blocks_have_distinct_and_repeatable_ids(monkeypatch: pytest.MonkeyPatch,) -> None:
    """
    测试分块器重复块，产生相同的ID 且非空
    """
    def fake_splitter(text: str) -> list[str]:
        return [text]

    monkeypatch.setattr("app.rag.chunk.recursive_chunk", fake_splitter)

    def generate_chunks() -> list[DocChunk]:
        return [
            DocChunk(
                text="测试文本",
                type="paragraph",
                source_file="dummy.pdf",
                page=1,
                section="第一章",
                table_md="",
                chunk_id="",
            ),
            DocChunk(
                text="测试文本",
                type="paragraph",
                source_file="dummy.pdf",
                page=1,
                section="第一章",
                table_md="",
                chunk_id="",
            ),
        ]

    chunks1 = generate_chunks()
    chunks2 = generate_chunks()
    result1 = chunk_docment(chunks1)
    result2 = chunk_docment(chunks2)
    assert len(result1) == len(result2) == 2
    assert all([chunk.chunk_id != "" for chunk in result1])
    assert result1[0].chunk_id != result1[1].chunk_id

    assert all([chunk.chunk_id != "" for chunk in result2])
    assert result2[0].chunk_id != result2[1].chunk_id
    assert [chunk.chunk_id for chunk in result1] == [chunk.chunk_id for chunk in result2]

def test_chunk_document_deleting_middle_block_keeps_remaining_ids(monkeypatch: pytest.MonkeyPatch,) -> None:
    """
    测试分块器删除中间块，保留剩余块的ID
    """
    def fake_splitter(text: str) -> list[str]:
        return [text]

    monkeypatch.setattr("app.rag.chunk.recursive_chunk", fake_splitter)

    chunks1 = []
    chunks1.append(DocChunk(
        text="A",
        type="paragraph",
        source_file="dummy.pdf",
        page=1,
        section="第一章",
        table_md="",
        chunk_id="",
    ))
    chunks1.append(DocChunk(
        text="B",
        type="paragraph",
        source_file="dummy.pdf",
        page=1,
        section="第一章",
        table_md="",
        chunk_id="",
    ))
    chunks1.append(DocChunk(
        text="C",
        type="paragraph",
        source_file="dummy.pdf",
        page=1,
        section="第一章",
        table_md="",
        chunk_id="",
    ))
    chunks2 = []
    chunks2.append(DocChunk(
        text="A",
        type="paragraph",
        source_file="dummy.pdf",
        page=1,
        section="第一章",
        table_md="",
        chunk_id="",
    ))
    chunks2.append(DocChunk(
        text="C",
        type="paragraph",
        source_file="dummy.pdf",
        page=1,
        section="第一章",
        table_md="",
        chunk_id="",
    ))

    result1 = chunk_docment(chunks1)
    result2 = chunk_docment(chunks2)
    id1a = [chunk.chunk_id for chunk in result1 if chunk.text == "A"][0]
    id1c = [chunk.chunk_id for chunk in result1 if chunk.text == "C"][0]
    id2a = [chunk.chunk_id for chunk in result2 if chunk.text == "A"][0]
    id2c = [chunk.chunk_id for chunk in result2 if chunk.text == "C"][0]
    assert id1a == id2a
    assert id1c == id2c

def test_chunk_document_reordering_distinct_blocks_keeps_each_id(monkeypatch: pytest.MonkeyPatch,) -> None:
    """
    测试分块器重新排序不同块，保留每个块的ID
    """
    def fake_splitter(text: str) -> list[str]:
        return [text]

    monkeypatch.setattr("app.rag.chunk.recursive_chunk", fake_splitter)

    chunks1 = []
    chunks1.append(DocChunk(
        text="A",
        type="paragraph",
        source_file="dummy.pdf",
        page=1,
        section="第一章",
        table_md="",
        chunk_id="",
    ))
    chunks1.append(DocChunk(
        text="B",
        type="paragraph",
        source_file="dummy.pdf",
        page=1,
        section="第一章",
        table_md="",
        chunk_id="",
    ))
    chunks2 = []
    chunks2.append(DocChunk(
        text="B",
        type="paragraph",
        source_file="dummy.pdf",
        page=1,
        section="第一章",
        table_md="",
        chunk_id="",
    ))
    chunks2.append(DocChunk(
        text="A",
        type="paragraph",
        source_file="dummy.pdf",
        page=1,
        section="第一章",
        table_md="",
        chunk_id="",
    ))
    result1 = chunk_docment(chunks1)
    result2 = chunk_docment(chunks2)
    id1a = [chunk.chunk_id for chunk in result1 if chunk.text == "A"][0]
    id1b = [chunk.chunk_id for chunk in result1 if chunk.text == "B"][0]
    id2a = [chunk.chunk_id for chunk in result2 if chunk.text == "A"][0]
    id2b = [chunk.chunk_id for chunk in result2 if chunk.text == "B"][0]
    assert id1a == id2a
    assert id1b == id2b
    assert [chunk.text for chunk in result2] == ["B", "A"]