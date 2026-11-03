"""Continue one known successful pre-job plan, never replay its paid preparation.

Operator only. The predecessor stopped on a harness-only role assertion and
contains exactly two returned SDK attempts, no job acknowledgement or unknown
mutation. Its own still-active private session is required unchanged.
"""
from datetime import datetime, UTC
import json
import os
from pathlib import Path

import httpx
from experiments.cplus.verify_real_agent_paths import (
    PROJECT, Runner, SQLiteLedger, StopRun, Window, digest, file_sha, public_budget,
)


def main():
    predecessor=PROJECT/'docs/cplus/eval/results/agent-paired-e0115-v1/result.json'
    prior=json.loads(predecessor.read_text())
    prepared=prior['cases'][0]
    if (prior.get('stop',{}).get('reason')!='plan_not_model_validated_or_role_scope_changed'
        or prior['new_guard_rows_count']!=2 or len(prior['cases'])!=1
        or prepared.get('job_ack') or any(r['state']!='returned' for r in prior['new_guard_rows'].values())
        or any(op['path'].endswith('/jobs') for op in prior['operations'])
        or any(op['state']!='RESPONSE_RECEIVED' for op in prior['operations'])):
        raise StopRun('predecessor_not_known_successful_pre_job_only')
    private=PROJECT/'data/cplus-private-session-pair-v1.json'
    descriptor=os.open(private,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(descriptor) as stream:
        if os.fstat(stream.fileno()).st_mode & 0o077:
            raise StopRun('private_owned_session_permissions')
        state=json.load(stream)
    ledger=SQLiteLedger(Path('/Users/aipuli/.codex/worktrees/findoc-showcase-c-integration/findoc-agent/data/showcase-cost-control/provider-budget.db'))
    if public_budget(ledger.snapshot())!=prior['budget_after']:
        raise StopRun('shared_window_changed_do_not_guess')
    output=PROJECT/'docs/cplus/eval/results/agent-paired-e0115-continued-v1'
    output.mkdir()  # no overwrite or automatic rerun
    cases={c['id']:c for c in json.loads((PROJECT/'docs/cplus/eval/fixed-cases.json').read_text())['cases']}
    origin='http://127.0.0.1:14542'
    with httpx.Client(base_url=origin,headers={'Origin':origin},trust_env=False,timeout=httpx.Timeout(100,connect=3)) as client:
        for c in state['cookies']:
            client.cookies.set(c['name'],c['value'],domain=c['domain'],path=c['path'])
        runner=Runner(client,Window(ledger,10),output,tier='OPERATOR_REAL_HTTP_EXISTING_SUCCESSFUL_PLAN_CONTINUATION',api_prefix='/api')
        runner.proof.update(predecessor={'path':str(predecessor.relative_to(PROJECT)),'sha256':file_sha(predecessor),'returned_preparation_calls':2},combined_new_calls_upper=12)
        try:
            session=runner.get('/demo/session')
            if session['state']!='active' or session['lease_generation']!=prior['session']['lease_generation'] or session['expires_at']!=prior['session']['expires_at'] or (datetime.fromisoformat(session['expires_at'])-datetime.now(UTC)).total_seconds()<360:
                raise StopRun('same_owned_lease_insufficient_no_reset_or_takeover')
            runner.proof['session']=session
            source,pages=runner.frozen_source()
            if source!=prior['source']:
                raise StopRun('source_changed')
            # The original plan identity and original no-active-turn conversation
            # must still exist before its first explicit job approval.
            current=runner.get('/conversations/'+prepared['conversation']['conversation_id'])
            if current['sources']!=prepared['conversation']['sources'] or current.get('active_turn_id'):
                raise StopRun('prepared_conversation_changed')
            runner.run_case(cases['E01-15'],'deep',10,source,pages,prepared=prepared)
            runner.run_case(cases['E01-15'],'synthesis',5,source,pages)
            a,b=runner.proof['cases']
            runner.proof['paired_same_question_comparison']=a['exact_question']==b['exact_question'] and a['conversation']['sources']==b['conversation']['sources']
            runner.proof['execution']='COMPLETED_REQUESTED_HTTP_PATHS_NOT_HUMAN_ANSWER_ACCEPTANCE'
        except Exception as exc:
            runner.proof.update(execution='STOPPED_WITH_RECEIPTS_NO_REPLAY',stop={'type':type(exc).__name__,'reason':str(exc)[:400]})
        finally:
            runner.save()
        print(json.dumps({'execution':runner.proof['execution'],'stop':runner.proof.get('stop'),'new_guard_rows':runner.proof['new_guard_rows_count'],'budget_after':runner.proof['budget_after']}))

if __name__=='__main__':
    main()
