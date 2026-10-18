"""本地两期收入确认：查证当前来源、绑定所见快照、持久读回后计算。

应用服务负责重新查证；快照摘要只是比较键，调用方自报版本不能代替查证。
不接入生产 Agent、不调用 LLM，也不定义第二套增长率公式。
"""

import asyncio
import sqlite3
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Literal, Protocol
from typing import Any

from app.agent import metric_extraction, revenue_extraction
from app.agent.financial_facts import FinancialFactRepository, FinancialUnit
from app.agent.research_workflow import (
    ConfirmedRevenueFact,
    RevenueCandidate,
    RevenueGrowthResult,
    RevenueWorkflowStage,
    begin_revenue_workflow,
    calculate_confirmed_revenue_growth,
    confirm_revenue_candidates,
    record_revenue_candidates,
)
from app.documents.models import DocumentRecord, DocumentStatus
from app.documents.ports import ObjectStore
from app.documents.preparation import DocumentReader
from app.documents.source_models import SourceError
from app.documents.source_service import DocumentSourceService
from app.companies.models import RegistryNotFoundError


ConfirmationKind = Literal["local_operator", "simulated_test"]


def canonical_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class FinancialReview:
    """D9 immutable review, including blocked candidates; never a financial fact."""

    workspace_id: str
    payload_json: str

    def to_payload(self) -> dict[str, Any]:
        payload = json.loads(self.payload_json)
        if not isinstance(payload, dict):
            raise ValueError("review payload must be an object")
        return payload

    @property
    def snapshot_id(self) -> str:
        return "financial-review-v1:" + hashlib.sha256(self.payload_json.encode()).hexdigest()

    @property
    def acceptable(self) -> bool:
        p = self.to_payload()
        source = p["source"]
        candidates = p["candidates"]
        expected = {
            (k, y) for k in p["selection"]["metric_keys"] for y in p["selection"]["periods"]
        }
        if (
            len(candidates) != len(expected)
            or {(c["metric_key"], c["period"]) for c in candidates} != expected
        ):
            return False
        records = {e["evidence_id"]: e for e in p["source_evidence"]}
        for c in candidates:
            if (
                c["status"] != "candidate"
                or c["failure_reason"] is not None
                or c["confirmation_status"] != "pending"
                or any(
                    c[k] != source[k]
                    for k in (
                        "company_id",
                        "document_id",
                        "source_revision",
                        "content_sha256",
                        "attempt",
                        "parser_version",
                    )
                )
                or c["currency"] != "CNY"
                or c["scope"] != "consolidated"
                or c["accounting_basis"] != "PRC_GAAP"
                or c["period_type"] != "annual"
                or not c["evidence"]
                or not c["basis_evidence"]
                or c["value_cny_yuan"] is None
                or c["raw_value"] is None
                or c["raw_unit"] is None
            ):
                return False
            # Reuse D7 Decimal parsing. This gate validates evidence, it does not extract a new value.
            normalized = metric_extraction.parse_amount(c["raw_value"], c["raw_unit"])
            if normalized is None or format(normalized, "f") != c["value_cny_yuan"]:
                return False
            if not any(e["role"] == "statement" for e in c["evidence"]):
                return False
            for e in [*c["evidence"], *c["basis_evidence"]]:
                record = records.get(e["evidence_id"])
                if (
                    record is None
                    or record["physical_page"] != e["physical_page"]
                    or record["source_revision"] != source["source_revision"]
                    or not record["text"]
                    or not 1 <= e["physical_page"] <= source["physical_pages"]
                ):
                    return False
            if any(
                e["failure_reason"] is not None
                or e["value"] is None
                or e["metric_key"] != c["metric_key"]
                or e["period"] != c["period"]
                or Decimal(e["value"]) != Decimal(c["value_cny_yuan"])
                for e in c["evidence"]
            ):
                return False
        return bool(candidates)


@dataclass(frozen=True)
class FinancialAcceptance:
    """Recoverable acceptance receipt. D10 will create dynamic financial facts."""

    receipt_id: str
    request_id: str
    accepted_at: datetime
    confirmation_kind: ConfirmationKind
    review: FinancialReview

    def to_payload(self) -> dict[str, Any]:
        return dict(
            schema="financial-acceptance-v1",
            receipt_id=self.receipt_id,
            request_id=self.request_id,
            accepted_at=self.accepted_at.isoformat(),
            confirmation_kind=self.confirmation_kind,
            snapshot_id=self.review.snapshot_id,
            status="acceptance_saved",
            facts_status="pending_d10",
            analysis_started=False,
            company_id=self.review.to_payload()["source"]["company_id"],
            document_id=self.review.to_payload()["source"]["document_id"],
            source_revision=self.review.to_payload()["source"]["source_revision"],
            review=self.review.to_payload(),
        )


@dataclass(frozen=True)
class ConfirmedFinancialFact:
    """One Decimal fact projected only from the accepted, trusted candidate."""

    fact_id: str
    fact_set_id: str
    candidate_json: str

    @property
    def value(self) -> Decimal:
        return Decimal(json.loads(self.candidate_json)["value_cny_yuan"])

    def to_payload(self) -> dict[str, Any]:
        return {
            **json.loads(self.candidate_json),
            "fact_id": self.fact_id,
            "fact_set_id": self.fact_set_id,
            "confirmation_status": "confirmed",
            "unit": "CNY_YUAN",
        }


@dataclass(frozen=True)
class FinancialFactSet:
    """Durable conversion of a D9 receipt; validity is checked at every read."""

    fact_set_id: str
    receipt: FinancialAcceptance
    disclosure_version: str
    saved_at: datetime
    facts: tuple[ConfirmedFinancialFact, ...]
    current_valid: bool = True
    invalid_reason: str | None = None

    def to_payload(self) -> dict[str, Any]:
        p = self.receipt.review.to_payload()
        return dict(
            schema="financial-fact-set-v1",
            fact_set_id=self.fact_set_id,
            receipt_id=self.receipt.receipt_id,
            snapshot_id=self.receipt.review.snapshot_id,
            confirmation_kind=self.receipt.confirmation_kind,
            accepted_at=self.receipt.accepted_at.isoformat(),
            saved_at=self.saved_at.isoformat(),
            company_id=p["source"]["company_id"],
            document_id=p["source"]["document_id"],
            source_revision=p["source"]["source_revision"],
            disclosure_version=self.disclosure_version,
            status="facts_saved",
            integrity="verified",
            current_valid=self.current_valid,
            invalid_reason=self.invalid_reason,
            calculable=self.current_valid,
            production_calculable=self.current_valid
            and self.receipt.confirmation_kind == "local_operator",
            facts=[f.to_payload() for f in self.facts],
            review=p,
        )


class RevenueConfirmationError(RuntimeError):
    """确认/读回/计算被拒绝；只带稳定错误码，不带可用旧结果。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class RevenueSourceRevision:
    """来源版本：服务端文档范围/内容/处理次数，以及当前抽取规则版本。"""

    workspace_id: str
    document_id: str
    content_sha256: str
    attempt: int
    extraction_method: str
    extraction_version: str


def candidate_payload(candidate: RevenueCandidate) -> dict[str, object]:
    """候选转可审阅 JSON；金额保存十进制字符串，全部原文证据保留。"""
    return {
        "workspace_id": candidate.workspace_id,
        "document_id": candidate.document_id,
        "source_ref": candidate.source_ref,
        "chunk_id": candidate.chunk_id,
        "source_file": candidate.source_file,
        "page": candidate.page,
        "period": candidate.period,
        "value": format(candidate.value, "f"),
        "unit": candidate.unit.value if candidate.unit is not None else None,
        "extraction_method": candidate.extraction_method,
        "extraction_version": candidate.extraction_version,
        "evidence": [asdict(item) for item in candidate.evidence],
    }


@dataclass(frozen=True)
class RevenueReview:
    """供操作者核对的一组不可变候选；摘要绑定版本与全部内容，不含检索分数。"""

    revision: RevenueSourceRevision
    candidates: tuple[RevenueCandidate, ...]

    def __post_init__(self) -> None:
        """复用候选准入，并收紧到有证据、人民币元、当前两期和明确抽取版本。"""
        revision = self.revision
        if (
            not revision.workspace_id.strip()
            or not revision.document_id.strip()
            or len(revision.content_sha256) != 64
            or any(char not in "0123456789abcdef" for char in revision.content_sha256)
            or isinstance(revision.attempt, bool)
            or not isinstance(revision.attempt, int)
            or revision.attempt < 1
            or not revision.extraction_method.strip()
            or not revision.extraction_version.strip()
        ):
            raise RevenueConfirmationError("source_invalid")
        state = record_revenue_candidates(
            begin_revenue_workflow(
                workspace_id=revision.workspace_id, document_id=revision.document_id
            ),
            self.candidates,
        )
        if state.stage is not RevenueWorkflowStage.AWAITING_CONFIRMATION:
            raise RevenueConfirmationError(str(state.failure_code))
        if len(self.candidates) != 2:
            raise RevenueConfirmationError("candidate_conflict")
        for item in self.candidates:
            if isinstance(item.period, bool) or not isinstance(item.period, int):
                raise RevenueConfirmationError("period_mismatch")
            if item.unit is not FinancialUnit.CNY_YUAN:
                raise RevenueConfirmationError("unit_conflict")
            if not item.evidence or any(e.source_file != item.source_file for e in item.evidence):
                raise RevenueConfirmationError("source_invalid")
            if (item.extraction_method, item.extraction_version) != (
                revision.extraction_method,
                revision.extraction_version,
            ):
                raise RevenueConfirmationError("source_changed")
        if len({item.source_ref for item in self.candidates}) != 2:
            raise RevenueConfirmationError("source_invalid")

    def to_payload(self) -> dict[str, object]:
        """输出版本和按期间排序的完整候选；调用方不得改写后直接保存。"""
        return {
            "schema": "revenue-review-v1",
            "revision": asdict(self.revision),
            "candidates": [
                candidate_payload(item) for item in sorted(self.candidates, key=lambda c: c.period)
            ],
        }

    @property
    def snapshot_id(self) -> str:
        """对完整可审阅内容生成稳定摘要；不拿 source_ref 充当来源版本。"""
        content = json.dumps(
            self.to_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RevenueConfirmation:
    """已保存的整组确认：操作者动作类型、原确认时间与完整所见快照。"""

    confirmation_id: str
    confirmed_at: datetime
    confirmation_kind: ConfirmationKind
    review: RevenueReview

    def confirmed_facts(self) -> tuple[ConfirmedRevenueFact, ...]:
        """从已读回候选复用原确认变体恢复事实；本方法不证明当前来源仍有效。"""
        state = record_revenue_candidates(
            begin_revenue_workflow(
                workspace_id=self.review.revision.workspace_id,
                document_id=self.review.revision.document_id,
            ),
            self.review.candidates,
        )
        return confirm_revenue_candidates(state).confirmed_facts


@dataclass(frozen=True)
class ConfirmedRevenueCalculation:
    """本次成功计算及其确认身份/版本；失败时不会构造此对象。"""

    confirmation: RevenueConfirmation
    result: RevenueGrowthResult

    def to_payload(self) -> dict[str, object]:
        """输出程序真值、两条输入及全部证据，不包含内部物理路径。"""
        return {
            "confirmation_id": self.confirmation.confirmation_id,
            "confirmed_at": self.confirmation.confirmed_at.isoformat(),
            "confirmation_kind": self.confirmation.confirmation_kind,
            "snapshot_id": self.confirmation.review.snapshot_id,
            "revision": asdict(self.confirmation.review.revision),
            "value": format(self.result.value, "f"),
            "unit": self.result.unit,
            "formula_id": self.result.formula_id,
            "inputs": [candidate_payload(item) for item in self.confirmation.review.candidates],
        }


class RevenueConfirmationRepository(Protocol):
    """整组保存/范围读回与本次计算的事实查询端口；不接收调用方裸金额。"""

    @property
    def financial_storage_path(self) -> Path: ...

    def recheck_financial_fact_sets(
        self,
        *,
        workspace_id: str,
        receipt_ids: tuple[str, ...],
        confirmation_kind: ConfirmationKind,
    ) -> tuple[FinancialFactSet, ...]: ...

    def save(
        self, *, review: RevenueReview, confirmation_kind: ConfirmationKind
    ) -> RevenueConfirmation: ...

    def load(
        self, *, confirmation_id: str, current_review: RevenueReview
    ) -> RevenueConfirmation: ...

    def fact_repository(
        self, *, confirmation_id: str, current_review: RevenueReview
    ) -> FinancialFactRepository: ...

    def save_acceptance(
        self, *, review: FinancialReview, confirmation_kind: ConfirmationKind, request_id: str
    ) -> FinancialAcceptance: ...

    def load_acceptance(
        self,
        *,
        current_review: FinancialReview,
        request_id: str,
        confirmation_kind: ConfirmationKind,
    ) -> FinancialAcceptance: ...

    def acceptance_review_for_request(
        self,
        *,
        workspace_id: str,
        document_id: str,
        company_id: str,
        request_id: str,
        confirmation_kind: ConfirmationKind,
    ) -> FinancialReview: ...

    def acceptance_by_id(
        self, *, workspace_id: str, receipt_id: str, confirmation_kind: ConfirmationKind
    ) -> FinancialAcceptance: ...

    def acceptance_ids_for_scope(
        self, *, workspace_id: str, document_id: str, company_id: str,
        source_revision: str, metric_keys: tuple[str, ...], periods: tuple[int, ...],
        confirmation_kind: ConfirmationKind,
    ) -> tuple[str, ...]: ...

    def save_financial_facts(
        self,
        *,
        receipt_id: str,
        current_review: FinancialReview,
        confirmation_kind: ConfirmationKind,
    ) -> FinancialFactSet: ...

    def recheck_financial_fact_sets_in(self, connection: sqlite3.Connection, *, workspace_id: str,
                                      receipt_ids: tuple[str, ...], confirmation_kind: ConfirmationKind
                                      ) -> tuple[FinancialFactSet, ...]: ...

    def revoke_financial_receipt(self, *, workspace_id: str, receipt_id: str,
                                 confirmation_kind: ConfirmationKind, reason: str) -> dict[str, Any]: ...

    def load_financial_facts(
        self,
        *,
        workspace_id: str,
        receipt_id: str,
        confirmation_kind: ConfirmationKind,
        include_invalid: bool = False,
    ) -> FinancialFactSet: ...

    def query_financial_fact_sets(
        self,
        *,
        workspace_id: str,
        confirmation_kind: ConfirmationKind,
        company_id: str,
        period: int | None = None,
        period_start: str | None = None,
        period_end: str | None = None,
        metric_key: str | None = None,
        scope: str = "consolidated",
        document_id: str | None = None,
        disclosure_version: str | None = None,
        source_revision: str | None = None,
        include_invalid: bool = False,
    ) -> tuple[FinancialFactSet, ...]: ...


class RevenueSourceReader:
    """每次从服务端文档、实际 PDF 和候选服务恢复当前可确认快照。"""

    def __init__(
        self,
        *,
        documents: DocumentReader,
        objects: ObjectStore,
        candidates: revenue_extraction.RevenueCandidateService,
        sources: DocumentSourceService | None = None,
    ) -> None:
        self._documents = documents
        self._objects = objects
        self._candidates = candidates
        self._sources = sources

    async def read_financial(
        self,
        *,
        document_id: str,
        company_id: str,
        source_revision: str,
        metric_keys: tuple[str, ...],
        periods: tuple[int, ...],
    ) -> FinancialReview:
        """Same reader and candidate service; every proof comes from the captured source."""
        if self._sources is None:
            raise RevenueConfirmationError("financial_service_unavailable")
        before = await self._read_document(document_id)
        collected = await self._candidates.collect_metrics(
            document_id=document_id,
            company_id=company_id,
            source_revision=source_revision,
            metric_keys=tuple(sorted(metric_keys)),
            periods=tuple(sorted(periods)),
        )
        source, records = await self._sources.parsed_evidence(
            document_id, company_id=company_id, source_revision=source_revision
        )
        company = await asyncio.to_thread(self._sources.companies.get, company_id)
        after = await self._read_document(document_id)
        if (
            before != after
            or source != collected["source"]
            or company.workspace_id != after.workspace_id
        ):
            raise RevenueConfirmationError("source_changed")
        ids = {
            e["evidence_id"]
            for c in collected["candidates"]
            for e in [*c["evidence"], *c["basis_evidence"]]
        }
        proofs = [e for e in records if e["evidence_id"] in ids]
        if {e["evidence_id"] for e in proofs} != ids:
            raise RevenueConfirmationError("source_invalid")
        payload = dict(
            schema="financial-review-v1",
            company=company.model_dump(mode="json", exclude={"workspace_id"}),
            document=dict(document_id=document_id, source_file=after.source_file),
            source=source,
            selection=dict(metric_keys=sorted(metric_keys), periods=sorted(periods)),
            candidates=collected["candidates"],
            source_evidence=proofs,
        )
        return FinancialReview(after.workspace_id, canonical_payload(payload))

    async def verify_financial_source(self, review: FinancialReview) -> None:
        """Read-only byte/version verification. No PDF parsing, candidate extraction or model."""
        if self._sources is None:
            raise RevenueConfirmationError("financial_service_unavailable")
        source = review.to_payload()["source"]
        document = await self._read_document(source["document_id"])
        if (
            document.workspace_id != review.workspace_id
            or document.content_sha256 != source["content_sha256"]
            or document.attempt != source["attempt"]
            or self._sources.parser_version != source["parser_version"]
        ):
            raise RevenueConfirmationError("source_changed")

    async def verify_discovery_source(self, document_id: str, company_id: str,
                                      source_revision: str) -> None:
        if self._sources is None:
            raise RevenueConfirmationError("financial_service_unavailable")
        await self._sources.source(document_id, company_id=company_id,
                                   source_revision=source_revision)

    async def _read_document(self, document_id: str) -> DocumentRecord:
        """核对当前 ready 和实际 PDF 摘要；文件或读取异常直接阻断。"""
        document = await self._documents.get_document(document_id)
        if document.status is not DocumentStatus.READY:
            raise RevenueConfirmationError("source_unavailable")
        try:
            content = await asyncio.to_thread(self._objects.read_bytes, document.object_key)
        except OSError as exc:
            raise RevenueConfirmationError("source_unavailable") from exc
        if hashlib.sha256(content).hexdigest() != document.content_sha256:
            raise RevenueConfirmationError("source_changed")
        return document

    async def read(self, *, document_id: str) -> RevenueReview:
        """收集前后均查证文档；候选由当前代码重新获取，不从旧确认复制版本。"""
        before = await self._read_document(document_id)
        try:
            collected = await self._candidates.collect(document_id=document_id)
        except SourceError as exc:
            raise RevenueConfirmationError("source_changed") from exc
        except RegistryNotFoundError as exc:
            raise RevenueConfirmationError("source_unavailable") from exc
        after = await self._read_document(document_id)
        if before != after:
            raise RevenueConfirmationError("source_changed")
        state = collected.state
        if state.stage is not RevenueWorkflowStage.AWAITING_CONFIRMATION:
            raise RevenueConfirmationError(str(state.failure_code))
        return RevenueReview(
            revision=RevenueSourceRevision(
                workspace_id=after.workspace_id,
                document_id=after.document_id,
                content_sha256=after.content_sha256,
                attempt=after.attempt,
                extraction_method=state.candidates[0].extraction_method,
                extraction_version=state.candidates[0].extraction_version,
            ),
            candidates=state.candidates,
        )


class RevenueConfirmationService:
    """本地业务入口：展示→明确接受→整组保存→当前查证→持久事实计算。"""

    def __init__(
        self, *, source_reader: RevenueSourceReader, repository: RevenueConfirmationRepository
    ) -> None:
        self._source_reader = source_reader
        self._repository = repository

    @property
    def financial_storage_path(self) -> Path:
        return self._repository.financial_storage_path

    async def recheck_financial_analysis_sources(
        self,
        *,
        workspace_id: str,
        groups: tuple[FinancialFactSet, ...],
        confirmation_kind: ConfirmationKind,
    ) -> None:
        """Check original bytes, then both groups in one SQLite read transaction.

        A correction while checking the second PDF must invalidate the first
        input too. No parser, candidate extraction or confirmation writes.
        """
        for group in groups:
            await self._source_reader.verify_financial_source(group.receipt.review)
        final = await asyncio.to_thread(
            self._repository.recheck_financial_fact_sets,
            workspace_id=workspace_id,
            receipt_ids=tuple(g.fact_set_id for g in groups),
            confirmation_kind=confirmation_kind,
        )
        if final != groups:
            raise RevenueConfirmationError("source_changed")

    async def preview(self, *, document_id: str) -> RevenueReview:
        """仅展示当前候选；不创建确认，也不计算。"""
        return await self._source_reader.read(document_id=document_id)

    async def preview_financial(
        self,
        *,
        document_id: str,
        company_id: str,
        source_revision: str,
        metric_keys: tuple[str, ...],
        periods: tuple[int, ...],
    ) -> FinancialReview:
        return await self._source_reader.read_financial(
            document_id=document_id,
            company_id=company_id,
            source_revision=source_revision,
            metric_keys=metric_keys,
            periods=periods,
        )

    async def confirm_financial(
        self,
        *,
        document_id: str,
        company_id: str,
        source_revision: str,
        metric_keys: tuple[str, ...],
        periods: tuple[int, ...],
        reviewed_snapshot_id: str,
        accepted: bool,
        confirmation_kind: ConfirmationKind,
        request_id: str,
    ) -> FinancialAcceptance:
        """Explicit accept, server reconstruction, durable receipt, read-back; no fact/analysis writes."""
        if accepted is not True or confirmation_kind not in ("local_operator", "simulated_test"):
            raise RevenueConfirmationError("confirmation_required")
        if not request_id.strip() or len(request_id) > 100:
            raise RevenueConfirmationError("invalid_financial_selection")
        current = await self.preview_financial(
            document_id=document_id,
            company_id=company_id,
            source_revision=source_revision,
            metric_keys=metric_keys,
            periods=periods,
        )
        if current.snapshot_id != reviewed_snapshot_id:
            raise RevenueConfirmationError("review_changed")
        if not current.acceptable:
            raise RevenueConfirmationError("candidate_not_acceptable")
        await asyncio.to_thread(
            self._repository.save_acceptance,
            review=current,
            confirmation_kind=confirmation_kind,
            request_id=request_id,
        )
        return await self.recover_financial(
            document_id=document_id,
            company_id=company_id,
            source_revision=source_revision,
            metric_keys=metric_keys,
            periods=periods,
            reviewed_snapshot_id=reviewed_snapshot_id,
            request_id=request_id,
            confirmation_kind=confirmation_kind,
        )

    async def recover_financial(
        self,
        *,
        document_id: str,
        company_id: str,
        source_revision: str,
        metric_keys: tuple[str, ...],
        periods: tuple[int, ...],
        reviewed_snapshot_id: str,
        request_id: str,
        confirmation_kind: ConfirmationKind,
    ) -> FinancialAcceptance:
        """Read-only recovery, including uncertain POST outcomes; never retries acceptance."""
        document = await self._source_reader._read_document(document_id)
        current = await asyncio.to_thread(
            self._repository.acceptance_review_for_request,
            workspace_id=document.workspace_id,
            document_id=document_id,
            company_id=company_id,
            request_id=request_id,
            confirmation_kind=confirmation_kind,
        )
        p = current.to_payload()
        if (
            current.snapshot_id != reviewed_snapshot_id
            or p["source"]["source_revision"] != source_revision
            or sorted(p["selection"]["metric_keys"]) != sorted(metric_keys)
            or sorted(p["selection"]["periods"]) != sorted(periods)
        ):
            raise RevenueConfirmationError("review_changed")
        await self._source_reader.verify_financial_source(current)
        await asyncio.to_thread(
            self._repository.load_acceptance,
            current_review=current,
            request_id=request_id,
            confirmation_kind=confirmation_kind,
        )
        await self._source_reader.verify_financial_source(current)
        return await asyncio.to_thread(
            self._repository.load_acceptance,
            current_review=current,
            request_id=request_id,
            confirmation_kind=confirmation_kind,
        )

    async def read_financial_acceptance(
        self,
        *,
        workspace_id: str,
        receipt_id: str,
        confirmation_kind: ConfirmationKind,
    ) -> FinancialAcceptance:
        receipt = await asyncio.to_thread(
            self._repository.acceptance_by_id,
            workspace_id=workspace_id,
            receipt_id=receipt_id,
            confirmation_kind=confirmation_kind,
        )
        await self._source_reader.verify_financial_source(receipt.review)
        return await asyncio.to_thread(
            self._repository.acceptance_by_id,
            workspace_id=workspace_id,
            receipt_id=receipt_id,
            confirmation_kind=confirmation_kind,
        )

    async def discover_financial_acceptances(
        self, *, workspace_id: str, document_id: str, company_id: str,
        source_revision: str, metric_keys: tuple[str, ...], periods: tuple[int, ...],
        confirmation_kind: ConfirmationKind,
    ) -> dict[str, Any]:
        await self._source_reader.verify_discovery_source(document_id, company_id, source_revision)
        ids = await asyncio.to_thread(
            self._repository.acceptance_ids_for_scope,
            workspace_id=workspace_id, document_id=document_id, company_id=company_id,
            source_revision=source_revision, metric_keys=metric_keys, periods=periods,
            confirmation_kind=confirmation_kind,
        )
        items = []
        for receipt_id in ids:
            receipt = await self.read_financial_acceptance(
                workspace_id=workspace_id, receipt_id=receipt_id,
                confirmation_kind=confirmation_kind,
            )
            items.append(receipt.to_payload())
        await self._source_reader.verify_discovery_source(document_id, company_id, source_revision)
        return dict(schema="financial-acceptance-discovery-v1", automatic_selection=False,
                    items=items)

    async def persist_financial(
        self, *, workspace_id: str, receipt_id: str, confirmation_kind: ConfirmationKind
    ) -> FinancialFactSet:
        receipt = await asyncio.to_thread(
            self._repository.acceptance_by_id,
            workspace_id=workspace_id,
            receipt_id=receipt_id,
            confirmation_kind=confirmation_kind,
        )
        p = receipt.review.to_payload()
        current = await self.preview_financial(
            document_id=p["source"]["document_id"],
            company_id=p["source"]["company_id"],
            source_revision=p["source"]["source_revision"],
            metric_keys=tuple(p["selection"]["metric_keys"]),
            periods=tuple(p["selection"]["periods"]),
        )
        if current.snapshot_id != receipt.review.snapshot_id or not current.acceptable:
            raise RevenueConfirmationError("review_changed")
        await asyncio.to_thread(
            self._repository.save_financial_facts,
            receipt_id=receipt_id,
            current_review=current,
            confirmation_kind=confirmation_kind,
        )
        # A failed read after commit must be recovered by this known receipt ID, never auto-POSTed.
        return await self.read_financial_facts(
            workspace_id=workspace_id,
            receipt_id=receipt_id,
            confirmation_kind=confirmation_kind,
        )

    def recheck_persisted_analysis_in(self, connection: sqlite3.Connection, *, workspace_id: str,
                                      receipt_ids: tuple[str, ...], confirmation_kind: ConfirmationKind
                                      ) -> tuple[FinancialFactSet, ...]:
        return self._repository.recheck_financial_fact_sets_in(connection,workspace_id=workspace_id,
            receipt_ids=receipt_ids,confirmation_kind=confirmation_kind)

    async def revoke_financial_acceptance(self, *, workspace_id: str, receipt_id: str,
                                          confirmation_kind: ConfirmationKind, reason: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._repository.revoke_financial_receipt,
            workspace_id=workspace_id,receipt_id=receipt_id,confirmation_kind=confirmation_kind,reason=reason)

    async def read_financial_facts(
        self,
        *,
        workspace_id: str,
        receipt_id: str,
        confirmation_kind: ConfirmationKind,
        include_invalid: bool = False,
    ) -> FinancialFactSet:
        result = await asyncio.to_thread(
            self._repository.load_financial_facts,
            workspace_id=workspace_id,
            receipt_id=receipt_id,
            confirmation_kind=confirmation_kind,
            include_invalid=include_invalid,
        )
        if result.current_valid:
            try:
                await self._source_reader.verify_financial_source(result.receipt.review)
            except RevenueConfirmationError as exc:
                if not include_invalid:
                    raise
                result = replace(result, current_valid=False, invalid_reason=exc.code)
            # Recheck the persisted source after external byte IO to close a correction race.
            final = await asyncio.to_thread(
                self._repository.load_financial_facts,
                workspace_id=workspace_id,
                receipt_id=receipt_id,
                confirmation_kind=confirmation_kind,
                include_invalid=include_invalid,
            )
            if not final.current_valid:
                return final
        return result

    async def query_financial_facts(
        self,
        *,
        workspace_id: str,
        confirmation_kind: ConfirmationKind,
        **filters: Any,
    ) -> dict[str, Any]:
        groups = await asyncio.to_thread(
            self._repository.query_financial_fact_sets,
            workspace_id=workspace_id,
            confirmation_kind=confirmation_kind,
            **filters,
        )
        result = []
        for group in groups:
            checked = await self.read_financial_facts(
                workspace_id=workspace_id,
                receipt_id=group.receipt.receipt_id,
                confirmation_kind=confirmation_kind,
                include_invalid=True,
            )
            if not checked.current_valid and not filters.get("include_invalid", False):
                continue
            for fact in checked.to_payload()["facts"]:
                if any(
                    filters.get(k) is not None and fact[k] != filters[k]
                    for k in ("period", "period_start", "period_end", "metric_key", "scope")
                ):
                    continue
                result.append(
                    dict(
                        **fact,
                        disclosure_version=checked.disclosure_version,
                        receipt_id=checked.receipt.receipt_id,
                        confirmation_kind=confirmation_kind,
                        current_valid=checked.current_valid,
                        calculable=checked.current_valid,
                        production_calculable=checked.current_valid
                        and confirmation_kind == "local_operator",
                        invalid_reason=checked.invalid_reason,
                        integrity="verified",
                    )
                )
        versions: dict[str, set[str]] = {}
        values: dict[str, set[Decimal]] = {}
        for fact in result:
            if not fact["current_valid"]:
                continue
            key = "/".join(
                str(fact[k])
                for k in (
                    "company_id",
                    "metric_key",
                    "period_start",
                    "period_end",
                    "scope",
                    "accounting_basis",
                )
            )
            versions.setdefault(key, set()).add(fact["disclosure_version"])
            values.setdefault(key, set()).add(Decimal(fact["value_cny_yuan"]))
        ambiguous = sorted(k for k, v in versions.items() if len(v) > 1)
        return dict(
            schema="financial-fact-query-v1",
            facts=result,
            requires_version_selection=bool(ambiguous),
            ambiguous_periods=ambiguous,
            conflicting_periods=sorted(k for k, v in values.items() if len(v) > 1),
            automatic_selection=False,
        )

    async def confirm(
        self,
        *,
        document_id: str,
        reviewed_snapshot_id: str,
        accepted: bool,
        confirmation_kind: ConfirmationKind,
    ) -> RevenueConfirmation:
        """接受明确动作与所见摘要；重新收集完全一致才保存，两期不能部分接受。"""
        if accepted is not True:
            raise RevenueConfirmationError("confirmation_required")
        if confirmation_kind not in ("local_operator", "simulated_test"):
            raise RevenueConfirmationError("confirmation_required")
        current = await self._source_reader.read(document_id=document_id)
        if current.snapshot_id != reviewed_snapshot_id:
            raise RevenueConfirmationError("review_changed")
        return await asyncio.to_thread(
            self._repository.save, review=current, confirmation_kind=confirmation_kind
        )

    async def calculate(
        self, *, document_id: str, confirmation_id: str
    ) -> ConfirmedRevenueCalculation:
        """重新核证来源，从 SQLite 读回完整有效确认，调用原业务计算函数。"""
        current = await self._source_reader.read(document_id=document_id)
        confirmation = await asyncio.to_thread(
            self._repository.load, confirmation_id=confirmation_id, current_review=current
        )
        state = replace(
            begin_revenue_workflow(
                workspace_id=current.revision.workspace_id,
                document_id=current.revision.document_id,
            ),
            stage=RevenueWorkflowStage.READY_FOR_CALCULATION,
            confirmed_facts=confirmation.confirmed_facts(),
        )
        repository = self._repository.fact_repository(
            confirmation_id=confirmation_id, current_review=current
        )
        calculated = await asyncio.to_thread(
            calculate_confirmed_revenue_growth, state, repository=repository
        )
        if calculated.result is None:
            raise RevenueConfirmationError(str(calculated.failure_code))
        # 计算只产生一个新结果；返回前再次查证，变化时不把刚算出的值交给调用方。
        final_review = await self._source_reader.read(document_id=document_id)
        if final_review.snapshot_id != current.snapshot_id:
            raise RevenueConfirmationError("source_changed")
        return ConfirmedRevenueCalculation(confirmation, calculated.result)
