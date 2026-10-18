"""Create explicit D30 report examples after owner finance gates; no model/accept/resume.

Every POST intent is saved before transmission. On an unknown response, inspect its
operation with GET; this command never retries a write automatically. The example
titles are authored by Codex for version testing, not owner semantic approvals.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import urllib.request
import uuid


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--task-map', type=Path,
                        help='JSON mapping midea/gree/dual-2025 to new owner-completed Task IDs')
    parser.add_argument('--create-report-examples', action='store_true', required=True)
    args = parser.parse_args()
    root, out = args.root.resolve(), args.out.resolve()
    if json.loads((root/'d30-root.json').read_text())['schema'] != 'd30-clean-root-v1':
        raise ValueError('not a D30 independent root')
    out.mkdir(parents=True, exist_ok=False)

    def write(name, value):
        (out/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')

    def request(path, payload=None, name=None):
        if payload is not None:
            if not (path == '/reports' or path == '/reports/drafts'
                    or path.startswith('/reports/') and path.endswith('/revisions')):
                raise ValueError('only report writes are allowed')
            write(name+'-request.json', dict(method='POST', path=path, payload=payload,
                  actor='Codex, authorized D30 report version verification'))
        req = urllib.request.Request('http://127.0.0.1:18180'+path,
              data=json.dumps(payload).encode() if payload is not None else None,
              headers={'Content-Type': 'application/json'} if payload is not None else {})
        with urllib.request.urlopen(req, timeout=60) as response:
            raw, headers = response.read(), dict(response.headers)
        if name:
            (out/(name+'.json')).write_bytes(raw)
        return json.loads(raw), headers

    def download(report_id, revision, name, payload_sha):
        path = f'/reports/{report_id}/revisions/{revision}/markdown'
        with urllib.request.urlopen('http://127.0.0.1:18180'+path, timeout=60) as response:
            raw = response.read()
            headers = {k.lower(): v for k, v in response.headers.items()}
        assert headers['x-report-id'] == report_id
        assert headers['x-report-revision'] == str(revision)
        assert headers['x-report-payload-sha256'] == payload_sha
        assert headers['x-markdown-sha256'] == sha(raw)
        assert headers['x-markdown-renderer'] == 'trusted-markdown-v1'
        assert headers['x-report-eligibility'] == 'qualified_at_export'
        (out/(name+'.md')).write_bytes(raw)
        write(name+'-headers.json', headers)
        return sha(raw)

    def events():
        return [json.loads(line) for line in (root/'events.jsonl').read_text().splitlines()]

    start = len(events())
    history, _ = request('/reports?limit=50')
    cases = [('midea', '296eaa6e-8360-40b3-b09a-2ed9c6bf235d'),
             ('gree', 'bb7e453e-40fc-4b62-a2aa-9ad67914048e'),
             ('dual-2025', 'a2d6c967-ba1e-4505-b612-bb66f3067cfa')]
    if args.task_map:
        selected = json.loads(args.task_map.read_text())
        if set(selected) != {name for name, _ in cases}:
            raise ValueError('task map must select exactly midea, gree and dual-2025')
        for task_id in selected.values():
            if str(uuid.UUID(task_id)) != task_id:
                raise ValueError('task IDs must be canonical UUIDs')
        cases = [(name, selected[name]) for name, _ in cases]
    if any(item['task_id'] in {t for _, t in cases} for item in history['items']):
        raise ValueError('D30 report examples already exist; inspect original operations')
    results = []
    for name, task_id in cases:
        task, _ = request('/research/tasks/'+task_id)
        assert task['status'] == 'completed' and task['revision'] == 4
        assert task['final_research_content']['test_mode'] is None
        draft, _ = request('/reports/drafts', dict(task_id=task_id, expected_revision=4),
                           name+'-draft')
        assert draft['status'] == 'qualified_draft' and draft['test_mode'] is None
        assert draft['human_review_status'] == 'pending'
        assert not draft['verified_operating_attribution']
        task_fact_ids = {r['fact']['fact_id'] for r in task['final_research_content']['financial_facts']}
        assert {r['fact_id'] for r in draft['financial_facts']} == task_fact_ids
        operation_v1 = str(uuid.uuid4())
        save = dict(operation_id=operation_v1, task_id=task_id,
                    expected_task_revision=4, edits={})
        v1, _ = request('/reports', save, name+'-v1')
        report_id = v1['report']['report_id']
        assert v1['report']['revision'] == 1
        before_v2 = download(report_id, 1, name+'-v1-before-v2', v1['payload_sha256'])
        operation_v2 = str(uuid.uuid4())
        append = dict(operation_id=operation_v2, task_id=task_id,
                      expected_task_revision=4, expected_report_revision=1,
                      edits=dict(title=draft['title']+' · D30 版本对照示例', conclusions=[]))
        v2, _ = request(f'/reports/{report_id}/revisions', append, name+'-v2')
        assert v2['report']['revision'] == 2 and v2['report']['parent_revision'] == 1
        a, b = v1['report']['trusted_snapshot'], v2['report']['trusted_snapshot']
        for key in ('source_content_sha256', 'business_content_sha256', 'financial_facts',
                    'financial_analysis', 'operating_information', 'model_interpretations'):
            assert a[key] == b[key], key
        assert b['human_review_status'] == 'pending' and b['test_mode'] is None
        assert not b['verified_operating_attribution']
        editor = v2['report']['editor_revision']
        assert editor['validation_status'] == 'pending_semantic_review'
        assert editor['qualification_limit'] == 'user_assertions_unverified'
        old, _ = request(f'/reports/{report_id}/revisions/1', name=name+'-v1-after-v2')
        assert old['report'] == v1['report'] and old['payload_sha256'] == v1['payload_sha256']
        assert old['current_revision'] == 2
        after_v2 = download(report_id, 1, name+'-v1-after-v2', v1['payload_sha256'])
        v2_sha = download(report_id, 2, name+'-v2', v2['payload_sha256'])
        assert before_v2 == after_v2 and after_v2 != v2_sha
        for operation, expected in [(operation_v1, v1), (operation_v2, v2)]:
            recovered, _ = request('/reports/by-operation/'+operation)
            assert recovered['report'] == expected['report']
            assert recovered['payload_sha256'] == expected['payload_sha256']
        results.append(dict(case=name, task_id=task_id, task_revision=4, report_id=report_id,
             operation_v1=operation_v1, operation_v2=operation_v2,
             v1_payload_sha256=v1['payload_sha256'], v2_payload_sha256=v2['payload_sha256'],
             v1_markdown_sha256=after_v2, v2_markdown_sha256=v2_sha,
             immutable_v1=True, exact_export_after_v2=True, business_content_unchanged=True,
             fact_ids=sorted(task_fact_ids), test_mode=None, human_semantic_review='pending',
             v2_title_actor='Codex release verification example; not owner approval'))
    interval = events()[start:]
    counts = Counter(e['kind'] for e in interval)
    assert all(counts[k] == 0 for k in ('provider', 'provider_http', 'retrieve', 'milvus_search', 'bge'))
    posts = [e for e in interval if e.get('method') == 'POST']
    assert len(posts) == 9
    assert all(e['path'].startswith('/reports') and e['status'] == 200 for e in posts)
    summary = dict(schema='d30-real-report-verification-v1', actor='Codex', cases=results,
                   event_offset_start=start, event_offset_end=len(events()), observed_posts=posts,
                   model_or_retrieval_calls=0, financial_accept_or_resume_calls=0,
                   reports=3, revisions=6, exact_downloads=9, owner_semantic_approvals_created=0)
    write('summary.json', summary)
    print('3 real reports / 6 revisions / 9 exact downloads; no model, acceptance or resume calls')


if __name__ == '__main__':
    main()
