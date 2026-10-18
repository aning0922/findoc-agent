import asyncio
from typing import Protocol

from app.documents.preparation import (
    DocumentNotReadyError as DocumentNotReadyError,
    DocumentTaskPreparer,
    PreparedDocumentTask,
)
from app.rag.retriever import SearchFilters, TrustedContext
from app.rag.service import RAGOutcome

# 保留聊天层原有公开类型名；它与共享准备结果是同一个类型，没有复制校验逻辑。
PreparedChat = PreparedDocumentTask


class RAGAnswerer(Protocol):
    """定义聊天执行阶段所需的同步可信RAG能力。

    输入：问题、可信workspace上下文和服务端过滤条件。
    输出：成功、正常拒答或系统失败三种RAG终态。
    失败边界：本协议不负责SSE编码，也不承诺线程取消。
    """

    def answer(
        self,
        query: str,
        *,
        context: TrustedContext,
        filters: SearchFilters | None = None,
    ) -> RAGOutcome:
        """同步执行可信问答，并返回一个领域终态。"""
        ...


class ChatService:
    """负责前置检查和调用同步 RAGService，不负责 SSE framing 或终态事件映射"""

    def __init__(self, *, document_preparer: DocumentTaskPreparer, rag_service: RAGAnswerer) -> None:
        """保存共享文档准备组件和同步可信RAG依赖。

        Args:
            document_preparer: 使用固定workspace文档服务的共享准备组件。
            rag_service: 同步RAG执行器。

        Returns:
            ChatService: 可准备并执行可信聊天的服务对象。

        边界：构造阶段不查询文档，也不调用RAG。
        """
        self._document_preparer = document_preparer
        self._rag_service = rag_service

    async def prepare(self, *, document_id: str, query: str) -> PreparedChat:
        """准备一次聊天请求的输入。

        Args:
            document_id: 文档唯一标识符。
            query: 用户问题。

        Returns:
            PreparedChat: 准备完成的聊天输入。

        失败：文档不存在时保留DocumentNotFoundError，未ready时抛出
        DocumentNotReadyError，输入非法时保留PreparedChat校验异常。
        边界：workspace和document_id过滤都从服务端DocumentRecord恢复。
        """
        return await self._document_preparer.prepare(document_id=document_id, query=query)

    async def answer(self, prepared: PreparedChat) -> RAGOutcome:
        """执行一次聊天请求。

        Args:
            prepared: 准备完成的聊天输入。

        Returns:
            RAGOutcome: 聊天请求的结果。

        失败：同步RAG意外抛出的异常从工作线程传播给调用者。
        边界：通过asyncio.to_thread离开event loop，但不承诺客户端断开后取消线程。
        """
        return await asyncio.to_thread(
            self._rag_service.answer,
            prepared.query,
            context=prepared.context,
            filters=prepared.filters,
        )
