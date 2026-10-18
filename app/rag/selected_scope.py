"""D15 reviewed retrieval adapter; no answers, numbering, model or second retrieval engine."""

import asyncio
import re

from app.documents.preparation import DocumentTaskPreparer, PreparedDocumentSelection
from app.rag.retriever import Retriever, SearchHit


class SelectedScopeSearch:
    def __init__(self, preparer: DocumentTaskPreparer, retriever: Retriever) -> None:
        self._preparer = preparer
        self._retriever = retriever

    async def table_context(
        self, hits: tuple[SearchHit, ...], *,
        excluded_pages: set[tuple[str, str, int]] | None = None,
    ) -> dict[tuple[str, str, int], str]:
        contexts = {}
        for hit in hits:
            if hit.type == "table" or "主要会计数据和财务指标" in hit.text or (
                re.search(r"\d", hit.text)
                and any(metric in re.sub(r'\s+', '', hit.text) for metric in ("营业收入", "净利润", "现金流量"))
            ):
                if hit.document_id is None or hit.source_revision is None:
                    raise ValueError("missing_table_identity")
                key = (hit.document_id, hit.source_revision, hit.page)
                if key not in contexts and key not in (excluded_pages or set()):
                    try:
                        contexts[key] = await self._preparer.page_context(*key)
                    except Exception as exc:
                        if excluded_pages is None or getattr(exc, 'code', None) != 'table_structure_unsupported':
                            raise
                        # Drop this whole physical page from publishable evidence.
                        # Never substitute its paragraph text or a partial table.
                        excluded_pages.add(key)
        return contexts

    async def revalidate(self, selection: PreparedDocumentSelection) -> None:
        await self._preparer.revalidate(selection)

    @staticmethod
    def retrieval_query(query: str) -> str:
        """Bounded intent phrases remove presentation instructions, never change source scope."""
        if "主要会计数据" in query:
            return "主要会计数据和财务指标"
        # Raw financial excerpts belong to the disclosed summary section. This
        # changes relevance only: the same BGE/Milvus query still verifies every
        # selected revision, with no page, amount, year or gold injected.
        if any(term in query for term in ("摘录", "原值", "原文")) and any(
            term in query for term in ("营业收入", "净利润", "现金流量净额")
        ):
            return "主要会计数据和财务指标"
        if any(term in query for term in ("主营业务", "主要业务", "核心业务", "主要产品")):
            return "公司主要业务 主要产品 核心业务概述"
        if "股票代码" in query or "股票简称" in query:
            return "公司简介 股票简称 股票代码 公司中文名称"
        return query

    async def search(
        self, selection: PreparedDocumentSelection, *, top_k: int = 5
    ) -> tuple[SearchHit, ...]:
        await self._preparer.revalidate(selection)
        hits = await asyncio.to_thread(
            self._retriever.retrieve,
            self.retrieval_query(selection.query),
            context=selection.context,
            filters=selection.filters,
            top_k=top_k,
        )
        await self._preparer.revalidate(selection)
        return tuple(hits)
