"""Withheld template subanswers remain auditable but cannot bypass the parent report gate."""
from uuid import uuid4
from types import SimpleNamespace
import sqlite3

from app.exports_v2.projection import digest
from app.retrieval_v2.service import sha
from tests.test_cplus_g4_templates_drafts import rig as rig, run_template


def test_quarantined_child_is_not_a_standalone_report_but_raw_audit_survives(rig, monkeypatch):
    _, client, templates, _, refs, _ = rig
    legacy=templates.store.path.parent/'empty-report-test.db'
    with sqlite3.connect(legacy) as db:
        db.executescript('CREATE TABLE reports(id TEXT,workspace TEXT);CREATE TABLE revisions(report_id TEXT,revision INTEGER,payload TEXT);')
    client.app.state.showcase_report_service=SimpleNamespace(path=legacy)
    calls=[]

    async def fake_once(question,evidence):
        calls.append(question)
        return {'text':'2024年现金流为46383114754.02元。'}

    monkeypatch.setattr(templates.hybrid,'provider',fake_once)
    body,result=run_template(rig,'cash',refs[:2],generate_explanation=True)
    assert result['provider_outcome']=='numeric_claim_requires_review' and result['interpretation'] is None
    child=next(c for c in templates.children(body['operation_id']) if c['label']=='explanation-once')
    answer=client.get('/cplus/research/answers/'+child['result_ref'])
    assert answer.status_code==200 and '2024' in answer.json()['interpretation']
    # Internal child is not a second business report, including direct export.
    query={'domain':'research_answer_v1','identifier':child['result_ref'],'revision':1}
    listing=client.get('/cplus/export-snapshots',params=query)
    assert listing.status_code==200 and listing.json()['items']==[]
    raw=templates.hybrid.read('answer',child['result_ref'],sha(rig[-1].model_dump()))
    exported=client.post('/cplus/exports',json={'operation_id':str(uuid4()),'report_ref':{
        'domain':'research_answer_v1','id':child['result_ref'],'revision':1,'payload_sha256':digest(raw)},
        'formats':['csv'],'export_profile_version':'research-v1'})
    assert exported.status_code==409 and exported.json()['detail']['code']=='template_child_is_not_report'
    parent=client.get('/cplus/export-snapshots',params={'domain':'template_run_v1','identifier':result['run_id'],'revision':1})
    assert parent.status_code==200 and len(parent.json()['items'])==1
    assert len(calls)==1
