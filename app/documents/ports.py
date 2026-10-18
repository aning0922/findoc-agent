from typing import Protocol

from app.documents.models import (
    DocumentRecord,
    DocumentStatus,
    FailureStage,
)


class ObjectStore(Protocol):
    """定义应用层保存和读取原始对象 bytes 的最小存储合同。"""

    def put_bytes(self, object_key: str, content: bytes) -> None:
        """按服务端生成的 object_key 保存 bytes。

        Args:
            object_key: 不包含本机绝对路径的逻辑对象定位符。
            content: 需要持久化的原始对象内容。

        Raises:
            ValueError: object_key 不安全或 content 不符合合同。
            OSError: 对象写入失败。
        """
        ...

    def read_bytes(self, object_key: str) -> bytes:
        """按 object_key 读取原始对象内容。

        Args:
            object_key: 服务端生成的逻辑对象定位符。

        Returns:
            已保存的原始 bytes。

        Raises:
            ValueError: object_key 不安全。
            FileNotFoundError: 对象不存在。
            OSError: 对象读取失败。
        """
        ...


class DocumentRepository(Protocol):
    """定义文档记录持久化、判重和原子状态迁移合同"""

    def find_by_content(self, workspace_id: str, content_sha256: str) -> DocumentRecord | None:
        """根据 workspace_id 和 content_sha256 查找文档记录。
        Args:
            workspace_id: 服务端固定 workspace
            content_sha256: PDF bytes 的 SHA-256
        Returns:
            文档记录或 None
        """
        ...

    def create_or_get(self, record: DocumentRecord) -> tuple[DocumentRecord, bool]:
        """创建或获取文档记录。
        Args:
            record: 文档记录
        Returns:
            文档记录和是否创建新记录
        """
        ...

    def get(self, document_id: str) -> DocumentRecord | None:
        """根据 document_id 获取文档记录。
        Args:
            document_id: 服务端生成的文档身份
        Returns:
            文档记录或 None
        """
        ...

    def list_by_workspace(self, workspace_id: str) -> list[DocumentRecord]:
        """根据 workspace_id 获取文档记录列表。
        Args:
            workspace_id: 服务端固定 workspace
        Returns:
            文档记录列表
        """
        ...

    def transition_status(
        self,
        document_id: str,
        *,
        expected_status: DocumentStatus,
        new_status: DocumentStatus,
        failed_stage: FailureStage | None = None,
        error_code: str | None = None,
        safe_error_message: str | None = None,
    ) -> DocumentRecord:
        """根据 document_id 和 expected_status 迁移文档状态。
        Args:
            document_id: 服务端生成的文档身份
            expected_status: 期望的当前状态
            new_status: 新的状态
            failed_stage: 失败阶段
            error_code: 错误码
            safe_error_message: 安全错误信息
        Returns:
            文档记录
        Raises:
            DocumentNotFoundError：document_id不存在。
            DocumentStateConflictError：expected status不匹配或转换不合法。
        """
        ...


class TaskDispatcher(Protocol):
    """定义按稳定 document_id 调度后台处理任务的最小合同"""

    def dispatch(self, document_id: str) -> bool:
        """派发文档处理任务。
        Args:
            document_id: 服务端生成的文档身份
        Returns:
            True表示本次任务被接受；
            False表示同一document_id已有活动任务，没有重复创建。
        """
        ...
