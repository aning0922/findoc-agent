"""Read-only checks of this round's live identities; never accept or resume."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3

import httpx

from scripts.run_d29_d_browser import GOLD


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--evidence', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    qa = sorted((args.evidence / 'qa-real').glob('[AR][0-9][0-9].json'))
    assert len(qa) == 18
    result = []
    with httpx.Client(base_url='http://127.0.0.1:14280/api', timeout=60, trust_env=False) as c:
        for path in qa:
            item = json.loads(path.read_text())
            run = item['response']
            assert item['http_status'] == 200
            response = c.get('/research/runs/' + run['run_id'])
            response.raise_for_status()
            assert response.json() == run
            events = item['events']
            counts = Counter(x['kind'] for x in events)
            projection = c.get('/research/runs/' + run['run_id'] + '/focus')
            projection.raise_for_status()
            focus = projection.json()
            assert focus['run_id'] == run['run_id']
            if path.stem.startswith('A'):
                index = int(path.stem[1:]) - 1
                assert run['status'] == 'answered'
                assert counts['provider'] == counts['provider_http'] == counts['retrieve'] == counts['milvus_search'] == counts['bge'] == 1
                assert focus['status'] == 'located'
                assert (focus['focus']['raw_value'],focus['focus']['raw_unit']) == GOLD[index]
                assert run['result']['human_review'] == 'pending'
            else:
                assert run['status'] == 'refused'
                assert all(counts[k] == 0 for k in ['provider','provider_http','retrieve','milvus_search','bge'])
                assert not run['result']['citations'] and not run['result']['content']
            (args.out / (path.stem+'-focus.json')).write_text(json.dumps(focus,ensure_ascii=False,indent=2)+'\n')
            result.append(dict(case=path.stem, run_id=run['run_id'], status=run['status'],
                               exact_http_sha256=hashlib.sha256(response.content).hexdigest(),
                               focus=focus['status'], event_counts=dict(counts), human_result='not_reviewed'))
    events = [json.loads(line) for line in (args.root / 'events.jsonl').read_text().splitlines()]
    confirmations = [x for x in events if x.get('kind') == 'http' and x.get('method') == 'POST'
                     and x.get('path') in ('/financial-facts/confirmations','/financial-facts/persisted')]
    # These counts describe the observed root, not authentication of a human actor.
    with sqlite3.connect(f'file:{args.root.resolve()}/runtime/documents.db?mode=ro', uri=True) as db:
        counts = {name: db.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]
                  for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
                  if name.startswith(('financial_', 'report_'))}
    summary = dict(qa=result, real_provider_calls=12, real_retrievals=12,
                   automatic_value_checks=12, human_semantic_acceptance='pending',
                   observed_confirmation_or_persistence_posts=confirmations, table_counts=counts,
                   historical_acceptances_imported=False, simulated_acceptances_created=False)
    (args.out / 'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print('18 real runs / 12 C1 raw-cell checks; human semantic results remain pending')


if __name__ == '__main__':
    main()
