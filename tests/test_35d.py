import json
from pathlib import Path
import pytest
from app.rag.parse.mineru_adapter import parse_mineru_output


def test_mineru_rejects_non_list_json(tmp_path: Path):
    """
    测试parse_mineru_output函数，当json 没有解析出list时，抛出ValueError
    """
    content_file = tmp_path / "sample_content_list.json"
    content_file.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="json 没有解析出list"):
        parse_mineru_output(str(tmp_path), "dummy.pdf")


def test_mineru_preserves_title_hierarchy(tmp_path: Path):
    """
    测试parse_mineru_output函数， 测试title层次结构
    """
    content_file = tmp_path / "title_content_list.json"
    content_file.write_text(
        '[{"type":"text","text":"公司概况","text_level":1,"page_idx":1},{"type":"text","text":"主要业务","text_level":2,"page_idx":1},{"type":"text","text":"公司主要从事……","text_level":null,"page_idx":1}]',
        encoding="utf-8",
    )
    result = parse_mineru_output(str(tmp_path), "dummy.pdf")
    assert len(result.chunks) == 3
    assert [chunk.type for chunk in result.chunks] == ["title", "title", "paragraph"]


def test_mineru_propagates_section_hierarchy(tmp_path: Path):
    """
    测试parse_mineru_output函数， 测试section层次结构
    """
    content_file = tmp_path / "title_content_list.json"
    content_file.write_text(
        '[{"type":"text","text":"公司概况","text_level":1,"page_idx":1},{"type":"text","text":"主要业务","text_level":2,"page_idx":1},{"type":"text","text":"公司主要从事……","text_level":null,"page_idx":1}]',
        encoding="utf-8",
    )
    result = parse_mineru_output(str(tmp_path), "dummy.pdf")
    assert [chunk.section for chunk in result.chunks] == [
        "公司概况",
        "公司概况/主要业务",
        "公司概况/主要业务",
    ]


def test_mineru_table_body_is_searchable(tmp_path: Path):
    """
    测试parse_mineru_output函数， table_body是否进入text字段
    """
    table_body = (
        "<table>"
        "<tr><th>项目</th><th>金额</th></tr>"
        "<tr><td>净利润专属项</td><td>98765</td></tr>"
        "</table>"
    )
    content_file = tmp_path / "table_content_list.json"
    tmp_json = json.dumps(
        [
            {
                "type": "table",
                "table_caption": ["利润明细表"],
                "table_body": table_body,
                "page_idx": 0,
            }
        ],
        ensure_ascii=False,
    )
    content_file.write_text(
        tmp_json,
        encoding="utf-8",
    )
    result = parse_mineru_output(str(tmp_path), "dummy.pdf")
    assert len(result.chunks) == 1
    assert result.chunks[0].type == "table"
    assert "净利润专属项" in result.chunks[0].text
    assert "98765" in result.chunks[0].text
    assert result.chunks[0].table_md == table_body
    assert result.chunks[0].page == 1


def test_mineru_preserves_mixed_element_order(tmp_path: Path):
    """
    测试parse_mineru_output函数，当content_file为table_caption_content_list时，返回的result为3个元素，分别是text、table、text
    """
    content_file = tmp_path / "table_caption_content_list.json"
    content_file.write_text(
        '[{"type":"text","text":"顺序A","page_idx":0},{"type":"table","table_caption":["顺序B"],"table_body":"<table><tr><td>表体专属B</td></tr></table>","page_idx":0},{"type":"text","text":"顺序C","page_idx":0}]',
        encoding="utf-8",
    )
    result = parse_mineru_output(str(tmp_path), "dummy.pdf")
    assert len(result.chunks) == 3
    assert [chunk.type for chunk in result.chunks] == ["paragraph", "table", "paragraph"]
    assert result.chunks[0].text == "顺序A"
    assert result.chunks[1].table_md is not None and "表体专属B" in result.chunks[1].table_md
    assert result.chunks[2].text == "顺序C"


def test_mineru_rejects_missing_page_idx(tmp_path: Path):
    """
    测试parse_mineru_output函数， 测试page_idx为空时，抛出ValueError
    """
    content_file = tmp_path / "missing_page_idx_content_list.json"
    content_file.write_text(
        '[{"type":"text","text":"缺页码正文","text_level":null}]',
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        parse_mineru_output(str(tmp_path), "dummy.pdf")


def test_mineru_rejects_empty_title(tmp_path: Path):
    """
    测试parse_mineru_output函数，当content_file为empty_title_content_list时，抛出ValueError
    """
    content_file = tmp_path / "empty_title_content_list.json"
    content_file.write_text(
        '[{"type":"text","text":"","text_level":1,"page_idx":0}]',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="标题为空"):
        parse_mineru_output(str(tmp_path), "dummy.pdf")


def test_mineru_rejects_empty_table_body(tmp_path: Path):
    """
    测试parse_mineru_output函数， 测试table_body为空时，抛出ValueError
    """
    content_file = tmp_path / "empty_table_body_content_list.json"
    tmp_json = json.dumps(
        [
            {
                "type": "table",
                "table_caption": ["空表测试"],
                "table_footnote": [],
                "table_body": "",
                "img_path": "",
                "page_idx": 0,
            }
        ],
        ensure_ascii=False,
    )
    content_file.write_text(
        tmp_json,
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as exc_info:
        parse_mineru_output(str(tmp_path), "dummy.pdf")
    message = str(exc_info.value)
    assert "表格内容为空" in message
    assert "raw element[0]" in message


def test_mineru_header_is_skipped_and_counted_without_section_pollution(tmp_path: Path) -> None:
    """验证已知 header 被跳过并计入统计，同时不会创建或污染后续正文的 section"""
    content_file = tmp_path / "header_content_list.json"
    content_file.write_text(
        '[{"type":"header","text":"某某公司2025年年度报告","page_idx":0},{"type":"text","text":"营业收入同比增长。","page_idx":0}]',
        encoding="utf-8",
    )

    result = parse_mineru_output(str(tmp_path), "dummy.pdf")

    assert len(result.chunks) == 1
    assert result.chunks[0].type == "paragraph"
    assert result.chunks[0].text == "营业收入同比增长。"
    assert result.chunks[0].section == ""
    assert result.chunks[0].page == 1

    assert result.stats.input_element_count == 2
    assert result.stats.output_chunk_count == 1
    assert result.stats.skipped_element_count == 1
    assert result.stats.skipped_count_by_type["header"] == 1


def test_mineru_unknown_type_fails_with_raw_index_and_type(tmp_path: Path) -> None:
    """验证未知 raw type 不会被跳过或伪装成正文，并且错误信息能够定位 raw 序号和实际类型"""
    content_file = tmp_path / "unknown_type_content_list.json"
    content_file.write_text(
        '[{"type":"chart_magic","text":"神秘图表内容","page_idx":0}]',
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as exc_info:
        parse_mineru_output(str(tmp_path), "dummy.pdf")

    message = str(exc_info.value)
    assert "未知类型" in message
    assert "raw element[0]" in message
    assert "chart_magic" in message


def test_mineru_page_furniture_is_skipped_without_changing_section(tmp_path: Path) -> None:
    """验证 footer/page_number 被跳过并计数，而且不会修改已有章节状态"""
    content_file = tmp_path / "page_furniture_content_list.json"
    content_file.write_text(
        '[{"type":"text","text":"经营情况","text_level":2,"page_idx":1},{"type":"footer","text":"年度报告页脚","page_idx":1},{"type":"page_number","text":"2 / 10","page_idx":1},{"type":"text","text":"营业收入增长。","page_idx":1}]',
        encoding="utf-8",
    )
    result = parse_mineru_output(str(tmp_path), "dummy.pdf")
    stats = result.stats
    assert stats.input_element_count == 4
    assert stats.output_chunk_count == 2
    assert stats.skipped_element_count == 2
    assert [chunk.type for chunk in result.chunks] == ["title", "paragraph"]
    assert result.chunks[1].text == "营业收入增长。"
    assert result.chunks[1].section == "经营情况"

    assert stats.skipped_count_by_type["footer"] == 1
    assert stats.skipped_count_by_type["page_number"] == 1


def test_mineru_title_candidates_are_downgraded_without_polluting_section(tmp_path: Path) -> None:
    """验证第一页封面标题和适用性选择行被降级为 paragraph，真实结构标题仍能建立 section"""
    content_file = tmp_path / "title_candidates_content_list.json"
    content_file.write_text(
        '[{"type":"text","text":"某某公司2025年年度报告","text_level":1,"page_idx":0},{"type":"text","text":"经营情况","text_level":2,"page_idx":1},{"type":"text","text":"√适用 □不适用","text_level":2,"page_idx":1},{"type":"text","text":"营业收入同比增长。","page_idx":1}]',
        encoding="utf-8",
    )
    result = parse_mineru_output(str(tmp_path), "dummy.pdf")
    assert len(result.chunks) == 4
    assert result.chunks[0].type == "paragraph"
    assert result.chunks[0].section == ""

    assert result.chunks[2].type == "paragraph"
    assert result.chunks[2].section == "经营情况"
    assert result.chunks[2].text == "√适用 □不适用"

    assert result.chunks[3].type == "paragraph"
    assert result.chunks[3].section == "经营情况"
    assert result.chunks[3].text == "营业收入同比增长。"

    assert result.stats.reclassified_count_by_reason["first_page_title"] == 1
    assert result.stats.reclassified_count_by_reason["selection_marker"] == 1


def test_mineru_image_text_is_preserved_while_empty_image_is_counted(tmp_path: Path) -> None:
    """验证无说明图片被跳过并计数，有说明图片保留已有文字，而且图片不会修改 section"""
    content_file = tmp_path / "image_text_content_list.json"
    content_file.write_text(
        '[{"type":"text","text":"公司治理","text_level":2,"page_idx":1},{"type":"image","img_path":"images/empty.jpg","image_caption":[],"image_footnote":[],"page_idx":1},{"type":"image","img_path":"images/structure.jpg","image_caption":["股权结构图"],"image_footnote":["截至2025年末"],"page_idx":1},{"type":"text","text":"治理结构保持稳定。","page_idx":1}]',
        encoding="utf-8",
    )
    result = parse_mineru_output(str(tmp_path), "dummy.pdf")
    assert len(result.chunks) == 3
    assert [chunk.type for chunk in result.chunks] == ["title", "paragraph", "paragraph"]
    assert result.chunks[1].type == "paragraph"
    assert result.chunks[1].section == "公司治理"
    assert result.chunks[1].text == "图片说明：股权结构图\n图片脚注：截至2025年末"
    assert result.stats.input_element_count == 4
    assert result.stats.output_chunk_count == 3
    assert result.stats.skipped_element_count == 1
    assert result.stats.skipped_count_by_type["image"] == 1


def test_mineru_blank_paragraph_is_skipped_and_counted_by_reason(tmp_path: Path) -> None:
    """验证空白普通正文不会生成 DocChunk，但必须同时按 raw type 和业务原因计入统计"""
    content_file = tmp_path / "blank_paragraph_content_list.json"
    content_file.write_text(
        '[{"type":"text","text":"   \\n","page_idx":1},{"type":"text","text":"有效正文","page_idx":1}]',
        encoding="utf-8",
    )
    result = parse_mineru_output(str(tmp_path), "dummy.pdf")
    assert len(result.chunks) == 1
    assert result.chunks[0].type == "paragraph"
    assert result.chunks[0].text == "有效正文"
    assert result.stats.input_element_count == 2
    assert result.stats.output_chunk_count == 1
    assert result.stats.skipped_element_count == 1
    assert result.stats.skipped_count_by_type["text"] == 1
    assert result.stats.skipped_count_by_reason["blank_text"] == 1


def test_mineru_html_table_builds_search_text_and_preserves_raw_table_md(tmp_path: Path) -> None:
    """验证真实 HTML 表格生成无标签的检索文本，同时原始 HTML 在 table_md 中字节级保持不变，并继承已有 section"""
    content_file = tmp_path / "html_table_content_list.json"
    content_file.write_text(
        '[{"type":"text","text":"第三节 管理层讨论与分析","text_level":1,"page_idx":17},{"type":"table","table_caption":["主营业务","收入构成"],"table_body":"<table><tr><td>业务</td><td>收入占比</td></tr><tr><td>显示器件</td><td>81.34%</td></tr></table>","page_idx":18}]',
        encoding="utf-8",
    )
    result = parse_mineru_output(str(tmp_path), "dummy.pdf")
    assert len(result.chunks) == 2
    assert result.chunks[1].type == "table"
    assert result.chunks[1].page == 19
    assert result.chunks[1].section == "第三节 管理层讨论与分析"
    assert (
        result.chunks[1].table_md
        == "<table><tr><td>业务</td><td>收入占比</td></tr><tr><td>显示器件</td><td>81.34%</td></tr></table>"
    )
    assert result.chunks[1].text == ("主营业务收入构成\n业务 | 收入占比\n显示器件 | 81.34%")


def test_mineru_html_table_normalizes_visible_text_without_expanding_spans(tmp_path: Path) -> None:
    """验证表头和嵌套标签文字被保留、连续空白被压缩，且 rowspan 内容不会被复制展开"""
    content_file = tmp_path / "html_table_with_spans_content_list.json"

    tmp_json = json.dumps(
        [
            {
                "type": "table",
                "table_caption": ["主营业务", "收入构成"],
                "table_body": '<table border="1"><tr><th>业务   类型</th><th>收入占比</th></tr><tr><td rowspan="2"><b>显示器件</b></td><td>81.34%</td></tr><tr><td>18.66%</td></tr></table>',
                "page_idx": 18,
            }
        ],
        ensure_ascii=False,
    )
    content_file.write_text(tmp_json, encoding="utf-8")

    result = parse_mineru_output(str(tmp_path), "dummy.pdf")
    assert len(result.chunks) == 1
    assert result.chunks[0].type == "table"
    assert (
        result.chunks[0].table_md
        == '<table border="1"><tr><th>业务   类型</th><th>收入占比</th></tr><tr><td rowspan="2"><b>显示器件</b></td><td>81.34%</td></tr><tr><td>18.66%</td></tr></table>'
    )
    assert result.chunks[0].text == (
        "主营业务收入构成\n业务 类型 | 收入占比\n显示器件 | 81.34%\n18.66%"
    )
    assert result.chunks[0].text.count("显示器件") == 1
    assert "   " not in result.chunks[0].text


def test_mineru_empty_table_shell_is_skipped_and_counted(tmp_path: Path) -> None:
    """验证完全没有表体、caption、footnote 和 img_path 的 table 被明确跳过并计数"""
    content_file = tmp_path / "empty_table_shell_content_list.json"
    tmp_json = json.dumps(
        [
            {
                "type": "table",
                "table_body": "",
                "table_caption": [],
                "table_footnote": [],
                "img_path": "",
                "page_idx": 0,
            },
            {"type": "text", "text": "有效正文", "page_idx": 0},
        ],
        ensure_ascii=False,
    )
    content_file.write_text(tmp_json, encoding="utf-8")
    result = parse_mineru_output(str(tmp_path), "dummy.pdf")
    assert result.stats.input_element_count == 2
    assert result.stats.output_chunk_count == 1
    assert result.stats.skipped_element_count == 1
    assert result.stats.skipped_count_by_type["table"] == 1
    assert result.stats.skipped_count_by_reason["empty_table_shell"] == 1
    assert result.chunks[0].text == "有效正文"
