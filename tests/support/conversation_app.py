"""V1.2 isolated official runtime assembly with deterministic heavy dependencies.

Real HTTP, SQLite migrations/services, original PDF parsing and source checks.
No real embedding/vector/model. This module is never imported by production.
"""

import json
import os
from pathlib import Path
import re
import sys
from tempfile import gettempdir
import threading
import time
from urllib.parse import unquote, urlparse


def create_app():
    raw = os.environ.get('FINDOC_CONVERSATION_RUNTIME_ROOT', '')
    root = Path(raw)
    if not raw or not root.is_absolute():
        raise ValueError('explicit_absolute_conversation_test_runtime_required')
    root = root.resolve()
    if not root.name.startswith('findoc-d11-conversation-v12-') or not root.is_relative_to(Path(gettempdir()).resolve()):
        raise ValueError('isolated_conversation_test_runtime_required')
    root.mkdir(parents=True, exist_ok=True)

    def audit(event, args):
        if event == 'socket.connect':
            raise RuntimeError('conversation_test_forbids_outgoing_network')
        if event == 'sqlite3.connect' and args[0] != ':memory:':
            value = str(args[0])
            if value.startswith('file:'):
                value = unquote(urlparse(value).path)
            if not Path(value).resolve().is_relative_to(root):
                raise RuntimeError('conversation_test_sqlite_outside_runtime')

    sys.addaudithook(audit)
    from app.api import runtime_factory as factory
    from app.companies.sqlite_repository import SQLiteCompanyRepository
    from app.documents.source_repository import SQLiteSourceRepository
    from app.documents.sqlite_repository import SQLiteDocumentRepository
    from app.rag.ingest import ReplaceResult
    from app.rag.retriever import SearchHit
    from app.rag.service import RAGService
    from app.rag.evidence_gate import ConservativeScoreEvidenceGate
    from app.rag.openai_compatible_llm import OpenAICompatibleLLMClient

    count_file = root / 'conversation-test-counts.json'
    calls = json.loads(count_file.read_text()) if count_file.exists() else dict(model=0, retrieval=0)
    modes = dict(delay_seconds=0.0, provider_failure=False, forged_quote=False, hold_provider=False)
    provider_release = threading.Event()
    provider_release.set()
    lock = threading.Lock()

    def count(name):
        with lock:
            calls[name] += 1
            count_file.write_text(json.dumps(calls))

    class Model:
        model = 'deterministic-conversation-test-provider'

        def generate_once(self, prompt):
            count('model')
            if not provider_release.wait(timeout=20):
                raise TimeoutError('bounded_conversation_test_provider_hold_expired')
            if modes['delay_seconds']:
                time.sleep(modes['delay_seconds'])
            if modes['provider_failure']:
                raise ConnectionError('isolated_provider_failure')
            numbers = [json.loads(line)['number'] for line in prompt.splitlines()
                       if line.startswith('{"number":')]
            if modes['forged_quote']:
                numbers = [9999]
            # Only choose validated evidence numbers; no fabricated financial text.
            return json.dumps({'decision': 'answer', 'quotes': [{'number': n} for n in numbers]})

        generate = generate_once

        def for_operating_research(self):
            return self

    class Retriever:
        def retrieve(self, query, *, context, filters, top_k):
            count('retrieval')
            registry = SQLiteCompanyRepository(root / 'documents.db')
            sources = SQLiteSourceRepository(registry)
            docs = SQLiteDocumentRepository(root / 'documents.db')
            hits = []
            for document_id, revision in filters.source_revisions:
                records = sources.evidence_batch(revision)
                keywords = ('营业收入', '净利润', '现金流') if any(w in query for w in ('收入', '现金流', '净利润')) else ('主要业务', '主营业务', '经营模式')
                eligible = [r for r in records if r['text'] and any(w in re.sub(r'\s+', '', r['text']) for w in keywords)]
                if not eligible:
                    eligible = [r for r in records if r['text']]
                # Use genuine captured evidence, not reference amounts or gold answers.
                for record in eligible[:min(top_k, 2)]:
                    is_table = record['kind'] == 'table'
                    hits.append(SearchHit(score=0.99, chunk_id=record['evidence_id'],
                        text='主要会计数据和财务指标' if is_table else record['text'],
                        table_md=record['text'] if is_table else None,
                        type='table' if is_table else 'paragraph',
                        page=record['physical_page'], source_file=docs.get(document_id).source_file,
                        workspace_id=context.workspace_id, document_id=document_id,
                        source_revision=revision))
            return hits[:top_k]

    class NoVectorClient:
        def close(self):
            pass

    model = Model()
    retriever = Retriever()
    rag = RAGService(retriever=retriever, llm_client=model,
                     evidence_gate=ConservativeScoreEvidenceGate(min_top_score=0.5),
                     max_evidence_chars=16000)

    def indexer(database_path, collection_name):
        def index(document_id, rows):
            return ReplaceResult(inserted=len(rows), updated=0, skipped=0,
                                 final_ids=frozenset(r['chunk_id'] for r in rows))
        return index

    # Replacements live only in this disposable server process. The official
    # factory still wires conversation/memory and all existing business services.
    OpenAICompatibleLLMClient.from_env = classmethod(lambda cls: model)
    factory._warm_runtime_bge_before_milvus = lambda: None
    factory._runtime_bge_embed = lambda texts: [[0.1] for _ in texts]
    factory._build_runtime_indexer = indexer
    factory._build_runtime_rag_resources = lambda *a: factory.RuntimeRAGResources(
        rag_service=rag, retriever=retriever, milvus_client=NoVectorClient())
    import app.conversations.graph as graph_module
    original_load_context = graph_module.load_context
    context_observations = {}

    def observed_context(execution, memory):
        context = original_load_context(execution, memory)
        # Capture the actual returned Graph input, not a separately reconstructed
        # or model-inferred preference. Enum data only; no raw prompt or amounts.
        context_observations[execution.turn.turn_id] = dict(
            turn_id=execution.turn.turn_id,
            conversation_id=execution.turn.conversation_id,
            memory_generation=context.memory_generation,
            preferences=list(context.preferences),
            prompt_preferences=json.loads(context.prompt_data)['confirmed_preferences'],
            prior_turn_ids=[turn.turn_id for turn in context.turns],
            actual_context_observation=True, actual_llm=False)
        return context

    graph_module.load_context = observed_context
    app = factory.create_runtime_app(root)
    paths = app.openapi()['paths']
    if '/conversations' not in paths:
        if os.environ.get('FINDOC_CONVERSATION_A1_ONLY') != '1':
            raise RuntimeError('actual_conversation_runtime_routes_not_implemented_yet')
        # Explicit A1-only wiring uses the actual store/API and its opt-in fake
        # handler. No A2 semantic test may be reported from this mode.
        from app.conversations.api import create_conversation_router
        from app.conversations.repository import ConversationRepository
        from app.conversations.service import ConversationService, fake_handler
        repository = ConversationRepository(SQLiteCompanyRepository(root / 'documents.db'), 'demo')
        repository.recover_interrupted()
        service = ConversationService(repository, app.state.selection_preparer, handler=fake_handler)
        app.include_router(create_conversation_router(repository, service))

    @app.get('/__test__/conversation-counts')
    def counts():
        registry = SQLiteCompanyRepository(root / 'documents.db')
        with registry._connect() as db:
            names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            allowed = [n for n in names if n.startswith(('conversation_', 'memory_')) or n in (
                'conversations', 'research_runs', 'financial_acceptance_receipts', 'confirmed_financial_facts')]
            tables = {n: db.execute('SELECT count(*) FROM "' + n + '"').fetchone()[0] for n in allowed}
        return dict(calls=calls, tables=tables, actual_llm=False, actual_bge=False,
                    actual_milvus=False, simulated_test=True, human_acceptances=0)

    @app.post('/__test__/conversation-mode')
    def mode(payload: dict):
        if set(payload) - set(modes):
            raise ValueError('unknown_test_fault')
        if 'delay_seconds' in payload and not 0 <= float(payload['delay_seconds']) <= 5:
            raise ValueError('bounded_test_delay_required')
        modes.update(payload)
        if 'hold_provider' in payload:
            if payload['hold_provider'] is True:
                provider_release.clear()
            else:
                provider_release.set()
        return dict(isolated_test_only=True, **modes)

    @app.get('/__test__/conversation-context/{turn_id}')
    def observed_turn_context(turn_id: str):
        from fastapi import HTTPException
        if turn_id not in context_observations:
            raise HTTPException(404, 'context_not_observed')
        return context_observations[turn_id]

    return app
