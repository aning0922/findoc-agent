"""真实收入服务/抽取/SQLite 的 HTTP 合同，检索与 PDF 内容使用明确替身。

HTTP accepted=true 均是自动化模拟动作；产品固定 local_operator 不代表本人确认。
不证明真实 BGE/Milvus、浏览器、上传解析或完整收入研究产品链。
"""

import copy
from dataclasses import replace
from datetime import datetime
from pathlib import Path
import sqlite3
from unittest.mock import AsyncMock, Mock

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from app.agent.revenue_confirmation import RevenueConfirmationError, RevenueConfirmationService
from app.agent.sqlite_financial_facts import SQLiteRevenueConfirmationRepository
from app.api.app import create_app
from app.api.revenue_research_schemas import (
    RevenueConfirmationResponse,
    RevenueReviewResponse,
)
from app.documents.models import DocumentStatus
from tests.test_revenue_confirmation import Harness


REVIEW = "/revenue-research/reviews"
CONFIRM = "/revenue-research/confirmations"
PRIVATE = "private-test-token /private/documents.db SELECT secret"


@pytest.fixture
def h(tmp_path: Path) -> Harness:
    """复用明确替身业务环境；本文件接受动作全部通过 HTTP 模拟。"""
    return Harness(tmp_path)


def client_for(h: Harness, *, enabled: bool = True, workspace: str = "demo") -> TestClient:
    """注入真实服务和文档读取，服务缺省用同一 app 验证安全降级。"""
    return TestClient(
        create_app(
            h.documents,
            revenue_service=h.service if enabled else None,
            revenue_workspace_id=workspace if enabled else None,
        )
    )


def confirmation_request(h: Harness, *, snapshot_id: str = "a" * 64) -> dict[str, object]:
    """构造 HTTP 模拟接受请求；实际成功用审阅响应里的服务端摘要。"""
    return {"document_id": h.document_id, "snapshot_id": snapshot_id, "accepted": True}


def assert_safe_error(response: object, status: int, code: str) -> None:
    """固定错误结构不含输入/原异常/旧回执；不接受仅状态码正确。"""
    assert response.status_code == status  # type: ignore[attr-defined]
    body = response.json()  # type: ignore[attr-defined]
    assert set(body) == {"detail"}
    assert set(body["detail"]) == {"code", "message"}
    assert body["detail"]["code"] == code
    assert PRIVATE not in response.text  # type: ignore[attr-defined]


def test_review_preserves_all_merged_evidence_and_internal_snapshot_without_writing(
    h: Harness,
) -> None:
    """相同金额的两处真实抽取输入合并，公开响应保留每一处证据与原摘要。"""
    primary = h.retriever.retrieve.return_value[0]
    h.retriever.retrieve.return_value.append(replace(primary, chunk_id="test-chunk-2", page=2))
    internal = h.preview()
    with client_for(h) as client:
        response = client.post(REVIEW, json={"document_id": h.document_id})
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {
        "schema",
        "document_id",
        "source_file",
        "snapshot_id",
        "revision",
        "candidates",
    }
    assert body["schema"] == "revenue-research-review-v1"
    assert body["snapshot_id"] == internal.snapshot_id
    assert set(body["revision"]) == {
        "content_sha256",
        "attempt",
        "extraction_method",
        "extraction_version",
    }
    assert [c["period"] for c in body["candidates"]] == [2024, 2025]
    assert [c["value"] for c in body["candidates"]] == ["1000000", "1200000"]
    for candidate, original in zip(body["candidates"], internal.candidates, strict=True):
        assert set(candidate) == {
            "source_ref",
            "chunk_id",
            "source_file",
            "page",
            "period",
            "value",
            "unit",
            "extraction_method",
            "extraction_version",
            "evidence",
        }
        assert candidate["unit"] == "CNY_YUAN"
        assert len(candidate["evidence"]) == len(original.evidence) == 2
        assert {e["page"] for e in candidate["evidence"]} == {1, 2}
        for evidence in candidate["evidence"]:
            assert set(evidence) == {
                "chunk_id",
                "source_file",
                "page",
                "text",
                "start",
                "end",
                "raw_value",
                "raw_unit",
            }
            assert evidence["raw_unit"] == "万元"
            assert evidence["raw_value"] in evidence["text"][evidence["start"] : evidence["end"]]
    assert "workspace_id" not in response.text and "object_key" not in response.text
    assert h.counts() == (0, 0)


def test_http_simulated_acceptance_is_saved_and_duplicate_after_reopen_reuses_receipt(
    h: Harness,
) -> None:
    """HTTP 模拟接受走原 confirm/事务；重建仓储/app 后重复仍复用原 ID/时间。"""
    with client_for(h) as client:
        review = client.post(REVIEW, json={"document_id": h.document_id}).json()
        request = confirmation_request(h, snapshot_id=review["snapshot_id"])
        first = client.post(CONFIRM, json=request)
    assert first.status_code == 200, first.text
    body = first.json()
    assert set(body) == {
        "schema",
        "document_id",
        "confirmation_id",
        "confirmed_at",
        "snapshot_id",
        "confirmation_kind",
    }
    assert body["schema"] == "revenue-research-confirmation-v1"
    assert body["document_id"] == h.document_id and body["snapshot_id"] == review["snapshot_id"]
    assert body["confirmation_kind"] == "local_operator"  # 固定产品字段；接受行为仍为自动化模拟。
    assert datetime.fromisoformat(body["confirmed_at"]).utcoffset() is not None
    h.service = RevenueConfirmationService(
        source_reader=h.reader, repository=SQLiteRevenueConfirmationRepository(h.database)
    )
    with client_for(h) as client:
        duplicate = client.post(CONFIRM, json=request)
    assert duplicate.status_code == 200 and duplicate.json() == body
    stored = h.repository.load(confirmation_id=body["confirmation_id"], current_review=h.preview())
    assert stored.confirmation_id == body["confirmation_id"] and h.counts() == (1, 2)


@pytest.mark.parametrize("path", [REVIEW, CONFIRM])
@pytest.mark.parametrize(
    "extra",
    [
        "workspace_id",
        "workspace",
        "value",
        "unit",
        "candidates",
        "confirmation_kind",
        "research_id",
    ],
)
def test_extra_fields_are_422_before_document_candidate_or_save(
    h: Harness,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    extra: str,
) -> None:
    documents = AsyncMock(wraps=h.documents.get_document)
    monkeypatch.setattr(h.documents, "get_document", documents)
    request = confirmation_request(h) if path == CONFIRM else {"document_id": h.document_id}
    with client_for(h) as client:
        response = client.post(path, json={**request, extra: PRIVATE})
    assert_safe_error(response, 422, "invalid_revenue_request")
    documents.assert_not_called()
    h.retriever.retrieve.assert_not_called()
    assert h.counts() == (0, 0)


@pytest.mark.parametrize("path", [REVIEW, CONFIRM])
@pytest.mark.parametrize("value", [None, 1, True, [], {}, "", " \n\t"])
def test_document_id_is_strict_nonempty(h: Harness, path: str, value: object) -> None:
    request = confirmation_request(h) if path == CONFIRM else {}
    with client_for(h) as client:
        response = client.post(path, json={**request, "document_id": value})
    assert_safe_error(response, 422, "invalid_revenue_request")
    h.retriever.retrieve.assert_not_called()
    assert h.counts() == (0, 0)


@pytest.mark.parametrize("value", [None, 1, 0, "true", "false", [], {}, 1.0])
def test_accepted_is_strict_boolean_before_confirm_is_called(
    h: Harness,
    monkeypatch: pytest.MonkeyPatch,
    value: object,
) -> None:
    confirm = AsyncMock(wraps=h.service.confirm)
    monkeypatch.setattr(h.service, "confirm", confirm)
    with client_for(h) as client:
        response = client.post(CONFIRM, json={**confirmation_request(h), "accepted": value})
    assert_safe_error(response, 422, "invalid_revenue_request")
    confirm.assert_not_called()
    h.retriever.retrieve.assert_not_called()
    assert h.counts() == (0, 0)


@pytest.mark.parametrize(
    "value", [None, 1, "", " ", "a" * 63, "a" * 65, "A" * 64, "g" * 64, "a" * 64 + "\n"]
)
def test_snapshot_requires_exact_lowercase_hex(h: Harness, value: object) -> None:
    with client_for(h) as client:
        response = client.post(CONFIRM, json={**confirmation_request(h), "snapshot_id": value})
    assert_safe_error(response, 422, "invalid_revenue_request")
    h.retriever.retrieve.assert_not_called()
    assert h.counts() == (0, 0)


@pytest.mark.parametrize("path", [REVIEW, CONFIRM])
def test_missing_fields_and_malformed_json_are_safe(h: Harness, path: str) -> None:
    with client_for(h) as client:
        missing = client.post(path, json={})
        malformed = client.post(
            path,
            content='{"document_id":"' + PRIVATE,
            headers={"Content-Type": "application/json"},
        )
    assert_safe_error(missing, 422, "invalid_revenue_request")
    assert_safe_error(malformed, 422, "invalid_revenue_request")
    assert missing.json() == malformed.json() and h.counts() == (0, 0)


def test_accepted_is_required(h: Harness) -> None:
    request = confirmation_request(h)
    del request["accepted"]
    with client_for(h) as client:
        response = client.post(CONFIRM, json=request)
    assert_safe_error(response, 422, "invalid_revenue_request")
    assert h.counts() == (0, 0)


def test_false_is_conflict_without_document_lookup_candidate_or_confirm(
    h: Harness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    documents = AsyncMock(wraps=h.documents.get_document)
    confirm = AsyncMock(wraps=h.service.confirm)
    monkeypatch.setattr(h.documents, "get_document", documents)
    monkeypatch.setattr(h.service, "confirm", confirm)
    with client_for(h) as client:
        response = client.post(CONFIRM, json={**confirmation_request(h), "accepted": False})
    assert_safe_error(response, 409, "confirmation_required")
    documents.assert_not_called()
    confirm.assert_not_called()
    h.retriever.retrieve.assert_not_called()
    assert h.counts() == (0, 0)


@pytest.mark.parametrize("path", [REVIEW, CONFIRM])
def test_missing_dependency_is_503_without_service_or_candidate(h: Harness, path: str) -> None:
    with client_for(h, enabled=False) as client:
        response = client.post(
            path,
            json=(confirmation_request(h) if path == CONFIRM else {"document_id": h.document_id}),
        )
    assert_safe_error(response, 503, "revenue_service_unavailable")
    h.retriever.retrieve.assert_not_called()
    assert h.counts() == (0, 0)


@pytest.mark.parametrize("workspace", [None, "", " ", 1])
def test_enabled_dependency_requires_server_scope(h: Harness, workspace: object) -> None:
    with pytest.raises(ValueError, match="服务端 workspace"):
        create_app(h.documents, revenue_service=h.service, revenue_workspace_id=workspace)


@pytest.mark.parametrize("path", [REVIEW, CONFIRM])
def test_unknown_and_other_workspace_documents_are_same_404(h: Harness, path: str) -> None:
    with sqlite3.connect(h.database) as connection:
        connection.execute("UPDATE documents SET workspace_id='other'")
    with client_for(h) as client:
        request = confirmation_request(h) if path == CONFIRM else {"document_id": h.document_id}
        outside = client.post(path, json=request)
        unknown = client.post(path, json={**request, "document_id": "unknown"})
    assert_safe_error(outside, 404, "document_not_found")
    assert unknown.status_code == 404 and unknown.json() == outside.json()
    h.retriever.retrieve.assert_not_called()
    assert h.counts() == (0, 0)


@pytest.mark.parametrize("path", [REVIEW, CONFIRM])
@pytest.mark.parametrize(
    "status", [s.value for s in DocumentStatus if s is not DocumentStatus.READY]
)
def test_not_ready_is_distinct_409_before_candidate(h: Harness, path: str, status: str) -> None:
    with sqlite3.connect(h.database) as connection:
        if status == "failed":
            connection.execute(
                "UPDATE documents SET status='failed', failed_stage='parsing', "
                "error_code='simulated_parse_error', safe_error_message='模拟解析失败'"
            )
        else:
            connection.execute("UPDATE documents SET status=?", (status,))
    with client_for(h) as client:
        response = client.post(
            path,
            json=(confirmation_request(h) if path == CONFIRM else {"document_id": h.document_id}),
        )
    assert_safe_error(response, 409, "document_not_ready")
    h.retriever.retrieve.assert_not_called()
    assert h.counts() == (0, 0)


def test_stale_review_blocks_repository_save(h: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    saved = Mock(wraps=h.repository.save)
    monkeypatch.setattr(h.repository, "save", saved)
    with client_for(h) as client:
        review = client.post(REVIEW, json={"document_id": h.document_id}).json()
        h.set_text("2024年度营业收入：100万元。\n2025年度营业收入：125万元。")
        response = client.post(
            CONFIRM, json=confirmation_request(h, snapshot_id=review["snapshot_id"])
        )
    assert_safe_error(response, 409, "review_changed")
    saved.assert_not_called()
    assert h.counts() == (0, 0)


@pytest.mark.parametrize("path", [REVIEW, CONFIRM])
@pytest.mark.parametrize(
    "text,code",
    [
        ("2024年度营业收入：100万元。", "missing_candidate"),
        ("2024年度营业收入：100万元。\n2025年度营业收入：120美元。", "unit_unknown"),
        ("2023年度营业收入：100万元。\n2024年度营业收入：120万元。", "period_mismatch"),
        (
            "2024年度营业收入：100万元。\n2024年度营业收入：110万元。\n2025年度营业收入：120万元。",
            "candidate_conflict",
        ),
    ],
)
def test_business_candidate_failures_are_safe_conflicts(
    h: Harness, path: str, text: str, code: str
) -> None:
    h.set_text(text)
    with client_for(h) as client:
        response = client.post(
            path,
            json=(confirmation_request(h) if path == CONFIRM else {"document_id": h.document_id}),
        )
    assert_safe_error(response, 409, code)
    assert h.counts() == (0, 0)


def test_changed_actual_file_is_409_without_save(h: Harness) -> None:
    h.objects.put_bytes(h.object_key, b"%PDF-changed-explicit-double")
    with client_for(h) as client:
        response = client.post(REVIEW, json={"document_id": h.document_id})
    assert_safe_error(response, 409, "source_changed")
    h.retriever.retrieve.assert_not_called()
    assert h.counts() == (0, 0)


@pytest.mark.parametrize("damage", ["missing_fact", "amount", "evidence", "time"])
def test_duplicate_damaged_confirmation_returns_500_without_old_receipt(
    h: Harness, damage: str
) -> None:
    with client_for(h) as client:
        review = client.post(REVIEW, json={"document_id": h.document_id}).json()
        request = confirmation_request(h, snapshot_id=review["snapshot_id"])
        assert client.post(CONFIRM, json=request).status_code == 200
        with sqlite3.connect(h.database) as connection:
            statements = {
                "missing_fact": "DELETE FROM confirmed_revenue_facts WHERE period=2025",
                "amount": "UPDATE confirmed_revenue_facts SET value_text='999' WHERE period=2025",
                "evidence": "UPDATE confirmed_revenue_facts SET evidence_json='[]' WHERE period=2025",
                "time": "UPDATE revenue_confirmations SET confirmed_at='2026-10-09T00:00:00'",
            }
            connection.execute(statements[damage])
        before = h.counts()
        response = client.post(CONFIRM, json=request)
    assert_safe_error(response, 500, "confirmation_integrity_error")
    assert h.counts() == before


def test_transaction_write_failure_is_safe_500_and_entire_group_rolls_back(h: Harness) -> None:
    with sqlite3.connect(h.database) as connection:
        connection.execute(
            "CREATE TRIGGER fail_second_fact BEFORE INSERT ON confirmed_revenue_facts "
            "WHEN NEW.period=2025 BEGIN SELECT RAISE(ABORT, '" + PRIVATE + "'); END"
        )
    with client_for(h) as client:
        review = client.post(REVIEW, json={"document_id": h.document_id}).json()
        response = client.post(
            CONFIRM, json=confirmation_request(h, snapshot_id=review["snapshot_id"])
        )
    assert_safe_error(response, 500, "revenue_storage_error")
    assert h.counts() == (0, 0)


@pytest.mark.parametrize(
    "exception,code",
    [
        (sqlite3.OperationalError(PRIVATE), "revenue_storage_error"),
        (OSError(PRIVATE), "revenue_internal_error"),
        (RevenueConfirmationError(PRIVATE), "revenue_internal_error"),
    ],
)
def test_read_and_unknown_failures_do_not_echo_exceptions(
    h: Harness,
    monkeypatch: pytest.MonkeyPatch,
    exception: Exception,
    code: str,
) -> None:
    monkeypatch.setattr(h.documents, "get_document", AsyncMock(side_effect=exception))
    with client_for(h) as client:
        response = client.post(REVIEW, json={"document_id": h.document_id})
    assert_safe_error(response, 500, code)
    assert h.counts() == (0, 0)


def test_decimal_precision_has_no_float_roundtrip(h: Harness) -> None:
    h.set_text(
        "2024年度营业收入：1000000.0000000000000000001元。\n2025年度营业收入：1200000.0000000000000000001元。"
    )
    with client_for(h) as client:
        response = client.post(REVIEW, json={"document_id": h.document_id})
    assert response.status_code == 200
    assert response.json()["candidates"][0]["value"] == "1000000.0000000000000000001"


def test_output_dtos_reject_nested_extras_numbers_boolean_ints_and_naive_time(h: Harness) -> None:
    with client_for(h) as client:
        review = client.post(REVIEW, json={"document_id": h.document_id}).json()
        receipt = client.post(
            CONFIRM, json=confirmation_request(h, snapshot_id=review["snapshot_id"])
        ).json()
    for field in ("revision", "candidate", "evidence"):
        invalid = copy.deepcopy(review)
        target = {
            "revision": invalid["revision"],
            "candidate": invalid["candidates"][0],
            "evidence": invalid["candidates"][0]["evidence"][0],
        }[field]
        target["workspace_id"] = PRIVATE
        with pytest.raises(ValidationError):
            RevenueReviewResponse.model_validate(invalid)
    for field, value in (("value", 1000000), ("page", True), ("period", "2024")):
        invalid = copy.deepcopy(review)
        invalid["candidates"][0][field] = value
        with pytest.raises(ValidationError):
            RevenueReviewResponse.model_validate(invalid)
    with pytest.raises(ValidationError):
        RevenueConfirmationResponse.model_validate(
            {
                **receipt,
                "confirmed_at": datetime(2026, 10, 9),
            }
        )


def test_revenue_validation_handler_does_not_change_old_routes(h: Harness) -> None:
    with client_for(h) as client:
        revenue = client.post(REVIEW, json={"document_id": 1})
        agent = client.post("/agent/runs", json={"document_id": 1, "query": "x"})
        chat = client.post("/chat", json={})
        missing = client.get("/documents/missing")
    assert_safe_error(revenue, 422, "invalid_revenue_request")
    assert_safe_error(agent, 422, "invalid_agent_request")
    assert chat.status_code == 422 and isinstance(chat.json()["detail"], list)
    assert missing.status_code == 404 and missing.json() == {"detail": "文档不存在"}


def test_runs_get_and_research_repository_are_not_added(h: Harness) -> None:
    """今天只有两条 POST；已有确认库不混入研究终态表。"""
    with client_for(h) as client:
        paths = client.get("/openapi.json").json()["paths"]
        assert {p for p in paths if p.startswith("/revenue-research")} == {REVIEW, CONFIRM}
        assert set(paths[REVIEW]) == set(paths[CONFIRM]) == {"post"}
    with sqlite3.connect(h.database) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "revenue_research_results" not in tables
