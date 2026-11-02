"""A2 uses real LangGraph/RAG/Decimal services and isolated SQLite/PDF fixtures.

Provider and vector results are controlled. Positive local_operator projections
are read substitutes, not evidence of a human confirmation or production acceptance.
"""

import asyncio
from dataclasses import replace
from contextlib import closing
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.agent.revenue_confirmation import RevenueConfirmationError, RevenueConfirmationService
from app.conversations.api import create_conversation_router
from app.conversations.context import load_context, tokens
from app.conversations.graph import ConversationGraph
from app.conversations.models import CreateTurnRequest, EvidenceRef, ResolvedQuery, TurnResult
from app.conversations.repository import ConversationRepository
from app.conversations.service import ConversationService, ExecutionResult, TurnExecution
from app.conversations.tools import ConversationTools
from app.documents.preparation import DocumentTaskPreparer
from app.memory.models import CreateMemoryRequest, DeleteMemoryRequest
from app.memory.repository import MemoryRepository
from app.memory.service import MemoryService
from app.rag.retriever import SearchHit
from app.rag.service import RAGService
from tests.test_conversation_a1 import setup, create, send  # noqa: F401
from tests.test_d10_financial_facts import receipt, persist
from tests.test_d11_financial_analysis import substituted_group
from tests.test_financial_reviews import financial_harness


def uid():
    return str(uuid4())


@pytest.fixture
def graph_env(setup):  # noqa: F811
    h, repo, preparer, _, _, _, reader = setup

    async def checked_source(document_id):
        value = await h.service.source(document_id)
        return {**value, "assessment": dict.fromkeys(
            ("company", "report_year", "report_type"), "matches_cover")}

    # Retain real PDF-byte revalidation; override only the generated cover assessment.
    reader.source.side_effect = checked_source
    scope = Mock(search=AsyncMock(return_value=(SearchHit(score=.9, chunk_id="chunk-0",
        text="这是可信业务原文", page=1, source_file="fixture.pdf", type="paragraph",
        workspace_id="demo", document_id=h.id, source_revision=h.rev),)),
        table_context=AsyncMock(return_value={}), revalidate=preparer.revalidate)
    provider = Mock(return_value='{"decision":"answer","quotes":[{"number":1}]}')
    rag = RAGService(retriever=Mock(), llm_client=Mock(),
                     evidence_gate=Mock(allows=Mock(return_value=True)), max_evidence_chars=4000)
    facts = Mock(spec=RevenueConfirmationService)
    memory = MemoryService(MemoryRepository(h.registry))
    tools = ConversationTools(preparer=preparer, scope=scope, rag=rag, facts=facts,
                              generate_once=provider)
    graph = ConversationGraph(tools, memory)
    service = ConversationService(repo, preparer, handler=graph)
    app = FastAPI()
    app.include_router(create_conversation_router(repo, service))
    client = TestClient(app)
    body = {"operation_id": uid(), "document_ids": [h.id]}
    response = client.post("/conversations", json=body)
    assert response.status_code == 201, response.text
    return h, repo, preparer, scope, provider, facts, memory, graph, client, response.json()["conversation_id"]


def ask(env, text, facts=None):
    request = {"operation_id": uid(), "text": text, "fact_selections": facts or []}
    response = env[8].post(f"/conversations/{env[9]}/turns", json=request)
    assert response.status_code == 200, response.text
    return response.json(), request


def test_three_turn_focus_including_refused_comparison_and_only_one_provider(graph_env):
    env = graph_env
    first, _ = ask(env, "2025年营业收入是多少？")
    assert first["status"] == "completed", first
    assert first["result"]["kind"] == "source_quote"
    assert first["result"]["answer_text"].endswith("[1]")
    second, _ = ask(env, "同比变化呢？")
    assert second["status"] == "refused" and second["result"]["kind"] == "needs_human_review"
    assert second["resolved_query"]["periods"] == [2025, 2024]
    third, _ = ask(env, "经营现金流也这样吗？")
    assert third["status"] == "refused"
    assert third["resolved_query"]["intent"] == "compare_metric"
    assert third["resolved_query"]["metric_key"] == "operating_cash_flow"
    assert third["resolved_query"]["periods"] == [2025, 2024]
    assert third["resolved_query"]["context_turn_ids"] == [second["turn_id"]]
    assert env[4].call_count == 1
    assert first["usage"] == {"model_attempts": 1, "tool_calls": 1}
    assert [e["status"] for e in first["tool_events"]] == ["started", "completed"]
    assert first["result"]["actions"][0]["href"].endswith("#page=1")


@pytest.mark.parametrize("text,reason", [
    ("它的营业收入是多少？", "period_required"),
    ("2023年营业收入是多少？", "outside_period"),
    ("2027年营业收入是多少？", "outside_period"),
    ("腾讯2025年营业收入是多少？", "unknown_company"),
    ("苹果2025年营业收入", "unknown_company"),
    ("请查询格力集团2025年的营业收入", "unknown_company"),
    ("2025年苹果营业收入", "unknown_company"),
    ("换一家看看2025年营业收入", "new_conversation_required"),
    ("Other Corporation 2025年营业收入是多少？", "outside_company"),
    ("2025年营业收入和净利润是多少？", "ambiguous_reference"),
])
def test_ambiguity_and_out_of_scope_never_call_provider(graph_env, text, reason):
    value, _ = ask(graph_env, text)
    assert value["result"]["kind"] == "clarification" and value["result"]["reason_code"] == reason, value
    assert graph_env[4].call_count == 0 and graph_env[3].search.await_count == 0


def test_previous_year_context_and_read_only_get_no_repeat(graph_env):
    env = graph_env
    first, _ = ask(env, "2025年营业收入原文")
    second, request = ask(env, "那上一年呢？")
    assert second["resolved_query"]["periods"] == [2024]
    assert second["resolved_query"]["context_turn_ids"] == [first["turn_id"]]
    counts = (env[4].call_count, env[3].search.await_count)
    for _ in range(2):
        assert env[8].get(f"/conversations/{env[9]}").status_code == 200
        replay = env[8].post(f"/conversations/{env[9]}/turns", json=request)
        assert replay.json() == second
    assert (env[4].call_count, env[3].search.await_count) == counts


@pytest.mark.parametrize("text", [
    "2025年营业收入原文，不计算同比。",
    "2025年营业收入原文，不要计算同比。",
    "2025年营业收入，只摘录同比原文。",
    "2025年营业收入，不要计算，只摘录同比原文。",
    "请引用年报原文说明Example Corporation2025年的营业收入，不计算同比。",
])
def test_negative_calculation_and_explicit_reading_use_original_rag(graph_env, text):
    value, _ = ask(graph_env, text)
    assert value["status"] == "completed" and value["result"]["kind"] == "source_quote", value
    assert value["resolved_query"]["intent"] == "source_quote" and graph_env[4].call_count == 1


def test_registered_chinese_safe_alias_preserves_name_ending_in_de(graph_env, monkeypatch):
    env = graph_env
    company = env[0].company.model_copy(update={"name": "美的集团股份有限公司"})
    monkeypatch.setattr(env[1].registry, "list", Mock(return_value=[company]))
    for text in ("美的2025年营业收入原文", "请引用年报原文说明美的集团2025年的营业收入，不计算同比。"):
        value, _ = ask(env, text)
        assert value["status"] == "completed" and value["resolved_query"]["company_id"] == company.company_id, value


def test_mixed_positive_calculation_request_remains_confirmed_fact_gate(graph_env):
    value, _ = ask(graph_env, "2025年营业收入只摘录同比原文，然后计算同比差额")
    assert value["result"]["kind"] == "needs_human_review"
    assert graph_env[4].call_count == 0


@pytest.mark.parametrize("error", [TimeoutError("private provider"), ConnectionError("private endpoint")])
def test_provider_unknown_no_retry_and_no_candidate(graph_env, error):
    env = graph_env
    env[4].side_effect = error
    value, request = ask(env, "2025年营业收入原文")
    assert value["status"] == "failed" and value["provider_outcome"] == "unknown"
    assert value["result"]["error_code"] == "llm_error"
    assert not value["result"]["evidence_refs"] and "private" not in str(value)
    assert value["tool_events"][-1]["status"] == "unknown"
    assert env[8].post(f"/conversations/{env[9]}/turns", json=request).json() == value
    assert env[4].call_count == 1


@pytest.mark.parametrize("output", [
    '{"decision":"answer","quotes":[{"number":999}]}',
    '{"decision":"answer","content":"invented 999元","quotes":[{"number":1}]}',
    '{"decision":"answer","quotes":[{"number":1,"physical_page":99}]}',
    '```json\n{"decision":"refuse"}\n```',
])
def test_forged_quotes_and_invalid_json_are_withheld(graph_env, output):
    graph_env[4].return_value = output
    value, _ = ask(graph_env, "2025年营业收入原文")
    assert value["status"] == "failed" and value["provider_outcome"] == "returned"
    assert value["result"]["error_code"] == "citation_validation_error"
    assert not value["result"]["evidence_refs"] and graph_env[4].call_count == 1


def test_generation_change_in_provider_withdraws_answer_next_call_has_no_deleted_preference(graph_env):
    env = graph_env
    item, _ = env[6].create(CreateMemoryRequest(operation_id=uid(), type="research_preference",
        key="analysis_focus", value="cash_flow", confirmed=True))

    def provider(prompt):
        assert '"value":"cash_flow"' in prompt
        env[6].delete(item.memory_id, DeleteMemoryRequest(operation_id=uid(), expected_revision=1))
        return '{"decision":"answer","quotes":[{"number":1}]}'

    env[4].side_effect = provider
    value, _ = ask(env, "2025年营业收入原文")
    assert value["status"] == "interrupted" and value["result"]["error_code"] == "context_changed"
    assert value["result"]["evidence_refs"] == []
    env[4].side_effect = None
    follow, _ = ask(env, "2025年营业收入原文")
    assert follow["status"] == "completed"
    assert '"value":"cash_flow"' not in env[4].call_args[0][0]


def test_candidates_explicit_no_save_and_delete_conversation_detaches_memory(graph_env):
    env = graph_env
    value, _ = ask(env, "记住：我更关注现金流。")
    assert value["result"]["memory_candidates"][0]["value"] == "cash_flow"
    assert env[6].list().items == [] and env[4].call_count == 0
    item, _ = env[6].create(CreateMemoryRequest(operation_id=uid(), type="research_preference",
        key="analysis_focus", value="cash_flow", source_turn_id=value["turn_id"], confirmed=True))
    response = env[8].request("DELETE", f"/conversations/{env[9]}", json={"operation_id": uid()})
    assert response.status_code == 200
    assert env[6].get(item.memory_id).source_turn_id is None
    assert value["turn_id"] in env[6].excluded_source_turn_ids()


def test_bounded_recent_context_excludes_preference_management(graph_env):
    env = graph_env
    ask(env, "记住：我更关注现金流。")
    for _ in range(12):
        ask(env, "2025年营业收入原文")
    turn, claim, _ = env[1].register(env[9], CreateTurnRequest(operation_id=uid(), text="q"),
                                    env[1].selection(env[9], "q"))
    context = load_context(TurnExecution(env[1], turn, env[1].selection(env[9], "q"), claim), env[6])
    assert len(context.turns) <= 8 and tokens(context.prompt_data) < 4500
    assert "记住" not in context.prompt_data and "这是可信业务原文" not in context.prompt_data


@pytest.fixture
def financial_env(tmp_path):
    h = financial_harness(tmp_path)
    receipt_value, _ = receipt(h)
    assert persist(h, receipt_value).status_code == 200
    group = h.receipts.load_financial_facts(workspace_id="demo", receipt_id=receipt_value["receipt_id"],
                                           confirmation_kind="simulated_test")
    # Same controlled read projection pattern as existing D11 tests. SQLite receipt
    # remains simulated; no actual local_operator write or human approval is claimed.
    local = substituted_group(group, {}, local_operator=True)
    facts = Mock(spec=RevenueConfirmationService)
    facts.read_financial_facts = AsyncMock(return_value=local)
    facts.recheck_financial_analysis_sources = AsyncMock()
    facts.recheck_persisted_analysis_in.side_effect = lambda conn, **kw: tuple(
        local for _ in kw["receipt_ids"])
    preparer = DocumentTaskPreparer(document_service=h.documents, sources=h.service, workspace_id="demo")
    repo = ConversationRepository(h.registry, "demo")
    tools = ConversationTools(preparer=preparer, scope=Mock(), rag=Mock(), facts=facts,
                              generate_once=Mock(side_effect=AssertionError("financial path called model")))
    memory = MemoryService(MemoryRepository(h.registry))
    graph = ConversationGraph(tools, memory)
    app = FastAPI()
    app.include_router(create_conversation_router(repo, ConversationService(repo, preparer, handler=graph)))
    client = TestClient(app)
    response = client.post("/conversations", json={"operation_id": uid(), "document_ids": [h.id]})
    assert response.status_code == 201, response.text
    env = (h, repo, preparer, Mock(), tools.generate_once, facts, memory, graph, client,
           response.json()["conversation_id"])

    def choices(metric="revenue", periods=(2031, 2030)):
        return [dict(company_id=h.company.company_id, metric_key=metric, period=year,
            fact_set_id=local.fact_set_id, fact_id=next(f.fact_id for f in local.facts
                if f.to_payload()["period"] == year and f.to_payload()["metric_key"] == metric),
            disclosure_version=local.disclosure_version) for year in periods]
    return env, local, choices


def test_financial_real_decimal_service_with_explicit_choices_and_final_transaction_check(financial_env):
    env, group, choices = financial_env
    metric, _ = ask(env, "2031年营业收入是多少", choices(periods=(2031,)))
    assert metric["status"] == "completed", metric
    assert metric["result"]["verified_financial_fact_refs"][0]["value_cny_yuan"] == "12345000.00"
    comparison, _ = ask(env, "同比变化呢？", choices())
    assert comparison["status"] == "completed", comparison
    assert comparison["result"]["analysis"]["absolute_change"] == "12095000.00"
    assert comparison["result"]["analysis"]["percentage_change"] == "4838.00"
    assert comparison["usage"] == {"model_attempts": 0, "tool_calls": 1}
    assert comparison["result"]["evidence_refs"] == []
    assert comparison["result"]["actions"][0]["physical_page"] == 2
    assert "/file?source_revision=" in comparison["result"]["actions"][0]["href"]
    assert env[5].recheck_persisted_analysis_in.call_count == 2
    assert env[4].call_count == 0


@pytest.mark.parametrize("change", ["fact_id", "disclosure_version", "scope", "revoked", "simulated"])
def test_wrong_fact_disclosure_scope_revoked_and_simulated_withdraw(financial_env, change):
    env, local, choices = financial_env
    selected = choices()
    if change in ("fact_id", "disclosure_version"):
        selected[0][change] = "invented"
    elif change == "scope":
        source = local.receipt.review.to_payload()
        source["source"]["period_end"] = "2031-12-30"
        from app.agent.revenue_confirmation import FinancialReview, canonical_payload
        bad = replace(local, receipt=replace(local.receipt,
            review=FinancialReview("demo", canonical_payload(source))))
        env[5].read_financial_facts.return_value = bad
    elif change == "revoked":
        env[5].read_financial_facts.side_effect = RevenueConfirmationError("receipt_revoked")
    else:
        env[5].read_financial_facts.side_effect = env[0].confirmations.read_financial_facts
    value, _ = ask(env, "2031年营业收入同比变化", selected)
    assert value["status"] == "refused" and value["result"]["kind"] == "needs_human_review", value
    assert value["result"]["analysis"] is None and not value["result"]["verified_financial_fact_refs"]
    assert env[4].call_count == 0


def test_revoke_between_tool_and_commit_is_rechecked_in_same_transaction(financial_env):
    env, _, choices = financial_env
    env[5].recheck_persisted_analysis_in.side_effect = RevenueConfirmationError("acceptance_revoked")
    value, _ = ask(env, "2031年营业收入同比变化", choices())
    assert value["status"] == "failed" and value["result"]["error_code"] == "fact_changed", value
    assert value["result"]["analysis"] is None
    assert env[5].recheck_persisted_analysis_in.call_count == 1


def test_real_sqlite_revocation_before_commit_with_controlled_local_projection(financial_env, monkeypatch):
    env, local, choices = financial_env
    h, repo = env[0], env[1]

    def recheck(conn, **kwargs):
        checked = h.receipts.recheck_financial_fact_sets_in(conn, workspace_id="demo",
            receipt_ids=kwargs["receipt_ids"], confirmation_kind="simulated_test")
        return tuple(substituted_group(g, {}, local_operator=True) for g in checked)

    env[5].recheck_persisted_analysis_in.side_effect = recheck
    original = repo.finish

    def finish(*args, **kwargs):
        h.receipts.revoke_financial_receipt(workspace_id="demo", receipt_id=local.fact_set_id,
            confirmation_kind="simulated_test", reason="isolated revocation race")
        return original(*args, **kwargs)

    monkeypatch.setattr(repo, "finish", finish)
    value, _ = ask(env, "2031年营业收入同比变化", choices())
    assert value["status"] == "failed" and value["result"]["error_code"] == "fact_changed"
    assert value["result"]["verified_financial_fact_refs"] == []


def test_source_bytes_change_during_model_withdraws_and_never_reruns(graph_env):
    env = graph_env
    h = env[0]
    record = h.docs.get(h.id)

    def provider(prompt):
        h.objects.put_bytes(record.object_key, b"changed source")
        return '{"decision":"answer","quotes":[{"number":1}]}'

    env[4].side_effect = provider
    value, request = ask(env, "2025年营业收入原文")
    assert value["status"] == "failed" and value["result"]["error_code"] == "source_changed"
    assert value["result"]["evidence_refs"] == []
    assert env[8].post(f"/conversations/{env[9]}/turns", json=request).status_code == 200
    assert env[4].call_count == 1


def test_token_hard_budget_withholds_before_physical_model_call(graph_env):
    env = graph_env
    env[3].search.return_value = (SearchHit(score=.9, chunk_id="c", text="财" * 13000,
        page=1, source_file="fixture.pdf", type="paragraph", workspace_id="demo",
        document_id=env[0].id, source_revision=env[0].rev),)
    value, _ = ask(env, "2025年营业收入原文")
    assert value["status"] == "failed" and value["result"]["error_code"] == "context_budget_error", value
    assert value["usage"]["model_attempts"] == 0 and env[4].call_count == 0


def test_memory_change_during_retrieval_blocks_provider_reservation(graph_env):
    env = graph_env
    original = env[3].search.return_value

    async def search(*args, **kwargs):
        env[6].create(CreateMemoryRequest(operation_id=uid(), type="research_preference",
            key="analysis_focus", value="cash_flow", confirmed=True))
        return original

    env[3].search.side_effect = search
    value, _ = ask(env, "2025年营业收入原文")
    assert value["status"] == "interrupted" and value["result"]["error_code"] == "context_changed"
    assert env[4].call_count == 0


def test_no_fallback_past_unresolved_company_question(graph_env):
    ask(graph_env, "2025年营业收入原文")
    ask(graph_env, "苹果2025年营业收入")
    value, _ = ask(graph_env, "同比呢？")
    assert value["result"]["kind"] == "clarification"
    assert value["resolved_query"]["context_turn_ids"] == []
    assert graph_env[4].call_count == 1


@pytest.mark.parametrize("text", ["格力同一年呢？", "苹果上一年呢？", "苹果呢？", "格力的现金流也这样吗？"])
def test_unknown_named_elliptical_subject_never_inherits_old_company(graph_env, text):
    ask(graph_env, "2025年营业收入原文")
    calls = (graph_env[4].call_count, graph_env[3].search.await_count)
    value, _ = ask(graph_env, text)
    assert value["result"]["kind"] == "clarification", value
    assert value["resolved_query"]["company_id"] is None
    assert (graph_env[4].call_count, graph_env[3].search.await_count) == calls


def test_multiple_companies_require_subject_and_wrong_company_quote_cannot_publish(graph_env):
    from tests.test_document_sources import metadata, pdf_bytes
    env = list(graph_env)
    h = env[0]
    response = h.upload(pdf_bytes("Other unique generated report"), metadata(h.other.company_id))
    other_id = response.json()["document_id"]
    h.processor.process(other_id)
    response = env[8].post("/conversations", json={"operation_id": uid(),
        "document_ids": [h.id, other_id]})
    assert response.status_code == 201, response.text
    env[9] = response.json()["conversation_id"]
    ambiguous, _ = ask(env, "它2025年营业收入原文")
    assert ambiguous["result"]["kind"] == "clarification"
    assert env[4].call_count == 0
    wrong, _ = ask(env, "Other Corporation 2025年营业收入原文")
    assert wrong["status"] == "failed" and wrong["result"]["error_code"] == "citation_validation_error"
    assert wrong["result"]["evidence_refs"] == []


def test_runtime_factory_real_graph_and_memory_share_registry(tmp_path, monkeypatch):
    from app.api import runtime_factory as factory
    from app.rag.openai_compatible_llm import OpenAICompatibleLLMClient
    from app.rag.retriever import Retriever
    model = Mock(spec=OpenAICompatibleLLMClient, model="test-only")
    monkeypatch.setattr(factory.OpenAICompatibleLLMClient, "from_env", Mock(return_value=model))
    monkeypatch.setattr(factory, "_warm_runtime_bge_before_milvus", Mock())
    monkeypatch.setattr(factory, "_build_runtime_indexer", Mock(return_value=Mock()))
    resources = factory.RuntimeRAGResources(Mock(spec=RAGService), Mock(spec=Retriever), Mock())
    monkeypatch.setattr(factory, "_build_runtime_rag_resources", Mock(return_value=resources))
    app = factory.create_runtime_app(tmp_path)
    with TestClient(app) as client:
        assert isinstance(app.state.conversation_service.handler, ConversationGraph)
        assert client.get("/memories").status_code == 200
        assert client.post("/memories", json={"operation_id": uid(), "type": "research_preference",
            "key": "analysis_focus", "value": "cash_flow", "confirmed": True}).status_code == 201
        assert client.get("/conversations").status_code == 200
        with closing(app.state.conversation_repository.registry._connect()) as conn:
            assert [r[0] for r in conn.execute("SELECT version FROM analyst_schema_migrations")] == list(range(1, 12))
        model.generate_once.assert_not_called()


@pytest.mark.parametrize("kind", ["company", "quote"])
def test_invalid_new_candidate_closes_failed_without_replay_or_permanent_busy(setup, kind):  # noqa: F811
    h, repo, preparer, _, _, _, _ = setup
    if kind == "company":
        output = ExecutionResult(TurnResult(kind="clarification", answer_text="x"),
            resolved=ResolvedQuery(text="q", intent="clarify", company_id="outside", metric_key=None,
                                   periods=[], resolution="explicit", context_turn_ids=[]))
    else:
        selection = asyncio.run(preparer.prepare_many(document_ids=[h.id], query="q"))
        from dataclasses import asdict
        ref = EvidenceRef(**asdict(selection.documents[0]), ref_id="e1", number=1, chunk_id="c",
            physical_page=1, source_file="f.pdf", text="original", kind="paragraph",
            verification="exact_original_with_context")
        output = ExecutionResult(TurnResult(kind="source_quote", answer_text="forged", evidence_refs=[ref]))
    handler = AsyncMock(return_value=output)
    app = FastAPI()
    app.include_router(create_conversation_router(repo, ConversationService(repo, preparer, handler=handler)))
    client = TestClient(app)
    cid = client.post("/conversations", json={"operation_id": uid(), "document_ids": [h.id]}).json()["conversation_id"]
    request = {"operation_id": uid(), "text": "q"}
    value = client.post(f"/conversations/{cid}/turns", json=request).json()
    assert value["status"] == "failed" and value["result"]["error_code"] == "result_validation_error"
    assert value["resolved_query"] is None and value["result"]["evidence_refs"] == []
    assert client.post(f"/conversations/{cid}/turns", json=request).json() == value
    assert handler.await_count == 1
    assert repo.detail(cid).active_turn_id is None
    assert client.post(f"/conversations/{cid}/turns", json={"operation_id": uid(), "text": "new"}).status_code == 200
