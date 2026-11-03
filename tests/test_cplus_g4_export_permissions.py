"""Independent root wiring: temporary PDFs/SQLite, no models or human approvals."""

import asyncio
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
from threading import Thread
from types import SimpleNamespace
import sqlite3
import time
from uuid import uuid4

import pytest
from app.companies.models import CompanyCreate
from app.documents.preparation import DocumentTaskPreparer
from app.cplus.runtime import fast_ref
from app.exports_v2.projection import digest
from app.retrieval_v2 import TrustedIdentity
from app.retrieval_v2.models import RetrievalError
from tests.test_document_sources import Harness, metadata
from tests.test_cplus_g4_templates_drafts import pdf
from tests.test_cplus_m3_integration_review import root_app


@pytest.fixture
def rig(tmp_path, monkeypatch):
    h = Harness(tmp_path)
    company = h.companies.create(
        CompanyCreate(name="审查股份有限公司", security_code="600001", exchange="SSE")
    )
    docs = []
    for year in (2030, 2031):
        uploaded = h.upload(
            pdf(company.name, year), metadata(company.company_id, year), filename=f"{year}.pdf"
        )
        doc = uploaded.json()["document_id"]
        h.processor.process(doc)
        docs.append(doc)
    prep = DocumentTaskPreparer(
        document_service=h.documents, sources=h.service, workspace_id="demo"
    )
    app, client, _ = root_app(
        h, None, tmp_path, monkeypatch, prep
    )  # Only the production root registers G4.
    refs = [
        fast_ref(
            asyncio.run(prep.prepare_many(document_ids=[doc], query="经营风险")).documents[0]
        ).model_dump()
        for doc in docs
    ]
    legacy = tmp_path / "empty-legacy-reports.db"
    with sqlite3.connect(legacy) as db:
        db.executescript(
            "CREATE TABLE reports(id TEXT,workspace TEXT);CREATE TABLE revisions(report_id TEXT,revision INTEGER,payload TEXT);"
        )
    app.state.showcase_report_service = SimpleNamespace(
        path=legacy
    )  # Empty unrelated legacy listing only.
    i = TrustedIdentity(
        workspace_id="demo",
        instance_id="review-instance",
        generation=1,
        principal_id="demo-visitor",
        expires_at=datetime.fromisoformat(client.headers["X-Findoc-Lease-Expires-At"]).timestamp(),
    )
    response = client.post(
        "/cplus/template-runs",
        json=dict(
            operation_id=str(uuid4()),
            template_id="cash",
            template_version="cplus-template-v1",
            question="现金流与利润原文",
            selected_sources=refs,
            generate_explanation=False,
        ),
    )
    assert response.status_code == 200, response.text
    template = response.json()["result"]
    statements = app.state.cplus_statement_service
    trend = asyncio.run(
        statements.trends(str(uuid4()), template["collection_refs"], ["revenue"], True)
    )
    response = client.post(
        "/cplus/report-drafts",
        json=dict(
            operation_id=str(uuid4()),
            trend_id=trend["id"],
            chart_kind="line",
            metric_keys=["revenue"],
        ),
    )
    assert response.status_code == 200, response.text
    chart = response.json()["result"]
    return app, client, i, statements, {"template_run_v1": template, "chart_report_v1": chart}


def ref_for(domain, snapshot):
    return dict(
        domain=domain,
        id=snapshot.get("run_id", snapshot.get("report_id")),
        revision=1,
        payload_sha256=digest(snapshot),
    )


def resolve(service, ref, identity):
    return asyncio.run(
        service.resolver(ref["domain"], ref["id"], ref["revision"], ref["payload_sha256"], identity)
    )


@pytest.mark.parametrize("domain", ["template_run_v1", "chart_report_v1"])
def test_single_registry_exact_identity_and_stale_boundaries(rig, monkeypatch, domain):
    app, client, i, s, snapshots = rig
    service = app.state.cplus_export_service
    ref = ref_for(domain, snapshots[domain])
    listing = client.get("/cplus/export-snapshots")
    assert listing.status_code == 200, listing.text
    matches = [x for x in listing.json()["items"] if x["report_ref"] == ref]
    assert len(matches) == 1 and matches[0]["display_status"] == "current"
    assert resolve(service, ref, i)["snapshot"] == snapshots[domain]
    for changed in (
        {**ref, "revision": 2},
        {**ref, "payload_sha256": "0" * 64},
        {**ref, "domain": "chart_report_v1" if domain == "template_run_v1" else "template_run_v1"},
    ):
        with pytest.raises(RetrievalError):
            resolve(service, changed, i)
    for changed in (
        i.model_copy(update={"generation": 2}),
        i.model_copy(update={"expires_at": time.time() - 1}),
        i.model_copy(update={"expires_at": i.expires_at + 10}),
    ):
        with pytest.raises(RetrievalError):
            resolve(service, ref, changed)
    original = s.admitted
    monkeypatch.setattr(s, "admitted", lambda db, cell: "fixture-changed-receipt")
    assert resolve(service, ref, i)["display_status"] == "stale"
    with pytest.raises(RetrievalError):
        resolve(service, ref, i.model_copy(update={"generation": 2}))
    monkeypatch.setattr(s, "admitted", original)
    selected = s.selected

    async def changed_cells(refs):
        collections, contexts = await selected(refs)
        collections = deepcopy(collections)
        collections[0]["cells"][0]["normalized_decimal"] = "999.123"
        return collections, contexts

    monkeypatch.setattr(s, "selected", changed_cells)
    result = resolve(service, ref, i)
    assert result["display_status"] == "stale" and result["snapshot"] == snapshots[domain]


@pytest.mark.parametrize("domain", ["template_run_v1", "chart_report_v1"])
def test_current_export_holds_source_and_receipt_locks_through_commit(rig, domain):
    app, _, i, s, snapshots = rig
    service = app.state.cplus_export_service
    ref = ref_for(domain, snapshots[domain])
    resolved = resolve(service, ref, i)
    outcomes = []

    def writer(path, sql):
        with sqlite3.connect(path, timeout=0.05) as db:
            try:
                db.execute(sql)
                db.commit()
                outcomes.append("WRONG committed")
            except sqlite3.OperationalError:
                db.rollback()
                outcomes.append("blocked")

    with service.guard(i, resolved):
        with service.tx(i) as db:
            db.execute(
                "INSERT INTO ops VALUES(?,?,'fixture','unknown',NULL)",
                (str(uuid4()), service.check(i)),
            )
        # Inner export COMMIT has completed; outer source/receipt guard must still hold.
        for path, sql in (
            (s.root / "documents.db", "UPDATE companies SET name=name"),
            (s.path, "UPDATE operations SET state=state"),
        ):
            t = Thread(target=writer, args=(path, sql))
            t.start()
            t.join(2)
            assert not t.is_alive()
    assert outcomes == ["blocked", "blocked"]


@pytest.mark.parametrize("domain", ["template_run_v1", "chart_report_v1"])
def test_download_reresolves_original_domain_and_keeps_bytes(rig, monkeypatch, domain):
    app, client, i, s, snapshots = rig
    ref = ref_for(domain, snapshots[domain])
    response = client.post(
        "/cplus/exports",
        json=dict(
            operation_id=str(uuid4()),
            report_ref=ref,
            formats=["csv"],
            export_profile_version="research-v1",
        ),
    )
    assert response.status_code == 200, response.text
    href = response.json()["result"]["files"][0]["href"]
    first = client.get(href)
    assert first.status_code == 200
    monkeypatch.setattr(s, "admitted", lambda db, cell: "changed-receipt")
    historical = client.get(href)
    assert (
        historical.status_code == 200
        and historical.content == first.content
        and historical.headers["etag"] == first.headers["etag"]
    )
    name = "cplus_template_service" if domain == "template_run_v1" else "cplus_chart_report_service"
    leaf = getattr(app.state, name)
    setattr(app.state, name, None)
    denied = client.get(href)
    assert (
        denied.status_code == 403 and denied.json()["detail"]["code"] == "display_permission_denied"
    )
    setattr(app.state, name, leaf)
    assert client.get(href).content == first.content


@pytest.mark.parametrize("domain", ["template_run_v1", "chart_report_v1"])
def test_expiry_inside_export_insert_rolls_back(rig, domain):
    app, _, i, _, snapshots = rig
    service = app.state.cplus_export_service
    original = service.tx

    @contextmanager
    def delayed(identity=None):
        with original(identity) as db:
            db.create_function(
                "expire_review",
                0,
                lambda: object.__setattr__(i, "expires_at", time.time() - 1) or 0,
            )
            yield db

    with original() as db:
        db.execute(
            "CREATE TRIGGER review_expire AFTER INSERT ON files BEGIN SELECT expire_review();END"
        )
    service.tx = delayed
    body = dict(
        operation_id=str(uuid4()),
        report_ref=ref_for(domain, snapshots[domain]),
        formats=["csv"],
        export_profile_version="research-v1",
    )
    with pytest.raises(RetrievalError):
        asyncio.run(service.create(body, i))
    with sqlite3.connect(service.path) as db:
        assert db.execute("SELECT count(*) FROM files").fetchone()[0] == 0
        assert (
            db.execute("SELECT state FROM ops WHERE id=?", (body["operation_id"],)).fetchone()[0]
            == "unknown"
        )
