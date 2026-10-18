from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.documents.models import DocumentStatus, FailureStage


class HealthResponse(BaseModel):
    """health接口返回的最小进程存活信息。"""

    status: Literal["ok"]


class DocumentResponse(BaseModel):
    """对外展示文档状态，不包含存储定位和本机基础设施信息。"""

    model_config = ConfigDict(from_attributes=True)

    document_id: str
    source_file: str
    status: DocumentStatus
    failed_stage: FailureStage | None
    error_code: str | None
    safe_error_message: str | None
    created_at: datetime
    updated_at: datetime


class DocumentUploadResponse(DocumentResponse):
    """上传请求结果，额外说明是否命中已有相同内容。"""

    duplicate: bool


class ChatRequest(BaseModel):
    """浏览器提交的最小聊天请求，不接受可信上下文或过滤表达式。"""

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(
        min_length=1,
        description="浏览器当前选择的文档查找键",
    )
    query: str = Field(
        min_length=1,
        description="用户针对所选文档提出的问题",
    )
