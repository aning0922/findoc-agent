"""D23 real frozen inputs, races, atomic failures, read-only history and isolation."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import copy
import json
import shutil
import sqlite3
import uuid
from unittest.mock import AsyncMock, Mock
import pytest
from fastapi.testclient import TestClient
from app.api.report_drafts import create_report_router
from app.api.report_history import create_report_history_app
from app.reports.persistence_contracts import SaveReport, CreateRevision
from app.reports.persistence_service import ReportPersistenceService
from app.research.repository import HistoryError
from app.reports.service import ReportService
from tests.test_d22_reports import reports as d22_reports, run, rewrite  # noqa: F401


@pytest.fixture
def reports(d22_reports):  # noqa: F811
    return d22_reports


def req(task, **extra):
    return SaveReport(
        operation_id=str(uuid.uuid4()),
        task_id=task["task_id"],
        expected_task_revision=task["revision"],
        **extra,
    )


def counts(repo):
    with closing(repo.read_connection()) as conn:
        return tuple(
            conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            for t in (
                "reports",
                "report_revisions",
                "report_operations",
                "report_source_refs",
                "report_fact_refs",
            )
        )


def test_save_edits_append_original_unchanged_and_strict_http(reports):
    h, tasks, drafts, task = reports
    service = ReportPersistenceService(drafts)
    h.client.app.include_router(create_report_router(drafts))
    body = req(
        task, edits=dict(title="用户标题", conclusions=["这是用户判断，需人工审阅"])
    ).model_dump(mode="json")
    for field, value in [
        ("financial_facts", []),
        ("formula", {}),
        ("persisted", True),
        ("status", "qualified"),
        ("test_mode", None),
    ]:
        assert h.client.post("/reports", json={**body, field: value}).status_code == 422
    assert (
        h.client.post(
            "/reports", json={**body, "edits": {"validation_status": "verified"}}
        ).status_code
        == 422
    )
    saved = h.client.post("/reports", json=body)
    assert saved.status_code == 200 and saved.headers["cache-control"] == "no-store"
    value = saved.json()["report"]
    rid = value["report_id"]
    assert value["persisted"] and value["revision"] == 1 and value["parent_revision"] is None
    assert value["trusted_snapshot"]["title"] != value["editor_revision"]["title"]
    assert value["editor_revision"]["validation_status"] == "pending_semantic_review"
    assert value["editor_revision"]["verified_operating_attribution"] is False
    original = copy.deepcopy(value)
    append = CreateRevision(**req(task).model_dump(), expected_report_revision=1)
    result = run(service.save(append, rid))
    assert result["report"]["revision"] == 2 and result["report"]["parent_revision"] == 1
    assert service.repository.get(rid, 1)["report"] == original
    assert h.client.get(f"/reports/{rid}/revisions/1").json()["report"] == original
    assert h.client.get("/reports?limit=1").json()["items"][0]["current_revision"] == 2
    assert h.client.get("/reports?limit=0").status_code == 422
    assert h.client.get("/reports?foo=1").status_code == 422
    assert h.client.get(f"/reports/{rid}/revisions/0").status_code == 422
    assert h.client.get(f"/reports/{rid}/revisions/100").status_code == 404
    assert counts(service.repository)[0:3] == (1, 2, 2)
    with closing(h.registry._connect()) as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_operation_replay_after_new_version_and_revocation_never_rebuilds(reports, monkeypatch):
    h, _, drafts, task = reports
    service = ReportPersistenceService(drafts)
    body = req(task)
    saved = run(service.save(body))
    rid = saved["report"]["report_id"]
    run(service.save(CreateRevision(**req(task).model_dump(), expected_report_revision=1), rid))
    h.receipts.revoke_financial_receipt(
        workspace_id="demo",
        receipt_id=task["final_research_content"]["financial_facts"][0]["receipt_id"],
        confirmation_kind="simulated_test",
        reason="D23 replay audit",
    )
    monkeypatch.setattr(drafts, "pdf_evidence", AsyncMock(side_effect=AssertionError("replay PDF")))
    monkeypatch.setattr(drafts.builder, "build", Mock(side_effect=AssertionError("replay build")))
    result = run(service.save(body))
    assert result["report"] == saved["report"] and result["current_revision"] == 2
    assert result["current_eligibility"]["status"] == "invalidated"
    assert service.repository.by_operation(body.operation_id)["report"] == saved["report"]
    with pytest.raises(HistoryError, match="operation_request_conflict"):
        run(
            service.save(
                body.model_copy(update={"edits": req(task, edits=dict(title="different")).edits})
            )
        )


@pytest.mark.parametrize("race", ["revoke", "source", "revision", "content"])
def test_final_transaction_rejects_races_with_zero_partial_rows(reports, race):
    h, tasks, drafts, task = reports
    service = ReportPersistenceService(drafts)
    original = drafts.pdf_evidence
    calls = 0

    async def change(value):
        nonlocal calls
        await original(value)
        calls += 1
        if calls != 2:
            return
        if race == "revoke":
            h.receipts.revoke_financial_receipt(
                workspace_id="demo",
                receipt_id=task["final_research_content"]["financial_facts"][0]["receipt_id"],
                confirmation_kind="simulated_test",
                reason="D23 final race",
            )
        elif race == "source":
            report = task["final_research_content"]["selected_reports"][0]
            metadata = {
                k: report[k]
                for k in (
                    "company_id",
                    "report_year",
                    "report_type",
                    "period_start",
                    "period_end",
                    "basis",
                )
            }
            response = h.client.post(
                f"/documents/{report['document_id']}/binding-corrections",
                json=dict(
                    expected_attempt=report["attempt"],
                    metadata={**metadata, "basis": "unknown"},
                    reason="D23 final race",
                ),
            )
            assert response.status_code == 200
        else:
            value = copy.deepcopy(task)
            if race == "revision":
                value["revision"] += 1
            else:
                value["final_research_content"]["unresolved_questions"].append("新冻结问题")
                value["snapshot"]["final_research_content"] = copy.deepcopy(
                    value["final_research_content"]
                )
            rewrite(tasks, value)

    drafts.pdf_evidence = change
    with pytest.raises(HistoryError):
        run(service.save(req(task)))
    assert counts(service.repository) == (0, 0, 0, 0, 0)


@pytest.mark.parametrize(
    "table",
    ["reports", "report_revisions", "report_source_refs", "report_fact_refs", "report_operations"],
)
def test_write_failure_rolls_back_entire_group(reports, table):
    h, _, drafts, task = reports
    service = ReportPersistenceService(drafts)
    with closing(h.registry._connect()) as conn, conn:
        conn.execute(
            f"CREATE TRIGGER fail_d23 BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'injected storage failure'); END"
        )
    with pytest.raises(sqlite3.Error):
        run(service.save(req(task)))
    assert counts(service.repository) == (0, 0, 0, 0, 0)


def test_revision_head_failure_and_post_commit_unknown_get_recovery(reports, monkeypatch):
    h, _, drafts, task = reports
    service = ReportPersistenceService(drafts)
    first = run(service.save(req(task)))
    rid = first["report"]["report_id"]
    before = counts(service.repository)
    with closing(h.registry._connect()) as conn, conn:
        conn.execute(
            "CREATE TRIGGER fail_d23 BEFORE UPDATE ON reports BEGIN SELECT RAISE(ABORT,'injected head failure'); END"
        )
    with pytest.raises(sqlite3.Error):
        run(service.save(CreateRevision(**req(task).model_dump(), expected_report_revision=1), rid))
    assert counts(service.repository) == before
    with closing(h.registry._connect()) as conn, conn:
        conn.execute("DROP TRIGGER fail_d23")
    body = req(task)
    original = service.repository.get
    monkeypatch.setattr(
        service.repository, "get", Mock(side_effect=sqlite3.OperationalError("lost readback"))
    )
    with pytest.raises(sqlite3.Error):
        run(service.save(body))
    recovered = service.repository.by_operation(body.operation_id)
    assert original(recovered["report"]["report_id"], 1) == recovered


def test_concurrent_operation_and_revision_fences(reports):
    _, _, drafts, task = reports
    service = ReportPersistenceService(drafts)
    body = req(task)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(service.save(body)), range(2)))
    assert results[0]["report"] == results[1]["report"] and counts(service.repository)[0:3] == (
        1,
        1,
        1,
    )
    rid = results[0]["report"]["report_id"]
    requests = [
        CreateRevision(**req(task).model_dump(), expected_report_revision=1) for _ in range(2)
    ]

    def save(body):
        try:
            return run(service.save(body, rid))
        except HistoryError as e:
            return e.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, requests))
    assert sum(isinstance(r, dict) for r in results) == 1 and "report_revision_conflict" in results
    assert counts(service.repository)[0:3] == (1, 2, 2)


@pytest.mark.parametrize(
    "table", ["report_revisions", "report_operations", "report_source_refs", "report_fact_refs"]
)
@pytest.mark.parametrize("action", ["UPDATE", "DELETE"])
def test_database_immutable_guards(reports, table, action):
    h, _, drafts, task = reports
    service = ReportPersistenceService(drafts)
    run(service.save(req(task)))
    with closing(h.registry._connect()) as conn, conn:
        statement = (
            f"DELETE FROM {table}"
            if action == "DELETE"
            else f"UPDATE {table} SET workspace_id=workspace_id"
        )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute(statement)


@pytest.mark.parametrize("damage", ["sha", "schema", "canonical", "refs", "editor", "head"])
def test_unknown_schema_digest_and_identity_damage_fail_closed(reports, damage):
    h, _, drafts, task = reports
    service = ReportPersistenceService(drafts)
    saved = run(service.save(req(task)))
    rid = saved["report"]["report_id"]
    from app.research.models import canonical, sha

    with closing(h.registry._connect()) as conn, conn:
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'd23_%'"
        ).fetchall():
            conn.execute(f"DROP TRIGGER {row[0]}")
        if damage == "sha":
            conn.execute("UPDATE report_revisions SET payload_sha256=?", ("a" * 64,))
        elif damage == "refs":
            conn.execute("DELETE FROM report_fact_refs WHERE side=?", ("first",))
        elif damage == "editor":
            conn.execute("UPDATE report_revisions SET editor_json='{}'")
        elif damage == "head":
            conn.execute("PRAGMA defer_foreign_keys=ON")
            conn.execute("UPDATE reports SET current_revision=2")
        else:
            value = saved["report"]
            value["schema_version"] = "unknown" if damage == "schema" else value["schema_version"]
            payload = (
                canonical(value)
                if damage == "schema"
                else json.dumps(value, ensure_ascii=False, indent=2)
            )
            conn.execute(
                "UPDATE report_revisions SET canonical_payload=?,payload_sha256=?",
                (payload, sha(payload)),
            )
        if damage == "head":
            conn.rollback()
    if damage == "head":
        # Corrupt with constraints deliberately disabled, representing storage/admin damage.
        with sqlite3.connect(h.db) as conn:
            conn.execute("UPDATE reports SET current_revision=2")
    with pytest.raises(HistoryError, match="report_integrity_error"):
        service.repository.get(rid, 1)


def test_history_only_missing_pdf_no_writes_no_execution_and_workspace_isolation(
    reports, monkeypatch
):
    h, _, drafts, task = reports
    service = ReportPersistenceService(drafts)
    body = req(task)
    saved = run(service.save(body))
    rid = saved["report"]["report_id"]
    shutil.rmtree(h.root / "objects")
    monkeypatch.setattr(
        drafts, "pdf_evidence", AsyncMock(side_effect=AssertionError("history must not read PDF"))
    )
    before = h.db.read_bytes()
    app = create_report_history_app(h.db)
    client = TestClient(app)
    assert client.get(f"/reports/{rid}/revisions/1").json() == saved
    assert client.get(f"/reports/by-operation/{body.operation_id}").json() == saved
    assert client.get("/reports").json()["items"][0]["report_id"] == rid
    assert client.post("/reports", json=body.model_dump()).status_code == 405
    assert h.db.read_bytes() == before
    other = TestClient(create_report_history_app(h.db, workspace="other"))
    assert other.get("/reports").json()["items"] == []
    assert other.get(f"/reports/{rid}/revisions/1").status_code == 404
    assert other.get(f"/reports/by-operation/{body.operation_id}").status_code == 404


def test_production_cannot_save_simulation_and_stale_task_fails(reports):
    h, tasks, drafts, task = reports
    production = ReportPersistenceService(ReportService(tasks, h.service))
    with pytest.raises(HistoryError, match="report_production_confirmation_required"):
        run(production.save(req(task)))
    service = ReportPersistenceService(drafts)
    with pytest.raises(HistoryError, match="revision_conflict"):
        run(
            service.save(
                req(task).model_copy(update={"expected_task_revision": task["revision"] + 1})
            )
        )
    assert counts(service.repository) == (0, 0, 0, 0, 0)


def test_production_post_cannot_replay_a_saved_simulation(reports):
    h, tasks, drafts, task = reports
    simulated = ReportPersistenceService(drafts)
    body = req(task)
    saved = run(simulated.save(body))
    production = ReportPersistenceService(ReportService(tasks, h.service))
    with pytest.raises(HistoryError, match="report_production_confirmation_required"):
        run(production.save(body))
    assert production.repository.by_operation(body.operation_id)["report"] == saved["report"]
