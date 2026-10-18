from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class DocumentStatus(StrEnum):
    """文档当前状态"""

    QUEUED = "queued"
    """文档等待处理"""
    PARSING = "parsing"
    """文档解析中"""
    INDEXING = "indexing"
    """文档索引中"""
    READY = "ready"
    """文档处理完成"""
    FAILED = "failed"
    """文档处理失败"""


class FailureStage(StrEnum):
    """文档处理失败阶段"""

    QUEUED = "queued"
    """文档等待处理"""
    PARSING = "parsing"
    """文档解析中"""
    INDEXING = "indexing"
    """文档索引中"""


@dataclass(frozen=True)
class DocumentRecord:
    """保存文档身份、处理状态和安全失败信息的不可变记录快照。"""

    document_id: str
    """服务端生成的稳定文档身份"""
    workspace_id: str
    """服务端固定 workspace"""
    source_file: str
    """用户可理解的逻辑文件名"""
    object_key: str
    """ObjectStore 内部定位符"""
    content_sha256: str
    """PDF bytes 的 SHA-256"""
    status: DocumentStatus
    """当前五态之一"""
    failed_stage: FailureStage | None
    """失败阶段：非 failed 时为 None"""
    error_code: str | None
    """稳定机器错误码"""
    safe_error_message: str | None
    """可展示且不包含内部信息的错误说明"""
    created_at: datetime
    """建档时间"""
    updated_at: datetime
    """最后状态变化时间"""
    attempt: int
    """完整处理尝试次数"""


class DocumentStateConflictError(Exception):
    """document_id可能存在
    但当前状态不允许请求的转换
    """


class DocumentNotFoundError(Exception):
    """指定 document_id 不存在"""


@dataclass(frozen=True)
class DocumentUploadResult:
    """表示上传得到的文档记录以及是否命中已有内容。"""

    record: DocumentRecord
    """上传得到的文档记录"""
    duplicate: bool
    """是否命中同 workspace 中已有的相同内容"""


class InvalidDocumentError(ValueError):
    """上传内容不是今天支持的合法文本型 PDF 输入"""


class DocumentTooLargeError(ValueError):
    """上传内容超过服务端允许的最大字节数"""
