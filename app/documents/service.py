import asyncio
from datetime import datetime, UTC
import hashlib

from app.documents.models import (
    DocumentNotFoundError,
    DocumentRecord,
    DocumentStateConflictError,
    DocumentStatus,
    DocumentTooLargeError,
    DocumentUploadResult,
    FailureStage,
    InvalidDocumentError,
)
from app.documents.ports import (
    DocumentRepository,
    ObjectStore,
    TaskDispatcher,
)

DEFAULT_MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class DocumentService:
    """协调文档存储、持久状态和后台任务调度的应用服务。"""

    def __init__(
        self,
        *,
        repository: DocumentRepository,
        object_store: ObjectStore,
        dispatcher: TaskDispatcher,
        workspace_id: str,
        max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
    ) -> None:
        """绑定文档应用服务需要的三个端口和可信 workspace。

        Args:
            repository: 文档记录及状态迁移端口。
            object_store: 原始文档对象存储端口。
            dispatcher: 后台任务调度端口。
            workspace_id: 由服务端配置的固定 workspace 身份。
            max_upload_bytes: 服务端允许的单个上传内容最大字节数。

        Raises:
            ValueError: workspace_id为空，或max_upload_bytes不是正整数。
        """
        if not workspace_id.strip():
            raise ValueError("workspace_id 不能为空")

        if max_upload_bytes <= 0:
            raise ValueError("max_upload_bytes 必须是正整数")

        self._repository = repository
        self._object_store = object_store
        self._dispatcher = dispatcher
        self._workspace_id = workspace_id
        self._max_upload_bytes = max_upload_bytes

    async def _mark_dispatch_rejected(
        self,
        document_id: str,
    ) -> DocumentRecord:
        """把未能派发的queued任务恢复为可观察、可重试的failed。"""
        return await asyncio.to_thread(
            self._repository.transition_status,
            document_id,
            expected_status=DocumentStatus.QUEUED,
            new_status=DocumentStatus.FAILED,
            failed_stage=FailureStage.QUEUED,
            error_code="TASK_DISPATCH_REJECTED",
            safe_error_message="文档任务暂时无法开始，请稍后重试",
        )

    def _validate_upload(
        self,
        *,
        source_file: str,
        content: bytes,
    ) -> str:
        """验证上传大小、逻辑文件名和 PDF magic，并返回安全展示名。

        Args:
            source_file: 用户上传时提供的逻辑文件名。
            content: 已读取且准备处理的上传 bytes。

        Returns:
            去除客户端目录部分的逻辑 PDF 文件名。

        Raises:
            InvalidDocumentError: 文件名、空内容或 PDF magic 不合法。
            DocumentTooLargeError: content 超过服务端大小限制。
        """
        logical_name = source_file.replace("\\", "/").rsplit("/", 1)[-1].strip()

        if not logical_name or not logical_name.lower().endswith(".pdf"):
            raise InvalidDocumentError("只支持扩展名为 .pdf 的文件")

        if not content:
            raise InvalidDocumentError("PDF 文件不能为空")

        if len(content) > self._max_upload_bytes:
            raise DocumentTooLargeError("PDF 文件超过允许的大小限制")

        if not content.startswith(b"%PDF-"):
            raise InvalidDocumentError("文件缺少合法的 PDF 标识")

        return logical_name

    def _build_document_identity(self, content_sha256: str) -> tuple[str, str]:
        """根据可信 workspace 和内容摘要生成稳定文档身份与对象定位符。

        Args:
            content_sha256: 已验证上传内容的 SHA-256。

        Returns:
            document_id 和不包含本机绝对路径的 object_key。
        """
        identity_payload = (f"{self._workspace_id}\0{content_sha256}").encode("utf-8")
        document_id = hashlib.sha256(identity_payload).hexdigest()
        object_key = f"documents/{document_id}.pdf"
        return document_id, object_key

    async def retry_document(self, document_id: str) -> DocumentRecord:
        """把 failed 文档原子地重新排队，并且只在成功后派发任务。

        Args:
            document_id: 需要显式重试的稳定文档身份。

        Returns:
            已迁移为 queued 的最新文档记录。

        Raises:
            DocumentNotFoundError: document_id 不存在。
            DocumentStateConflictError: 当前状态不是 failed，或任务已在活动。
            sqlite3.Error: SQLite 状态迁移失败。
        """
        await self.get_document(document_id)
        record = await asyncio.to_thread(
            self._repository.transition_status,
            document_id,
            expected_status=DocumentStatus.FAILED,
            new_status=DocumentStatus.QUEUED,
        )

        accepted = self._dispatcher.dispatch(document_id)
        if not accepted:
            await self._mark_dispatch_rejected(document_id)
            raise DocumentStateConflictError("该文档已有活动任务")

        return record

    @property
    def workspace_id(self) -> str:
        """Server-owned scope; never read from a request."""
        return self._workspace_id

    async def get_document(self, document_id: str) -> DocumentRecord:
        """查询当前 workspace 的文档，不存在或不属于该 workspace 时失败。"""
        record = await asyncio.to_thread(
            self._repository.get,
            document_id,
        )

        if record is None or record.workspace_id != self._workspace_id:
            raise DocumentNotFoundError(document_id)

        return record

    async def list_documents(self) -> list[DocumentRecord]:
        """按稳定顺序列出服务端固定 workspace 的文档。"""
        return await asyncio.to_thread(
            self._repository.list_by_workspace,
            self._workspace_id,
        )

    async def upload_document(self, *, source_file: str, content: bytes) -> DocumentUploadResult:
        """校验并持久化PDF，创建queued记录后立即尝试派发任务。

        Args:
            source_file: 用户上传时提供的逻辑文件名。
            content: 已受大小限制读取的PDF bytes。

        Returns:
            新建或重复命中的文档记录，以及duplicate标志。

        Raises:
            InvalidDocumentError: 文件名、空内容或PDF magic不合法。
            DocumentTooLargeError: 上传内容超过服务端大小限制。
            OSError: 对象写入失败。
            sqlite3.Error: 文档记录持久化失败。
        """
        logical_name = self._validate_upload(source_file=source_file, content=content)
        content_sha256 = hashlib.sha256(content).hexdigest()

        existing = await asyncio.to_thread(
            self._repository.find_by_content,
            self._workspace_id,
            content_sha256,
        )
        if existing is not None:
            return DocumentUploadResult(record=existing, duplicate=True)

        document_id, object_key = self._build_document_identity(content_sha256)
        await asyncio.to_thread(
            self._object_store.put_bytes,
            object_key,
            content,
        )

        now = datetime.now(UTC)
        candidate = DocumentRecord(
            document_id=document_id,
            workspace_id=self._workspace_id,
            source_file=logical_name,
            object_key=object_key,
            content_sha256=content_sha256,
            status=DocumentStatus.QUEUED,
            failed_stage=None,
            error_code=None,
            safe_error_message=None,
            created_at=now,
            updated_at=now,
            attempt=1,
        )

        stored, created = await asyncio.to_thread(
            self._repository.create_or_get,
            candidate,
        )

        if not created:
            return DocumentUploadResult(record=stored, duplicate=True)
        accepted = self._dispatcher.dispatch(stored.document_id)

        if accepted:
            return DocumentUploadResult(
                record=stored,
                duplicate=False,
            )
        failed = await self._mark_dispatch_rejected(stored.document_id)
        return DocumentUploadResult(
            record=failed,
            duplicate=False,
        )
