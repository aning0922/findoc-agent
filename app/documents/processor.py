from collections.abc import Callable
from typing import Any

from app.documents.models import (
    DocumentRecord,
    DocumentStatus,
    FailureStage,
)
from app.documents.ports import (
    DocumentRepository,
    ObjectStore,
)
from app.rag.ingest import (
    Embedder,
    ReplaceResult,
    build_aligned_rows,
    build_versioned_export_rows,
)
from app.rag.parse.models import DocChunk

Chunker = Callable[
    [list[DocChunk]],
    list[DocChunk],
]

PdfParser = Callable[[bytes, str], list[DocChunk]]
DocumentIndexer = Callable[
    [str, list[dict[str, Any]]],
    ReplaceResult,
]


def chunk_with_existing_strategy(
    blocks: list[DocChunk],
) -> list[DocChunk]:
    """延迟调用现有中文切块策略，避免应用启动时初始化tiktoken。

    Args:
        blocks: 已恢复逻辑source_file的解析块。

    Returns:
        已生成稳定chunk_id的最终文档块。

    Raises:
        Exception: tiktoken初始化或现有切块逻辑失败。
    """
    from app.rag.chunk import chunk_docment

    return chunk_docment(blocks)


class DocumentProcessor:
    """同步执行单份文档的解析、切块、embedding和索引状态链。"""

    def __init__(
        self,
        *,
        repository: DocumentRepository,
        object_store: ObjectStore,
        parser: PdfParser,
        embedder: Embedder,
        index_document: DocumentIndexer,
        chunker: Chunker = chunk_with_existing_strategy,
        data_version: str,
        source_identity: Callable[[DocumentRecord], dict[str, Any]] | None = None,
        source_recorder: Callable[[DocumentRecord, bytes, list[DocChunk]], None] | None = None,
    ) -> None:
        """绑定文档处理需要的端口和可替换计算依赖。

        Args:
            repository: 文档记录和原子状态迁移端口。
            object_store: 原始PDF bytes读取端口。
            parser: 把PDF bytes解析成尚未生成稳定ID的DocChunk列表。
            embedder: 把文本列表转换成对齐向量列表。
            index_document: 按document_id执行document级索引替换。
            chunker: 把解析块转换成带稳定chunk_id的最终块；默认延迟复用现有中文策略。
            data_version: runtime上传数据的版本标识。

        Raises:
            ValueError: data_version为空。
        """
        if not data_version.strip():
            raise ValueError("data_version 不能为空")

        self._repository = repository
        self._object_store = object_store
        self._parser = parser
        self._embedder = embedder
        self._index_document = index_document
        self._data_version = data_version
        self._chunker = chunker
        self._source_recorder = source_recorder
        self._source_identity = source_identity

    def _mark_failed(
        self,
        document_id: str,
        *,
        expected_status: DocumentStatus,
        failed_stage: FailureStage,
        error_code: str,
        safe_error_message: str,
    ) -> DocumentRecord:
        """把指定工作状态原子地迁移为可观察的failed。

        Args:
            document_id: 处理失败的稳定文档身份。
            expected_status: 失败发生前应处于的工作状态。
            failed_stage: 对外展示的稳定失败阶段。
            error_code: 不包含底层异常信息的稳定错误码。
            safe_error_message: 可安全展示给用户的错误说明。

        Returns:
            已更新为failed的文档记录。

        Raises:
            DocumentNotFoundError: 文档不存在。
            DocumentStateConflictError: 状态已经被其他执行者改变。
        """
        return self._repository.transition_status(
            document_id,
            expected_status=expected_status,
            new_status=DocumentStatus.FAILED,
            failed_stage=failed_stage,
            error_code=error_code,
            safe_error_message=safe_error_message,
        )

    def process(self, document_id: str) -> DocumentRecord:
        """完整执行一份queued文档，最终返回ready或failed记录。

        Args:
            document_id: dispatcher传入的稳定文档身份。

        Returns:
            完整处理成功后的ready记录，或安全保存错误后的failed记录。

        Raises:
            DocumentNotFoundError: 文档不存在。
            DocumentStateConflictError: worker未取得当前阶段的状态迁移资格。
        """
        record = self._repository.transition_status(
            document_id,
            expected_status=DocumentStatus.QUEUED,
            new_status=DocumentStatus.PARSING,
        )

        try:
            content = self._object_store.read_bytes(record.object_key)
            parsed_blocks = self._parser(
                content,
                record.source_file,
            )

            # parser可能曾接触临时路径；稳定ID生成前再次覆盖逻辑文件名。
            for block in parsed_blocks:
                block.source_file = record.source_file

            if self._source_recorder is not None:
                self._source_recorder(record, content, parsed_blocks)

            chunks = self._chunker(parsed_blocks)

            if not chunks:
                return self._mark_failed(
                    document_id,
                    expected_status=DocumentStatus.PARSING,
                    failed_stage=FailureStage.PARSING,
                    error_code="PDF_NO_TEXT",
                    safe_error_message="未从该PDF提取到可索引文本",
                )

            versioned_rows = build_versioned_export_rows(
                chunks,
                workspace_id=record.workspace_id,
                document_id=record.document_id,
                data_version=self._data_version,
            )
            if self._source_identity is not None:
                identity = self._source_identity(record)
                versioned_rows = [{**row, **identity} for row in versioned_rows]
        except Exception:
            return self._mark_failed(
                document_id,
                expected_status=DocumentStatus.PARSING,
                failed_stage=FailureStage.PARSING,
                error_code="PDF_PARSE_FAILED",
                safe_error_message="无法解析该PDF的文本内容",
            )

        self._repository.transition_status(
            document_id,
            expected_status=DocumentStatus.PARSING,
            new_status=DocumentStatus.INDEXING,
        )

        try:
            aligned_rows = build_aligned_rows(
                versioned_rows,
                self._embedder,
            )
            replace_result = self._index_document(
                document_id,
                aligned_rows,
            )

            expected_ids = frozenset(chunk.chunk_id for chunk in chunks)
            if replace_result.final_ids != expected_ids:
                raise RuntimeError("索引最终ID集合与预期不一致")
        except Exception:
            return self._mark_failed(
                document_id,
                expected_status=DocumentStatus.INDEXING,
                failed_stage=FailureStage.INDEXING,
                error_code="DOCUMENT_INDEX_FAILED",
                safe_error_message="文档索引失败，请重试",
            )

        return self._repository.transition_status(
            document_id,
            expected_status=DocumentStatus.INDEXING,
            new_status=DocumentStatus.READY,
        )
