from pydantic import BaseModel
from collections.abc import Callable
from html.parser import HTMLParser


class LabDocChunk(BaseModel):
    text: str
    page: int
    type: str
    source_file: str
    table_md: str
    section: str
    chunk_id: str
    title_level: int | None = None


def decide_table_size_action(
    data_row_count: int,
    total_text_chars: int,
    max_single_row_text_chars: int,
    max_data_rows: int,
    max_text_chars: int,
) -> str:
    if data_row_count == 0:
        return "header_only"
    if max_single_row_text_chars > max_text_chars:
        return "oversized_row"
    if data_row_count > max_data_rows:
        return "split_rows_and_repeat_header"
    if total_text_chars > max_text_chars:
        return "split_rows_and_repeat_header"
    return "whole"


class TableHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self.current_row: list[str] | None = None
        self.current_cell_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self.current_row = []
        elif tag == "td" or tag == "th":
            if self.current_cell_parts is None:
                self.current_cell_parts = []
            if len(attrs) > 0:
                for attr, value in attrs:
                    if attr == "colspan" and value is not None and int(value) > 1:
                        raise ValueError("colspan is not supported")
                    elif attr == "rowspan" and value is not None and int(value) > 1:
                        raise ValueError("rowspan is not supported")

    def handle_data(self, data: str) -> None:
        if self.current_cell_parts is not None:
            self.current_cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" or tag == "th":
            if self.current_row is not None and self.current_cell_parts is not None:
                cell_text = "".join(self.current_cell_parts).strip()
                self.current_row.append(cell_text)
            self.current_cell_parts = None
        elif tag == "tr":
            if self.current_row is not None:
                self.rows.append(self.current_row)
            self.current_row = None


def table_md_to_list(table_md: str) -> list[list[str]]:
    """
    将表格md转换为列表
    """
    return_rows: list[list[str]] = []
    rows = table_md.split("\n")
    headers = rows[0].split("|")[1:-1]
    rowslen = len(rows)
    has_split_row = False
    if rowslen > 1:
        split_count = 0
        temp_row = rows[1]
        temp_cells = temp_row.split("|")[1:-1]
        temp_len = len(temp_cells)
        for i in range(temp_len):
            temp_cell = temp_cells[i].strip(" :")
            if bool(temp_cell) and all(c == "-" for c in temp_cell) and len(temp_cell) >= 3:
                split_count += 1
        if split_count == temp_len != 0:
            has_split_row = True

    if has_split_row:
        rows = rows[2:]
    else:
        rows = rows[1:]

    current_row: list[str] = []
    for header in headers:
        current_row.append(header.strip())
    return_rows.append(current_row)

    for row in rows:
        cells = row.split("|")[1:-1]
        current_row = []
        for cell in cells:
            current_row.append(cell.strip())
        return_rows.append(current_row)
    return return_rows


def table_to_text(text: str, table: str) -> str:
    if not table or table.strip() == "":
        return text
    rows: list[list[str]] | None = None
    table_str = table.strip()
    if table_str.startswith("<table"):
        parser = TableHTMLParser()
        parser.feed(table)
        rows = parser.rows
    elif table_str.startswith("|") and table_str.endswith("|"):
        rows = table_md_to_list(table_str)
    if rows is None:
        raise ValueError("表格转换为列表失败")
    if len(rows) == 0:
        return text
    return_str = text + ";"
    if len(rows) == 1:
        for row in rows:
            return_str += ",".join(row)
    else:
        headers = rows[0]
        rows = rows[1:]
        for i, row in enumerate(rows):
            if len(row) == len(headers):
                for i2, cell in enumerate(row):
                    if i2 == len(row) - 1:
                        if i == len(rows) - 1:
                            if cell.split():
                                return_str += headers[i2] + "=" + cell
                            else:
                                return_str += headers[i2] + "=空"
                        else:
                            if cell.split():
                                return_str += headers[i2] + "=" + cell + ";"
                            else:
                                return_str += headers[i2] + "=空;"
                    else:
                        if cell.split():
                            return_str += headers[i2] + "=" + cell + ","
                        else:
                            return_str += headers[i2] + "=空,"
            else:
                raise ValueError("表头和行单元格数量不一致")
    return return_str


def lab_doc_chunk_to_search_chunk(
    chunks: list[LabDocChunk], splitter: Callable[[str], list[str]]
) -> list[LabDocChunk]:
    result_chunks: list[LabDocChunk] = []
    section_path: dict[int, str] = {}
    for chunk in chunks:
        if chunk.type == "title":
            if chunk.title_level is None or chunk.title_level == 0:
                continue
            section_path = {k: v for k, v in section_path.items() if k < chunk.title_level}
            section_path[chunk.title_level] = chunk.text
        elif chunk.type == "table":
            result_chunks.append(
                LabDocChunk(
                    text=table_to_text(chunk.text, chunk.table_md),
                    page=chunk.page,
                    type=chunk.type,
                    source_file=chunk.source_file,
                    table_md=chunk.table_md,
                    section=" > ".join([v for _, v in sorted(section_path.items())])
                    if len(section_path) > 0
                    else "未分节",
                    chunk_id=chunk.chunk_id,
                    title_level=None,
                )
            )
        elif chunk.type == "paragraph":
            cleaned_text = splitter(chunk.text)
            for text in cleaned_text:
                result_chunks.append(
                    LabDocChunk(
                        text=text,
                        page=chunk.page,
                        type=chunk.type,
                        source_file=chunk.source_file,
                        table_md=chunk.table_md,
                        section=" > ".join([v for _, v in sorted(section_path.items())])
                        if len(section_path) > 0
                        else "未分节",
                        chunk_id=chunk.chunk_id,
                        title_level=None,
                    )
                )
    return result_chunks
