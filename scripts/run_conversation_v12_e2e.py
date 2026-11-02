"""Bounded conversation E2E: real HTTP/SQLite/PDF, deterministic provider.

Run with the installed Python environment and Node24 on PATH. Never connects to
a provider, reuses a server, or imports historical runtime/acceptance receipts.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def migration_proof(out, sources):
    """Build version eight from scratch; never strip tables from a newer DB."""
    from app.companies import migrations
    from app.companies.models import CompanyCreate
    from tests.test_document_sources import Harness, metadata
    runtime = Path(tempfile.mkdtemp(prefix='findoc-d11-conversation-v8-seed-')).resolve()
    original = migrations.MIGRATIONS
    try:
        migrations.MIGRATIONS = original[:8]
        harness = Harness(runtime)
        company = harness.companies.create(CompanyCreate(
            name='美的集团股份有限公司', security_code='000333', exchange='SZSE'))
        source = next(s for s in sources if s['id'] == 'midea-2025')
        response = harness.upload((REPO / source['path']).read_bytes(),
                                  metadata(company.company_id, 2025), filename='midea-2025.pdf')
        if response.status_code != 202:
            raise RuntimeError('v8_source_upload_failed')
        document = response.json()['document_id']
        harness.processor.process(document)
        with sqlite3.connect(runtime / 'documents.db') as db:
            if db.execute('SELECT max(version) FROM analyst_schema_migrations').fetchone()[0] != 8:
                raise RuntimeError('v8_seed_version_mismatch')
            if db.execute("SELECT name FROM sqlite_master WHERE name='reports'").fetchall():
                raise RuntimeError('v8_seed_must_have_no_report_schema')
        proof = out / 'migration-test-proof.json'
        proof.write_text(json.dumps(dict(runtime_root=str(runtime), schema_version=8,
                                        source_sha256=source['sha256'],
                                        freshly_generated=True, human_acceptances=0), indent=2))
        print(json.dumps(dict(status='prepared', migration_test_proof=str(proof))))
    finally:
        migrations.MIGRATIONS = original
    return 0


def unused_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--spec', nargs='+', default=[])
    parser.add_argument('--legacy-proof-only', action='store_true',
                        help='Run the original explicit simulated journey and export a clean D22/23/24 proof')
    parser.add_argument('--migration-proof-only', action='store_true',
                        help='Build a fresh schema-v8 source seed for the legacy migration-9 tests')
    parser.add_argument('--a1-only', action='store_true',
                        help='Only create/conflict/range checks with the explicitly marked actual-service A1 fake handler')
    args = parser.parse_args()
    node = shutil.which('node')
    if not node or not subprocess.check_output([node, '--version'], text=True).startswith('v24.'):
        parser.error('Node24 must be on PATH')
    if any('/' in s or not s.startswith('conversation') or not s.endswith('.spec.ts') for s in args.spec):
        parser.error('--spec accepts conversation*.spec.ts basenames only')
    sources = json.loads((REPO / 'product/validation/sources.json').read_text())
    for source in sources:
        path = REPO / source['path']
        if hashlib.sha256(path.read_bytes()).hexdigest() != source['sha256']:
            raise RuntimeError('Current worktree source SHA mismatch: ' + source['id'])
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    if args.migration_proof_only:
        return migration_proof(out, sources)
    runtime = Path(tempfile.mkdtemp(prefix='findoc-d11-conversation-v12-')).resolve()
    api_port, web_port = unused_port(), unused_port()
    while web_port == api_port:
        web_port = unused_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith('LLM_') and k != 'OPENAI_API_KEY'}
    env.update(
        FINDOC_CONVERSATION_RUNTIME_ROOT=str(runtime),
        FINDOC_CONVERSATION_OUT=str(out),
        FINDOC_CONVERSATION_WEB_ORIGIN=f'http://127.0.0.1:{web_port}',
        FINDOC_API_ORIGIN=f'http://127.0.0.1:{api_port}',
        FINDOC_E2E_DISABLE_ENV_FILES='1',
        PYTHONDONTWRITEBYTECODE='1',
        HF_HUB_OFFLINE='1',
        OMP_NUM_THREADS='1',
        FINDOC_UX_RUNTIME_ROOT=str(runtime),
        FINDOC_D21_RUNTIME_ROOT=str(runtime),
        FINDOC_D22_RUNTIME_ROOT=str(runtime),
        FINDOC_UX_LIVE='0',
        FINDOC_UX_INTEGRATION='1',
        UX_ARTIFACT_DIR=str(out),
        UX_SOURCE_FILE=str(out / 'sources.json'),
        FINDOC_CONVERSATION_A1_ONLY='1' if args.a1_only else '0',
    )
    (out / 'sources.json').write_text(json.dumps([
        dict(s, absolute_path=str(REPO / s['path'])) for s in sources
    ], ensure_ascii=False, indent=2))
    record = dict(
        schema='conversation-v12-e2e-v1', started_at=time.time(),
        head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
        git_status=subprocess.check_output(['git', 'status', '--short'], cwd=REPO, text=True),
        worktree=str(REPO), python=sys.executable,
        node_version=subprocess.check_output([node, '--version'], text=True).strip(),
        runtime_root=str(runtime), sources=[{'id': s['id'], 'sha256': s['sha256']} for s in sources],
        actual_llm=False, actual_bge=False, actual_milvus=False,
        simulated_test=True, human_acceptances=0, retries=0,
        status='starting', exit_code=None, servers_stopped=False,
        execution_stage='A1_fake_handler' if args.a1_only else 'A2_graph_with_fake_provider',
    )

    def save():
        (out / 'run-manifest.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')

    save()
    processes, handles = [], []
    code = 1
    try:
        factory = ('tests.support.d26_app:create_app' if args.legacy_proof_only
                   else 'tests.support.conversation_app:create_app')
        for name, cmd, cwd, url in [
            ('api', [sys.executable, '-m', 'uvicorn', factory,
                     '--factory', '--host', '127.0.0.1', '--port', str(api_port)], REPO,
             f'http://127.0.0.1:{api_port}/health'),
            ('web', [node, 'node_modules/vite/bin/vite.js', '--host', '127.0.0.1',
                     '--port', str(web_port), '--strictPort'], REPO / 'frontend',
             f'http://127.0.0.1:{web_port}'),
        ]:
            log = (out / f'{name}.log').open('w')
            handles.append(log)
            process = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
            processes.append(process)
            deadline = time.monotonic() + 120
            while True:
                if process.poll() is not None:
                    raise RuntimeError(name + ' exited before readiness; see isolated log')
                try:
                    with urlopen(url, timeout=2) as response:
                        if response.status == 200:
                            break
                except Exception:
                    if time.monotonic() >= deadline:
                        raise RuntimeError(name + ' readiness timeout')
                    time.sleep(0.25)
        record['status'] = 'running'
        save()
        command = [node, 'node_modules/@playwright/test/cli.js', 'test',
                   '--config', 'playwright.conversations.config.ts', *args.spec]
        if args.a1_only:
            command = [node, 'node_modules/@playwright/test/cli.js', 'test',
                       '--config', 'playwright.conversations.config.ts', 'conversation-api.spec.ts',
                       '--grep', 'creation operation replay|strict create range']
        if args.legacy_proof_only:
            config = runtime / 'legacy-proof.config.mjs'
            config.write_text('import {defineConfig} from ' + json.dumps(str(
                REPO / 'frontend/node_modules/@playwright/test/index.mjs'
            )) + ';export default defineConfig(' + json.dumps(dict(
                testDir=str(REPO / 'frontend/e2e'), testMatch='ux-simplification-journey.spec.ts',
                workers=1, retries=0, timeout=180000, forbidOnly=True,
                outputDir=str(out / 'legacy-traces'),
                reporter=[['line'], ['json', {'outputFile': str(out / 'results.json')}]],
                use=dict(baseURL=env['FINDOC_CONVERSATION_WEB_ORIGIN'],
                         viewport=dict(width=1440, height=900), trace='retain-on-failure'),
            )) + ');\n')
            command = [node, 'node_modules/@playwright/test/cli.js', 'test', '--config', str(config)]
        record['command'] = command
        with (out / 'browser.log').open('w') as log:
            code = subprocess.run(command, cwd=REPO / 'frontend', env=env,
                                  stdout=log, stderr=subprocess.STDOUT).returncode
        record['status'] = 'passed' if code == 0 else 'failed'
        if code == 0 and args.legacy_proof_only:
            seed = Path(tempfile.mkdtemp(prefix='findoc-d11-conversation-report-seed-')).resolve()
            with sqlite3.connect(f'file:{runtime / "documents.db"}?mode=ro', uri=True) as source_db:
                with sqlite3.connect(seed / 'documents.db') as seed_db:
                    source_db.backup(seed_db)
                    if seed_db.execute('SELECT count(*) FROM reports').fetchone()[0] != 0:
                        raise RuntimeError('Report seed must precede all report generation')
            shutil.copytree(runtime / 'objects', seed / 'objects')
            result = json.loads((out / 'journey-proof.json').read_text())['result']
            proof = out / 'report-test-proof.json'
            proof.write_text(json.dumps(dict(runtime_root=str(seed), cases=[dict(result=result)]),
                                        ensure_ascii=False, indent=2))
            record.update(clean_seed_root=str(seed), report_test_proof=str(proof),
                          report_test_environment='FINDOC_REPORT_TEST_PROOF',
                          seed_method='sqlite_backup_before_report_generation')
    except Exception as exc:
        record.update(status='failed', error_type=type(exc).__name__)
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for handle in handles:
            handle.close()
        record.update(exit_code=code, ended_at=time.time(), servers_stopped=True,
                      server_exit_codes=[p.returncode for p in processes])
        save()
    print(json.dumps({'status': record['status'], 'exit_code': code, 'out': str(out)}))
    return code


if __name__ == '__main__':
    sys.exit(main())
