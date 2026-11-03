"""ee836e6 independent root assembly regressions; synthetic fixtures, provider disabled."""

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


def mounted(tmp_path, monkeypatch):
    h, doc, _, _, rev, engine, parse = fixture(tmp_path)
    run(parse.retry(doc, str(uuid4()), rev))
    quality = run(parse.quality(doc))
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

    register_cplus_runtime(
        app,
        tmp_path,
        sources=h.service,
        parse_service=parse,
        preparer=None,
        dense_scope=None,
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
    client = TestClient(app, headers=headers)

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


@pytest.mark.xfail(
    strict=True,
    reason="P1: active OCR replacement is rejected for execution but answer GET still says current",
)
def test_root_ocr_history_exposes_current_status_after_artifact_replaced(tmp_path, monkeypatch):
    h, doc, rev, parse, app, client, context, answer, memory = mounted(tmp_path, monkeypatch)
    endpoint = f"/cplus/research/answers/{answer['answer_id']}"
    assert client.get(endpoint).status_code == 200  # same owner/expiry survives HTTP recovery
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
    history = client.get(endpoint).json()
    with sqlite3.connect(app.state.cplus_retrieval_service.path) as db:
        assert db.execute("SELECT count(*) FROM operations").fetchone()[0] == before
    assert (
        history.get("historical_snapshot") is True
        and history.get("current_source_status") != "current"
    )


@pytest.mark.xfail(
    strict=True,
    reason="P1: root DocumentResearchPanel sends OCR-only page fields for fast evidence favorites",
)
def test_root_fast_favorite_payload_is_accepted(tmp_path):
    h = Harness(tmp_path).ready()
    conversations = ConversationRepository(h.registry, "demo")
    memory = ResearchMemoryService(
        runtime_root=tmp_path,
        workspace_id="demo",
        sources=h.service,
        conversations=conversations,
        embedder=lambda t: [[1.0] for x in t],
        embedding_model_version="fake",
    )
    app = FastAPI()
    app.include_router(create_research_memory_router(memory))
    client = TestClient(app)
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
    assert client.post("/research-memories", json=corrected).status_code == 200
    assert result.status_code == 200, result.text


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


@pytest.mark.xfail(
    strict=True,
    reason="P1: root guard SHARED plus legacy memory check_generation write transaction self-locks",
)
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
    with app.state.cplus_publication_guard(identity, context):
        assert (
            app.state.cplus_peer_service.memory.check_generation(context["memory_generation"])
            == context["memory_generation"]
        )
