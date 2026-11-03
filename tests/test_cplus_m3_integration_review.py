"""b2b73d5 independent root assembly verification; disposable SQLite, provider disabled."""

from datetime import UTC, datetime, timedelta
import sqlite3
from threading import Thread
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.cplus.runtime import register_cplus_runtime
from app.conversations.repository import ConversationRepository
from app.research_memory import ResearchMemoryService, create_research_memory_router
from tests.test_document_sources import Harness
from tests.test_parse_v2 import fixture, run


def root_app(h, parse, tmp_path, monkeypatch, preparer=None):
    conversations = ConversationRepository(h.registry, "demo")
    memory = ResearchMemoryService(
        runtime_root=tmp_path,
        workspace_id="demo",
        sources=h.service,
        conversations=conversations,
        embedder=lambda texts: [[1.0] for t in texts],
        embedding_model_version="fake",
        parse_service=parse,
    )
    monkeypatch.setenv("DEMO_INTERNAL_INSTANCE", "review-instance")
    app = FastAPI()

    @app.middleware("http")
    async def private_test_marker(request, call_next):
        request.scope["findoc_private_identity"] = (
            request.headers.get("X-Findoc-Generation"),
            request.headers.get("X-Findoc-Instance"),
        )
        return await call_next(request)

    async def empty_dense(selection, *, top_k):
        return []  # Deliberately fake retrieval adapter; never load embeddings or Milvus.

    register_cplus_runtime(
        app,
        tmp_path,
        sources=h.service,
        parse_service=parse,
        preparer=preparer,
        dense_scope=SimpleNamespace(search=empty_dense),
        memory=memory,
        conversations=conversations,
        workspace="demo",
        llm_client=SimpleNamespace(model="disabled-no-calls", client=SimpleNamespace()),
        owner_authorizer=None,
        generation=1,
    )
    headers = {
        "X-Findoc-Generation": "1",
        "X-Findoc-Instance": "review-instance",
        "X-Findoc-Lease-Expires-At": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
    }
    app.include_router(create_research_memory_router(memory))
    client = TestClient(app, headers=headers)
    return app, client, memory


def mounted(tmp_path, monkeypatch):
    h, doc, _, _, rev, engine, parse = fixture(tmp_path)
    run(parse.retry(doc, str(uuid4()), rev))
    quality = run(parse.quality(doc))
    app, client, memory = root_app(h, parse, tmp_path, monkeypatch)

    def post(path, body):
        r = client.post(path, json={"operation_id": str(uuid4()), **body})
        assert r.status_code == 200, r.text
        return r.json()["result"]

    enrolled = post(
        "/cplus/research/enrollments",
        dict(
            document_id=doc,
            artifact_id=quality["artifact_id"],
            expected_source_revision=rev,
            expected_artifact_sha256=quality["output_sha256"],
            selected_pages=[1],
            confirmed=True,
        ),
    )
    post("/cplus/retrieval/builds", {"sources": [enrolled["source_ref"]]})
    context = post(
        "/cplus/research/contexts",
        {"title": "review OCR", "selected_sources": [enrolled["source_ref"]]},
    )
    answer = post(
        "/cplus/research/answers",
        dict(
            context_id=context["context_id"],
            context_revision=1,
            context_sha256=context["context_sha256"],
            question="营业收入候选未核对",
        ),
    )
    assert answer["state"] == "provider_unconfigured" and answer["findings"]
    return h, doc, rev, parse, app, client, context, answer, memory


def test_root_ocr_history_exposes_current_status_after_artifact_replaced(tmp_path, monkeypatch):
    h, doc, rev, parse, app, client, context, answer, memory = mounted(tmp_path, monkeypatch)
    endpoint = f"/cplus/research/answers/{answer['answer_id']}"
    current = client.get(endpoint)
    assert current.status_code == 200  # same owner/expiry survives HTTP recovery
    assert current.json()["current_source_status"] == "current"
    expired = {
        **dict(client.headers),
        "x-findoc-lease-expires-at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
    }
    assert client.get(endpoint, headers=expired).status_code == 403
    run(parse.retry(doc, str(uuid4()), rev))
    assert run(parse.quality(doc))["artifact_id"] != context["selected_sources"][0]["artifact_id"]
    rejected = client.post(
        "/cplus/research/answers",
        json=dict(
            operation_id=str(uuid4()),
            context_id=context["context_id"],
            context_revision=1,
            context_sha256=context["context_sha256"],
            question="营业收入候选未核对",
        ),
    )
    assert rejected.status_code == 409 and rejected.json()["detail"]["code"] == "artifact_changed"
    with sqlite3.connect(app.state.cplus_retrieval_service.path) as db:
        before = db.execute("SELECT count(*) FROM operations").fetchone()[0]
        stored_before = db.execute("SELECT * FROM objects").fetchall()
    context_history = client.get(f"/cplus/research/contexts/{context['context_id']}")
    assert context_history.status_code == 200
    assert context_history.json()["current_source_status"] == "stale_or_unavailable"
    assert context_history.json()["historical_snapshot"] is True
    history = client.get(endpoint).json()
    with sqlite3.connect(app.state.cplus_retrieval_service.path) as db:
        assert db.execute("SELECT count(*) FROM operations").fetchone()[0] == before
        assert db.execute("SELECT * FROM objects").fetchall() == stored_before
    assert (
        history.get("historical_snapshot") is True
        and history.get("current_source_status") == "stale_or_unavailable"
    )


def test_root_fast_favorite_payload_is_accepted(tmp_path, monkeypatch):
    h = Harness(tmp_path).ready()
    app, client, memory = root_app(h, None, tmp_path, monkeypatch)
    body = dict(
        operation_id=str(uuid4()),
        type="saved_evidence",
        confirmed=True,
        company_id=h.company.company_id,
        document_id=h.id,
        source_revision=h.rev,
        evidence_id=h.source["evidence_ids"][0],
        artifact_id=None,
        physical_page=1,
        source_line_index=None,
        text=None,
    )
    result = client.post("/research-memories", json=body)
    corrected = {**body, "operation_id": str(uuid4()), "physical_page": None}
    accepted = client.post("/research-memories", json=corrected)
    assert accepted.status_code == 200, accepted.text
    assert (
        client.get(f"/research-memories/operations/{corrected['operation_id']}").status_code == 200
    )
    assert result.status_code == 422  # Historical malformed UI shape remains rejected.


def test_root_guard_holds_source_artifact_memory_locks_through_inner_commit(tmp_path, monkeypatch):
    h, doc, rev, parse, app, client, context, answer, memory = mounted(tmp_path, monkeypatch)
    hybrid = app.state.cplus_retrieval_service
    from app.retrieval_v2 import TrustedIdentity

    identity = TrustedIdentity(
        workspace_id="demo",
        instance_id="review-instance",
        generation=1,
        principal_id="demo-visitor",
        expires_at=float((datetime.now(UTC) + timedelta(minutes=3)).timestamp()),
    )
    outcomes = []

    def try_write(path, sql, args):
        with sqlite3.connect(path, timeout=0.03) as writer:
            try:
                writer.execute(sql, args)
                writer.commit()
                outcomes.append("COMMITTED")
            except sqlite3.OperationalError:
                writer.rollback()
                outcomes.append("locked")

    def before_commit():
        for path, sql, args in [
            (
                tmp_path / "documents.db",
                "UPDATE companies SET name=name WHERE company_id=?",
                (h.company.company_id,),
            ),
            (parse.path, "UPDATE active SET artifact_id=artifact_id WHERE document_id=?", (doc,)),
            (memory.path, "UPDATE generation SET value=value+1 WHERE workspace=?", ("demo",)),
        ]:
            thread = Thread(target=try_write, args=(path, sql, args))
            thread.start()
            thread.join(2)
            assert not thread.is_alive()

    with app.state.cplus_publication_guard(identity, context):
        with hybrid.tx(before_commit=before_commit) as db:
            db.execute("SELECT count(*) FROM objects").fetchone()
    assert outcomes == ["locked"] * 3
    # Root evidence handler delegates the complete quoted text to the real verifier.
    from copy import deepcopy

    read = hybrid.read

    def tampered(kind, identifier, owner):
        value = deepcopy(read(kind, identifier, owner))
        if kind == "answer":
            value["findings"][0]["evidence_ref"]["text"] += "不存在的引文尾部"
        return value

    monkeypatch.setattr(hybrid, "read", tampered)
    eid = answer["findings"][0]["evidence_ref"]["evidence_id"]
    response = client.get(f"/cplus/research/answers/{answer['answer_id']}/evidence/{eid}/location")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "exact_evidence_unverified"


def test_root_peer_nested_memory_generation_check_is_read_only(tmp_path, monkeypatch):
    h, doc, rev, parse, app, client, context, answer, memory = mounted(tmp_path, monkeypatch)
    from app.retrieval_v2 import TrustedIdentity

    identity = TrustedIdentity(
        workspace_id="demo",
        instance_id="review-instance",
        generation=1,
        principal_id="demo-visitor",
        expires_at=float((datetime.now(UTC) + timedelta(minutes=3)).timestamp()),
    )
    connect = sqlite3.connect

    def short_connect(*args, **kwargs):
        kwargs["timeout"] = 0.03
        return connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", short_connect)
    traced = []

    def traced_connect(*args, **kwargs):
        db = short_connect(*args, **kwargs)
        db.set_trace_callback(traced.append)
        return db

    monkeypatch.setattr(sqlite3, "connect", traced_connect)
    with app.state.cplus_publication_guard(identity, context):
        for service in (app.state.cplus_peer_service, app.state.cplus_checkup_explanation_service):
            assert (
                service.memory.check_generation(context["memory_generation"])
                == context["memory_generation"]
            )
    assert not any("BEGIN IMMEDIATE" in sql.upper() for sql in traced)
    assert sum(sql.upper() == "ROLLBACK" for sql in traced) >= 2
    with connect(memory.path) as db:
        db.execute("UPDATE generation SET value=value+1 WHERE workspace='demo'")
    from app.research_memory.service import MemoryError

    with pytest.raises(MemoryError, match="memory_context_changed"):
        app.state.cplus_peer_service.memory.check_generation(context["memory_generation"])


def test_root_financial_focus_http_preserves_comparative_period_and_rejects_changes(
    tmp_path, monkeypatch
):
    from copy import deepcopy
    from app.documents.preparation import DocumentTaskPreparer
    from tests.test_finance_v2 import assembled, synthetic_pdf

    h, company, doc, source = assembled(tmp_path, synthetic_pdf())
    preparer = DocumentTaskPreparer(
        document_service=h.service.documents, sources=h.service, workspace_id="demo"
    )
    app, client, memory = root_app(h, None, tmp_path, monkeypatch, preparer)
    statements = app.state.cplus_statement_service
    collection = run(statements.collect(str(uuid4()), doc, source["source_revision"]))
    cell = next(c for c in collection["cells"] if c["time"].get("as_of_date") == "2030-12-31")
    endpoint = f"/cplus/financial/cells/{cell['cell_id']}/research-focus"
    response = client.get(
        endpoint,
        params={"revision": cell["cell_revision"], "payload_sha256": cell["payload_sha256"]},
    )
    assert response.status_code == 200, response.text
    focus = response.json()
    assert focus["cell_id"] == cell["cell_id"] and focus["time"] == cell["time"]
    assert focus["source_ref"]["report_year"] == 2031
    assert focus["source_ref"]["document_id"] == doc
    assert focus["financial_authority"] is False
    body = dict(
        title="2031年报中的2030比较期",
        selected_sources=[deepcopy(focus["source_ref"])],
        financial_focus=focus,
    )
    response = client.post("/cplus/research/contexts", json=dict(operation_id=str(uuid4()), **body))
    assert response.status_code == 200, response.text
    context = response.json()["result"]
    assert context["financial_focus"] == focus
    question = "请核查2030-12-31的总资产比较数据。"
    response = client.post(
        "/cplus/research/answers",
        json=dict(
            operation_id=str(uuid4()),
            context_id=context["context_id"],
            context_revision=context["revision"],
            context_sha256=context["context_sha256"],
            question=question,
        ),
    )
    assert response.status_code == 200, response.text
    answer = response.json()["result"]
    assert answer["financial_focus"] == focus and answer["question"] == question
    assert answer["financial_authority"] is False
    for field in ("time", "source_ref"):
        changed = deepcopy(body)
        if field == "time":
            changed["financial_focus"]["time"]["as_of_date"] = "2031-12-31"
        else:
            changed["financial_focus"]["source_ref"]["document_id"] = "unselected-document"
        response = client.post(
            "/cplus/research/contexts", json=dict(operation_id=str(uuid4()), **changed)
        )
        assert response.status_code == 409, response.text
        expected = "focus_cell_changed" if field == "time" else "focus_source_changed"
        assert response.json()["detail"]["code"] == expected


def test_root_peer_and_checkup_http_complete_with_real_sqlite_memory_fences(tmp_path, monkeypatch):
    from app.companies.models import CompanyCreate
    from app.documents.preparation import DocumentTaskPreparer
    from app.retrieval_v2.service import sha
    from tests.test_document_sources import metadata
    from tests.test_finance_v2 import assembled, synthetic_pdf
    import pymupdf

    h, company, doc, source = assembled(tmp_path, synthetic_pdf())
    other = h.companies.create(
        CompanyCreate(name="测试股份有限公司", security_code="REVIEW2", exchange="DEMO")
    )
    with pymupdf.open(stream=synthetic_pdf(), filetype="pdf") as pdf:
        pdf.set_metadata({"title": "second disposable review company"})
        second_bytes = pdf.tobytes()
    response = h.upload(second_bytes, metadata(other.company_id, 2031), filename="second.pdf")
    assert response.status_code == 202, response.text
    second = response.json()["document_id"]
    h.processor.process(second)
    second_source = h.client.get(f"/documents/{second}/source").json()
    preparer = DocumentTaskPreparer(
        document_service=h.service.documents, sources=h.service, workspace_id="demo"
    )
    app, client, memory = root_app(h, None, tmp_path, monkeypatch, preparer)
    statements = app.state.cplus_statement_service
    collections = [
        run(statements.collect(str(uuid4()), d, rev))
        for d, rev in ((doc, source["source_revision"]), (second, second_source["source_revision"]))
    ]
    refs = [
        {
            "collection_id": c["id"],
            "cell_ids": [
                next(
                    cell["cell_id"]
                    for cell in c["cells"]
                    if cell["metric_key"] == "total_assets"
                    and cell["time"].get("as_of_date") == "2030-12-31"
                )
            ],
        }
        for c in collections
    ]
    response = client.post(
        "/cplus/peer-comparisons",
        json=dict(
            operation_id=str(uuid4()),
            company_ids=[company, other.company_id],
            collection_refs=refs,
            candidate_view=True,
        ),
    )
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "completed"
    checkup_refs = [
        {
            "collection_id": collections[0]["id"],
            "cell_ids": [c["cell_id"] for c in collections[0]["cells"]],
        }
    ]
    response = client.post(
        "/cplus/checkups",
        json=dict(
            operation_id=str(uuid4()),
            collection_refs=checkup_refs,
            candidate_view=True,
            generate_explanation=False,
        ),
    )
    assert response.status_code == 200, response.text
    checkup = response.json()
    assert any(r["status"] == "candidate_observation" for r in checkup["rules"])
    response = client.post(
        "/cplus/checkup-explanations",
        json=dict(
            operation_id=str(uuid4()),
            checkup_id=checkup["id"],
            expected_payload_sha256=sha(checkup),
            confirmed=True,
        ),
    )
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "completed"
    assert response.json()["result"]["provider_outcome"] == "unconfigured"
    assert response.json()["result"]["financial_authority"] is False
