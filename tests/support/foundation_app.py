"""S0/S1 disposable assembly over this round's stopped simulated seed only."""
import os
import json
from pathlib import Path
from app.api.research_tasks import create_task_router
from app.api.research_runs import create_research_runs_router
from app.documents.preparation import DocumentTaskPreparer
from app.rag.retriever import SearchHit
from app.rag.selected_scope import SelectedScopeSearch
from app.rag.service import RAGService
from app.research.repository import ResearchRepository
from unittest.mock import Mock
from tests.support.d26_report_app import create_app as guarded_readers
from tests.support.d19_runtime import reopen
from tests.test_d21_research import configured, response
from tests.test_d18_templates import final
from app.api.financial_analyses import FinancialAnalysisRequest, CompanyComparisonRequest, AnalysisRoute
from app.agent.financial_analysis import FinancialAnalysisService, FinancialFactReference, IsolatedAnalysisTestConfig
from fastapi import APIRouter
from fastapi.responses import JSONResponse

def create_app():
    app = guarded_readers()  # Existing root/socket/foreign-worktree guards.
    h = reopen(Path(os.environ['FINDOC_UX_RUNTIME_ROOT']))
    analysis = FinancialAnalysisService(facts=h.confirmations, workspace_id='demo', isolated_test=IsolatedAnalysisTestConfig(h.root))
    router = APIRouter(prefix='/__test__', route_class=AnalysisRoute)

    @router.post('/analyses')
    async def analyze(payload: FinancialAnalysisRequest):
        value = await analysis.analyze(company_id=payload.company_id, metric_key=payload.metric_key,
            current=FinancialFactReference(**payload.current.model_dump()) if payload.current else None,
            previous=FinancialFactReference(**payload.previous.model_dump()) if payload.previous else None)
        return JSONResponse(value, status_code=409 if value['status'] == 'blocked' else 200)

    @router.post('/company-comparison')
    async def compare(payload: CompanyComparisonRequest):
        value = await analysis.compare(company_a_id=payload.company_a_id, company_b_id=payload.company_b_id, period=payload.period,
            selections={s.metric_key: (FinancialFactReference(**s.a.model_dump()) if s.a else None, FinancialFactReference(**s.b.model_dump()) if s.b else None) for s in payload.selections})
        return JSONResponse(value, status_code=409 if value['status'] == 'blocked' else 200)

    app.include_router(router)
    templates, repository, graph = configured(h, (1,))

    async def search(selection, top_k):
        hits = []
        for d in selection.documents:
            _, records = await h.service.parsed_evidence(d.document_id, company_id=d.company_id, source_revision=d.source_revision)
            paragraphs = [r for r in records if r['kind'] == 'paragraph' and r['text']]
            chosen = next((r for r in paragraphs if any(w in r['text'] for w in ('主营业务', '主要业务', '经营模式'))), paragraphs[0])
            doc = await h.documents.get_document(d.document_id)
            hits.append(SearchHit(chunk_id=chosen['evidence_id'], text=chosen['text'], page=chosen['physical_page'], score=1.0,
                source_file=doc.source_file, type='paragraph', workspace_id=d.workspace_id, document_id=d.document_id, source_revision=d.source_revision))
        return tuple(hits)

    class OperatingModel:
        def complete(self, messages, tools):
            evidence = str(messages[-1]['content']).split('本次选定来源与编号原文：\n', 1)[1]
            numbers = tuple(json.loads(line)['number'] for line in evidence.splitlines() if line.startswith('{'))
            return final(response(numbers))

    templates.scope.search, templates.model = search, OperatingModel()
    app.include_router(create_task_router(repository, graph))

    class Retriever:
        def retrieve(self, query, *, context, filters, top_k):
            hits = []
            for document_id, revision in filters.source_revisions:
                table = next(r for r in h.sources.evidence_batch(revision) if r['kind'] == 'table' and '营业收入' in r['text'])
                hits.append(SearchHit(score=1.0, chunk_id=table['evidence_id'], text='主要会计数据和财务指标', table_md=table['text'], type='table',
                    page=table['physical_page'], source_file=h.docs.get(document_id).source_file, workspace_id=context.workspace_id, document_id=document_id, source_revision=revision))
            return hits

    class QAModel:
        def generate(self, prompt):
            numbers = [json.loads(line)['number'] for line in prompt.splitlines() if line.startswith('{"number":')]
            return json.dumps({'decision': 'answer', 'quotes': [{'number': n} for n in numbers]})

    preparer = DocumentTaskPreparer(document_service=h.documents, sources=h.service, workspace_id='demo')
    app.include_router(create_research_runs_router(ResearchRepository(h.registry, 'demo'), preparer, SelectedScopeSearch(preparer, Retriever()),
        RAGService(retriever=Retriever(), llm_client=QAModel(), evidence_gate=Mock(allows=Mock(return_value=True)), max_evidence_chars=16000)))
    return app
