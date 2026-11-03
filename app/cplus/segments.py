"""Explicit, immutable revenue-composition extraction over current public reports."""
import asyncio
from uuid import uuid4
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from app.financial_statements_v3.api import Collect
from app.financial_statements_v3.segments import extract_segments


def create_segments_router(statements, identity_provider, guard, validate):
    router=APIRouter(prefix='/cplus')

    @router.post('/segments')
    async def extract(payload: Collect,request: Request):
        try:
            identity=identity_provider(request)
            validate(identity)
            old=statements.reserve(payload.operation_id,['segments',payload.document_id,payload.expected_source_revision])
            if old:
                return statements.operation(payload.operation_id)
            source,cells=await statements.context(payload.document_id,payload.expected_source_revision)
            raw=await statements.sources.file(payload.document_id,source_revision=payload.expected_source_revision)
            value=await asyncio.to_thread(extract_segments,{**source,'workspace_id':identity.workspace_id},raw)
            value.update(id=str(uuid4()),financial_authority=False)
            fence={'selected_sources':[source]}
            with guard(identity,fence),statements.tx(source=True) as db:
                statements.guard(db,[(source,cells)])
                statements._record(db,'segments',value)
                statements.finish(db,payload.operation_id,value)
                validate(identity)
            return statements.operation(payload.operation_id)
        except Exception as exc:
            return JSONResponse({'detail':{'code':getattr(exc,'code','segments_unavailable')}},
                                status_code=getattr(exc,'status',409))

    @router.get('/segments/{result_id}')
    async def read(result_id: str,request: Request):
        try:
            validate(identity_provider(request))
            value=statements.read(result_id,'segments')
            try:
                await statements.sources.source(value['source']['document_id'],source_revision=value['source']['source_revision'])
                status='current'
            except Exception:
                status='stale_or_unavailable'
            return {**value,'current_source_status':status,'historical_snapshot':True}
        except Exception as exc:
            return JSONResponse({'detail':{'code':getattr(exc,'code','segments_unavailable')}},
                                status_code=getattr(exc,'status',409))
    return router
