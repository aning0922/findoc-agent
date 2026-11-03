"""Root-only one-call native validation of the new non-numeric template policy."""
import json,os,subprocess,time
from pathlib import Path
from uuid import uuid4
import httpx
from dotenv import dotenv_values
from experiments.cplus.verify_real_agent_paths import PROJECT,Runner,SQLiteLedger,Window,StopRun,file_sha


def main():
    budget=Path('/Users/aipuli/.codex/worktrees/findoc-showcase-c-integration/findoc-agent/data/showcase-cost-control/provider-budget.db')
    output=PROJECT/'docs/cplus/eval/results/template-numeric-policy-real-v1';output.mkdir()
    cfg=dotenv_values(PROJECT/'data/cplus-agent-login.env',interpolate=False)
    with httpx.Client(base_url='http://127.0.0.1:14540',headers={'Origin':'http://127.0.0.1:14540'},trust_env=False,timeout=100) as client:
        runner=Runner(client,Window(SQLiteLedger(budget),1),output,tier='REAL_NATIVE_TWO_YEAR_TEMPLATE_NON_NUMERIC_POLICY',api_prefix='/api',private_session_file=PROJECT/'data/cplus-private-session-corrected-v1.json')
        try:
            runner.login(cfg['DEMO_USERNAME'],cfg['DEMO_PASSWORD']);runner.window.admit(1)
            command=['/Users/aipuli/.nvm/versions/node/v24.19.0/bin/node','frontend/e2e/cplus-final-business-native.mjs']
            child=subprocess.run(command,cwd=PROJECT,env={**os.environ,'CPLUS_CORRECTED_FINAL':'1'},capture_output=True,text=True,timeout=420)
            runner.proof['native_stdout']=child.stdout[-1000:]
            runner.proof['native_exit']=child.returncode
            path=PROJECT/'data/cplus-final-business-native-corrected-v1/result.json'
            native=json.loads(path.read_text());runner.proof['native_proof']={'path':str(path.relative_to(PROJECT)),'sha256':file_sha(path),'result':native['result'],'checks':len(native['checks'])}
            run=native['template_receipt']['result'];runner.proof['template_receipt']=native['template_receipt'];runner.proof['interpretation_published']=bool(run.get('interpretation'))
            added=runner.window.delta()
            assert len(added)==1 and all(v['state']=='returned' for v in added.values())
            assert native['result']=='PASS' and run['interpretation_policy']=='non_numeric_review_v1'
            assert run['provider_outcome'] in ('returned','numeric_claim_requires_review')
            runner.proof['execution']='PASS_REAL_PROVIDER_NATIVE_NON_NUMERIC_POLICY_HUMAN_PENDING'
        except Exception as exc:
            runner.proof.update(execution='STOPPED_WITH_RECEIPTS_NO_REPLAY',stop={'type':type(exc).__name__,'reason':str(exc).split('Call log:')[0][:400]})
        finally:
            try:
                response=client.post('/api/demo/logout',json={'operation_id':str(uuid4())});runner.proof['logout_http_status']=response.status_code
                runner.proof['old_session_http_status']=client.get('/api/demo/session').status_code
                for _ in range(120):
                    state=client.get('/api/demo/status').json()['service_state']
                    if state=='ready':break
                    time.sleep(.5)
                runner.proof['controller_after']=state
            except Exception as exc:runner.proof['cleanup_error_type']=type(exc).__name__
            runner.save()
        print(json.dumps({'execution':runner.proof['execution'],'stop':runner.proof.get('stop'),'new_calls':runner.proof['new_guard_rows_count'],'budget_after':runner.proof['budget_after'],'interpretation_published':runner.proof.get('interpretation_published'),'logout':runner.proof.get('logout_http_status'),'controller_after':runner.proof.get('controller_after')},ensure_ascii=False))

if __name__=='__main__':main()
