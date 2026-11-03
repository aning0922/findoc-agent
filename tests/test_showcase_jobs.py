"""UNIT_FAKE native-function provider; real source verification/SQLite, no paid model or signatures."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import sqlite3
import time
from uuid import uuid4

import pytest

from app.rag.openai_compatible_llm import ModelCompletion
from app.rag.retriever import SearchHit
from app.showcase_research.models import IntentRequest, JobRequest, PlanRequest, ResearchError
from tests.test_showcase_research import FakeProvider, environment, op


class NativeFake(FakeProvider):
    def __init__(self):
        super().__init__()
        self.role_calls = []
        self.before_merge = None

    def generate_once(self, prompt):
        if prompt.startswith("KIND=merge"):
            self.calls.append(prompt)
            payload = json.loads(prompt.split("\n", 1)[1])
            if self.before_merge:
                self.before_merge()
            refs = [item["reference_id"] for item in payload["verified_findings"] if item["kind"] == "sourced_excerpt"][:1]
            return json.dumps({"interpretations": [{"text": "FAKE汇合解释草稿，仍需核对语义。", "evidence_ids": refs}]})
        return super().generate_once(prompt)

    def complete(self, messages, tools):
        prompt = messages[0]["content"]
        role, payload = prompt.split("\n", 1)
        role = role.removeprefix("ROLE=")
        payload = json.loads(payload)
        self.role_calls.append(role)
        allowed = {tool["function"]["name"] for tool in tools}
        assert not any("confirm" in name and name != "read_confirmed_facts" for name in allowed)
        used = {item["name"] for item in payload["tools_used"]}
        tool = "read_confirmed_facts" if role == "finance" and not used else "search_evidence" if not used else None
        if role == "generalist" and "比较" in payload["goal"] and "read_confirmed_facts" not in used and used:
            tool = "read_confirmed_facts"
        if tool:
            assert tool in allowed
            arguments = {"query": payload["goal"]} if tool == "search_evidence" else {}
            return ModelCompletion(message={"role": "assistant", "content": None, "tool_calls": [{"id": str(uuid4()), "type": "function",
                "function": {"name": tool, "arguments": json.dumps(arguments)}}]}, finish_reason="tool_calls")
        refs = [item["reference_id"] for call in payload["tools_used"] for item in call["result"] if item["kind"] == "sourced_excerpt"][:1]
        return ModelCompletion(message={"role": "assistant", "content": json.dumps({"interpretations": [{"text": role + " FAKE角色解释草稿", "evidence_ids": refs}]})}, finish_reason="stop")


def install_search(h, service):
    class FakeVectorSearch:
        calls = []
        async def search(self, selection, *, top_k=3):
            self.calls.append(selection.query)
            await service.preparer.revalidate(selection)
            source = selection.documents[0]
            record = next(r for r in h.service.repository.evidence_batch(source.source_revision) if r["kind"] == "paragraph" and r["physical_page"] == 2)
            return (SearchHit(score=1, chunk_id="fake-vector-chunk", text=record["text"], page=2, source_file="source.pdf",
                type="paragraph", workspace_id="demo", document_id=source.document_id, source_revision=source.source_revision),)
    service.search = FakeVectorSearch()


async def create(service, cid, identity, *, mode, text):
    intent = await service.intent(IntentRequest(**op(conversation_id=cid, text=text, requested_mode=mode)), identity)
    plan = await service.plan(PlanRequest(**op(intent_id=intent["intent_id"])), identity)
    request = JobRequest(**op(approved_plan_id=plan["plan_id"], approved_plan_revision=plan["revision"],
                             approved_plan_sha256=plan["plan_sha256"], confirmed=True))
    job = await service.create_job(request, identity, mode)
    await asyncio.gather(*list(service.pending_jobs))
    return intent, plan, request, service.job(job["job_id"], identity)


def test_single_vs_dynamic_two_native_agents_persist_and_read_only_report(tmp_path):
    fake = NativeFake()
    h, cid, service, client, identity = environment(tmp_path, fake)
    install_search(h, service)
    async def run():
        question = "整理2031年经营风险原文"
        _, single_plan, _, single = await create(service, cid, identity, mode="synthesis", text=question)
        _, deep_plan, request, deep = await create(service, cid, identity, mode="deep", text=question)
        assert single["state"] == deep["state"] == "completed", (single, deep)
        assert single_plan["roles"] == ["generalist"]
        assert deep_plan["roles"] == ["evidence", "risk_operations"]
        assert single["usage"]["attempts"] == 4 and deep["usage"]["attempts"] == 7
        assert {step["agent_id"] for step in deep["steps"]} == {"evidence", "risk_operations"}
        assert deep["usage"]["tools"] == 2 and len(service.store.events(deep["job_id"])) >= 3
        count = len(fake.calls) + len(fake.role_calls)
        assert (await service.create_job(request, identity, "deep"))["job_id"] == deep["job_id"]
        for _ in range(3):
            service.job(deep["job_id"], identity)
            service.jobs(identity, conversation_id=cid)
            service.store.events(deep["job_id"])
        verified = await service.verified_job(deep["job_id"], identity)
        assert verified["data_origin"] == "fake" and verified["state"] == "completed"
        assert all(f["kind"] != "confirmed_financial" for f in verified["findings"])
        assert len(fake.calls) + len(fake.role_calls) == count
        _, financial_plan, _, financial = await create(service, cid, identity, mode="deep", text="比较2031和2030年营业收入")
        assert financial_plan["roles"] == ["evidence", "finance"]
        assert financial["state"] == "completed"
        assert any(f["kind"] == "unresolved_question" for f in financial["result"]["findings"])
        assert all(f["kind"] != "confirmed_financial" for f in financial["result"]["findings"])
        await service.close()
    asyncio.run(run())


class MemoryProtocolFake:
    """SQLite SHARED publication guard implementing the injected public protocol only."""
    def __init__(self, root):
        self.path = root / "test-memory.db"
        self.generation, self.guard_entered = 0, False
        self.blocked_writer = None
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE generation(value INTEGER NOT NULL)")
            db.execute("INSERT INTO generation VALUES (0)")
    async def recall_snapshot(self, q, company_id=None):
        return {"memory_generation": self.generation, "items": []}
    def check_generation(self, expected):
        if expected != self.generation:
            raise ResearchError("memory_context_changed")
    @contextmanager
    def publication_guard(self, expected, revisions=None):
        self.check_generation(expected)
        db = sqlite3.connect(self.path)
        db.execute("BEGIN")
        if db.execute("SELECT value FROM generation").fetchone()[0] != expected:
            db.close()
            raise ResearchError("memory_context_changed")
        self.guard_entered = True
        try:
            yield
        finally:
            self.guard_entered = False
            db.rollback()
            db.close()


def test_memory_change_during_merge_discards_and_publication_guard_contains_job_commit(tmp_path):
    fake = NativeFake()
    h, cid, service, client, identity = environment(tmp_path, fake)
    install_search(h, service)
    memory = MemoryProtocolFake(tmp_path)
    service.scopes.memory = memory
    async def run():
        fake.before_merge = lambda: setattr(memory, "generation", 1)
        _, _, _, changed = await create(service, cid, identity, mode="deep", text="整理2031年经营风险原文")
        assert changed["state"] == "interrupted" and changed["result"] is None
        assert changed["error_code"] == "memory_context_changed"
        with sqlite3.connect(memory.path) as db:
            db.execute("UPDATE generation SET value=1")
        fake.before_merge = None
        original_tx = service.store.tx
        checks = []
        @contextmanager
        def instrumented_tx(**kwargs):
            with original_tx(**kwargs) as db:
                yield db
                if kwargs.get("attachments"):
                    checks.append(memory.guard_entered)
            if kwargs.get("attachments"):
                checks.append(memory.guard_entered)  # actual commit already finished, guard is still held.
        service.store.tx = instrumented_tx
        _, _, _, complete = await create(service, cid, identity, mode="deep", text="整理2031年主营业务原文")
        assert complete["state"] == "completed", complete
        assert checks and all(checks)
        await service.close()
    asyncio.run(run())


def test_budget_last_reservation_race_and_plan_hash_no_implicit_replay(tmp_path):
    fake = NativeFake()
    h, cid, service, client, identity = environment(tmp_path, fake)
    install_search(h, service)
    run_id = str(uuid4())
    service.store.create_budget(run_id, time.time() + 30, max_attempts=1)
    def reserve():
        try:
            return service.store.reserve_call(run_id, "race")
        except ResearchError as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: reserve(), range(2)))
    assert outcomes.count("model_budget_exhausted") == 1
    assert service.store.usage(run_id)["attempts"] == 1 and service.store.usage(run_id)["unknown_attempts"] == 1
    async def run():
        intent = await service.intent(IntentRequest(**op(conversation_id=cid, text="2031年主营业务", requested_mode="deep")), identity)
        plan = await service.plan(PlanRequest(**op(intent_id=intent["intent_id"])), identity)
        bad = JobRequest(**op(approved_plan_id=plan["plan_id"], approved_plan_revision=1, approved_plan_sha256="a" * 64, confirmed=True))
        with pytest.raises(ResearchError, match="approved_plan_mismatch"):
            await service.create_job(bad, identity, "deep")
        assert service.jobs(identity)["items"] == []
        assert not fake.role_calls
        await service.close()
    asyncio.run(run())

    with client:
        intent_response = client.post("/research/intent", json=op(conversation_id=cid, text="深度整理2031年经营风险", requested_mode="synthesis"))
        assert intent_response.status_code == 200 and intent_response.json()["mode"] == "synthesis"
        plan_response = client.post("/synthesis/plans", json=op(intent_id=intent_response.json()["intent_id"]))
        assert plan_response.status_code == 200, plan_response.text
        plan_value = plan_response.json()
        created = client.post("/synthesis/jobs", json=op(approved_plan_id=plan_value["plan_id"], approved_plan_revision=1,
            approved_plan_sha256=plan_value["plan_sha256"], confirmed=True))
        assert created.status_code == 202, created.text
        job_id = created.json()["job_id"]
        for _ in range(100):
            status = client.get("/synthesis/jobs/" + job_id)
            if status.json()["state"] not in ("queued", "running"):
                break
            time.sleep(0.01)
        assert status.json()["state"] == "completed", status.text
        count = len(fake.calls) + len(fake.role_calls)
        events = client.get(f"/synthesis/jobs/{job_id}/events?after_seq=0")
        assert events.status_code == 200 and len(events.json()["events"]) >= 3
        sse = client.get(f"/synthesis/jobs/{job_id}/events?after_seq=0", headers={"Accept": "text/event-stream"})
        assert "data:" in sse.text and "text/event-stream" in sse.headers["content-type"]
        history = client.get("/synthesis/jobs", params={"conversation_id": cid})
        assert history.status_code == 200 and len(history.json()["items"]) == 1
        assert len(fake.calls) + len(fake.role_calls) == count
