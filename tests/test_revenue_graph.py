"""图 + 真实业务服务/SQLite 集成；检索及 PDF bytes 是显式替身。

复用 G2b 测试装配，所有测试确认都为 simulated_test；不证明真实 BGE/Milvus。
"""

import asyncio
from decimal import Decimal
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest

from app.agent.revenue_confirmation import RevenueConfirmation
from app.agent.revenue_graph import RevenueGraphInput, RevenueGraphState, build_revenue_graph
from tests.test_revenue_confirmation import Harness


@pytest.fixture
def h(tmp_path: Path) -> Harness:
    return Harness(tmp_path)


def invoke(h: Harness, confirmation_id: str | None = None) -> RevenueGraphState:
    """实际编译并异步调用图；真实业务服务在图外注入。"""
    graph = build_revenue_graph(service=h.service)
    return cast(
        RevenueGraphState,
        asyncio.run(graph.ainvoke({"document_id": h.document_id, "confirmation_id": confirmation_id})),
    )


def test_graph_and_direct_service_return_same_confirmed_payload_without_new_confirmation(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    accepted = h.simulate_acceptance(h.preview())
    direct = asyncio.run(
        h.service.calculate(document_id=h.document_id, confirmation_id=accepted.confirmation_id)
    )
    confirm = Mock(side_effect=AssertionError("图不得确认"))
    monkeypatch.setattr(h.service, "confirm", confirm)
    h.retriever.retrieve.reset_mock()
    output = invoke(h, accepted.confirmation_id)
    assert output["status"] == "completed"
    result = output["result"]
    assert result is not None and result.to_payload() == direct.to_payload()
    assert result.result.value == Decimal("20.00")
    assert result.confirmation.confirmation_kind == "simulated_test"
    assert output["error_code"] is None and output["error_kind"] is None
    summary = output["review_summary"]
    assert summary is not None and summary.snapshot_id == accepted.review.snapshot_id
    assert [c.value for c in summary.candidates] == [Decimal("1000000"), Decimal("1200000")]
    # 图多一次 preview；calculate 必要的两次来源重查保留，边没有额外检索。
    assert h.retriever.retrieve.call_count == 3
    assert h.counts() == (1, 2)
    confirm.assert_not_called()


@pytest.mark.parametrize("confirmation_id", [None, "", "   "])
def test_missing_id_ends_without_calculation_or_confirmation(
    h: Harness, confirmation_id: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    calculate = Mock(side_effect=AssertionError("无 ID 不得进入计算"))
    monkeypatch.setattr(h.service, "calculate", calculate)
    output = invoke(h, confirmation_id)
    assert output["status"] == "needs_confirmation"
    assert output["error_code"] == "confirmation_required"
    assert output["result"] is None and h.counts() == (0, 0)
    assert h.retriever.retrieve.call_count == 1
    calculate.assert_not_called()


def test_supplied_id_does_not_prove_confirmation_exists(h: Harness) -> None:
    output = invoke(h, "not-a-saved-confirmation")
    assert output["status"] == "needs_confirmation"
    assert output["error_code"] == "confirmation_required" and output["result"] is None
    assert h.counts() == (0, 0)
    assert h.retriever.retrieve.call_count == 2


def test_changed_candidate_snapshot_rejects_old_confirmation_without_retry(h: Harness) -> None:
    accepted = h.simulate_acceptance(h.preview())
    h.set_text("2024年度营业收入：100万元。\n2025年度营业收入：125万元。")
    h.retriever.retrieve.reset_mock()
    output = invoke(h, accepted.confirmation_id)
    assert output["status"] == "refused" and output["error_code"] == "source_changed"
    assert output["error_kind"] == "business" and output["result"] is None
    assert h.retriever.retrieve.call_count == 2 and h.counts() == (1, 2)


def test_actual_object_checksum_change_stops_before_candidate_retrieval(h: Harness) -> None:
    accepted = h.simulate_acceptance(h.preview())
    h.objects.put_bytes(h.object_key, b"%PDF-changed-test-double")
    h.retriever.retrieve.reset_mock()
    output = invoke(h, accepted.confirmation_id)
    assert output["status"] == "refused" and output["error_code"] == "source_changed"
    assert output["review_summary"] is None and output["result"] is None
    assert h.retriever.retrieve.call_count == 0 and h.counts() == (1, 2)


def test_change_during_calculation_preserves_service_final_source_check(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    accepted = h.simulate_acceptance(h.preview())
    load = h.repository.load
    calls = 0

    def load_then_change(**kwargs: object) -> RevenueConfirmation:
        nonlocal calls
        confirmation = load(**kwargs)  # type: ignore[arg-type]
        calls += 1
        if calls == 3:  # 完成两次事实查询后变更候选，必须被服务的返回前查证发现。
            h.set_text("2024年度营业收入：100万元。\n2025年度营业收入：125万元。")
        return confirmation

    monkeypatch.setattr(h.repository, "load", load_then_change)
    h.retriever.retrieve.reset_mock()
    output = invoke(h, accepted.confirmation_id)
    assert output["status"] == "refused" and output["error_code"] == "source_changed"
    assert output["result"] is None and calls == 3
    assert h.retriever.retrieve.call_count == 3


def test_zero_denominator_remains_existing_business_refusal(h: Harness) -> None:
    h.set_text("2024年度营业收入：0万元。\n2025年度营业收入：120万元。")
    accepted = h.simulate_acceptance(h.preview())
    output = invoke(h, accepted.confirmation_id)
    assert output["status"] == "refused" and output["result"] is None
    assert output["error_code"] == "division_by_zero"


def test_reusing_previous_output_cannot_republish_result_on_missing_confirmation(h: Harness) -> None:
    accepted = h.simulate_acceptance(h.preview())
    graph = build_revenue_graph(service=h.service)
    success = asyncio.run(
        graph.ainvoke({"document_id": h.document_id, "confirmation_id": accepted.confirmation_id})
    )
    assert success["result"] is not None
    # 误传完整旧输出时，输入 schema 只接受 ID，读取节点也显式清除旧结果。
    success["confirmation_id"] = None
    failure = asyncio.run(graph.ainvoke(cast(RevenueGraphInput, success)))
    assert failure["status"] == "needs_confirmation" and failure["result"] is None


def test_stream_exposes_actual_node_order_and_pending_is_not_confirmation(h: Harness) -> None:
    accepted = h.simulate_acceptance(h.preview())
    graph = build_revenue_graph(service=h.service)

    async def updates() -> list[dict[str, object]]:
        return [
            item
            async for item in graph.astream(
                {"document_id": h.document_id, "confirmation_id": accepted.confirmation_id},
                stream_mode="updates",
            )
        ]

    events = asyncio.run(updates())
    assert [next(iter(item)) for item in events] == [
        "read_review", "check_confirmation", "calculate"
    ]
    pending = cast(dict[str, object], events[1]["check_confirmation"])
    assert pending["status"] == "verification_pending" and pending["result"] is None
