"""Export exact already saved successful versions, no new model or authority."""
import hashlib,json
from pathlib import Path
from uuid import uuid4
import httpx
from experiments.cplus.verify_real_agent_paths import digest
from experiments.cplus.real_model_paths import ledger
ROOT=Path(__file__).resolve().parents[2]

def main():
    output=ROOT/'data/cplus-g4-exact-exports-v2';output.mkdir()
    state=json.loads((ROOT/'data/cplus-private-session-pair-v1.json').read_text())
    pair=json.loads((ROOT/'docs/cplus/eval/results/agent-paired-e0115-continued-v1/result.json').read_text())
    draft=json.loads((ROOT/'data/cplus-g4-finish-v2/result.json').read_text())['chart_draft']['result']
    budget=Path('/Users/aipuli/.codex/worktrees/findoc-showcase-c-integration/findoc-agent/data/showcase-cost-control/provider-budget.db')
    proof={'tier':'REAL_HTTP_EXACT_SAVED_MODEL_REPORT_AND_CHART_FILES','budget_before':ledger(budget),'human_financial_approvals':0,'items':[]}
    items=[('chart-draft','chart_report_v1',draft)]+[('paired-'+c['mode'],'showcase_report_v2',c['saved_report']) for c in pair['cases']]
    with httpx.Client(base_url='http://127.0.0.1:14542/api',headers={'Origin':'http://127.0.0.1:14542'},trust_env=False,timeout=180) as c:
        for v in state['cookies']:c.cookies.set(v['name'],v['value'],domain=v['domain'],path=v['path'])
        try:
            for name,domain,snapshot in items:
                if domain=='chart_report_v1':
                    exact=c.get('/cplus/report-drafts/'+snapshot['report_id']);exact.raise_for_status();snapshot=exact.json();snapshot.pop('historical_snapshot',None);snapshot.pop('current_source_status',None)
                ref={'domain':domain,'id':snapshot['report_id'],'revision':1,'payload_sha256':digest(snapshot)}
                operation_id=str(uuid4());entry={'name':name,'ref':ref,'operation_id':operation_id,'files':[]};proof['items'].append(entry);(output/'result.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2))
                r=c.post('/cplus/exports',json={'operation_id':operation_id,'report_ref':ref,'formats':['csv','xlsx','pptx'],'export_profile_version':'research-v1'});entry['status']=r.status_code;r.raise_for_status();entry['receipt']=r.json();assert entry['receipt']['state']=='completed'
                for f in entry['receipt']['result']['files']:
                    response=c.get(f['href']);response.raise_for_status();data=response.content;assert hashlib.sha256(data).hexdigest()==f['sha256'];(output/(name+'.'+f['format'])).write_bytes(data);entry['files'].append(f)
                path=f"/cplus/export-snapshots/{domain}/{ref['id']}/revisions/1/print"
                response=c.get(path,params={'snapshot_sha256':ref['payload_sha256']});response.raise_for_status();(output/(name+'.html')).write_text(response.text);entry['print_status']=response.status_code
                print('PASS exact saved files and print',name,flush=True)
                (output/'result.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2))
            proof['result']='PASS'
        except Exception as exc:
            proof.update(result='FAIL',error_type=type(exc).__name__,safe_reason=str(exc).split('Call log:')[0][:300])
        finally:
            proof['budget_after']=ledger(budget);proof['zero_new_provider_calls']=proof['budget_before']==proof['budget_after'];(output/'result.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    print(proof['result'],proof.get('safe_reason',''))

if __name__=='__main__':main()
