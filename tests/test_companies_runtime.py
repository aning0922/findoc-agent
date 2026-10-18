"""Companies use the D4 production factory's existing SQLite/root and close boundary."""

from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from app.api import runtime_factory
from tests import test_runtime_revenue


@pytest.fixture
def assembled(tmp_path, monkeypatch):
    return test_runtime_revenue.assembled.__wrapped__(tmp_path, monkeypatch)


def test_runtime_company_persistence_reuses_document_database(tmp_path, assembled):
    app = runtime_factory.create_runtime_app(tmp_path)
    service = app.state.company_service
    assert (
        service._repository._database_path == app.state.revenue_service._repository._database_path
    )
    with TestClient(app) as client:
        created = client.post(
            "/companies",
            json={
                "name": "运行装配企业",
                "security_code": "688123",
                "exchange": "SSE",
            },
        )
        assert created.status_code == 201
    reopened = runtime_factory.create_runtime_app(tmp_path)
    with TestClient(reopened) as client:
        assert client.get("/companies").json() == [created.json()]
    assert assembled[5].close.call_count == 2


@pytest.mark.parametrize("failure_at", ["SQLiteCompanyRepository", "CompanyService"])
def test_company_assembly_failure_closes_shared_rag(tmp_path, assembled, monkeypatch, failure_at):
    monkeypatch.setattr(
        runtime_factory, failure_at, Mock(side_effect=OSError("company init failed"))
    )
    with pytest.raises(OSError, match="company init failed"):
        runtime_factory.create_runtime_app(tmp_path)
    assembled[5].close.assert_called_once_with()
