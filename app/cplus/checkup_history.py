"""Read-only checkup identity projection for the explicit AI explanation UI."""
import json
from fastapi import APIRouter
from app.finance_v2.api import FinanceRoute
from app.retrieval_v2.service import sha


def create_checkup_history_router(statements):
    router=APIRouter(prefix='/cplus',route_class=FinanceRoute)

    @router.get('/companies/{company_id}/checkups')
    async def history(company_id:str):
        statements.companies.get(company_id)
        with statements.tx() as db:
            values=[json.loads(row[0]) for row in db.execute("SELECT payload FROM records WHERE kind='checkup'")]
        items=[]
        for value in values:
            refs=value['collection_refs']
            collections=[statements.read(r['collection_id'] if isinstance(r,dict) else r,'collection') for r in refs]
            if {c['source']['company_id'] for c in collections}!={company_id}:
                continue
            try:
                await statements.selected(refs)
                status='current'
            except Exception:
                status='stale_or_unavailable'
            items.append({'checkup_id':value['id'],'payload_sha256':sha(value),'rules':value['rules'],
                          'candidate_view':value['candidate_view'],'current_source_status':status})
        return {'schema_version':'checkup-history-v1','items':items}
    return router
