"""真实 SQLite/文档服务/抽取/计算 + 替身检索与伪 PDF bytes 的定向合同测试。

所有接受动作明确标为 simulated_test；不证明真实 PDF/BGE/Milvus 或人工确认。
真实路径使用隔离上传和交互 CLI 单独验收。
"""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
from pathlib import Path
import sqlite3
from typing import cast
from unittest.mock import Mock

import pytest

from app.agent import revenue_extraction
from app.agent.financial_facts import FinancialFactKey, FinancialUnit
from app.agent.revenue_confirmation import (
    RevenueConfirmation,
    RevenueConfirmationError,
    RevenueConfirmationService,
    RevenueReview,
    RevenueSourceReader,
)
from app.agent.revenue_extraction import RevenueCandidateService
from app.agent.sqlite_financial_facts import SQLiteRevenueConfirmationRepository
from app.agent.tool_loop import ToolExecutionContext
from app.documents.local_object_store import LocalObjectStore
from app.documents.models import DocumentRecord, DocumentStatus
from app.documents.preparation import DocumentTaskPreparer
from app.documents.service import DocumentService
from app.documents.sqlite_repository import SQLiteDocumentRepository
from app.rag.retriever import Retriever, SearchFilters, SearchHit, TrustedContext


class _NoDispatch:
    def dispatch(self, document_id: str) -> bool:
        raise AssertionError("测试不运行真实 PDF 处理")


class Harness:
    """使用实际本地持久层；只替换检索输入，保留所有确认/来源查证。"""

    def __init__(self, root: Path) -> None:
        self.database = root / "documents.db"
        self.documents_repository = SQLiteDocumentRepository(self.database)
        self.objects = LocalObjectStore(root / "objects")
        content = b"%PDF-explicit-test-double"
        content_sha = hashlib.sha256(content).hexdigest()
        self.document_id = hashlib.sha256(f"demo\0{content_sha}".encode()).hexdigest()
        self.object_key = f"documents/{self.document_id}.pdf"
        self.objects.put_bytes(self.object_key, content)
        now = datetime.now(UTC)
        self.documents_repository.create_or_get(
            DocumentRecord(
                document_id=self.document_id,
                workspace_id="demo",
                source_file="synthetic.pdf",
                object_key=self.object_key,
                content_sha256=content_sha,
                status=DocumentStatus.READY,
                failed_stage=None,
                error_code=None,
                safe_error_message=None,
                created_at=now,
                updated_at=now,
                attempt=1,
            )
        )
        self.documents = DocumentService(
            repository=self.documents_repository,
            object_store=self.objects,
            dispatcher=_NoDispatch(),
            workspace_id="demo",
        )
        self.retriever = Mock(spec=Retriever)
        self.set_text("2024年度营业收入：100万元。\n2025年度营业收入：120万元。")
        self.reader = RevenueSourceReader(
            documents=self.documents,
            objects=self.objects,
            candidates=RevenueCandidateService(
                preparer=DocumentTaskPreparer(document_service=self.documents),
                retriever=self.retriever,
            ),
        )
        self.repository = SQLiteRevenueConfirmationRepository(self.database)
        self.service = RevenueConfirmationService(
            source_reader=self.reader, repository=self.repository
        )

    def set_text(self, text: str) -> None:
        self.retriever.retrieve.return_value = [
            SearchHit(
                score=0.8,
                chunk_id="test-chunk-1",
                text=text,
                page=1,
                source_file="synthetic.pdf",
                type="paragraph",
                workspace_id="demo",
                document_id=self.document_id,
            )
        ]

    def preview(self) -> RevenueReview:
        return asyncio.run(self.service.preview(document_id=self.document_id))

    def simulate_acceptance(self, review: RevenueReview) -> RevenueConfirmation:
        """明确模拟测试动作；不冒充真实操作者，也不自动发生于 preview。"""
        return asyncio.run(
            self.service.confirm(
                document_id=self.document_id,
                reviewed_snapshot_id=review.snapshot_id,
                accepted=True,
                confirmation_kind="simulated_test",
            )
        )

    def calculate(self, confirmation_id: str) -> object:
        return asyncio.run(
            self.service.calculate(document_id=self.document_id, confirmation_id=confirmation_id)
        )

    def counts(self) -> tuple[int, int]:
        with sqlite3.connect(self.database) as connection:
            return (
                connection.execute("SELECT COUNT(*) FROM revenue_confirmations").fetchone()[0],
                connection.execute("SELECT COUNT(*) FROM confirmed_revenue_facts").fetchone()[0],
            )


@pytest.fixture
def h(tmp_path: Path) -> Harness:
    return Harness(tmp_path)


def test_preview_or_database_numbers_without_acceptance_do_not_authorize_calculation(
    h: Harness,
) -> None:
    review = h.preview()
    assert len(review.candidates) == 2 and h.counts() == (0, 0)
    with pytest.raises(RevenueConfirmationError, match="confirmation_required"):
        asyncio.run(
            h.service.confirm(
                document_id=h.document_id,
                reviewed_snapshot_id=review.snapshot_id,
                accepted=False,
                confirmation_kind="simulated_test",
            )
        )
    with pytest.raises(RevenueConfirmationError, match="confirmation_required") as caught:
        h.calculate("not-confirmed")
    assert not hasattr(caught.value, "result") and h.counts() == (0, 0)


def test_simulated_acceptance_reopen_persisted_facts_calculate_all_sources_and_idempotency(
    h: Harness,
) -> None:
    review = h.preview()
    accepted = h.simulate_acceptance(review)
    assert h.counts() == (1, 2) and accepted.confirmation_kind == "simulated_test"
    duplicate = h.simulate_acceptance(review)
    assert duplicate == accepted and h.counts() == (1, 2)
    reopened = SQLiteRevenueConfirmationRepository(h.database)
    service = RevenueConfirmationService(source_reader=h.reader, repository=reopened)
    result = asyncio.run(
        service.calculate(document_id=h.document_id, confirmation_id=accepted.confirmation_id)
    )
    assert result.result.value == Decimal("20.00")
    assert result.result.formula_id == "revenue_growth_rate_v1"
    assert result.confirmation == accepted
    assert {item.fact.period for item in result.result.sources} == {2024, 2025}
    assert all(item.evidence and item.page == 1 for item in result.result.sources)
    payload = result.to_payload()
    assert payload["value"] == "20.00" and payload["snapshot_id"] == review.snapshot_id
    assert "evidence" in cast(list[dict[str, object]], payload["inputs"])[0]


def test_decimal_text_survives_sqlite_without_float_roundtrip(h: Harness) -> None:
    h.set_text(
        "2024年度营业收入：1000000.0000000000000000001元。\n"
        "2025年度营业收入：1200000.0000000000000000001元。"
    )
    accepted = h.simulate_acceptance(h.preview())
    restored = h.repository.load(
        confirmation_id=accepted.confirmation_id, current_review=h.preview()
    )
    assert restored.review.candidates[0].value == Decimal("1000000.0000000000000000001")
    with sqlite3.connect(h.database) as connection:
        value, sql_type = connection.execute(
            "SELECT value_text, typeof(value_text) FROM confirmed_revenue_facts WHERE period=2024"
        ).fetchone()
    assert value == "1000000.0000000000000000001" and sql_type == "text"


@pytest.mark.parametrize(
    ("previous", "current", "expected"),
    [
        ("3", "4", "33.33"),
        ("20000", "20001", "0.01"),
    ],
)
def test_existing_formula_and_half_up_rounding(
    h: Harness, previous: str, current: str, expected: str
) -> None:
    h.set_text(f"2024年度营业收入：{previous}元。\n2025年度营业收入：{current}元。")
    accepted = h.simulate_acceptance(h.preview())
    output = asyncio.run(
        h.service.calculate(document_id=h.document_id, confirmation_id=accepted.confirmation_id)
    )
    assert output.result.value == Decimal(expected)


def test_changed_evidence_same_refs_same_amount_cannot_be_silently_confirmed(h: Harness) -> None:
    reviewed = h.preview()
    h.set_text("2024年度营业收入：100万元。\n2025年度营业收入：120万元。\n改为另一口径说明")
    current = h.preview()
    assert [c.source_ref for c in reviewed.candidates] == [c.source_ref for c in current.candidates]
    assert reviewed.snapshot_id != current.snapshot_id
    with pytest.raises(RevenueConfirmationError, match="review_changed"):
        h.simulate_acceptance(reviewed)
    assert h.counts() == (0, 0)


@pytest.mark.parametrize("change", ["pdf", "evidence", "rule", "attempt", "not_ready"])
def test_source_change_after_success_refuses_old_confirmation_without_old_result(
    h: Harness, change: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    accepted = h.simulate_acceptance(h.preview())
    assert h.calculate(accepted.confirmation_id) is not None
    if change == "pdf":
        h.objects.put_bytes(h.object_key, b"%PDF-replaced-test-double")
    elif change == "evidence":
        h.set_text("2024年度营业收入：100万元。\n2025年度营业收入：125万元。")
    elif change == "rule":
        monkeypatch.setattr(revenue_extraction, "EXTRACTION_VERSION", "v2-test")
    else:
        with sqlite3.connect(h.database) as connection:
            if change == "attempt":
                connection.execute("UPDATE documents SET attempt=attempt+1")
            else:
                connection.execute("UPDATE documents SET status='indexing'")
    expected = "source_unavailable" if change == "not_ready" else "source_changed"
    with pytest.raises(RevenueConfirmationError, match=expected) as caught:
        h.calculate(accepted.confirmation_id)
    assert not hasattr(caught.value, "result") and h.counts() == (1, 2)


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("2024年度营业收入：100万元。\n2025年度营业收入：120美元。", "unit_unknown"),
        ("2023年度营业收入：100万元。\n2024年度营业收入：120万元。", "period_mismatch"),
        ("2024年度营业收入：100万元。", "missing_candidate"),
    ],
)
def test_current_invalid_units_periods_or_incomplete_inputs_never_fall_back_to_old_success(
    h: Harness, text: str, code: str
) -> None:
    accepted = h.simulate_acceptance(h.preview())
    assert h.calculate(accepted.confirmation_id) is not None
    h.set_text(text)
    with pytest.raises(RevenueConfirmationError, match=code) as caught:
        h.calculate(accepted.confirmation_id)
    assert not hasattr(caught.value, "result")


def test_zero_denominator_is_confirmable_but_calculator_refuses_without_result(h: Harness) -> None:
    h.set_text("2024年度营业收入：0元。\n2025年度营业收入：120元。")
    accepted = h.simulate_acceptance(h.preview())
    with pytest.raises(RevenueConfirmationError, match="division_by_zero") as caught:
        h.calculate(accepted.confirmation_id)
    assert not hasattr(caught.value, "result")


def test_range_query_rejects_other_workspace_document_metric_or_ref(h: Harness) -> None:
    review = h.preview()
    accepted = h.simulate_acceptance(review)
    repository = h.repository.fact_repository(
        confirmation_id=accepted.confirmation_id, current_review=review
    )
    for workspace, document, ref, metric in [
        ("other", h.document_id, review.candidates[0].source_ref, "revenue"),
        ("demo", "other-document", review.candidates[0].source_ref, "revenue"),
        ("demo", None, review.candidates[0].source_ref, "revenue"),
        ("demo", h.document_id, "other-ref", "revenue"),
        ("demo", h.document_id, review.candidates[0].source_ref, "net_profit"),
    ]:
        fact_key = (
            FinancialFactKey.REVENUE if metric == "revenue" else cast(FinancialFactKey, metric)
        )
        assert (
            repository.find_fact(
                execution_context=ToolExecutionContext(
                    trusted_context=TrustedContext(workspace),
                    filters=SearchFilters(document_id=document),
                ),
                source_ref=ref,
                fact_key=fact_key,
            )
            is None
        )


def test_another_existing_document_cannot_use_previous_document_confirmation(h: Harness) -> None:
    accepted = h.simulate_acceptance(h.preview())
    original = h.documents_repository.get(h.document_id)
    assert original is not None
    content = b"%PDF-another-explicit-test-double"
    sha = hashlib.sha256(content).hexdigest()
    h.document_id = hashlib.sha256(f"demo\0{sha}".encode()).hexdigest()
    h.object_key = f"documents/{h.document_id}.pdf"
    h.objects.put_bytes(h.object_key, content)
    h.documents_repository.create_or_get(
        replace(original, document_id=h.document_id, object_key=h.object_key, content_sha256=sha)
    )
    h.set_text("2024年度营业收入：100万元。\n2025年度营业收入：120万元。")
    with pytest.raises(RevenueConfirmationError, match="confirmation_required") as caught:
        h.calculate(accepted.confirmation_id)
    assert not hasattr(caught.value, "result") and h.counts() == (1, 2)


def test_normalized_wrong_unit_is_not_accepted_even_when_both_units_match(h: Harness) -> None:
    review = h.preview()
    with pytest.raises(RevenueConfirmationError, match="unit_conflict"):
        replace(
            review,
            candidates=tuple(
                replace(c, unit=FinancialUnit.CNY_100_MILLION) for c in review.candidates
            ),
        )


def test_second_fact_insert_failure_rolls_back_header_and_first_fact(h: Harness) -> None:
    review = h.preview()
    with sqlite3.connect(h.database) as connection:
        connection.execute(
            "CREATE TRIGGER fail_second_fact BEFORE INSERT ON confirmed_revenue_facts "
            "WHEN NEW.period = 2025 BEGIN SELECT RAISE(ABORT, 'simulated disk/write failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="simulated disk/write failure"):
        h.simulate_acceptance(review)
    assert h.counts() == (0, 0)
    with pytest.raises(RevenueConfirmationError, match="confirmation_required"):
        h.calculate("missing-after-rollback")


@pytest.mark.parametrize("damage", ["missing_fact", "amount", "evidence"])
def test_incomplete_or_corrupt_confirmation_does_not_supply_any_old_result(
    h: Harness, damage: str
) -> None:
    accepted = h.simulate_acceptance(h.preview())
    with sqlite3.connect(h.database) as connection:
        if damage == "missing_fact":
            connection.execute("DELETE FROM confirmed_revenue_facts WHERE period=2025")
        elif damage == "amount":
            connection.execute(
                "UPDATE confirmed_revenue_facts SET value_text='999' WHERE period=2025"
            )
        else:
            connection.execute(
                "UPDATE confirmed_revenue_facts SET evidence_json='[]' WHERE period=2025"
            )
    with pytest.raises(RevenueConfirmationError, match="confirmation_integrity_error") as caught:
        h.calculate(accepted.confirmation_id)
    assert not hasattr(caught.value, "result")


def test_transaction_rechecks_document_instead_of_comparing_two_old_versions(h: Harness) -> None:
    stale = h.preview()
    with sqlite3.connect(h.database) as connection:
        connection.execute("UPDATE documents SET attempt=attempt+1")
    with pytest.raises(RevenueConfirmationError, match="source_changed"):
        h.repository.save(review=stale, confirmation_kind="simulated_test")
    assert h.counts() == (0, 0)


def test_change_during_calculation_is_detected_before_result_is_returned(h: Harness) -> None:
    accepted = h.simulate_acceptance(h.preview())
    original_load = h.repository.load
    calls = 0

    def load_then_change(**kwargs: object) -> RevenueConfirmation:
        nonlocal calls
        confirmation = original_load(**kwargs)  # type: ignore[arg-type]
        calls += 1
        if calls == 3:  # 应用读回与计算器的两次事实查询后，改变当前证据。
            h.set_text("2024年度营业收入：100万元。\n2025年度营业收入：125万元。")
        return confirmation

    h.repository.load = load_then_change  # type: ignore[method-assign]
    with pytest.raises(RevenueConfirmationError, match="source_changed") as caught:
        h.calculate(accepted.confirmation_id)
    assert not hasattr(caught.value, "result")
