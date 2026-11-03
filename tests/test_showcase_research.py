"""UNIT_FAKE providers, real source/SQLite and real PersistentTemplateService. No human receipts."""
import asyncio
from dataclasses import replace
import json
import time
from unittest.mock import Mock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.agent.operating_research_graph import PersistentTemplateService
from app.agent.revenue_confirmation import RevenueConfirmationService, RevenueSourceReader
from app.agent.revenue_extraction import RevenueCandidateService
from app.agent.sqlite_financial_facts import SQLiteRevenueConfirmationRepository
from app.conversations.models import CreateConversationRequest
from app.conversations.repository import ConversationRepository
from app.documents.preparation import DocumentTaskPreparer
from app.rag.retriever import SearchHit
from app.rag.selected_scope import SelectedScopeSearch
from app.research.task_repository import TaskRepository
from app.research.templates import TemplateService
from app.showcase_research.api import create_showcase_research_router
from app.showcase_research.findings import interpretation
from app.showcase_research.intent import fallback
from app.showcase_research.models import ResearchError, RuntimeIdentity
from app.showcase_research.service import ShowcaseResearchService
from tests.test_finance_v2 import assembled, synthetic_pdf


def op(**kw):
    return {"operation_id": str(uuid4()), **kw}


class FakeProvider:
    def __init__(self, malicious=False):
        self.calls, self.malicious = [], malicious
    def generate_once(self, prompt):
        self.calls.append(prompt)
        payload = json.loads(prompt.split("\n", 1)[1])
        result = payload["safe_fallback"]
        if self.malicious:
            result = {**result, "company_ids": ["unselected-company"], "actions": ["create_task"]}
        return json.dumps(result)


def environment(tmp_path, provider=None):
    h, company, document, source = assembled(tmp_path, synthetic_pdf())
    preparer = DocumentTaskPreparer(document_service=h.documents, sources=h.service, workspace_id="demo")
    conversations = ConversationRepository(h.registry, "demo")
    selection = asyncio.run(preparer.prepare_many(document_ids=[document], query="create"))
    cid, _ = conversations.create(CreateConversationRequest(**op(document_ids=[document])), selection)
    search = SelectedScopeSearch(preparer, Mock())
    candidates = RevenueCandidateService(preparer=preparer, retriever=Mock(), sources=h.service)
    facts = RevenueConfirmationService(source_reader=RevenueSourceReader(documents=h.documents, objects=h.objects,
        candidates=candidates, sources=h.service), repository=SQLiteRevenueConfirmationRepository(h.db))
    task_repository = TaskRepository(h.registry, "demo")
    templates = TemplateService(preparer=preparer, facts=facts, workspace_id="demo", scope=search)
    tasks = PersistentTemplateService(templates, task_repository)
    identity = RuntimeIdentity("isolated-test-instance", 1, time.time() + 1200, "demo", "test-visitor")
    service = ShowcaseResearchService(tmp_path, conversations=conversations, preparer=preparer, sources=h.service,
        search=search, facts=facts, task_service=tasks, task_repository=task_repository,
        llm_client=provider, local_identity=identity)
    app = FastAPI()
    app.include_router(create_showcase_research_router(service))
    return h, cid, service, TestClient(app), identity


def test_intent_15_fixed_cases_program_scope_and_no_implicit_tasks(tmp_path):
    fake = FakeProvider()
    h, cid, service, client, identity = environment(tmp_path, fake)
    cases = [
        ("测试股份有限公司2031年营业收入原文", "quick", False),
        ("比较测试股份有限公司2031和2030年营业收入", "quick", True),
        ("深度研究测试股份有限公司2031年现金流和风险", "deep", False),
        ("综合整理测试股份有限公司2031年经营风险", "synthesis", False),
        ("只要原文，测试股份有限公司2031年现金流", "quick", False),
        ("不要计算比例，整理测试股份有限公司2031年财务风险", "synthesis", False),
        ("比较测试股份有限公司2031和2030年归母净利润", "quick", True),
        ("测试股份有限公司2031年产品和主营业务", "quick", False),
        ("根据原文整理测试股份有限公司2031年报告", "synthesis", False),
        ("比较测试股份有限公司2031年总资产和总负债", "quick", True),
        ("测试股份有限公司2031年资产负债率原文", "quick", False),
        ("创建测试股份有限公司2031和2030年财务研究任务", "quick", True),
        ("深度比较测试股份有限公司2031和2030年经营现金流", "deep", True),
        ("综合总结测试股份有限公司2031年经营模式", "synthesis", False),
        ("计算测试股份有限公司2031和2030年营业收入同比", "quick", True),
    ]
    for text, mode, financial in cases:
        response = client.post("/research/intent", json=op(conversation_id=cid, text=text))
        assert response.status_code == 200, response.text
        value = response.json()
        assert (value["mode"], value["requires_confirmed_facts"]) == (mode, financial), text
        assert value["proposal_origin"] == "model_proposal_program_validated"
    assert len(fake.calls) == 15
    assert service.task_repository.page(20, None)["items"] == []
    payload = op(conversation_id=cid, text=cases[0][0])
    first = client.post("/research/intent", json=payload)
    assert client.post("/research/intent", json=payload).json() == first.json()
    assert len(fake.calls) == 16
    assert client.post("/research/intent", json={**payload, "text": "changed"}).status_code == 409
    scope = service.store.get(first.json()["intent_id"], "intent")["scope"]
    assert fallback("比较那一年现金流", {**scope, "history": [{"turn_id": str(uuid4()), "user_text": "2030年营业收入", "focus": None}]}).periods == [2030]


def test_malicious_model_fallback_unknown_charged_and_findings_numeric_axis(tmp_path):
    fake = FakeProvider(malicious=True)
    h, cid, service, client, identity = environment(tmp_path, fake)
    result = client.post("/research/intent", json=op(conversation_id=cid, text="比较2031和2030年营业收入"))
    assert result.status_code == 200
    assert result.json()["proposal_origin"] == "finite_rule_fallback"
    assert result.json()["provider_error"] == "intent_proposal_outside_frozen_scope"
    assert "unselected-company" not in result.text
    finding = interpretation("模型声称利润增长50%，尚未核实。")
    assert finding["numeric_claim_status"] == "numeric_claim_unverified" and finding["financial_refs"] == []
    assert interpretation("模型声称利润翻番，尚未核实。")["numeric_claim_status"] == "numeric_claim_unverified"
    run_id = result.json()["intent_id"]
    scope = service.store.get(run_id, "intent")["scope"]
    source = scope["sources"][0]
    records = h.service.repository.evidence_batch(source["source_revision"])
    record = next(r for r in records if r["kind"] == "paragraph" and r["physical_page"] == 2)
    hit = SearchHit(score=1, chunk_id="controlled-test-chunk", text=record["text"], page=2, source_file="source.pdf",
                    type="paragraph", workspace_id="demo", document_id=source["document_id"], source_revision=source["source_revision"])
    quote = asyncio.run(service.findings.quote(scope, hit))
    assert quote["kind"] == "sourced_excerpt" and quote["financial_refs"] == []
    assert quote["transcription_review_status"] == "fast_extraction_unreviewed"
    with pytest.raises(ResearchError, match="exact_excerpt_unverified"):
        asyncio.run(service.findings.quote(scope, replace(hit, text="An invented source quote")))
    with service.store.tx() as db:
        db.execute("UPDATE sr_budgets SET max_attempts=1 WHERE id=?", (run_id,))
    with pytest.raises(ResearchError, match="model_budget_exhausted"):
        service.store.reserve_call(run_id, "second")
    assert service.store.usage(run_id)["attempts"] == 1
    def uncertain(prompt):
        fake.calls.append(prompt)
        raise TimeoutError("fake provider unknown outcome")
    fake.generate_once = uncertain
    unknown_payload = op(conversation_id=cid, text="2031年主营业务")
    unknown = client.post("/research/intent", json=unknown_payload)
    assert unknown.status_code == 200 and unknown.json()["proposal_origin"] == "finite_rule_fallback"
    assert service.store.usage(unknown.json()["intent_id"])["unknown_attempts"] == 1
    call_count = len(fake.calls)
    assert client.post("/research/intent", json=unknown_payload).json() == unknown.json()
    assert len(fake.calls) == call_count  # UNKNOWN is not refunded or replayed.
    service.local_identity = None
    assert client.post("/research/intent", json=op(conversation_id=cid, text="业务"), headers={
        "X-Findoc-Generation": "1", "X-Findoc-Instance": "forged", "X-Findoc-Lease-Expires-At": "2099-01-01T00:00:00+00:00"}).status_code == 403
    service.local_identity = replace(identity, lease_expires_at=time.time() - 1)
    assert client.get("/research/intents/" + run_id).status_code == 401


def test_explicit_handoff_real_legacy_task_once_no_accept_save_resume(tmp_path):
    _, cid, service, client, identity = environment(tmp_path)
    intent = client.post("/research/intent", json=op(conversation_id=cid, text="创建2031和2030年财务研究任务，比较营业收入")).json()
    body = op(conversation_id=cid, intent_id=intent["intent_id"], confirmed=True)
    assert client.post("/research/handoffs", json={**body, "confirmed": False}).status_code == 422
    first = client.post("/research/handoffs", json=body)
    assert first.status_code == 200, first.text
    assert first.json()["automatic_confirmation"] is False and first.json()["automatic_resume"] is False
    assert first.json()["task_status"] == "awaiting_human_confirmation", first.text
    assert client.post("/research/handoffs", json=body).json() == first.json()
    assert client.post("/research/handoffs", json=op(conversation_id=cid, intent_id=intent["intent_id"], confirmed=True)).status_code == 409
    assert len(service.task_repository.page(20, None)["items"]) == 1
    assert len(client.get(f"/research/conversations/{cid}/links").json()["items"]) == 1
