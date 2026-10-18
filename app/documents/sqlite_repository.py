from pathlib import Path
import sqlite3
from contextlib import closing
from datetime import UTC, datetime


from app.documents.models import (
    DocumentNotFoundError,
    DocumentRecord,
    DocumentStateConflictError,
    DocumentStatus,
    FailureStage,
)
from app.documents.ports import DocumentRepository

_ALLOWED_TRANSITIONS = frozenset(
    {
        (DocumentStatus.QUEUED, DocumentStatus.PARSING),
        (DocumentStatus.QUEUED, DocumentStatus.FAILED),
        (DocumentStatus.PARSING, DocumentStatus.INDEXING),
        (DocumentStatus.PARSING, DocumentStatus.FAILED),
        (DocumentStatus.INDEXING, DocumentStatus.READY),
        (DocumentStatus.INDEXING, DocumentStatus.FAILED),
        (DocumentStatus.FAILED, DocumentStatus.QUEUED),
    }
)


class SQLiteDocumentRepository(DocumentRepository):
    """基于 SQLite 的文档存储库"""

    def __init__(self, database_path: Path) -> None:
        """绑定 SQLite 文件路径，并幂等创建文档表。

        Args:
            database_path: SQLite 数据库文件路径。

        Raises:
            OSError: 数据库父目录创建失败。
            sqlite3.Error: 数据库连接或建表失败。
        """
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._database_path = database_path
        self._initialize_schema()

    def _connect(self) -> sqlite3.Connection:
        """读取self._database_path
        → sqlite3.connect(...)
        → 设置row_factory
        → 返回新connection

        每调用一次都必须返回一个新的 connection
        """
        conn = sqlite3.connect(self._database_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize_schema(self) -> None:
        """使用独立短连接幂等创建 documents 表。

        Raises:
            sqlite3.Error: 数据库连接、事务或建表失败。
        """
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS documents (
                        document_id TEXT PRIMARY KEY,
                        workspace_id TEXT NOT NULL,
                        source_file TEXT NOT NULL,
                        object_key TEXT NOT NULL,
                        content_sha256 TEXT NOT NULL,
                        status TEXT NOT NULL
                            CHECK (
                                status IN (
                                    'queued',
                                    'parsing',
                                    'indexing',
                                    'ready',
                                    'failed'
                                )
                            ),
                        failed_stage TEXT
                            CHECK (
                                failed_stage IS NULL
                                OR failed_stage IN (
                                    'queued',
                                    'parsing',
                                    'indexing'
                                )
                            ),
                        error_code TEXT,
                        safe_error_message TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        attempt INTEGER NOT NULL
                            CHECK (attempt >= 1),
                        UNIQUE (workspace_id, content_sha256),
                        CHECK (
                            (
                                status = 'failed'
                                AND failed_stage IS NOT NULL
                                AND error_code IS NOT NULL
                                AND safe_error_message IS NOT NULL
                            )
                            OR
                            (
                                status != 'failed'
                                AND failed_stage IS NULL
                                AND error_code IS NULL
                                AND safe_error_message IS NULL
                            )
                        )
                    )
                    """
                )

    def _record_to_parameters(self, record: DocumentRecord) -> dict[str, str | int | None]:
        """把 DocumentRecord 转换成 SQLite 命名参数。

        Args:
            record: 需要写入 SQLite 的文档记录。

        Returns:
            可以直接传给 sqlite3.execute 的参数字典。

        Raises:
            ValueError: datetime 或领域字段不符合上游合同。
        """
        return {
            "document_id": record.document_id,
            "workspace_id": record.workspace_id,
            "source_file": record.source_file,
            "object_key": record.object_key,
            "content_sha256": record.content_sha256,
            "status": record.status.value,
            "failed_stage": (
                record.failed_stage.value if record.failed_stage is not None else None
            ),
            "error_code": record.error_code,
            "safe_error_message": record.safe_error_message,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
            "attempt": record.attempt,
        }

    def _row_to_record(self, row: sqlite3.Row) -> DocumentRecord:
        """把 SQLite 查询行转换成不可变 DocumentRecord。

        Args:
            row: 使用 sqlite3.Row row_factory 得到的数据库行。

        Returns:
            完成枚举和时间类型恢复的文档记录。

        Raises:
            ValueError: 数据库中的状态、失败阶段或时间格式非法。
        """
        failed_stage_value = row["failed_stage"]
        failed_stage = None if failed_stage_value is None else FailureStage(failed_stage_value)

        return DocumentRecord(
            document_id=str(row["document_id"]),
            workspace_id=str(row["workspace_id"]),
            source_file=str(row["source_file"]),
            object_key=str(row["object_key"]),
            content_sha256=str(row["content_sha256"]),
            status=DocumentStatus(row["status"]),
            failed_stage=failed_stage,
            error_code=(None if row["error_code"] is None else str(row["error_code"])),
            safe_error_message=(
                None if row["safe_error_message"] is None else str(row["safe_error_message"])
            ),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            updated_at=datetime.fromisoformat(str(row["updated_at"])),
            attempt=int(row["attempt"]),
        )

    def get(self, document_id: str) -> DocumentRecord | None:
        """按稳定 document_id 查询文档记录。

        Args:
            document_id: 服务端生成的稳定文档身份。

        Returns:
            找到时返回 DocumentRecord，否则返回 None。

        Raises:
            sqlite3.Error: 数据库连接或查询失败。
            ValueError: 数据库行无法恢复成合法领域记录。
        """
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT * FROM documents WHERE document_id = ?
                """,
                (document_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def find_by_content(self, workspace_id: str, content_sha256: str) -> DocumentRecord | None:
        """查询同一 workspace 内具有相同内容身份的文档。

        Args:
            workspace_id: 服务端固定的 workspace 身份。
            content_sha256: 上传内容的 SHA-256。

        Returns:
            找到时返回已有记录，否则返回 None。

        Raises:
            sqlite3.Error: 数据库连接或查询失败。
            ValueError: 数据库行无法恢复成合法领域记录。
        """
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT * FROM documents WHERE workspace_id = ? AND content_sha256 = ?
                """,
                (workspace_id, content_sha256),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def list_by_workspace(self, workspace_id: str) -> list[DocumentRecord]:
        """按稳定顺序列出指定 workspace 的全部文档。

        Args:
            workspace_id: 服务端固定的 workspace 身份。

        Returns:
            按创建时间和 document_id 排序的记录列表；没有记录时返回空列表。

        Raises:
            sqlite3.Error: 数据库连接或查询失败。
            ValueError: 某一数据库行无法恢复成合法领域记录。
        """
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM documents
                WHERE workspace_id = ?
                ORDER BY created_at ASC, document_id ASC
                """,
                (workspace_id,),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def create_or_get(self, record: DocumentRecord) -> tuple[DocumentRecord, bool]:
        """原子地创建文档记录，内容重复时返回已有记录。

        Args:
            record: 准备写入 SQLite 的新文档记录。

        Returns:
            文档记录和本次是否成功创建。重复内容返回已有记录和 False。

        Raises:
            sqlite3.IntegrityError: 主键或其他数据库约束冲突。
            sqlite3.Error: 数据库连接、事务或查询失败。
            RuntimeError: 插入或判重后未能读回文档记录。
            ValueError: 数据库行无法恢复成合法领域记录。
        """
        parameters = self._record_to_parameters(record)
        with closing(self._connect()) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    INSERT INTO documents (
                        document_id,
                        workspace_id,
                        source_file,
                        object_key,
                        content_sha256,
                        status,
                        failed_stage,
                        error_code,
                        safe_error_message,
                        created_at,
                        updated_at,
                        attempt
                    )
                    VALUES (
                        :document_id,
                        :workspace_id,
                        :source_file,
                        :object_key,
                        :content_sha256,
                        :status,
                        :failed_stage,
                        :error_code,
                        :safe_error_message,
                        :created_at,
                        :updated_at,
                        :attempt
                    )
                    ON CONFLICT (workspace_id, content_sha256)
                    DO NOTHING
                    """,
                    parameters,
                )

                created = cursor.rowcount == 1

                if created:
                    stored_row = connection.execute(
                        """
                        SELECT * FROM documents WHERE document_id = ?
                        """,
                        (record.document_id,),
                    ).fetchone()
                else:
                    stored_row = connection.execute(
                        """
                        SELECT * FROM documents WHERE workspace_id = ? AND content_sha256 = ?
                        """,
                        (record.workspace_id, record.content_sha256),
                    ).fetchone()
            if stored_row is None:
                raise RuntimeError("创建或获取文档后未能读回文档记录")
            return self._row_to_record(stored_row), created

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
            ValueError：失败信息与目标状态不符合合同。
            sqlite3.Error：数据库连接、事务或查询失败。
            RuntimeError：更新成功后无法读回记录。
        """
        if (expected_status, new_status) not in _ALLOWED_TRANSITIONS:
            raise DocumentStateConflictError(
                f"不允许从 {expected_status.value} 转换到 {new_status.value}"
            )

        if new_status is DocumentStatus.FAILED:
            if failed_stage is None:
                raise ValueError("FAILED 状态必须指定失败阶段")

            if failed_stage.value != expected_status.value:
                raise ValueError("failed_stage 必须与失败前状态一致")

            if error_code is None or not error_code.strip():
                raise ValueError("FAILED 状态必须指定非空错误码")

            if safe_error_message is None or not safe_error_message.strip():
                raise ValueError("FAILED 状态必须指定非空安全错误信息")
        else:
            if any(
                value is not None
                for value in (
                    failed_stage,
                    error_code,
                    safe_error_message,
                )
            ):
                raise ValueError("非 FAILED 状态不能携带失败信息")
        parameters: dict[str, str | int | None] = {
            "document_id": document_id,
            "expected_status": expected_status.value,
            "new_status": new_status.value,
            "failed_stage": (failed_stage.value if failed_stage is not None else None),
            "error_code": error_code,
            "safe_error_message": safe_error_message,
            "updated_at": datetime.now(UTC).isoformat(),
            "attempt_increment": (
                1
                if (
                    expected_status is DocumentStatus.FAILED and new_status is DocumentStatus.QUEUED
                )
                else 0
            ),
        }

        with closing(self._connect()) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    UPDATE documents
                    SET
                        status = :new_status,
                        failed_stage = :failed_stage,
                        error_code = :error_code,
                        safe_error_message = :safe_error_message,
                        updated_at = :updated_at,
                        attempt = attempt + :attempt_increment
                    WHERE document_id = :document_id
                        AND status = :expected_status
                    """,
                    parameters,
                )
                transitioned = cursor.rowcount == 1

                if not transitioned:
                    current_row = connection.execute(
                        """
                        SELECT status
                        FROM documents
                        WHERE document_id = ?
                        """,
                        (document_id,),
                    ).fetchone()

                    if current_row is None:
                        raise DocumentNotFoundError(document_id)

                    actual_status = DocumentStatus(str(current_row["status"]))
                    raise DocumentStateConflictError(
                        "文档当前状态不允许本次转换："
                        f"expected={expected_status.value}, "
                        f"actual={actual_status.value}, "
                        f"new={new_status.value}"
                    )

                stored_row = connection.execute(
                    """
                    SELECT *
                    FROM documents
                    WHERE document_id = ?
                    """,
                    (document_id,),
                ).fetchone()

            if stored_row is None:
                raise RuntimeError("转换状态后未能读回文档记录")
            return self._row_to_record(stored_row)
