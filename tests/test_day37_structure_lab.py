import pytest
from experiments.day37_structure_lab import (
    LabDocChunk,
    lab_doc_chunk_to_search_chunk,
    TableHTMLParser,
    decide_table_size_action,
)


def test_paragraph_before_title_uses_unsectioned_fallback() -> None:
    """
    测试段落前没有标题时，使用未分节作为 fallback
    """

    def fake_splitter(text: str) -> list[str]:
        return [text]

    chunks = []
    chunks.append(
        LabDocChunk(
            text="本报告供投资者参考。",
            type="paragraph",
            page=1,
            source_file="demo.pdf",
            table_md="",
            section="",
            chunk_id="",
        )
    )

    result = lab_doc_chunk_to_search_chunk(chunks, fake_splitter)
    assert len(result) == 1
    assert result[0].section == "未分节"
    assert result[0].text == "本报告供投资者参考。"
    assert result[0].page == 1
    assert result[0].source_file == "demo.pdf"
    assert result[0].table_md == ""
    assert result[0].title_level is None
    assert result[0].type == "paragraph"


def test_consecutive_titles_build_full_section_path() -> None:
    """
    测试连续的标题构建完整的 section 路径
    """

    def fake_splitter(text: str) -> list[str]:
        return [text]

    chunks = []
    chunks.append(
        LabDocChunk(
            text="第一章 公司概况",
            title_level=1,
            type="title",
            page=1,
            source_file="demo.pdf",
            table_md="",
            section="",
            chunk_id="",
        )
    )
    chunks.append(
        LabDocChunk(
            text="1.1 收入构成",
            title_level=2,
            type="title",
            page=2,
            source_file="demo.pdf",
            table_md="",
            section="",
            chunk_id="",
        )
    )

    chunks.append(
        LabDocChunk(
            text="公司收入保持增长。",
            title_level=None,
            type="paragraph",
            page=2,
            source_file="demo.pdf",
            table_md="",
            section="",
            chunk_id="",
        )
    )

    result = lab_doc_chunk_to_search_chunk(chunks, fake_splitter)
    assert len(result) == 1
    assert result[0].type == "paragraph"
    assert result[0].section == "第一章 公司概况 > 1.1 收入构成"
    assert result[0].text == "公司收入保持增长。"
    assert result[0].page == 2
    assert result[0].source_file == "demo.pdf"
    assert result[0].table_md == ""
    assert result[0].title_level is None


def test_split_paragraphs_preserve_section_metadata_and_order() -> None:
    """
    测试分段保留 section 元数据和顺序
    """

    def fake_splitter(text: str) -> list[str]:
        if text == "甲乙":
            return ["甲", "乙"]
        elif text == "丙":
            return ["丙"]
        else:
            return [text]

    chunks = []
    chunks.append(
        LabDocChunk(
            text="第一章 公司概况",
            title_level=1,
            type="title",
            page=1,
            source_file="demo.pdf",
            table_md="",
            section="",
            chunk_id="",
        )
    )
    chunks.append(
        LabDocChunk(
            text="甲乙",
            title_level=None,
            type="paragraph",
            page=2,
            source_file="demo.pdf",
            table_md="",
            section="",
            chunk_id="",
        )
    )
    chunks.append(
        LabDocChunk(
            text="丙",
            title_level=None,
            type="paragraph",
            page=3,
            source_file="demo.pdf",
            table_md="",
            section="",
            chunk_id="",
        )
    )
    result = lab_doc_chunk_to_search_chunk(chunks, fake_splitter)
    assert len(result) == 3
    assert [chunk.text for chunk in result] == ["甲", "乙", "丙"]
    assert [chunk.section for chunk in result] == [
        "第一章 公司概况",
        "第一章 公司概况",
        "第一章 公司概况",
    ]
    assert [chunk.page for chunk in result] == [2, 2, 3]
    assert [chunk.source_file for chunk in result] == ["demo.pdf", "demo.pdf", "demo.pdf"]
    assert [chunk.table_md for chunk in result] == ["", "", ""]
    assert [chunk.title_level for chunk in result] == [None, None, None]
    assert [chunk.type for chunk in result] == ["paragraph", "paragraph", "paragraph"]


def test_table_keeps_position_payload_and_higher_title_resets_subsection() -> None:
    """
    测试表格保持位置负载并重置子节
    """
    splitter_calls: list[str] = []

    def fake_splitter(text: str) -> list[str]:
        splitter_calls.append(text)

        return [text]

    chunks = []
    chunks.append(
        LabDocChunk(
            text="第一章 公司概况",
            title_level=1,
            type="title",
            page=1,
            source_file="demo.pdf",
            table_md="",
            section="",
            chunk_id="",
        )
    )
    chunks.append(
        LabDocChunk(
            text="1.1 收入构成",
            title_level=2,
            type="title",
            page=2,
            source_file="demo.pdf",
            table_md="",
            section="",
            chunk_id="",
        )
    )
    chunks.append(
        LabDocChunk(
            text="收入构成表",
            title_level=None,
            type="table",
            page=3,
            source_file="demo.pdf",
            table_md="|业务|收入|\n|显示器件|100|",
            section="",
            chunk_id="",
        )
    )
    chunks.append(
        LabDocChunk(
            text="第二章 风险因素",
            title_level=1,
            type="title",
            page=4,
            source_file="demo.pdf",
            table_md="",
            section="",
            chunk_id="",
        )
    )
    chunks.append(
        LabDocChunk(
            text="市场波动可能影响业绩。",
            title_level=None,
            type="paragraph",
            page=4,
            source_file="demo.pdf",
            table_md="",
            section="",
            chunk_id="",
        )
    )
    result = lab_doc_chunk_to_search_chunk(chunks, fake_splitter)
    assert splitter_calls == ["市场波动可能影响业绩。"]
    assert len(result) == 2
    assert result[0].text == "收入构成表;业务=显示器件,收入=100"
    assert result[0].title_level is None
    assert result[0].section == "第一章 公司概况 > 1.1 收入构成"
    assert result[0].page == 3
    assert result[0].type == "table"
    assert result[0].source_file == "demo.pdf"
    assert result[0].table_md == "|业务|收入|\n|显示器件|100|"
    assert result[1].section == "第二章 风险因素"
    assert result[1].page == 4
    assert result[1].type == "paragraph"
    assert result[1].source_file == "demo.pdf"
    assert result[1].table_md == ""
    assert result[1].text == "市场波动可能影响业绩。"
    assert result[1].title_level is None


def test_returning_to_middle_title_level_keeps_valid_ancestors() -> None:
    """
    测试返回中间标题级别时保留有效的祖先
    """

    def fake_splitter(text: str) -> list[str]:
        return [text]

    chunks = []
    chunks.append(
        LabDocChunk(
            text="A",
            title_level=1,
            type="title",
            page=1,
            source_file="demo.pdf",
            table_md="",
            section="",
            chunk_id="",
        )
    )
    chunks.append(
        LabDocChunk(
            text="B",
            title_level=2,
            type="title",
            page=1,
            source_file="demo.pdf",
            table_md="",
            section="",
            chunk_id="",
        )
    )
    chunks.append(
        LabDocChunk(
            text="C",
            title_level=3,
            type="title",
            page=1,
            source_file="demo.pdf",
            table_md="",
            section="",
            chunk_id="",
        )
    )
    chunks.append(
        LabDocChunk(
            text="D",
            title_level=2,
            type="title",
            page=1,
            source_file="demo.pdf",
            table_md="",
            section="",
            chunk_id="",
        )
    )
    chunks.append(
        LabDocChunk(
            text="P",
            title_level=None,
            type="paragraph",
            page=1,
            source_file="demo.pdf",
            table_md="",
            section="",
            chunk_id="",
        )
    )
    result = lab_doc_chunk_to_search_chunk(chunks, fake_splitter)
    assert len(result) == 1
    assert result[0].section == "A > D"
    assert result[0].text == "P"
    assert result[0].title_level is None
    assert result[0].page == 1
    assert result[0].type == "paragraph"
    assert result[0].source_file == "demo.pdf"
    assert result[0].table_md == ""


def test_skipped_title_level_does_not_discard_valid_ancestor() -> None:
    """
    测试跳过的标题级别不会丢弃有效的祖先
    """

    def fake_splitter(text: str) -> list[str]:
        return [text]

    chunks = []
    chunks.append(
        LabDocChunk(
            text="A",
            title_level=1,
            type="title",
            page=1,
            source_file="demo.pdf",
            table_md="",
            section="",
            chunk_id="",
        )
    )
    chunks.append(
        LabDocChunk(
            text="C",
            title_level=3,
            type="title",
            page=1,
            source_file="demo.pdf",
            table_md="",
            section="",
            chunk_id="",
        )
    )
    chunks.append(
        LabDocChunk(
            text="D",
            title_level=2,
            type="title",
            page=1,
            source_file="demo.pdf",
            table_md="",
            section="",
            chunk_id="",
        )
    )
    chunks.append(
        LabDocChunk(
            text="P",
            title_level=None,
            type="paragraph",
            page=1,
            source_file="demo.pdf",
            table_md="",
            section="",
            chunk_id="",
        )
    )
    result = lab_doc_chunk_to_search_chunk(chunks, fake_splitter)
    assert len(result) == 1
    assert result[0].section == "A > D"
    assert result[0].text == "P"
    assert result[0].title_level is None
    assert result[0].page == 1
    assert result[0].type == "paragraph"
    assert result[0].source_file == "demo.pdf"
    assert result[0].table_md == ""


def test_table_builds_searchable_text_without_changing_citation_payload() -> None:
    """
    测试表格构建可搜索文本而不改变引用负载
    """
    splitter_calls: list[str] = []

    def fake_splitter(text: str) -> list[str]:
        splitter_calls.append(text)
        return [text]

    table_md = """|项目|期初账面价值|期末账面价值|
|---|---:|---:|
|资产A||2|
|资产B|3|4|"""
    chunks = []
    chunks.append(
        LabDocChunk(
            text="资产价值表",
            title_level=None,
            type="table",
            page=1,
            source_file="demo.pdf",
            table_md=table_md,
            section="",
            chunk_id="",
        )
    )
    result = lab_doc_chunk_to_search_chunk(chunks, fake_splitter)
    assert len(result) == 1
    assert (
        result[0].text
        == "资产价值表;项目=资产A,期初账面价值=空,期末账面价值=2;项目=资产B,期初账面价值=3,期末账面价值=4"
    )
    assert result[0].title_level is None
    assert result[0].section == "未分节"
    assert result[0].page == 1
    assert result[0].type == "table"
    assert result[0].source_file == "demo.pdf"
    assert result[0].table_md == table_md
    assert len(splitter_calls) == 0


def test_empty_table_body_keeps_summary_without_inventing_data() -> None:
    """
    测试空表格体保持摘要而不编造数据
    """
    splitter_calls: list[str] = []

    def fake_splitter(text: str) -> list[str]:
        splitter_calls.append(text)
        return [text]

    chunks = []
    chunks.append(
        LabDocChunk(
            text="收入构成表",
            title_level=None,
            type="table",
            page=10,
            source_file="demo.pdf",
            table_md="",
            section="",
            chunk_id="",
        )
    )
    result = lab_doc_chunk_to_search_chunk(chunks, fake_splitter)
    assert len(result) == 1
    assert result[0].text == "收入构成表"
    assert result[0].title_level is None
    assert result[0].section == "未分节"
    assert result[0].page == 10
    assert result[0].type == "table"
    assert result[0].source_file == "demo.pdf"
    assert result[0].table_md == ""
    assert len(splitter_calls) == 0


def test_header_only_table_keeps_headers_without_inventing_row_values() -> None:
    """
    测试空表格体保持摘要而不编造数据
    """
    splitter_calls: list[str] = []

    def fake_splitter(text: str) -> list[str]:
        splitter_calls.append(text)
        return [text]

    chunks = []
    chunks.append(
        LabDocChunk(
            text="资产价值表",
            title_level=None,
            type="table",
            page=11,
            source_file="demo.pdf",
            table_md="|项目|账面价值|\n|---|---:|",
            section="",
            chunk_id="",
        )
    )
    result = lab_doc_chunk_to_search_chunk(chunks, fake_splitter)
    assert len(result) == 1
    assert result[0].text == "资产价值表;项目,账面价值"
    assert result[0].title_level is None
    assert result[0].section == "未分节"
    assert result[0].page == 11
    assert result[0].type == "table"
    assert result[0].source_file == "demo.pdf"
    assert result[0].table_md == "|项目|账面价值|\n|---|---:|"
    assert len(splitter_calls) == 0


def test_html_table_builds_searchable_text_and_preserves_payload() -> None:
    splitter_calls: list[str] = []

    def fake_splitter(text: str) -> list[str]:
        splitter_calls.append(text)
        return [text]

    table_md = """<table>
  <tr>
    <td rowspan=1 colspan=1>项目</td>
    <td rowspan=1 colspan=1>账面价值</td>
    <td rowspan=1 colspan=1>原因</td>
  </tr>
  <tr>
    <td rowspan=1 colspan=1>项目A</td>
    <td rowspan=1 colspan=1>330</td>
    <td rowspan=1 colspan=1>办理中</td>
  </tr>
</table>"""
    chunks = []
    chunks.append(
        LabDocChunk(
            text="产权表",
            title_level=None,
            type="table",
            page=1,
            source_file="demo.pdf",
            table_md=table_md,
            section="",
            chunk_id="",
        )
    )
    result = lab_doc_chunk_to_search_chunk(chunks, fake_splitter)
    assert len(result) == 1
    assert result[0].table_md == table_md
    assert len(splitter_calls) == 0
    assert result[0].type == "table"
    assert result[0].text == "产权表;项目=项目A,账面价值=330,原因=办理中"
    assert result[0].title_level is None
    assert result[0].section == "未分节"
    assert result[0].page == 1
    assert result[0].source_file == "demo.pdf"


def test_html_parser_collects_rows_and_combines_nested_text() -> None:
    """
    测试 HTML 解析器收集行并组合嵌套文本
    """
    parser = TableHTMLParser()
    html = """<table>
  <tr><th>项目</th><th>说明</th></tr>
  <tr>
    <td rowspan="1" colspan="1">项目A</td>
    <td>hello <b>world</b></td>
  </tr>
</table>"""
    parser.feed(html)
    assert parser.rows == [["项目", "说明"], ["项目A", "hello world"]]


def test_unknown_table_format_raises_instead_of_silently_losing_payload() -> None:
    """
    测试未知表格格式时抛出异常而不是静默丢失负载
    """
    splitter_calls: list[str] = []

    def fake_splitter(text: str) -> list[str]:
        splitter_calls.append(text)
        return [text]

    chunks = []
    chunks.append(
        LabDocChunk(
            text="产权表",
            title_level=None,
            type="table",
            page=1,
            source_file="demo.pdf",
            table_md="项目,账面价值\n项目A,330",
            section="",
            chunk_id="",
        )
    )
    with pytest.raises(ValueError, match="表格转换为列表失败"):
        lab_doc_chunk_to_search_chunk(chunks, fake_splitter)


def test_table_row_with_mismatched_column_count_raises() -> None:
    """
    测试表格行与表头列数不匹配时抛出异常
    """
    splitter_calls: list[str] = []

    def fake_splitter(text: str) -> list[str]:
        splitter_calls.append(text)
        return [text]

    chunks = []
    md_str = """|项目|账面价值|
|---|---:|
|项目A|"""
    chunks.append(
        LabDocChunk(
            text="产权表",
            title_level=None,
            type="table",
            page=1,
            source_file="demo.pdf",
            table_md=md_str,
            section="",
            chunk_id="",
        )
    )
    with pytest.raises(ValueError, match="表头和行单元格数量不一致"):
        lab_doc_chunk_to_search_chunk(chunks, fake_splitter)


def test_html_colspan_greater_than_one_is_explicitly_rejected() -> None:
    splitter_calls: list[str] = []

    def fake_splitter(text: str) -> list[str]:
        splitter_calls.append(text)
        return [text]

    html_str = """<table><tr><th colspan="2">资产信息</th></tr></table>"""
    chunks = []
    chunks.append(
        LabDocChunk(
            text="资产信息",
            title_level=None,
            type="table",
            page=1,
            source_file="demo.pdf",
            table_md=html_str,
            section="",
            chunk_id="",
        )
    )
    with pytest.raises(ValueError, match="colspan is not supported"):
        lab_doc_chunk_to_search_chunk(chunks, fake_splitter)

def test_table_size_policy_has_executable_boundaries() -> None:
    assert decide_table_size_action(0, 0, 0, 2, 80) == "header_only"
    assert decide_table_size_action(1, 50, 50, 2, 80) == "whole"
    assert decide_table_size_action(2, 70, 40, 2, 80) == "whole"
    assert decide_table_size_action(3, 70, 30, 2, 80) == "split_rows_and_repeat_header"
    assert decide_table_size_action(1, 80, 80, 2, 80) == "whole"
    assert decide_table_size_action(2, 100, 60, 2, 80) == "split_rows_and_repeat_header"
    assert decide_table_size_action(1, 90, 90, 2, 80) == "oversized_row"