"""Resolve chart points to immutable statement cells without granting finance authority."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from app.retrieval_v2.models import FinancialFocus, RetrievalError


class FinancialFocusService:
    def __init__(self,statements,preparer):
        self.statements,self.preparer=statements,preparer

    def verify(self,value,selected_sources):
        focus=FinancialFocus.model_validate(value)
        collection=self.statements.read(focus.collection_id,'collection')
        cells=[c for c in collection['cells'] if c['cell_id']==focus.cell_id]
        if len(cells)!=1:
            raise RetrievalError('focus_cell_changed')
        cell=cells[0]
        for key in ('cell_revision','payload_sha256','metric_key','time','normalized_decimal','normalized_unit'):
            if cell[key]!=getattr(focus,key):
                raise RetrievalError('focus_cell_changed')
        if (focus.source_ref.kind!='fast' or not any(focus.source_ref==r for r in selected_sources)
                or any(collection['source'][k]!=getattr(focus.source_ref,k) for k in (
                    'company_id','document_id','source_revision','content_sha256','parser_version','report_year',
                    'attempt','report_type','period_start','period_end','basis'))):
            raise RetrievalError('focus_source_changed')
        return focus

    async def resolve(self,cell_id,revision,payload_sha256):
        with self.statements.tx() as db:
            ids=[r[0] for r in db.execute("SELECT id FROM records WHERE kind='collection'")]
        matches=[]
        for identifier in ids:
            collection=self.statements.read(identifier,'collection')
            for cell in collection['cells']:
                if (cell['cell_id']==cell_id and cell['cell_revision']==revision
                        and cell['payload_sha256']==payload_sha256):
                    matches.append((collection,cell))
        if not matches:
            raise RetrievalError('focus_cell_not_found',404)
        collection,cell=matches[0]
        # Repeated extraction of an identical cell is permitted; different bytes are not.
        if any(c!=cell or x['source']!=collection['source'] for x,c in matches):
            raise RetrievalError('focus_cell_ambiguous')
        await self.statements.selected([{'collection_id':collection['id'],'cell_ids':[cell_id]}])
        selection=await self.preparer.prepare_many(document_ids=[collection['source']['document_id']],query='只读核验图表点位')
        from .runtime import fast_ref
        value=FinancialFocus(schema_version='financial-point-focus-v1',collection_id=collection['id'],
                             cell_id=cell_id,source_ref=fast_ref(selection.documents[0]),
                             **{k:cell[k] for k in ('cell_revision','payload_sha256','metric_key','time',
                                                  'normalized_decimal','normalized_unit')})
        self.verify(value.model_dump(),[value.source_ref])
        return value.model_dump()


def create_focus_router(service,identity_provider,validate):
    router=APIRouter(prefix='/cplus')
    @router.get('/financial/cells/{cell_id}/research-focus')
    async def focus(cell_id:str,revision:int,payload_sha256:str,request:Request):
        try:
            validate(identity_provider(request))
            value=await service.resolve(cell_id,revision,payload_sha256)
            validate(identity_provider(request))
            return value
        except Exception as exc:
            return JSONResponse({'detail':{'code':getattr(exc,'code','focus_unavailable')}},status_code=getattr(exc,'status',409))
    return router
