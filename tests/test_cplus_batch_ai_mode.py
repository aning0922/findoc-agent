"""Explicit AI mode only; frozen child IDs and sources are retained, no provider here."""
import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.batch_research.tools import ExistingToolAdapter


def test_ai_risk_uses_frozen_context_and_single_answer_not_implicit_search_retry():
    async def run():
        calls=[]
        async def validate(prepared,identity):
            return None
        async def mutate(kind,body,identity):
            calls.append((kind,body))
            if kind=='context':
                return {'state':'completed','result':{'context_id':'ctx','revision':1,'context_sha256':'hash'}}
            return {'state':'completed','result':{'answer_id':'answer','state':'completed','interpretation':'待审解释','findings':[]}}
        adapter=ExistingToolAdapter(hybrid=SimpleNamespace(mutate=mutate),annual_diff=None)
        adapter.validate_prepared=validate
        context_op,answer_op=str(uuid4()),str(uuid4())
        sources=[{'kind':'fast','document_id':'selected-only'}]
        cell={'template':'risk_excerpt','question':'仅所选范围','child_context_operation_id':context_op,
              'prepared':{'generate_explanation':True,'selected_sources':sources}}
        result=await adapter.execute_cell(cell,answer_op,object())
        assert result['domain']=='research_answer_v1'
        assert [kind for kind,_ in calls]==['context','answer']
        assert calls[0][1]['operation_id']==context_op
        assert calls[0][1]['selected_sources']==sources
        assert calls[1][1]['operation_id']==answer_op and calls[1][1]['context_id']=='ctx'
        assert result['payload']['interpretation']=='待审解释'
    asyncio.run(run())


def test_annual_ai_flag_is_explicit_and_default_remains_no_provider():
    async def run():
        requests=[]
        async def validate(prepared,identity):
            return None
        async def create(request,identity):
            requests.append(request)
            return {'state':'completed','result':{'result_id':'saved'}}
        adapter=ExistingToolAdapter(hybrid=None,annual_diff=SimpleNamespace(create=create))
        adapter.validate_prepared=validate
        def source(year):
            return dict(kind='fast',workspace_id='demo',company_id='c',document_id=str(year),
                        source_revision='revision',content_sha256='sha',parser_version='fixture',
                        report_year=year,identity_status='fast_source_verified')
        for flag in [False,True]:
            await adapter.execute_cell({'template':'annual_changes','prepared':{
                'selected_sources':[source(2024),source(2025)],'generate_explanation':flag}},str(uuid4()),object())
        assert [r.generate_explanation for r in requests]==[False,True]
    asyncio.run(run())
