"""UNIT_SYNTHETIC: real root services/SQLite, generated PDFs, no human/provider calls."""

import asyncio
from datetime import datetime
import json
import sqlite3
from threading import Thread
from uuid import uuid4

import pymupdf
import pytest

from app.companies.models import CompanyCreate
from app.documents.models import DocumentStatus
from app.documents.preparation import DocumentTaskPreparer
from app.research_templates_v1 import (
    TemplateRunService,
    create_template_run_router,
)
from app.chart_report_drafts import ChartReportDraftService, create_chart_report_draft_router
from app.checkup import CheckupService
from app.cplus.runtime import fast_ref
from app.retrieval_v2 import TrustedIdentity
from tests.test_document_sources import Harness, metadata
from tests.test_cplus_m3_integration_review import root_app


def pdf(name, year, *, empty=False):
    with pymupdf.open() as doc:
        p = doc.new_page()
        for y, text in [
            (60, name),
            (90, f"{year}年年度报告"),
            (130, "遵循企业会计准则：财务报表符合企业会计准则的要求"),
            (160, "主要业务：产品销售及研发技术创新。主要经营风险：原材料市场竞争。"),
        ]:
            p.insert_text((40, y), text, fontname="china-s", fontsize=10)
        if not empty:
            for title, rows, duration in [
                (
                    "合并资产负债表",
                    [("资产总计", "1000", "900"), ("负债合计", "500", "450")],
                    False,
                ),
                (
                    "合并利润表",
                    [("其中：营业收入", "800", "700"), ("归属于母公司股东的净利润", "100", "90")],
                    True,
                ),
                ("合并现金流量表", [("经营活动产生的现金流量净额", "120", "110")], True),
            ]:
                p = doc.new_page()
                contents = [
                    (40, 45, title),
                    (40, 65, "单位：人民币元"),
                    (40, 85, "项目"),
                    (250, 85, f"{year}年度" if duration else f"{year}年12月31日"),
                    (420, 85, f"{year - 1}年度" if duration else f"{year - 1}年12月31日"),
                ]
                for idx, (label, value, prior) in enumerate(rows):
                    contents.extend(
                        [
                            (40, 110 + idx * 25, label),
                            (280, 110 + idx * 25, value + ".00"),
                            (450, 110 + idx * 25, prior + ".00"),
                        ]
                    )
                for x, y, text in contents:
                    p.insert_text((x, y), text, fontname="china-s", fontsize=9)
        return doc.tobytes()


@pytest.fixture
def rig(tmp_path, monkeypatch):
    h = Harness(tmp_path)
    companies = [
        h.companies.create(CompanyCreate(name=name, security_code=str(idx), exchange="DEMO"))
        for idx, name in enumerate(["测试股份有限公司", "对照股份有限公司"], 10)
    ]
    sources = []
    for company, year, empty in [
        (companies[0], 2030, False),
        (companies[0], 2031, False),
        (companies[1], 2031, False),
        (companies[1], 2032, True),
    ]:
        upload = h.upload(
            pdf(company.name, year, empty=empty),
            metadata(company.company_id, year),
            filename=f"{year}.pdf",
        )
        assert upload.status_code == 202, upload.text
        identifier = upload.json()["document_id"]
        assert h.processor.process(identifier).status == DocumentStatus.READY
        source = h.client.get(f"/documents/{identifier}/source").json()
        sources.append(source)
    preparer = DocumentTaskPreparer(
        document_service=h.documents, sources=h.service, workspace_id="demo"
    )
    app, client, memory = root_app(h, None, tmp_path, monkeypatch, preparer)
    state = app.state
    hybrid = state.cplus_retrieval_service
    kwargs = dict(
        statements=state.cplus_statement_service,
        identity_validator=hybrid.identity_validator,
        publication_guard=state.cplus_publication_guard,
        commit_check=lambda i, f: hybrid.commit_check(i),
    )
    templates = TemplateRunService(
        tmp_path,
        checkups=CheckupService(kwargs["statements"]),
        annual_diff=state.cplus_annual_diff_service,
        peers=state.cplus_peer_service,
        hybrid=hybrid,
        **kwargs,
    )
    drafts = ChartReportDraftService(tmp_path, **kwargs)
    app.include_router(create_template_run_router(templates, state.cplus_identity_provider))
    app.include_router(create_chart_report_draft_router(drafts, state.cplus_identity_provider))
    refs = []
    for source in sources:
        selection = asyncio.run(
            preparer.prepare_many(document_ids=[source["document_id"]], query="主要业务")
        )
        refs.append(fast_ref(selection.documents[0]).model_dump())
    identity = TrustedIdentity(
        workspace_id="demo",
        instance_id="review-instance",
        generation=1,
        principal_id="demo-visitor",
        expires_at=datetime.fromisoformat(client.headers["X-Findoc-Lease-Expires-At"]).timestamp(),
    )
    return h, client, templates, drafts, refs, identity


def run_template(rig, kind, refs, **extra):
    body = dict(
        operation_id=str(uuid4()),
        template_id=kind,
        template_version="cplus-template-v1",
        question="主要业务与主要经营风险",
        selected_sources=refs,
        **extra,
    )
    response = rig[1].post("/cplus/template-runs", json=body)
    assert response.status_code == 200, response.text
    return body, response.json()["result"]


@pytest.mark.parametrize(
    "kind,indices,expected",
    [("overview", [1], 5), ("cash", [0, 1], 10), ("peer", [1, 2], 10), ("changes", [0, 1], 10)],
)
def test_four_actual_workflows_current_period_only_and_readonly_recovery(
    rig, kind, indices, expected
):
    h, client, service, drafts, refs, identity = rig
    body, result = run_template(rig, kind, [refs[n] for n in indices])
    assert result["schema_version"] == "template-run-v1" and result["financial_authority"] is False
    assert result["provider_outcome"] == "not_requested" and result["interpretation"] is None
    assert len(result["financial_points"]) == expected
    for p in result["financial_points"]:
        year = str(p["report_year"])
        assert p["time"].get("as_of_date", p["time"].get("period_end", "")).startswith(year)
        assert p["receipt_ref"] is None
    assert all("cells" not in c for c in result["collection_refs"])
    if kind == "cash":
        assert len(result["checkup_rules"]) == 3 and len(result["changes"]) == 5
    if kind == "changes":
        assert len(result["topics"]) == 3
    if kind == "peer":
        assert len(result["peer_comparisons"]) == 5 and all(
            "points" not in p for p in result["peer_comparisons"]
        )
    with sqlite3.connect(service.store.path) as db:
        before = db.iterdump()
        before = list(before)
    op = client.get("/cplus/template-runs/operations/" + body["operation_id"])
    history = client.get("/cplus/template-runs/" + result["run_id"])
    assert op.json()["result"] == result and history.json()["current_source_status"] == "current", (
        history.text
    )
    assert client.post("/cplus/template-runs", json=body).json()["result"] == result
    with sqlite3.connect(service.store.path) as db:
        assert list(db.iterdump()) == before
    changed = {**body, "question": "不同问题"}
    assert client.post("/cplus/template-runs", json=changed).status_code == 409


def test_scope_rejections_before_reservation_and_strict_chart_body(rig):
    _, client, templates, _, refs, _ = rig
    for kind, indices in [
        ("overview", [0, 1]),
        ("cash", [1, 2]),
        ("changes", [1, 1]),
        ("peer", [0, 2]),
    ]:
        response = client.post(
            "/cplus/template-runs",
            json=dict(
                operation_id=str(uuid4()),
                template_id=kind,
                template_version="cplus-template-v1",
                question="问题",
                selected_sources=[refs[n] for n in indices],
            ),
        )
        assert response.status_code == 422, response.text
    with sqlite3.connect(templates.store.path) as db:
        assert db.execute("SELECT count(*) FROM operations").fetchone()[0] == 0
    response = client.post(
        "/cplus/report-drafts",
        json=dict(
            operation_id=str(uuid4()),
            trend_id=str(uuid4()),
            chart_kind="line",
            metric_keys=["revenue"],
            amount="999",
            x=42,
        ),
    )
    assert response.status_code == 422


def test_missing_peer_metrics_do_not_fabricate_or_abort(rig):
    # Same-year missing source generated independently from the fixture's existing second company.
    h, client, _, _, refs, _ = rig
    source = refs[1]
    company = h.companies.get(refs[2]["company_id"])
    upload = h.upload(
        pdf(company.name, 2031, empty=True),
        metadata(company.company_id, 2031),
        filename="empty.pdf",
    )
    doc = upload.json()["document_id"]
    h.processor.process(doc)
    preparer = DocumentTaskPreparer(
        document_service=h.documents, sources=h.service, workspace_id="demo"
    )
    empty = fast_ref(
        asyncio.run(preparer.prepare_many(document_ids=[doc], query="主要业务")).documents[0]
    ).model_dump()
    _, result = run_template(rig, "peer", [source, empty])
    assert len(result["financial_points"]) == 5 and len(result["missing_metrics"]) == 5
    assert len(result["peer_comparisons"]) == 5
    assert all(
        p["state"] == "incomparable" and p["differences"] == [] for p in result["peer_comparisons"]
    )


def trend(rig):
    _, _, service, _, refs, _ = rig
    statements = service.statements
    collection = asyncio.run(
        statements.collect(str(uuid4()), refs[1]["document_id"], refs[1]["source_revision"])
    )
    # Explicitly select the comparative column to prove chart copying preserves actual period.
    cell = next(
        c
        for c in collection["cells"]
        if c["metric_key"] == "revenue" and c["time"].get("period_end") == "2030-12-31"
    )
    result = asyncio.run(
        statements.trends(
            str(uuid4()),
            [dict(collection_id=collection["id"], cell_ids=[cell["cell_id"]])],
            ["revenue"],
            True,
        )
    )
    return result


def test_chart_actual_server_reload_version_one_and_receipt_drift(rig, monkeypatch):
    _, client, templates, drafts, _, _ = rig
    data = trend(rig)
    body = dict(
        operation_id=str(uuid4()), trend_id=data["id"], chart_kind="bar", metric_keys=["revenue"]
    )
    response = client.post("/cplus/report-drafts", json=body)
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert (
        result["revision"] == 1
        and result["status"] == "draft"
        and result["financial_authority"] is False
    )
    assert result["financial_points"][0]["time"]["period_end"] == "2030-12-31"
    assert result["selected_sources"][0]["report_year"] == 2031
    assert result["chart"]["record_refs"] == [
        {k: data["points"][0][k] for k in ("cell_id", "cell_revision", "payload_sha256")}
    ]
    assert (
        client.get("/cplus/report-drafts/" + result["report_id"]).json()["current_source_status"]
        == "current"
    )
    with sqlite3.connect(drafts.store.path) as db:
        before = list(db.iterdump())
    monkeypatch.setattr(
        templates.statements, "admitted", lambda db, p: "synthetic-different-receipt"
    )
    history = client.get("/cplus/report-drafts/" + result["report_id"]).json()
    assert history["current_source_status"] == "stale_or_unavailable"
    assert history["financial_points"] == result["financial_points"]
    assert (
        client.get("/cplus/report-drafts/operations/" + body["operation_id"]).json()["result"]
        == result
    )
    rejected = client.post("/cplus/report-drafts", json={**body, "operation_id": str(uuid4())})
    assert rejected.status_code == 409, rejected.text
    with sqlite3.connect(drafts.store.path) as db:
        assert list(db.execute("SELECT payload FROM snapshots")) == [
            (json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")),)
        ]
        assert len(list(db.iterdump())) >= len(before)


def test_parent_unknown_persists_child_and_never_dispatches_twice(rig, monkeypatch):
    _, client, service, _, refs, _ = rig
    calls = []

    async def fail(*args, **kwargs):
        calls.append(1)
        raise TimeoutError("synthetic lost response")

    monkeypatch.setattr(service.statements, "collect", fail)
    body = dict(
        operation_id=str(uuid4()),
        template_id="overview",
        template_version="cplus-template-v1",
        question="主要业务",
        selected_sources=[refs[1]],
    )
    first = client.post("/cplus/template-runs", json=body)
    assert first.status_code == 503
    original = client.get("/cplus/template-runs/operations/" + body["operation_id"]).json()
    assert original["state"] == "unknown" and len(original["child_operations"]) == 1
    assert original["child_operations"][0]["state"] == "unknown"
    assert client.post("/cplus/template-runs", json=body).json() == original
    assert len(calls) == 1


def test_final_commit_keeps_source_and_receipt_locks(rig):
    h, client, service, drafts, _, _ = rig
    data = trend(rig)
    outcomes = []

    def write(path, sql):
        with sqlite3.connect(path, timeout=0.03) as db:
            try:
                db.execute(sql)
                db.commit()
                outcomes.append("committed")
            except sqlite3.OperationalError:
                db.rollback()
                outcomes.append("locked")

    def check(i, f):
        for path, sql in [
            (h.db, "UPDATE companies SET name=name"),
            (
                service.statements.path,
                "INSERT INTO operations VALUES('synthetic-race','synthetic','unknown',NULL)",
            ),
        ]:
            worker = Thread(target=write, args=(path, sql))
            worker.start()
            worker.join()

    drafts.commit_check = check
    response = client.post(
        "/cplus/report-drafts",
        json=dict(
            operation_id=str(uuid4()),
            trend_id=data["id"],
            chart_kind="line",
            metric_keys=["revenue"],
        ),
    )
    assert response.status_code == 200, response.text
    assert outcomes == ["locked", "locked"]


def test_optional_explanation_is_one_guarded_call_and_unknown_never_replayed(rig, monkeypatch):
    _, client, service, _, refs, _ = rig
    calls = []

    async def fake_once(question, evidence):
        calls.append((question, len(evidence)))
        raise TimeoutError("synthetic provider response lost")

    monkeypatch.setattr(service.hybrid, "provider", fake_once)
    body = dict(
        operation_id=str(uuid4()),
        template_id="overview",
        template_version="cplus-template-v1",
        question="主要业务",
        selected_sources=[refs[1]],
        generate_explanation=True,
    )
    response = client.post("/cplus/template-runs", json=body)
    assert response.status_code == 503, response.text
    original = client.get("/cplus/template-runs/operations/" + body["operation_id"]).json()
    assert original["state"] == "unknown"
    explanation = [c for c in original["child_operations"] if c["label"] == "explanation-once"]
    assert len(explanation) == 1 and explanation[0]["state"] == "unknown"
    assert len(calls) == 1 and calls[0][1] > 0
    for _ in range(2):
        assert (
            client.get("/cplus/template-runs/operations/" + body["operation_id"]).json() == original
        )
        assert client.post("/cplus/template-runs", json=body).json() == original
    assert len(calls) == 1


def test_optional_explanation_returns_unreviewed_draft_and_no_annual_provider(rig, monkeypatch):
    _, client, service, _, refs, _ = rig
    calls = []

    async def fake_once(question, evidence):
        calls.append(question)
        return {"text": "合成解释，待审。"}

    async def forbidden(*args):
        raise AssertionError("annual provider must remain disabled")

    monkeypatch.setattr(service.hybrid, "provider", fake_once)
    monkeypatch.setattr(service.annual, "provider", forbidden)
    _, result = run_template(rig, "changes", refs[:2], generate_explanation=True)
    assert len(calls) == 1 and result["interpretation"] == "合成解释，待审。"
    assert (
        result["provider_outcome"] == "returned"
        and result["interpretation_review_status"] == "ai_unreviewed"
    )
    assert result["financial_authority"] is False


def test_source_bytes_change_marks_history_stale_without_rewriting_snapshot(rig):
    h, client, service, _, refs, _ = rig
    body, result = run_template(rig, "overview", [refs[1]])
    with sqlite3.connect(service.store.path) as db:
        before = list(db.iterdump())
    h.objects.put_bytes(h.docs.get(refs[1]["document_id"]).object_key, b"synthetic corrupt source")
    history = client.get("/cplus/template-runs/" + result["run_id"])
    assert (
        history.status_code == 200
        and history.json()["current_source_status"] == "stale_or_unavailable"
    )
    assert history.json()["financial_points"] == result["financial_points"]
    assert (
        client.get("/cplus/template-runs/operations/" + body["operation_id"]).json()["result"]
        == result
    )
    with sqlite3.connect(service.store.path) as db:
        assert list(db.iterdump()) == before


def test_wal_receipt_fence_refuses_publication_and_retains_unknown(rig):
    _, client, service, drafts, _, _ = rig
    data = trend(rig)
    with sqlite3.connect(service.statements.path) as db:
        db.execute("PRAGMA journal_mode=WAL")
    body = dict(
        operation_id=str(uuid4()), trend_id=data["id"], chart_kind="line", metric_keys=["revenue"]
    )
    response = client.post("/cplus/report-drafts", json=body)
    assert response.status_code == 503, response.text
    assert (
        client.get("/cplus/report-drafts/operations/" + body["operation_id"]).json()["state"]
        == "unknown"
    )
    with sqlite3.connect(drafts.store.path) as db:
        assert db.execute("SELECT count(*) FROM snapshots").fetchone()[0] == 0


@pytest.mark.parametrize("kind", ["template", "chart"])
def test_history_source_fallback_cannot_hide_late_identity_rejection(rig, kind):
    _, client, templates, drafts, refs, _ = rig
    if kind == "template":
        _, result = run_template(rig, "overview", [refs[1]])
        service = templates
        endpoint = "/cplus/template-runs/" + result["run_id"]
    else:
        data = trend(rig)
        response = client.post(
            "/cplus/report-drafts",
            json=dict(
                operation_id=str(uuid4()),
                trend_id=data["id"],
                chart_kind="line",
                metric_keys=["revenue"],
            ),
        )
        service = drafts
        endpoint = "/cplus/report-drafts/" + response.json()["result"]["report_id"]
    calls = []

    def validator(i):
        calls.append(1)
        return len(calls) == 1

    service.validator = validator
    assert client.get(endpoint).status_code == 403
