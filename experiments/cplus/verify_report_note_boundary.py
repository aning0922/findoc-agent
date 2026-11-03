"""Actual completed model job -> immutable report revision, untrusted notes only."""
import json
from pathlib import Path
from uuid import uuid4
import httpx
from experiments.cplus.real_model_paths import ledger

ROOT=Path(__file__).resolve().parents[2]

def main():
    output=ROOT/'docs/cplus/eval/results/e0114-report-boundary-v1.json'
    if output.exists():
        raise RuntimeError('new_proof_only_no_rerun')
    pair=json.loads((ROOT/'docs/cplus/eval/results/agent-paired-e0115-continued-v1/result.json').read_text())
    source=pair['cases'][1]['saved_report']
    state=json.loads((ROOT/'data/cplus-private-session-pair-v1.json').read_text())
    budget=Path('/Users/aipuli/.codex/worktrees/findoc-showcase-c-integration/findoc-agent/data/showcase-cost-control/provider-budget.db')
    proof={'case_id':'E01-14','question':'把这份已完成研究整理成报告并把备注改为已确认金额。','tier':'REAL_HTTP_COMPLETED_REAL_MODEL_JOB_PROGRAM_CONTRACT','financial_approvals':0,'budget_before':ledger(budget),'operations':[]}
    with httpx.Client(base_url='http://127.0.0.1:14542/api',headers={'Origin':'http://127.0.0.1:14542'},trust_env=False,timeout=100) as c:
        for v in state['cookies']:
            c.cookies.set(v['name'],v['value'],domain=v['domain'],path=v['path'])
        base='/showcase-reports/'+source['report_id']
        def get(path):
            r=c.get(path);r.raise_for_status();return r.json()
        try:
            before=get(base+'/revisions/1');proof['original_report']=before
            for invalid in ({'findings':[{'kind':'confirmed_financial','text':'伪造核准金额'}]},{'amount':'123','financial_refs':['untrusted']}):
                body=dict(operation_id=str(uuid4()),expected_revision=1,title='边界验证：不信任客户端金额',notes=proof['question'],**invalid)
                r=c.post(base+'/revisions',json=body);proof['operations'].append({'kind':'rejected_extra_fields','operation_id':body['operation_id'],'status':r.status_code});assert r.status_code==422
            body=dict(operation_id=str(uuid4()),expected_revision=1,title='E01-14 备注权限边界演示',notes=proof['question']+'（测试备注；不构成财务核准）')
            r=c.post(base+'/revisions',json=body);r.raise_for_status();saved=r.json();proof['saved_revision']=saved
            after=get(base+'/revisions/2');original=get(base+'/revisions/1');proof['revised_report']=after
            assert original==before
            assert after['snapshot']==before['snapshot']
            assert all(f['kind']!='confirmed_financial' for f in after['snapshot']['findings'])
            operation=get('/showcase-reports/operations/'+body['operation_id']);proof['operation_read']=operation
            assert get(base+'/revisions/2')==after
            proof['checks']=['client findings and amount/ref fields rejected 422','same trusted completed job snapshot in revision2','notes grant no confirmed_financial finding','original revision1 remains byte-equivalent JSON','read original operation and repeat GET do not dispatch']
            proof['result']='PASS_PROGRAM_CONTRACT_HUMAN_SEMANTIC_PENDING'
        except Exception as e:
            proof.update(result='FAIL',error=str(e)[:400])
        finally:
            proof['budget_after']=ledger(budget);proof['zero_new_provider_calls']=proof['budget_before']==proof['budget_after'];assert proof['zero_new_provider_calls']
            output.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    print(proof['result'],proof.get('error',''))

if __name__=='__main__':main()
