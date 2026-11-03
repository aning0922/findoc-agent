"""Bounded real local HTTP regression: at most five explicitly requested model answers.

Uses the EXISTING session-wide ledger. Never creates an allowance or signs finance.
Failures/UNKNOWN are recorded; no operation is re-sent. Public PDFs only.
"""
import argparse
from decimal import Decimal
from pathlib import Path
import json
import sqlite3
import time
from uuid import uuid4

from dotenv import dotenv_values
import httpx
from app.retrieval_v2.service import sha


def ledger(path):
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
        rows=db.execute('SELECT reserved,state FROM calls').fetchall()
        return {'cap_cny':db.execute('SELECT cap FROM config WHERE id=1').fetchone()[0],
                'physical_calls':len(rows),'conservative_reserved_cny':str(sum((Decimal(r[0]) for r in rows),Decimal(0))),
                'unknown':sum(r[1]=='unknown' for r in rows),'actual_billed_cny':'not_observed'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--origin',default='http://127.0.0.1:14540')
    p.add_argument('--login-config',required=True,type=Path);p.add_argument('--existing-budget-db',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--no-provider-expected',action='store_true')
    p.add_argument('--explanations-only',action='store_true',help='Only checkup/annual/OCR: at most three new physical calls')
    p.add_argument('--annual-only',action='store_true',help='One new annual explanation after prompt-projection fix')
    args=p.parse_args();config=dotenv_values(args.login_config,interpolate=False)
    proof={'tier':'REAL_HTTP_PUBLIC_PDF_BGE_MILVUS_NO_PROVIDER' if args.no_provider_expected else 'REAL_HTTP_PUBLIC_PDF_BGE_MILVUS_PROVIDER','human_approvals':0,'cases':[],
           'budget_before':ledger(args.existing_budget_db),'max_expected_new_provider_calls':0 if args.no_provider_expected else 1 if args.annual_only else 3 if args.explanations_only else 5}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    def save():
        proof['budget_after']=ledger(args.existing_budget_db)
        if proof['budget_after']['physical_calls']-proof['budget_before']['physical_calls']>proof['max_expected_new_provider_calls']:
            raise RuntimeError('new_call_budget_exceeded')
        args.output.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    with httpx.Client(base_url=args.origin,timeout=180,trust_env=False,headers={'Origin':args.origin}) as c:
        def req(method,path,body=None):
            if method=='POST':body={'operation_id':str(uuid4()),**(body or {})}
            response=c.request(method,'/api'+path,json=body if body is not None else None)
            if response.status_code>=400:
                raise RuntimeError(f'{method} {path}: {response.status_code} {response.text[:600]}')
            return response.json()
        def case(name,fn):
            try:
                value=fn();proof['cases'].append({'id':name,'execution':'PASS','result':value});print('PASS',name,flush=True)
                save();return value
            except Exception as exc:
                proof['cases'].append({'id':name,'execution':'FAIL','error':str(exc)[:1000]});print('FAIL',name,str(exc)[:300],flush=True);save();return None
        for _ in range(180):
            if req('GET','/demo/status')['service_state']=='ready':break
            time.sleep(.5)
        login=req('POST','/demo/login',{'username':config['DEMO_USERNAME'],'password':config['DEMO_PASSWORD']})
        try:
            for _ in range(180):
                status=req('GET','/demo/operations/'+login['operation_id'])
                if status.get('claimable'):break
                time.sleep(.5)
            req('POST','/demo/claim',{'attempt_operation_id':login['operation_id']})
            proof['generation']=req('GET','/demo/session')['lease_generation']
            companies=req('GET','/companies');gree=next(x for x in companies if x['security_code']=='000651')
            documents=req('GET','/documents');fast=[];collections=[]
            for d in documents:
                if d['status']!='ready':continue
                ref=req('GET',f"/cplus/documents/{d['document_id']}/research-source");fast.append(ref)
                value=case('collect-'+str(ref['report_year'])+'-'+ref['company_id'][:8],lambda ref=ref:req('POST','/cplus/financial/collections',{'document_id':ref['document_id'],'expected_source_revision':ref['source_revision']}))
                if value:collections.append(value)
            for offset in range(0,len(fast),4):
                case('build-fast-fts-'+str(offset//4+1),lambda offset=offset:req('POST','/cplus/retrieval/builds',{'sources':fast[offset:offset+4]}))
            grefs=sorted((r for r in fast if r['company_id']==gree['company_id']),key=lambda r:r['report_year'])
            core=['revenue','net_profit_parent','operating_cash_flow','total_assets','total_liabilities']
            def selection(collection):
                year=collection['source']['report_year'];picked=[]
                for metric in core:
                    items=[v for v in collection['cells'] if v['metric_key']==metric and v['extraction_status']=='candidate'
                           and ((v['time']['kind']=='instant' and v['time']['as_of_date']==f'{year}-12-31') or
                           (v['time']['kind']=='duration' and v['time']['period_start']==f'{year}-01-01' and v['time']['period_end']==f'{year}-12-31'))]
                    if len(items)==1:picked.append(items[0]['cell_id'])
                return {'collection_id':collection['id'],'cell_ids':picked}
            gcols=[v for v in collections if v['source']['company_id']==gree['company_id']]
            selected=[selection(v) for v in gcols]
            case('real-candidate-trends',lambda:req('POST','/cplus/financial/trend-projections',{'collection_refs':selected,'metric_keys':core,'candidate_view':True}))
            check=case('real-three-rule-checkup',lambda:req('POST','/cplus/checkups',{'collection_refs':selected,'candidate_view':True,'generate_explanation':False}))
            if check and not args.annual_only:
                case('real-model-checkup-explanation',lambda:req('POST','/cplus/checkup-explanations',{'checkup_id':check['id'],'expected_payload_sha256':sha(check),'confirmed':True}))
            # One current annual filing from each company, explicit comparable current-year cells.
            peers=[v for v in collections if v['source']['report_year']==2025 and v['source']['company_id'] in {c['company_id'] for c in companies if c['security_code'] in ('000651','000333')}]
            case('real-candidate-peer',lambda:req('POST','/cplus/peer-comparisons',{'company_ids':[v['source']['company_id'] for v in peers],'collection_refs':[selection(v) for v in peers],'candidate_view':True}))
            case('real-revenue-segments',lambda:req('POST','/cplus/segments',{'document_id':grefs[-1]['document_id'],'expected_source_revision':grefs[-1]['source_revision']}))
            case('real-model-annual-diff',lambda:req('POST','/cplus/annual-diffs',{'left_source':grefs[0],'right_source':grefs[-1],'topics':['经营风险','主要业务','研发'],'generate_explanation':True}))
            # Same baseline questions; retrieval executions cost no provider request.
            for q in ['格力2025年的主要经营风险是什么','原材料价格风险有哪些','市场竞争风险有哪些','海外经营风险有哪些','主要业务有哪些','经营现金流变化情况']:
                case('retrieval-after:'+q,lambda q=q:req('POST','/cplus/retrieval/searches',{'sources':[grefs[-1]],'query':q,'top_k':5}))
            for name,question in ([] if (args.explanations_only or args.annual_only) else [('risk','请概括主要经营风险并给出原文依据。'),('cash','经营现金流变化有哪些原文说明？')]):
                context=req('POST','/cplus/research/contexts',{'title':name,'selected_sources':[grefs[-1]]})['result']
                case('real-model-answer-'+name,lambda context=context,question=question:req('POST','/cplus/research/answers',{'context_id':context['context_id'],'context_revision':context['revision'],'context_sha256':context['context_sha256'],'question':question}))
            if not args.annual_only:
                scan=next(d for d in documents if d['status']=='failed')
                quality=req('GET',f"/documents/{scan['document_id']}/parse-quality")
                ref=req('POST','/cplus/research/enrollments',{'document_id':scan['document_id'],'artifact_id':quality['artifact_id'],'expected_source_revision':quality['source_revision'],'expected_artifact_sha256':quality['output_sha256'],'selected_pages':[1],'confirmed':True})['result']['source_ref']
                req('POST','/cplus/retrieval/builds',{'sources':[ref]})
                context=req('POST','/cplus/research/contexts',{'title':'OCR转录研究','selected_sources':[ref]})['result']
                case('real-model-ocr-answer',lambda:req('POST','/cplus/research/answers',{'context_id':context['context_id'],'context_revision':context['revision'],'context_sha256':context['context_sha256'],'question':'营业收入。只解读所选OCR转录，不确认财务金额。'}))
            proof['result']='PASS_HTTP_EXECUTION_ONLY' if all(v['execution']=='PASS' for v in proof['cases']) else 'PARTIAL'
            proof['real_provider_successes']=sum(bool((v.get('result') or {}).get('result',{}).get('interpretation')) or (v.get('result') or {}).get('result',{}).get('provider_outcome')=='returned' for v in proof['cases'])
            if args.no_provider_expected and ledger(args.existing_budget_db)['physical_calls']!=proof['budget_before']['physical_calls']:
                raise RuntimeError('unexpected_provider_call')
            save()
        finally:
            try:req('POST','/demo/logout')
            except Exception as exc:proof['cleanup_error']=str(exc)[:300]
            save()


if __name__=='__main__':main()
