"""真实检索证据到两期营业收入候选；仅支持带明确年份的独立文本行。

不确认事实，不读取计算事实仓库，不调用模型。未识别的格式不猜数值。
"""

import asyncio
from dataclasses import dataclass, replace
from decimal import Decimal, localcontext
import hashlib
import json
import re
from typing import Any

from app.agent import metric_extraction

from app.agent.financial_facts import FinancialUnit
from app.agent.research_workflow import (
    RevenueCandidate,
    RevenueEvidence,
    RevenueWorkflowFailureCode,
    RevenueWorkflowStage,
    RevenueWorkflowState,
    TARGET_PERIODS,
    begin_revenue_workflow,
    record_revenue_candidates,
)
from app.documents.preparation import DocumentTaskPreparer, PreparedDocumentTask
from app.documents.source_service import DocumentSourceService
from app.rag.retriever import Retriever, SearchHit


EXTRACTION_METHOD = "revenue_line_rule"
EXTRACTION_VERSION = "v1"
REVENUE_QUERY = "查询2024和2025年度营业收入"

# 整行匹配固定指标；不能从表格列、其他指标或句中任意数字拼造候选。
REVENUE_LINE = re.compile(
    r"^[ \t]*(?P<period>[0-9]{4})年度营业收入[：:][ \t]*"
    r"(?P<value>[+-]?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?)"
    r"[ \t]*(?P<unit>[^0-9\s。；;\r\n]*)[。]?[ \t]*$",
    re.MULTILINE,
)
UNIT_FACTORS = metric_extraction.UNIT_FACTORS


@dataclass(frozen=True)
class RevenueCandidateCollection:
    """候选收集输出：状态、原始命中和被排除的非目标期间。

    state.candidates 包含未确认候选；hits 供复核真实输入，不能用来计算。
    excluded_periods 解释期间不足，非目标年份不会被改写成 2024/2025。
    """

    state: RevenueWorkflowState
    hits: tuple[SearchHit, ...]
    excluded_periods: tuple[int, ...] = ()


class RevenueCandidateService:
    """查证 ready 文档、真实检索、生成候选的本地应用入口。

    输入：已绑定文档范围的 preparer、真实 Retriever；调用仅给 document_id。
    输出：RevenueCandidateCollection。前置/检索异常传播，候选问题由状态表示。
    边界：只完成收集步骤，没有确认、计算、持久候选或新 HTTP 端点。
    """

    def __init__(
        self,
        *,
        preparer: DocumentTaskPreparer,
        retriever: Retriever,
        sources: DocumentSourceService | None = None,
    ) -> None:
        self._preparer = preparer
        self._retriever = retriever
        self._sources = sources

    async def collect_metrics(
        self,
        *,
        document_id: str,
        company_id: str,
        source_revision: str,
        metric_keys: tuple[str, ...],
        periods: tuple[int, ...],
    ) -> dict[str, Any]:
        """Same candidate service, with dynamic selections over persisted D6 evidence."""
        if self._sources is None:
            raise ValueError("trusted source service is required")
        source, records = await self._sources.parsed_evidence(
            document_id,
            company_id=company_id,
            source_revision=source_revision,
        )
        result = await asyncio.to_thread(
            metric_extraction.extract_metrics,
            source=source,
            records=records,
            metric_keys=metric_keys,
            periods=periods,
        )
        final = await self._sources.source(
            document_id,
            company_id=company_id,
            source_revision=source_revision,
        )
        if final != source:
            raise ValueError("source changed during extraction")
        return result

    async def collect(self, *, document_id: str) -> RevenueCandidateCollection:
        """恢复服务端文档范围，把同步检索/抽取移到线程，返回未确认候选。"""
        if self._sources is not None:
            return await self._collect_report_revenue(document_id)
        prepared = await self._preparer.prepare(document_id=document_id, query=REVENUE_QUERY)
        return await asyncio.to_thread(self._collect_prepared, prepared)

    async def _collect_report_revenue(self, document_id: str) -> RevenueCandidateCollection:
        assert self._sources is not None
        source = await self._sources.source(document_id)
        result = await self.collect_metrics(
            document_id=document_id,
            company_id=source["company_id"],
            source_revision=source["source_revision"],
            metric_keys=("revenue",),
            periods=TARGET_PERIODS,
        )
        document = await self._sources.documents.get_document(document_id)
        state = begin_revenue_workflow(workspace_id=document.workspace_id, document_id=document_id)
        if any(c["status"] != "candidate" for c in result["candidates"]):
            return RevenueCandidateCollection(
                state=replace(
                    state,
                    stage=RevenueWorkflowStage.FAILED,
                    failure_code=RevenueWorkflowFailureCode.MISSING_CANDIDATE,
                ),
                hits=(),
            )
        converted = []
        for item in result["candidates"]:
            # Keep the complete table/period/scope proof in the existing evidence snapshot.
            evidence = []
            for proof in item["evidence"]:
                text = json.dumps(proof, ensure_ascii=False, sort_keys=True)
                evidence.append(
                    RevenueEvidence(
                        chunk_id=proof["evidence_id"],
                        source_file=document.source_file,
                        page=proof["physical_page"],
                        text=text,
                        start=0,
                        end=len(text),
                        raw_value=proof["raw_value"],
                        raw_unit=proof["raw_unit"],
                    )
                )
            # Candidate ID binds company/revision, geometry and basis evidence as well.
            first = evidence[0]
            converted.append(
                RevenueCandidate(
                    workspace_id=document.workspace_id,
                    document_id=document_id,
                    source_ref=f"revenue:{item['candidate_id']}",
                    chunk_id=first.chunk_id,
                    source_file=first.source_file,
                    page=first.page,
                    period=item["period"],
                    value=Decimal(item["value_cny_yuan"]),
                    unit=FinancialUnit.CNY_YUAN,
                    evidence=tuple(evidence),
                    extraction_method=metric_extraction.EXTRACTION_METHOD,
                    extraction_version=metric_extraction.EXTRACTION_VERSION,
                )
            )
        return RevenueCandidateCollection(
            state=record_revenue_candidates(state, tuple(converted)), hits=()
        )

    def _collect_prepared(self, prepared: PreparedDocumentTask) -> RevenueCandidateCollection:
        """只检索核准文档一次，再把实际 SearchHit 原样交给抽取层。"""
        hits = self._retriever.retrieve(
            prepared.query,
            context=prepared.context,
            filters=prepared.filters,
            top_k=5,
        )
        return extract_revenue_candidates(prepared=prepared, hits=tuple(hits))


def extract_revenue_candidates(
    *,
    prepared: PreparedDocumentTask,
    hits: tuple[SearchHit, ...],
) -> RevenueCandidateCollection:
    """核对整个命中批次后抽取、去重和合并，交给既有候选状态检查。

    prepared 必须来自文档准备入口；身份实际取自命中，过滤条件仅用于比对。
    来源缺失/不符或同 chunk 内容变化时整体阻断，避免留下部分合法候选。
    空检索/不支持的格式进入 missing_candidate；非目标期间不足有独立出口。
    """
    if prepared.filters is None or prepared.filters.document_id is None or not prepared.source_file:
        raise ValueError("候选抽取必须有已核准的单文档及来源文件")
    if not isinstance(hits, tuple) or not all(isinstance(hit, SearchHit) for hit in hits):
        raise TypeError("hits 必须是 SearchHit 元组")
    state = begin_revenue_workflow(
        workspace_id=prepared.context.workspace_id,
        document_id=prepared.filters.document_id,
    )
    source_failure = _check_sources(prepared, hits)
    if source_failure is not None:
        return RevenueCandidateCollection(
            state=replace(state, stage=RevenueWorkflowStage.FAILED, failure_code=source_failure),
            hits=hits,
        )

    candidates: list[RevenueCandidate] = []
    excluded: set[int] = set()
    for hit in hits:
        if hit.type != "paragraph":
            continue
        for match in REVENUE_LINE.finditer(hit.text):
            period = int(match["period"])
            if period not in TARGET_PERIODS:
                excluded.add(period)
                continue
            raw_value, raw_unit = match["value"], match["unit"] or None
            amount = Decimal(raw_value.replace(",", ""))
            factor = UNIT_FACTORS.get(raw_unit or "")
            # 加大局部精度，万元/亿元换算不截断长小数；未知单位保留原数。
            with localcontext() as context:
                context.prec = max(28, len(amount.as_tuple().digits) + 8)
                value = amount * factor if factor is not None else amount
            evidence = RevenueEvidence(
                chunk_id=hit.chunk_id,
                source_file=hit.source_file,
                page=hit.page,
                text=hit.text,
                start=match.start(),
                end=match.end(),
                raw_value=raw_value,
                raw_unit=raw_unit,
            )
            candidates.append(
                _candidate(
                    workspace_id=hit.workspace_id,
                    document_id=hit.document_id,
                    period=period,
                    value=value,
                    unit=FinancialUnit.CNY_YUAN if factor is not None else None,
                    evidence=(evidence,),
                )
            )

    merged = _merge_candidates(candidates)
    state = record_revenue_candidates(state, merged)
    if state.failure_code == RevenueWorkflowFailureCode.MISSING_CANDIDATE and excluded:
        state = replace(state, failure_code=RevenueWorkflowFailureCode.PERIOD_MISMATCH)
    return RevenueCandidateCollection(
        state=state, hits=hits, excluded_periods=tuple(sorted(excluded))
    )


def _check_sources(
    prepared: PreparedDocumentTask,
    hits: tuple[SearchHit, ...],
) -> RevenueWorkflowFailureCode | None:
    """检验实际来源身份与同片段内容的一致性；不补造任何身份字段。"""
    assert prepared.filters is not None
    seen: dict[str, SearchHit] = {}
    for hit in hits:
        if not hit.workspace_id or not hit.document_id:
            return RevenueWorkflowFailureCode.SOURCE_INVALID
        if (
            hit.workspace_id != prepared.context.workspace_id
            or hit.document_id != prepared.filters.document_id
            or hit.source_file != prepared.source_file
        ):
            return RevenueWorkflowFailureCode.SCOPE_MISMATCH
        if (
            not isinstance(hit.chunk_id, str)
            or not hit.chunk_id.strip()
            or not isinstance(hit.text, str)
            or not hit.text.strip()
            or isinstance(hit.page, bool)
            or not isinstance(hit.page, int)
            or hit.page < 1
        ):
            return RevenueWorkflowFailureCode.SOURCE_INVALID
        comparable = replace(hit, score=0.0)
        if hit.chunk_id in seen and seen[hit.chunk_id] != comparable:
            return RevenueWorkflowFailureCode.SOURCE_INVALID
        seen[hit.chunk_id] = comparable
    return None


def _candidate(
    *,
    workspace_id: str | None,
    document_id: str | None,
    period: int,
    value: Decimal,
    unit: FinancialUnit | None,
    evidence: tuple[RevenueEvidence, ...],
) -> RevenueCandidate:
    """生成带全部证据的候选；引用包含期间与证据位置，避免同 chunk 两年碰撞。"""
    assert workspace_id is not None and document_id is not None
    ordered = tuple(sorted(set(evidence), key=lambda item: (item.chunk_id, item.start, item.end)))
    reference_input = [
        workspace_id,
        document_id,
        "revenue",
        period,
        [[item.chunk_id, item.start, item.end] for item in ordered],
    ]
    digest = hashlib.sha256(json.dumps(reference_input, ensure_ascii=False).encode()).hexdigest()
    primary = ordered[0]
    return RevenueCandidate(
        workspace_id=workspace_id,
        document_id=document_id,
        source_ref=f"revenue:{digest}",
        chunk_id=primary.chunk_id,
        source_file=primary.source_file,
        page=primary.page,
        period=period,
        value=value,
        unit=unit,
        evidence=ordered,
        extraction_method=EXTRACTION_METHOD,
        extraction_version=EXTRACTION_VERSION,
    )


def _merge_candidates(candidates: list[RevenueCandidate]) -> tuple[RevenueCandidate, ...]:
    """已知单位按期间/金额合并全部来源；未知单位只去除完全相同的证据。"""
    groups: dict[tuple[object, ...], RevenueCandidate] = {}
    for item in candidates:
        key: tuple[object, ...] = (item.period, item.value, item.unit)
        if item.unit is None:
            key += (item.evidence,)
        previous = groups.get(key)
        if previous is None:
            groups[key] = item
        else:
            groups[key] = _candidate(
                workspace_id=item.workspace_id,
                document_id=item.document_id,
                period=item.period,
                value=item.value,
                unit=item.unit,
                evidence=previous.evidence + item.evidence,
            )
    return tuple(sorted(groups.values(), key=lambda item: (item.period, item.source_ref)))
