"""Freeze audit: execution sources, exact assets, preserved history and layered counts."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'product/d30'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export_sha(path):
    # Preserve exact renderer bytes, including its final newlines, in lossless packaging.
    if path.is_file():
        return sha(path)
    return hashlib.sha256(gzip.decompress(Path(str(path)+'.gz').read_bytes())).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--secret-file', type=Path, required=True)
    args = p.parse_args()
    release = json.loads((OUT/'release-manifest.json').read_text())
    source = json.loads((OUT/'source-manifest.json').read_text())
    for name, expected in source['final_source_files'].items():
        assert sha(ROOT/name)==expected, name
    for name, expected in release['content_manifests'].items():
        assert sha(OUT/name)==expected,name
    for name, entry in json.loads((OUT/'human-followup-manifest.json').read_text())['files'].items():
        assert sha(OUT/name)==entry['sha256'],name
    protected = ['app','frontend/src','product/d28','product/d29-a','product/d29-b',
                 'product/d29-c1','product/d29-c2','product/d29-d']
    subprocess.run(['git','diff','--exit-code',release['baseline'],'--',*protected],
                   cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
    browsers={}
    for name, expected in [('reading-final',21),('native-final',1),('live-browser',2),('public-browser',3)]:
        result=json.loads((OUT/'evidence'/name/'results.json').read_text())
        stats=result['stats']
        assert (stats['expected'],stats['unexpected'],stats['skipped'],stats['flaky'])==(expected,0,0,0),name
        browsers[name]=stats
    for name in ['reading-final','native-final']:
        record=json.loads((OUT/'evidence'/name/'record.json').read_text())
        assert record['exit_code']==0 and record['servers_stopped']
        for path,expected in record['executed_source_sha256'].items():
            assert sha(ROOT/path)==expected,path
    junit={}
    for name,rel,expected in [('backend_initial','checks/backend-junit.xml',(425,1)),
            ('preflight_rerun','checks/preflight-r2/backend-junit.xml',(1,0)),
            ('reports','checks/reports-final/backend-junit.xml',(57,0)),
            ('public_security','public-security-frozen-junit.xml',(2,0))]:
        suite=ET.parse(OUT/'evidence'/rel).getroot().find('testsuite')
        assert (int(suite.attrib['tests']),int(suite.attrib['failures']))==expected,name
        assert int(suite.attrib['errors'])==int(suite.attrib['skipped'])==0
        junit[name]=suite.attrib
    assert 'ℹ pass 208' in (OUT/'evidence/frontend-tests.log').read_text()
    for marker in ['formal-build-frozen.log','frontend-lint-frozen.log','ruff-frozen.log']:
        assert (OUT/'evidence'/marker).is_file()
    public=json.loads((OUT/'public-artifact.json').read_text())
    artifact=OUT/public['artifact']
    assert sha(artifact)==public['sha256']
    public_manifest=json.loads((OUT/'public-demo-manifest.json').read_text())
    with tarfile.open(artifact,'r:gz') as archive:
        assert sorted(archive.getnames())==public['files']
        for member in archive.getmembers():
            assert member.isfile() and '/' not in member.name
            raw=archive.extractfile(member).read()
            if member.name=='release-public-manifest.json':
                assert raw==(OUT/'public-demo-manifest.json').read_bytes()
            else:
                assert hashlib.sha256(raw).hexdigest()==public_manifest['files'][member.name]['sha256']
    for entry in json.loads((OUT/'evidence-packaging.json').read_text())['files']:
        archive=OUT/entry['archive_path']
        assert sha(archive)==entry['archive_sha256']
        assert hashlib.sha256(gzip.decompress(archive.read_bytes())).hexdigest()==entry['original_sha256']
    assert json.loads((OUT/'evidence/after-restart.json').read_text())['restart_verified']
    assert len(json.loads((OUT/'evidence/after-restart.json').read_text())['exact_http'])==29
    followup=OUT/'evidence/human-followup'
    finance=json.loads((followup/'four-report-twelve-facts-saved.json').read_text())
    assert finance['reports']==4 and finance['facts']==12
    assert len({row['fact_id'] for row in finance['rows']})==12
    assert all(row['current_valid'] and row['production_calculable']
               and row['confirmation_kind']=='local_operator' for row in finance['rows'])
    for name in ['midea-2024','midea-2025','gree-2024','gree-2025']:
        owner=json.loads((followup/(name+'-owner-source-check.json')).read_text())
        accepted=json.loads((followup/(name+'-user-accepted-unsaved.json')).read_text())
        saved=json.loads((followup/(name+'-user-saved.json')).read_text())
        assert owner['source_check_result']=='pass' and owner['user_exact_words']
        assert not owner['agent_created_confirmation']
        assert accepted['acceptance_get']['body']['snapshot_id']==owner['snapshot_id']
        assert accepted['persisted_get']['http_status']==404
        assert not accepted['agent_created_acceptance'] and not saved['agent_saved_facts']
        group=saved['persisted_get']['body']
        assert group['review']==accepted['acceptance_get']['body']['review']
        assert group['current_valid'] and group['production_calculable']
        assert group['integrity']=='verified' and len(group['facts'])==3
    for name in ['midea','gree','dual-2025']:
        proof=json.loads((followup/(name+'-user-resume-completed-proof.json')).read_text())
        task_path=followup/proof['task_evidence']
        assert sha(task_path)==proof['http_task_response_sha256']
        task=json.loads(task_path.read_text())
        assert task['revision']==4 and task['status']=='completed'
        assert task['final_research_content']['test_mode'] is None
        assert task['final_research_content']['human_review_status']=='pending'
        assert not task['final_research_content']['verified_operating_attribution']
        assert not proof['agent_triggered_resume'] and proof['owner_fact_ids_preserved']
        assert proof['budget_within_limits']
        assert all(proof['event_counts'][kind]==1 for kind in
                   ['bge','milvus_search','retrieve','provider_http','provider'])
    reports=json.loads((OUT/'evidence/reports-real-final/summary.json').read_text())
    assert (reports['reports'],reports['revisions'],reports['exact_downloads'])==(3,6,9)
    assert reports['financial_accept_or_resume_calls']==reports['model_or_retrieval_calls']==0
    for report in reports['cases']:
        prefix=OUT/'evidence/reports-real-final'/report['case']
        assert export_sha(Path(str(prefix)+'-v1-before-v2.md'))==report['v1_markdown_sha256']
        assert export_sha(Path(str(prefix)+'-v1-after-v2.md'))==report['v1_markdown_sha256']
        assert export_sha(Path(str(prefix)+'-v2.md'))==report['v2_markdown_sha256']
        assert report['business_content_unchanged'] and report['immutable_v1']
    before=json.loads((followup/'before-final-restart.json').read_text())
    after=json.loads((followup/'after-final-restart.json').read_text())
    assert after['restart_verified'] and len(after['exact_http'])==60
    for key in ['exact_http','business_tables','objects']:
        assert before[key]==after[key]
    assert after['get_interval_model_retrieval_embedding_calls']==0
    assert after['startup_bge_events']==before['startup_bge_events']+1
    from dotenv import dotenv_values
    values=dotenv_values(args.secret_file)
    needles=[values[k].encode() for k in ['LLM_API_KEY','LLM_BASE_URL'] if values.get(k)]
    # Check new private evidence too, not just the public package. No values/hashes printed.
    scanned=0
    for path in OUT.rglob('*'):
        if path.is_file():
            raw=path.read_bytes()
            if path.suffix=='.gz' and path.name!='public-demo-rc.tar.gz':
                raw=gzip.decompress(raw)
            assert not any(value in raw for value in needles),str(path.relative_to(OUT))
            scanned+=1
    for doc in ['FINAL-DELIVERY','FINAL-ACCEPTANCE','DEMO-GUIDE','INTERVIEW-GUIDE',
                'PUBLIC-DEMO-PLAN','KNOWN-LIMITATIONS','RELEASE-MANIFEST']:
        assert (OUT/(doc+'.md')).is_file()
    summary=dict(schema='d30-freeze-audit-v1',baseline=release['baseline'],
        production_source_and_history_unchanged=True,source_files_verified=len(source['final_source_files']),
        actual_browser_results=browsers,junit=junit,public_artifact=public['sha256'],
        public_files=53,secret_matches=0,private_evidence_files_scanned=scanned,
        new_human_acceptance='pass_financial_scope',owner_saved_facts=12,
        completed_real_tasks=3,new_reports=3,new_report_revisions=6,restart_exact_gets=60,
        freeze='historical_readonly_rc_for_user_review',
        full_live_acceptance='engineering_verified_semantics_pending',
        new_semantic_review='pending',public_deployment='not_performed')
    (OUT/'validation-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print('D30 freeze audit passed; owner finance and real tasks/reports verified; semantics pending')


if __name__=='__main__':
    main()
