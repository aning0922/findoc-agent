import json
from pathlib import Path
from typing import Literal
from .models import DocChunk
from html.parser import HTMLParser
from pydantic import BaseModel, Field

KNOWN_MINERU_TYPES = frozenset(["text", "table", "header", "footer", "page_number", "image"])
PAGE_FURNITURE_TYPES = frozenset(["header", "footer", "page_number"])


class MineruParseStats(BaseModel):
    """Mineru 解析统计信息"""

    input_element_count: int = Field(
        default=0, ge=0, description="从 content_list 读取的原始元素总数"
    )
    """从 content_list 读取的原始元素总数"""

    output_chunk_count: int = Field(default=0, ge=0, description="本次归一化后生成的 DocChunk 总数")
    """本次归一化后生成的 DocChunk 总数"""

    skipped_element_count: int = Field(
        default=0, ge=0, description="本次按已知生产策略明确跳过的 raw element 总数"
    )
    """本次按已知生产策略明确跳过的 raw element 总数"""
    skipped_count_by_type: dict[str, int] = Field(
        default_factory=dict, description="按 MinerU raw type 统计被跳过的元素数量"
    )
    """按 MinerU raw type 统计被跳过的元素数量"""

    reclassified_count_by_reason: dict[str, int] = Field(
        default_factory=dict, description="MinerU 标题候选被降级为 paragraph 的数量"
    )
    """MinerU 标题候选被降级为 paragraph 的数量"""

    skipped_count_by_reason: dict[str, int] = Field(
        default_factory=dict, description="按业务原因统计被跳过的元素数量"
    )
    """按业务原因统计被跳过的元素数量"""


class MineruParseResult(BaseModel):
    """Mineru 解析结果"""

    chunks: list[DocChunk] = Field(default_factory=list, description="解析结果块列表")
    """解析结果块列表"""
    stats: MineruParseStats = Field(default_factory=MineruParseStats, description="解析统计信息")
    """解析统计信息"""


class _MineruItem(BaseModel):
    """Mineru 适配器模型，对应单个文档块
    Args:
        type: 块类型，adapter 支持校验的 raw 元素
        text: 文本内容，对应 DocChunk.text
        text_level: 文本级别，对应 DocChunk.text_level
        page_idx: 页码，对应 DocChunk.page
        table_body: 表格内容，对应 DocChunk.table_body
        table_caption: 表格标题，对应 DocChunk.table_caption
    """

    type: Literal["table", "text", "image"]
    text: str = ""
    text_level: int | None = None
    page_idx: int
    table_body: str = ""
    table_caption: list[str] = Field(default_factory=list, description="表格标题")
    table_footnote: list[str] = Field(default_factory=list, description="图片脚注")
    img_path: str = Field(default="", description="表格或图片资源相对路径")
    image_caption: list[str] = Field(default_factory=list, description="图片说明")
    image_footnote: list[str] = Field(default_factory=list, description="图片脚注")


class TableHTMLParser(HTMLParser):
    """把 MinerU 表格 HTML 转换为按原始顺序排列的二维可见单元格。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._current_row: list[str] | None = None
        self._current_cell_parts: list[str] | None = None
        self._has_seen_table = False
        self._inside_table = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "table":
            self._has_seen_table = True
            self._inside_table = True
            return
        if not self._inside_table:
            return
        if tag == "tr":
            if self._current_row is not None:
                raise ValueError("不支持嵌套行")
            self._current_row = []
        if tag == "td" or tag == "th":
            if self._current_row is None:
                raise ValueError("单元格不在表格行中")
            if self._current_cell_parts is not None:
                raise ValueError("不支持嵌套单元格")
            self._current_cell_parts = []
        if tag == "br":
            if self._current_cell_parts is not None:
                self._current_cell_parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._inside_table and self._current_cell_parts is not None:
            self._current_cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._inside_table:
            if tag == "td" or tag == "th":
                if self._current_cell_parts is None:
                    raise ValueError("单元格结束标签不匹配")
                cell_text = " ".join("".join(self._current_cell_parts).split())

                if self._current_row is not None:
                    self._current_row.append(cell_text)
                self._current_cell_parts = None
            elif tag == "tr":
                if self._current_cell_parts is not None:
                    raise ValueError("行结束前单元格没有结束")
                if self._current_row is None:
                    raise ValueError("行结束标签不匹配")
                self.rows.append(self._current_row)
                self._current_row = None
            elif tag == "table":
                self._inside_table = False
            return

    def finish(self) -> None:
        if not self._has_seen_table:
            raise ValueError("表格未正确打开")
        if self._inside_table:
            raise ValueError("表格未正确关闭")
        if self._current_row is not None:
            raise ValueError("表格结构不完整")
        if self._current_cell_parts is not None:
            raise ValueError("表格结构不完整")
        text = ""
        for row in self.rows:
            for cell in row:
                text += cell.strip()
        if text.strip() == "":
            raise ValueError("表格没有可检索内容")


def table_html_to_rows(table_body: str) -> list[list[str]]:
    """把 HTML 表格解析成二维单元格；结构不受支持或没有可见文字时抛出 ValueError"""

    rows: list[list[str]] = []

    html_parser = TableHTMLParser()
    html_parser.feed(table_body)
    html_parser.close()
    html_parser.finish()
    rows = html_parser.rows
    return rows


def parse_mineru_output(out_dir: str, source_file: str) -> MineruParseResult:
    """解析 Mineru 输出目录中的内容列表文件，转换为 DocChunk 列表
    Args:
        out_dir: Mineru 输出目录
        source_file: 源文件路径
    Returns:
        MineruParseResult: 包含按原始顺序生成的 chunks 和本次解析统计
    """
    stats = MineruParseStats()
    matches = list(Path(out_dir).rglob("*_content_list.json"))
    if not matches:
        raise FileNotFoundError(f"没在{out_dir}找到 *_content_list.json 文件")
    content = matches[0].read_text(encoding="utf-8")
    json_data = json.loads(content)
    if not isinstance(json_data, list):
        raise ValueError("json 没有解析出list")
    items: list[_MineruItem] = []
    for index, raw in enumerate(json_data):
        stats.input_element_count += 1
        raw_type = raw.get("type")
        if raw_type not in KNOWN_MINERU_TYPES:
            raise ValueError(f"未知类型: {raw_type} 在 raw element[{index}]")
        if raw_type in PAGE_FURNITURE_TYPES:
            stats.skipped_element_count += 1
            stats.skipped_count_by_type[raw_type] = stats.skipped_count_by_type.get(raw_type, 0) + 1
            continue
        item = _MineruItem.model_validate(raw)
        if item.text_level is not None and item.text.strip() == "":
            raise ValueError("标题为空")
        if item.type == "table" and item.table_body.strip() == "":
            if (
                not "".join(item.table_caption).strip()
                and not "".join(item.table_footnote).strip()
                and not item.img_path.strip()
            ):
                stats.skipped_element_count += 1
                stats.skipped_count_by_type["table"] = (
                    stats.skipped_count_by_type.get("table", 0) + 1
                )
                stats.skipped_count_by_reason["empty_table_shell"] = (
                    stats.skipped_count_by_reason.get("empty_table_shell", 0) + 1
                )
                continue
            else:
                raise ValueError(
                    f"表格内容为空但有 caption、footnote 或 img_path: raw element[{index}]"
                )
        if raw_type == "text" and item.text.strip() == "" and item.text_level is None:
            stats.skipped_element_count += 1
            stats.skipped_count_by_type["text"] = stats.skipped_count_by_type.get("text", 0) + 1
            stats.skipped_count_by_reason["blank_text"] = (
                stats.skipped_count_by_reason.get("blank_text", 0) + 1
            )
            continue

        items.append(item)

    section_path: dict[int, str] = {}
    chunks: list[DocChunk] = []
    for el in items:
        page = el.page_idx + 1
        if el.type == "table":
            caption = "".join(el.table_caption).strip()
            if not caption:
                caption = f"第{page}页表格"
            rows = table_html_to_rows(el.table_body)
            table_md = ""
            for index, row in enumerate(rows):
                if index == len(rows) - 1:
                    table_md += " | ".join(row)
                else:
                    table_md += " | ".join(row) + "\n"
            chunks.append(
                DocChunk(
                    text=caption + "\n" + table_md,
                    page=page,
                    type="table",
                    source_file=source_file,
                    table_md=el.table_body,
                    section="/".join([v for _, v in sorted(section_path.items())])
                    if len(section_path) > 0
                    else "",
                    chunk_id="",
                )
            )
        elif el.type == "image":
            caption = "".join(el.image_caption).strip()
            footnote = "".join(el.image_footnote).strip()
            if not caption and not footnote:
                stats.skipped_element_count += 1
                stats.skipped_count_by_type["image"] = (
                    stats.skipped_count_by_type.get("image", 0) + 1
                )
                continue
            text = ""
            if caption:
                text += f"图片说明：{caption}"
            if footnote:
                text += f"\n图片脚注：{footnote}"

            chunks.append(
                DocChunk(
                    text=text,
                    page=page,
                    type="paragraph",
                    source_file=source_file,
                    table_md=None,
                    section="/".join([v for _, v in sorted(section_path.items())])
                    if len(section_path) > 0
                    else "",
                    chunk_id="",
                )
            )
        elif el.type == "text":
            if el.text_level is not None:
                if el.page_idx == 0:
                    stats.reclassified_count_by_reason["first_page_title"] = (
                        stats.reclassified_count_by_reason.get("first_page_title", 0) + 1
                    )
                    chunks.append(
                        DocChunk(
                            text=el.text.strip(),
                            page=page,
                            type="paragraph",
                            source_file=source_file,
                            table_md=None,
                            section="",
                            chunk_id="",
                        )
                    )
                elif "√" in el.text.strip() or "□" in el.text.strip():
                    stats.reclassified_count_by_reason["selection_marker"] = (
                        stats.reclassified_count_by_reason.get("selection_marker", 0) + 1
                    )
                    chunks.append(
                        DocChunk(
                            text=el.text.strip(),
                            page=page,
                            type="paragraph",
                            source_file=source_file,
                            table_md=None,
                            section="/".join([v for _, v in sorted(section_path.items())])
                            if len(section_path) > 0
                            else "",
                            chunk_id="",
                        )
                    )
                else:
                    section_path = {k: v for k, v in section_path.items() if k < el.text_level}
                    section_path[el.text_level] = el.text.strip()
                    chunks.append(
                        DocChunk(
                            text=el.text.strip(),
                            page=page,
                            type="title",
                            source_file=source_file,
                            table_md=None,
                            section="/".join([v for _, v in sorted(section_path.items())])
                            if len(section_path) > 0
                            else "",
                            chunk_id="",
                        )
                    )

            else:
                chunks.append(
                    DocChunk(
                        text=el.text.strip(),
                        page=page,
                        type="paragraph",
                        source_file=source_file,
                        section="/".join([v for _, v in sorted(section_path.items())])
                        if len(section_path) > 0
                        else "",
                        chunk_id="",
                    )
                )
    stats.output_chunk_count = len(chunks)
    return MineruParseResult(chunks=chunks, stats=stats)
