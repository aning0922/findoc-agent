"""Real observed crop failure and source-bounded raw excerpt intent regression."""
import pytest
import asyncio
from unittest.mock import AsyncMock, Mock

from app.rag.parse.models import PDFCell, PDFLayout
from app.rag.parse.table_structure import project_table
from app.rag.parse.tables import extract_table_chunks
from app.rag.selected_scope import SelectedScopeSearch
from app.rag.selected_intent import outside_annual_evidence
from app.rag.retriever import SearchHit
from app.documents.source_models import SourceError
from tests.test_d17_history import setup as budget_harness  # noqa: F401


def test_cropped_financial_statement_cannot_be_an_ordinary_table():
    layout = PDFLayout(strategy='ruled', rows=[
        [PDFCell(text='附注', bbox=(0,0,80,20)), PDFCell(text='2024年度', bbox=(80,0,160,20))],
        [PDFCell(text='五、54', bbox=(0,20,80,60)),
         PDFCell(text='190,038,071,604.78\n189,163,654,064.64', bbox=(80,20,160,60))],
    ])
    assert project_table(layout) is None  # The D26 omission: label/other year are outside crop.
    assert project_table(layout, financial_page=True).status == 'unsupported'


def test_gree_real_statement_crop_is_unsupported_and_summary_remains_verified():
    chunks = extract_table_chunks('data/30d-foundation/gree-2024.pdf', 113)
    assert chunks and all(c.layout.table_structure.status == 'unsupported' for c in chunks)
    assert all('189,163,654,064.64' not in c.table_md for c in chunks)
    summary = extract_table_chunks('data/30d-foundation/gree-2024.pdf', 7)
    assert not any(c.layout.table_structure and c.layout.table_structure.status=='unsupported' for c in summary)
    assert any('189,163,654,064.64' in c.table_md for c in summary)


@pytest.mark.parametrize('query', [
    '摘录2024年营业收入原值', '请列2025年净利润原文',
    '经营活动产生的现金流量净额原值及原单位',
])
def test_financial_excerpt_uses_existing_section_anchor(query):
    assert SelectedScopeSearch.retrieval_query(query)=='主要会计数据和财务指标'


@pytest.mark.parametrize('query,blocked', [
    ('请保证2027年的净利润金额', True), ('格力现在的股票实时价格是多少？', True),
    ('请证明变化完全由渠道改革造成，没有其他原因', True), ('未选资料的某公司营业收入原值', True),
    ('请摘录2024年营业收入原值', False), ('请列2023年比较列净利润', False),
    ('股票简称或股票代码的原文', False), ('公司主要业务原文', False),
])
def test_annual_evidence_scope_is_independent_of_model(query, blocked):
    assert outside_annual_evidence(query, (2024, 2025)) is blocked


def test_irrelevant_unsupported_page_does_not_poison_verified_page_or_fall_back_to_text():
    preparer = Mock(page_context=AsyncMock(side_effect=[
        SourceError('table_structure_unsupported'), 'verified complete page table',
    ]))
    scope = SelectedScopeSearch(preparer, Mock())
    hits = tuple(SearchHit(score=.8, chunk_id=f'chunk-{page}', text='主要会计数据和财务指标',
        page=page, source_file='report.pdf', type='paragraph', workspace_id='demo',
        document_id='same-document', source_revision='same-revision') for page in (136,9))
    excluded = set()
    contexts = asyncio.run(scope.table_context(hits, excluded_pages=excluded))
    assert excluded == {('same-document','same-revision',136)}
    assert contexts == {('same-document','same-revision',9): 'verified complete page table'}
    assert preparer.page_context.await_count==2


def test_strict_table_context_keeps_unsupported_failure_contract():
    scope = SelectedScopeSearch(Mock(page_context=AsyncMock(side_effect=SourceError('table_structure_unsupported'))), Mock())
    hit = SearchHit(score=.8, chunk_id='crop', text='主要会计数据和财务指标', page=136,
        source_file='report.pdf', type='paragraph', document_id='doc', source_revision='revision')
    with pytest.raises(SourceError):
        asyncio.run(scope.table_context((hit,)))


def test_context_budget_is_saved_as_error_not_evidence_refusal(budget_harness):  # noqa: F811
    from dataclasses import replace
    _, _, client, body, adapter, model, *_ = budget_harness
    hit = adapter.search.return_value[0]
    adapter.search.return_value = (replace(hit, text='已核验原文' * 4000),)
    response = client.post('/research/runs', json=body)
    assert response.status_code == 200
    result = response.json()
    assert result['status'] == 'system_error'
    assert result['result']['error_code'] == 'context_budget_error'
    assert not result['result']['content'] and not result['result']['citations']
    assert model.generate.call_count == 0
    assert client.get('/research/runs/by-operation/' + body['operation_id']).json() == result
    assert client.post('/research/runs', json=body).json() == result
    assert model.generate.call_count == 0 and adapter.search.await_count == 1
