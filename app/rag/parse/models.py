from typing import Literal
from pydantic import BaseModel, Field


class PDFCell(BaseModel):
    text: str | None
    bbox: tuple[float, float, float, float] | None
    row_span: int | None = None
    column_span: int | None = None


class TableCell(BaseModel):
    row: int
    column: int
    text: str
    bbox: tuple[float, float, float, float]
    raw_cells: list[list[int]]
    actual_year: int | None = None
    is_header: bool = False


class TableStructure(BaseModel):
    schema_version: Literal["pdf-table-geometry-v1"] = "pdf-table-geometry-v1"
    status: Literal["verified", "unsupported"]
    reason: str | None = None
    columns: list[float] = Field(default_factory=list)
    rows: list[float] = Field(default_factory=list)
    cells: list[TableCell] = Field(default_factory=list)


class PDFLayout(BaseModel):
    strategy: Literal["ruled", "text_geometry"]
    rows: list[list[PDFCell]]
    table_structure: TableStructure | None = None


class DocChunk(BaseModel):
    text: str = Field(..., description="检索用文本，表格这块放标题+摘要")
    page: int = Field(ge=1)
    type: Literal["paragraph", "table", "title"]
    source_file: str = Field(..., description="源文件路径")
    table_md: str | None = Field(default=None, description="给LLM用，非表格为None")
    section: str = Field(default="", description="章节")
    chunk_id: str = Field(default="", description="唯一，分块时填 uuid")
    workspace_id: str = Field(default="", description="workspace id")
    document_id: str = Field(default="", description="document id")
    data_version: str = Field(default="", description="data version")
    layout: PDFLayout | None = None
