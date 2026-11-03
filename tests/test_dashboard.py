"""UNIT_FAKE: fresh temporary SQLite and simulated receipts; no human signing/model."""

from contextlib import closing
from dataclasses import replace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dashboard import DashboardService, create_dashboard_router
from app.memory.models import CreateMemoryRequest
from app.memory.repository import MemoryRepository
from app.memory.service import MemoryService
from app.research.task_contracts import StartTask
from app.research.task_repository import TaskRepository
from tests.test_d11_financial_analysis import saved as saved  # noqa: F401
from tests.test_d18_templates import body


def setup(h):
    tasks = TaskRepository(h.registry, "demo")
    memory = MemoryService(MemoryRepository(h.registry))
    service = DashboardService(
        runtime_root=h.root,
        workspace_id="demo",
        tasks=tasks,
        facts=h.confirmations,
        memory=memory,
        lease_generation=7,
        seed_version="unit-fake",
    )
    app = FastAPI()
    app.include_router(create_dashboard_router(service))
    return service, tasks, memory, TestClient(app)


def test_snapshot_counts_preferences_and_task_integrity(saved):
    h, group, _ = saved
    svc, tasks, memory, client = setup(h)
    task, _ = tasks.start(StartTask(operation_id=str(uuid4()), input=body(group)))
    value = client.get("/dashboard/overview").json()
    assert value["kpis"] == dict(companies=3, reports_ready=1, research_completed=0, reports=0)
    assert value["task_distribution"] == [dict(status="running", count=1)]
    assert value["lease_generation"] == 7 and value["seed_version"] == "unit-fake"
    assert value["recent_research"][0]["review_status"] == "source_recheck_required"
    memory.create(
        CreateMemoryRequest(
            operation_id=str(uuid4()),
            type="research_preference",
            key="analysis_focus",
            value="cash_flow",
            confirmed=True,
        )
    )
    before = h.db.read_bytes()
    result = client.get("/dashboard/overview")
    assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
    assert result.json()["suggested_questions"][0]["id"] == "operating_cash_flow"
    assert "question=" in result.json()["suggested_questions"][0]["href"]
    assert h.db.read_bytes() == before  # GET never migrates or writes.
    with closing(h.registry._connect()) as conn, conn:
        conn.execute(
            "UPDATE template_tasks SET payload_sha=? WHERE task_id=?", ("0" * 64, task["task_id"])
        )
    broken = client.get("/dashboard/overview")
    assert broken.status_code == 503 and "kpis" not in broken.json()
    assert client.get("/dashboard/overview?workspace_id=other").status_code == 422


def test_empty_missing_storage_and_isolated_samples(tmp_path):
    from app.companies.sqlite_repository import SQLiteCompanyRepository

    registry = SQLiteCompanyRepository(tmp_path / "documents.db")
    svc = DashboardService(
        runtime_root=tmp_path, workspace_id="demo", tasks=TaskRepository(registry, "demo")
    )
    app = FastAPI()
    app.include_router(create_dashboard_router(svc))
    client = TestClient(app)
    assert client.get("/dashboard/overview").json()["kpis"] == dict(
        companies=0, reports_ready=0, research_completed=0, reports=0
    )
    assert client.get("/dashboard/charts?company_id=foreign").status_code == 404
    sample = client.get("/dashboard/charts?sample_mode=true&company_id=real-company").json()
    assert sample["origin"] == "illustrative" and sample["company_id"] != "real-company"
    assert all("fact_ref" not in p for p in sample["points"])
    invalid = client.get("/dashboard/charts?metric_key=made_up")
    assert invalid.status_code == 422 and invalid.json()["detail"]["code"] == "unsupported_metric"
    assert client.get("/dashboard/charts?sample_mode=bad").status_code == 422
    assert client.get("/dashboard/charts?metric_key=revenue&metric_key=revenue").status_code == 422
    (tmp_path / "documents.db").unlink()
    assert client.get("/dashboard/overview").status_code == 503
    assert not (tmp_path / "documents.db").exists()


def test_chart_actual_admission_with_unit_fake_read_substitute(saved, monkeypatch):
    h, group, _ = saved
    svc, _, _, client = setup(h)
    empty = client.get("/dashboard/charts?company_id=" + h.company.company_id)
    assert empty.status_code == 200 and empty.json()["points"] == []
    assert empty.json()["empty_reason"] == "no_eligible_facts"
    # No local_operator receipt is created: only the read projection is substituted.
    projected = replace(group, receipt=replace(group.receipt, confirmation_kind="local_operator"))
    payload = projected.to_payload()
    facts = [
        {
            **f,
            **{
                k: payload[k]
                for k in (
                    "fact_set_id",
                    "disclosure_version",
                    "source_revision",
                    "current_valid",
                    "calculable",
                    "production_calculable",
                    "confirmation_kind",
                )
            },
        }
        for f in payload["facts"]
        if f["metric_key"] == "revenue"
    ]
    query = AsyncMock(return_value=dict(facts=facts))
    monkeypatch.setattr(h.confirmations, "query_financial_facts", query)
    reader = AsyncMock(return_value=projected)
    monkeypatch.setattr(h.confirmations, "read_financial_facts", reader)
    recheck = AsyncMock()
    monkeypatch.setattr(h.confirmations, "recheck_financial_analysis_sources", recheck)
    url = "/dashboard/charts?company_id=" + h.company.company_id
    result = client.get(url)
    assert result.status_code == 200, result.text
    points = result.json()["points"]
    assert len(points) == 2 and all(isinstance(p["value_decimal"], str) for p in points)
    assert points[0]["period"] == 2030 and points[0]["report_year"] == 2031
    assert points[0]["fact_ref"]["disclosure_version"] == group.disclosure_version
    assert query.call_args.kwargs["confirmation_kind"] == "local_operator"
    recheck.assert_awaited_once()
    # Multiple eligible receipts for the same period are not silently selected.
    duplicate = replace(
        projected, fact_set_id="different-fact-set", disclosure_version="different-disclosure"
    )
    extra = dict(
        facts[0], fact_set_id=duplicate.fact_set_id, disclosure_version=duplicate.disclosure_version
    )
    query.return_value = dict(facts=[facts[0], extra])
    reader.side_effect = lambda **kw: (
        duplicate if kw["receipt_id"] == duplicate.fact_set_id else projected
    )
    ambiguous = client.get(url).json()
    assert ambiguous["points"] == []
    assert ambiguous["limitations"] == [f"version_selection_required:{extra['period']}"]
    # Source invalidation at final admission closes the response, never stale numeric success.
    from app.agent.revenue_confirmation import RevenueConfirmationError

    query.return_value = dict(facts=facts)
    reader.side_effect = None
    recheck.side_effect = RevenueConfirmationError("source_changed")
    failed = client.get(url)
    assert failed.status_code == 503 and "points" not in failed.json()
