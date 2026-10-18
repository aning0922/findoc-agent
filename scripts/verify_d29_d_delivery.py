"""Verify D29-D final evidence, exact immutable history and executed product bytes."""
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'product/d29-d'
BASE = 'b9cabd922c5363f3c6ed438a948de98ac0ca8e3d'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    p = OUT / path
    return p.read_bytes() if p.exists() else gzip.decompress(p.with_suffix(p.suffix + '.gz').read_bytes())


def load(path):
    return json.loads(read(path))


counts = {'after-final-r3': 21, 'before-final': 15, 'a-final-r2': 22,
          'b-final-r2': 38, 'c1-final-r2': 68, 'c2-final-r2': 46, 's6-final': 18, 'native-final-r6': 1}
summary = {'base': BASE, 'browser': {}}
for name, count in counts.items():
    stats = load(f'evidence/{name}/results.json')['stats']
    assert stats['expected'] == count and all(stats[k] == 0 for k in ('unexpected', 'skipped', 'flaky')), (name, stats)
    record = load(f'evidence/{name}/record.json')
    assert record['exit_code'] == 0 and record['servers_stopped'], name
    for path, digest in record.get('executed_source_sha256', {}).items():
        raw = subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=ROOT) if name.startswith('before') else (ROOT / path).read_bytes()
        assert sha(raw) == digest, (name, path)
    summary['browser'][name] = stats

# Reading alone must leave every SQLite table byte-for-byte equivalent logically.
audits = []
for p in sorted((OUT / 'evidence/after-final-r3').glob('*-audit.json*')):
    relative = str(p.relative_to(OUT)).removesuffix('.gz')
    value = load(relative)
    assert value['start'] == value['end'] and all(m == 'GET' for m in value['methods']), p
    audits.append({'path': relative, 'requests': len(value['methods'])})
assert len(audits) == 18, len(audits)
summary['readonly_audits'] = audits
proof = load('evidence/after-final-r3/restart-proof.json')
assert proof['before_state'] == proof['after_state'] and len(proof['exact_http_bytes']) == 25
summary['restart_exact_http_reads'] = 25
empty = sha(b'[]')
for name in ('confirmed_financial_facts', 'financial_fact_sets', 'template_tasks', 'reports', 'report_revisions', 'report_operations'):
    assert proof['after_state'][name] == empty, name
summary['native_qualification_imported'] = False

manifest = load('evidence/c2-final-r2/manifest.json')
http_runs = []
for item in manifest['runs']:
    original = json.loads((ROOT / f"product/d28/evidence/qa-real/{item['case']}.json").read_bytes())
    raw = json.dumps(item['run'], ensure_ascii=False, separators=(',', ':')).encode()
    assert sha(raw) == original['response_bytes_sha256'], item['case']
    http_runs.append({'case': item['case'], 'exact_http_sha256': sha(raw), 'historical_http_sha256': original['response_bytes_sha256']})
assert len(http_runs) == 18

paths = [f"product/d28/evidence/qa-real/{r['case']}.json" for r in manifest['runs']]
paths += [f'product/d28/evidence/human-followup/{name}-user-resume-completed.json' for name in ('midea', 'gree', 'comparison')]
paths += [f'product/d28/evidence/human-followup/midea-report-v{n}-user-saved.json' for n in (1, 2)]
paths += ['product/d28/evidence/human-followup/midea-report-v1-user-downloaded.md',
          'app/reports/markdown.py', 'frontend/src/product/d28ExternalReviews.ts']
unchanged = []
for path in paths:
    baseline = subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=ROOT)
    current = (ROOT / path).read_bytes()
    assert baseline == current, path
    unchanged.append({'path': path, 'baseline_sha256': sha(baseline), 'current_sha256': sha(current)})
for area in ('app', 'product/d28', 'product/d29-a', 'product/d29-b', 'product/d29-c1', 'product/d29-c2'):
    assert subprocess.check_output(['git', 'diff', '--name-only', BASE, '--', area], cwd=ROOT) == b'', area
assert manifest['archive_reports'][0]['markdown_sha256'] == '28ddda7dc495e3396a387ff966d9c56a99679084de8841d9eb57d940fd61b9d0'
(OUT / 'evidence/historical-byte-proof.json').write_text(json.dumps({'http_runs': http_runs, 'unchanged': unchanged,
    'reports': manifest['archive_reports'], 'all_protected_trees_unchanged': True}, ensure_ascii=False, indent=2) + '\n')

for suite in ET.fromstring(read('evidence/checks/backend-junit.xml')).iter('testsuite'):
    assert all(int(suite.attrib.get(k, 0)) == 0 for k in ('failures', 'errors', 'skipped'))
    assert int(suite.attrib['tests']) == 425
summary['backend'] = 425
for suite in ET.fromstring(read('evidence/checks/reports-final/backend-junit.xml')).iter('testsuite'):
    assert all(int(suite.attrib.get(k, 0)) == 0 for k in ('failures', 'errors', 'skipped'))
    assert int(suite.attrib['tests']) == 57
summary['report_backend'] = 57
summary['backend_total'] = 482
native = load('evidence/native-final-r6/native-integration-proof.json')
assert [c['comparison'] for c in native['proof']] == [False, True]
assert len(native['recoveryReads']) == 1 and native['recoveryReads'][0].endswith(native['proof'][1]['recovery_operation'])
assert sum(w.endswith('/financial-facts/confirmations') for w in native['writes']) == 3
assert sum(w.endswith('/financial-facts/persisted') for w in native['writes']) == 3
assert sum(w.endswith('/resume') for w in native['writes']) == 2
native_http = [json.loads(line) for line in read('evidence/native-final-r6/http.jsonl').decode().splitlines()]
for case, label in zip(native['proof'], ('single', 'dual')):
    report = load(f'evidence/native-final-r6/{label}-reports/guided-report-proof.json')
    assert [d['width'] for d in report['downloads']] == [1440, 1280, 1024]
    assert len({d['sha256'] for d in report['downloads']}) == 1
    assert report['saved']['report']['trusted_snapshot']['task_id'] == case['task']
    assert report['saved']['report']['revision'] == 1 and report['v2']['report']['revision'] == 2
    assert report['saved']['report']['trusted_snapshot']['test_mode'] == 'simulated_test'
    facts = {f['fact_id'] for f in report['saved']['report']['trusted_snapshot']['financial_facts']}
    for group in case['groups']:
        assert set(group['facts']) <= facts
        reads = [r['status'] for r in native_http if r['method'] == 'GET' and r['path'] == '/financial-facts/persisted/' + group['receipt']]
        assert reads and reads[0] == 404 and 200 in reads
summary['native_single_dual_and_s6_downloads'] = True
summary['new_human_acceptances'] = 0
summary['real_provider_calls'] = 0
log = read('evidence/frontend-final.log').decode()
assert re.search(r'pass 208\b', log) and re.search(r'fail 0\b', log)
summary['frontend'] = 208
subprocess.run([str(ROOT / '.venv/bin/python'), 'scripts/build_d29_c2_reviews.py', '--check'], cwd=ROOT, check=True)
frozen = load('evidence/final-product-source.json')['sha256']
assert all(sha((ROOT / path).read_bytes()) == digest for path, digest in frozen.items())
summary['frozen_product_files'] = len(frozen)
assert (OUT / 'human/unfamiliar-users.csv').read_bytes() == (ROOT / 'product/d28/human/unfamiliar-users.csv').read_bytes()
if (OUT / 'evidence-packaging.json').exists():
    packaging = json.loads((OUT / 'evidence-packaging.json').read_bytes())
    for item in packaging:
        raw = (OUT / item['archive']).read_bytes()
        assert sha(raw) == item['archive_sha256']
        if item['kind'] == 'gzip':
            original = gzip.decompress(raw)
            assert len(original) == item['bytes'] and sha(original) == item['sha256']
    summary['lossless_archive_entries_verified'] = len(packaging)
(OUT / 'validation-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
print('Verified final tests, exact execution source, read-only SQLite, 18 historical Run bytes and 25 restart reads.')
