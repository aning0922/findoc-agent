#!/usr/bin/env python3
"""Validate FinDoc C+ package checksums, feature coverage and task DAG; no network/deps."""
from pathlib import Path
import csv,json,hashlib,sys
root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/'data/release_manifest.json').read_text(encoding='utf-8'))
errors=[]
for item in manifest['files']:
 p=root/item['path']; h=hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
 if h!=item['sha256']:errors.append('SHA mismatch '+item['path'])
def csvrows(name):
 with (root/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
tasks=csvrows('data/task_board.csv');features=csvrows('data/feature_matrix.csv')
ids={r['task_id'] for r in tasks};fids={r['feature_id'] for r in features}
if len(ids)!=len(tasks):errors.append('duplicate task IDs')
if len(fids)!=len(features):errors.append('duplicate feature IDs')
for row in tasks:
 for dep in row['depends_on'].split(','):
  if dep.strip() and dep.strip()!='—' and dep.strip() not in ids:errors.append(row['task_id']+' missing dep '+dep)
 for fid in row['features'].split(','):
  if fid.strip() and fid.strip()!='ALL' and fid.strip() not in fids:errors.append(row['task_id']+' unknown feature '+fid)
deps={r['task_id']:set(x for x in r['depends_on'].split(',') if x in ids) for r in tasks}
seen=set();active=set()
def visit(k):
 if k in active:errors.append('cycle '+k);return
 if k in seen:return
 active.add(k)
 for q in deps[k]:visit(q)
 active.remove(k);seen.add(k)
for k in ids:visit(k)
if len(tasks)!=manifest['task_count'] or len(features)!=manifest['feature_count']:errors.append('count mismatch')
print(json.dumps({'package':str(root),'features':len(features),'tasks':len(tasks),'files_checked':len(manifest['files']),'errors':errors},ensure_ascii=False,indent=2))
sys.exit(bool(errors))
