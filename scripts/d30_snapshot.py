"""Fingerprint exact history and business tables through a real stop/restart."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3

import httpx


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--evidence', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--compare', type=Path)
    p.add_argument('--include-accepted-reports', action='store_true',
                   help='also fingerprint this round\'s owner facts, resume operations and real reports')
    args = p.parse_args()
    assert json.loads((args.root/'d30-root.json').read_text())['schema']=='d30-clean-root-v1'
    paths = ['/companies','/research/runs','/research/tasks','/reports']
    for r in json.loads((args.evidence/'live-preparation/reports.json').read_text()):
        paths.append('/documents/'+r['document_id']+'/source')
    for f in sorted((args.evidence/'qa-real').glob('[AR][0-9][0-9].json')):
        paths.append('/research/runs/'+json.loads(f.read_text())['response']['run_id'])
    for f in sorted((args.evidence/'waiting-tasks').glob('*.json')):
        value=json.loads(f.read_text())
        if 'task' in value:
            paths.append('/research/tasks/'+value['task']['task_id'])
    if args.include_accepted_reports:
        followup = args.evidence/'human-followup'
        finance = json.loads((followup/'four-report-twelve-facts-saved.json').read_text())
        assert finance['reports'] == 4 and finance['facts'] == 12
        for receipt in sorted({r['receipt_id'] for r in finance['rows']}):
            paths.extend(['/financial-facts/acceptances/'+receipt,
                          '/financial-facts/persisted/'+receipt])
        groups = [json.loads((followup/(name+'-user-saved.json')).read_text())
                  ['persisted_get']['body']
                  for name in ('midea-2024','midea-2025','gree-2024','gree-2025')]
        for company in sorted({group['company_id'] for group in groups}):
            paths.append('/financial-facts?company_id='+company)
        for name in ('midea', 'gree', 'dual-2025'):
            completed = json.loads((followup/(name+'-user-resume-completed-proof.json')).read_text())
            paths.append('/research/tasks/by-operation/'+completed['resume_operation_id'])
        reports = json.loads((args.evidence/'reports-real-final/summary.json').read_text())
        assert reports['reports'] == 3 and reports['revisions'] == 6
        for report in reports['cases']:
            for revision in (1,2):
                path = f'/reports/{report["report_id"]}/revisions/{revision}'
                paths.extend([path, path+'/markdown'])
                paths.append('/reports/by-operation/'+report[f'operation_v{revision}'])
    def events():
        return [json.loads(line) for line in (args.root/'events.jsonl').read_text().splitlines()]
    start=len(events())
    http={}
    with httpx.Client(base_url='http://127.0.0.1:14280/api',timeout=60,trust_env=False) as c:
        for path in paths:
            response=c.get(path)
            response.raise_for_status()
            http[path]=digest(response.content)
    during=events()[start:]
    assert not [x for x in during if x['kind'] in ('bge','provider','provider_http','retrieve','milvus_search')]
    assert all(x.get('method')=='GET' for x in during if x['kind']=='http')
    tables={}
    for name in ('documents.db','agent-runs.db'):
        path=args.root/'runtime'/name
        if not path.exists():
            continue
        with sqlite3.connect(f'file:{path.resolve()}?mode=ro',uri=True) as db:
            tables[name]={}
            for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
                rows=sorted(db.execute(f'SELECT * FROM "{table}"').fetchall(),key=str)
                tables[name][table]=dict(rows=len(rows),sha256=digest(json.dumps(rows,default=str).encode()))
    result=dict(exact_http=http,business_tables=tables,
                objects={str(f.relative_to(args.root/'runtime/objects')):digest(f.read_bytes())
                         for f in sorted((args.root/'runtime/objects').rglob('*')) if f.is_file()},
                get_interval_model_retrieval_embedding_calls=0,
                current_session=json.loads((args.root/'active-session.json').read_text())['session'],
                startup_bge_events=len([x for x in events() if x['kind']=='bge' and x.get('request')=='startup']))
    if args.compare:
        before=json.loads(args.compare.read_text())
        assert before['current_session']!=result['current_session']
        for key in ('exact_http','business_tables','objects'):
            assert before[key]==result[key],key
        assert result['startup_bge_events']==before['startup_bge_events']+1
        result['restart_verified']=True
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(exact_gets=len(http),tables=sum(len(t) for t in tables.values()),
                          restart_verified=result.get('restart_verified',False))))


if __name__=='__main__':
    main()
