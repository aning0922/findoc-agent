"""Independent synthesis after completed two-year deep job; no preparation replay."""
import json,os
from pathlib import Path
import httpx
from experiments.cplus.verify_real_agent_paths import PROJECT,Runner,SQLiteLedger,Window,StopRun,file_sha,public_budget


def main():
    predecessor=PROJECT/'docs/cplus/eval/results/interview-b-two-years-v1/result.json'
    prior=json.loads(predecessor.read_text());deep=prior['cases'][0]
    if (prior.get('stop',{}).get('reason')!='insufficient_physical_call_headroom_no_further_task_started'
        or len(prior['cases'])!=1 or deep.get('job',{}).get('state')!='completed'
        or any(r['state']!='returned' for r in prior['new_guard_rows'].values())):
        raise StopRun('predecessor_not_completed_deep_only')
    private=PROJECT/'data/cplus-private-session-interview-b-v1.json'
    fd=os.open(private,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd) as f:
        if os.fstat(f.fileno()).st_mode&0o077:raise StopRun('private_permissions')
        state=json.load(f)
    ledger=SQLiteLedger(Path('/Users/aipuli/.codex/worktrees/findoc-showcase-c-integration/findoc-agent/data/showcase-cost-control/provider-budget.db'))
    if public_budget(ledger.snapshot())!=prior['budget_after']:raise StopRun('shared_window_changed')
    out=PROJECT/'docs/cplus/eval/results/interview-b-two-years-synthesis-v1';out.mkdir()
    cases={c['id']:c for c in json.loads((PROJECT/'docs/cplus/eval/fixed-cases.json').read_text())['cases']}
    with httpx.Client(base_url='http://127.0.0.1:14540',headers={'Origin':'http://127.0.0.1:14540'},trust_env=False,timeout=100) as client:
        for v in state['cookies']:client.cookies.set(v['name'],v['value'],domain=v['domain'],path=v['path'])
        r=Runner(client,Window(ledger,5),out,tier='REAL_HTTP_TWO_YEAR_INTERVIEW_SYNTHESIS_AFTER_COMPLETED_DEEP',api_prefix='/api')
        r.proof.update(predecessor={'path':str(predecessor.relative_to(PROJECT)),'sha256':file_sha(predecessor),'successful_model_calls':prior['new_guard_rows_count']},combined_upper_new_calls=prior['new_guard_rows_count']+5,interview_scope_variant='two_explicit_report_years_not_the_single_2025_fixed_fixture')
        try:
            session=r.get('/demo/session');r.proof['session']=session
            if session['state']!='active' or session['lease_generation']!=prior['session']['lease_generation'] or session['expires_at']!=prior['session']['expires_at']:raise StopRun('owned_lease_changed')
            sources,pages=r.frozen_two_years()
            if sources!=prior['sources']:raise StopRun('two_year_sources_changed')
            r.run_case(cases['E01-15'],'synthesis',5,sources,pages)
            synthesis=r.proof['cases'][0]
            r.proof['comparison']={'question_equal':deep['exact_question']==synthesis['exact_question'],'frozen_sources_equal':deep['conversation']['sources']==synthesis['conversation']['sources'],'fact_selection_equal':deep['intent']['scope']['fact_selection_sha']==synthesis['intent']['scope']['fact_selection_sha'],'deep_report':deep['saved_report'],'synthesis_report':synthesis['saved_report'],'human_quality_preference':'pending_no_claim_multi_agent_is_better'}
            assert all(r.proof['comparison'][k] for k in ('question_equal','frozen_sources_equal','fact_selection_equal'))
            r.proof['execution']='COMPLETED_TWO_YEAR_INTERVIEW_COMPARISON_HUMAN_PENDING'
        except Exception as exc:r.proof.update(execution='STOPPED_WITH_RECEIPTS_NO_REPLAY',stop={'type':type(exc).__name__,'reason':str(exc)[:300]})
        finally:r.save()
        print(json.dumps({'execution':r.proof['execution'],'stop':r.proof.get('stop'),'budget_after':r.proof['budget_after'],'new_calls':r.proof['new_guard_rows_count']}))

if __name__=='__main__':main()
