from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from app.agent.finance_tools import build_finance_tool_registry
from app.agent.financial_facts import (
    FinancialFact,
    FinancialFactKey,
    FinancialUnit,
    InMemoryFinancialFactRepository,
)
from app.agent.tool_loop import ToolExecutionContext, ToolRegistry
from app.rag.retriever import Retriever, SearchFilters, SearchStore, TrustedContext


AGENT_EVAL_WORKSPACE_ID = "WS-AGENT-EVAL"
AGENT_EVAL_DOCUMENT_ID = "DOC-AGENT-EVAL"


def _frozen_eval_embedder(queries: list[str]) -> list[list[float]]:
    """用固定类别编码路由评测查询，不调用外部 embedding。"""
    vectors: list[list[float]] = []
    for query in queries:
        if "研发" in query:
            vectors.append([3.0])
        elif "现金流" in query:
            vectors.append([2.0])
        else:
            vectors.append([1.0])
    return vectors


class _FrozenAgentEvalStore(SearchStore):
    """为 Agent 评测返回独立于 W8 资产的确定性检索片段。"""

    def search(
        self,
        query_vector: list[float],
        *,
        top_k: int,
        filter_expression: str,
    ) -> list[Mapping[str, Any]]:
        """根据固定类别编码返回最多 top_k 条白名单命中。"""
        category = query_vector[0]
        if category == 3.0:
            hits: list[Mapping[str, Any]] = [
                {
                    "score": 0.91,
                    "chunk_id": "chunk-rd",
                    "text": "2025 年研发费用为 8 亿元。",
                    "page": 12,
                    "source_file": "agent-eval-report.pdf",
                    "type": "paragraph",
                    "section": "研发投入",
                }
            ]
        elif category == 2.0:
            hits = [
                {
                    "score": 0.92,
                    "chunk_id": "chunk-cash-flow",
                    "text": "2025 年经营活动产生的现金流量净额为 30 亿元。",
                    "page": 8,
                    "source_file": "agent-eval-report.pdf",
                    "type": "paragraph",
                    "section": "现金流量表",
                }
            ]
        else:
            hits = [
                {
                    "score": 0.99,
                    "chunk_id": "chunk-current",
                    "text": "2025 年营业收入为 100 亿元。",
                    "page": 5,
                    "source_file": "agent-eval-report.pdf",
                    "type": "paragraph",
                    "section": "主要会计数据",
                },
                {
                    "score": 0.98,
                    "chunk_id": "chunk-previous",
                    "text": "2024 年营业收入为 80 亿元。",
                    "page": 5,
                    "source_file": "agent-eval-report.pdf",
                    "type": "paragraph",
                    "section": "主要会计数据",
                },
            ]
        return hits[:top_k]


def build_agent_eval_dependencies() -> tuple[ToolRegistry, ToolExecutionContext]:
    """构造独立、确定性且受可信上下文约束的 Agent 评测依赖。"""
    retriever = Retriever(_frozen_eval_embedder, _FrozenAgentEvalStore())
    fact_repository = InMemoryFinancialFactRepository(
        [
            FinancialFact(
                workspace_id=AGENT_EVAL_WORKSPACE_ID,
                document_id=AGENT_EVAL_DOCUMENT_ID,
                source_ref="chunk-current",
                fact_key=FinancialFactKey.REVENUE,
                period=2025,
                value=Decimal("100"),
                unit=FinancialUnit.CNY_100_MILLION,
            ),
            FinancialFact(
                workspace_id=AGENT_EVAL_WORKSPACE_ID,
                document_id=AGENT_EVAL_DOCUMENT_ID,
                source_ref="chunk-previous",
                fact_key=FinancialFactKey.REVENUE,
                period=2024,
                value=Decimal("80"),
                unit=FinancialUnit.CNY_100_MILLION,
            ),
        ]
    )
    registry = build_finance_tool_registry(
        retriever=retriever,
        financial_fact_repository=fact_repository,
    )
    execution_context = ToolExecutionContext(
        trusted_context=TrustedContext(workspace_id=AGENT_EVAL_WORKSPACE_ID),
        filters=SearchFilters(document_id=AGENT_EVAL_DOCUMENT_ID),
    )
    return registry, execution_context
