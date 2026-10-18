"""纯图调度测试：业务服务完全 fake；不能替代 SQLite/真实事实链集成。"""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from app.agent.revenue_confirmation import RevenueConfirmationError, RevenueReview
from app.agent.revenue_graph import build_revenue_graph


def service_double() -> Mock:
    """明确 fake 的候选摘要与服务，只观察图的调度/失败清理，不证明业务校验。"""
    review = Mock(spec=RevenueReview, candidates=(), snapshot_id="fake-snapshot", revision=Mock())
    return Mock(preview=AsyncMock(return_value=review), calculate=AsyncMock())


def test_preview_business_refusal_never_calls_calculate() -> None:
    service = service_double()
    service.preview.side_effect = RevenueConfirmationError("candidate_conflict")
    graph = build_revenue_graph(service=service)
    output = asyncio.run(graph.ainvoke({"document_id": "fake", "confirmation_id": "fake-id"}))
    assert output["status"] == "refused" and output["error_code"] == "candidate_conflict"
    assert output["result"] is None and output["review_summary"] is None
    service.calculate.assert_not_called()


@pytest.mark.parametrize("node", ["preview", "calculate"])
def test_unexpected_program_error_is_failed_not_success_or_business_refusal(
    node: str, caplog: pytest.LogCaptureFixture
) -> None:
    service = service_double()
    getattr(service, node).side_effect = ValueError("internal-program-fault")
    graph = build_revenue_graph(service=service)
    output = asyncio.run(graph.ainvoke({"document_id": "fake", "confirmation_id": "fake-id"}))
    assert output["status"] == "failed" and output["error_kind"] == "program"
    assert output["error_code"] == "unexpected_error" and output["result"] is None
    assert "internal-program-fault" in caplog.text
    assert getattr(service, node).await_count == 1
    if node == "preview":
        service.calculate.assert_not_called()


def test_calculate_refusal_is_not_retried_or_turned_into_success() -> None:
    service = service_double()
    service.calculate.side_effect = RevenueConfirmationError("source_changed")
    graph = build_revenue_graph(service=service)
    output = asyncio.run(graph.ainvoke({"document_id": "fake", "confirmation_id": "fake-id"}))
    assert output["status"] == "refused" and output["result"] is None
    assert output["error_code"] == "source_changed"
    assert service.preview.await_count == 1 and service.calculate.await_count == 1


def test_invalid_service_success_envelope_is_program_failure() -> None:
    service = service_double()
    service.calculate.return_value = None
    graph = build_revenue_graph(service=service)
    output = asyncio.run(graph.ainvoke({"document_id": "fake", "confirmation_id": "fake-id"}))
    assert output["status"] == "failed" and output["result"] is None
    assert output["error_kind"] == "program"
