"""Build four fixed-SHA reports with the actual runtime, BGE and Milvus in a fresh root."""
import asyncio
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

from dotenv import dotenv_values

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from app.api.runtime_factory import create_runtime_app  # noqa: E402
from app.companies.models import CompanyCreate  # noqa: E402
from app.documents.source_models import ReportUploadInput  # noqa: E402
from app.rag.publications import IndexPublications  # noqa: E402
from app.companies.sqlite_repository import SQLiteCompanyRepository  # noqa: E402

# Read existing secure configuration; never persist or print its contents.
for key, value in dotenv_values(root.parent / 'findoc-rag/.env').items():
    if value is not None:
        os.environ.setdefault(key, value)
runtime_root = Path(tempfile.mkdtemp(prefix='findoc-d16-real-')).resolve()
report = dict(runtime_root=str(runtime_root), reports=[], bge='BAAI/bge-m3',
              dimensions=1024, llm=os.environ.get('LLM_MODEL'), human_review='pending')
output = root / 'product/validation/d16-real-index.json'


def save():
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


save()


async def main():
    started = time.monotonic()
    app = create_runtime_app(runtime_root)
    sources = app.state.source_service
    companies = app.state.company_service
    pub = IndexPublications(SQLiteCompanyRepository(runtime_root / 'documents.db'),
                            app.state.runtime_rag_resources.milvus_client)
    identities = {}
    for code, name in [('midea', '美的集团股份有限公司'), ('gree', '珠海格力电器股份有限公司')]:
        identities[code] = companies.create(CompanyCreate(name=name, security_code=code.upper(),
                                                         exchange='SZSE')).company_id
    try:
        for original in json.loads((root / 'product/validation/sources.json').read_text()):
            t = time.monotonic()
            content = (root / original['path']).read_bytes()
            assert hashlib.sha256(content).hexdigest() == original['sha256']
            code, year_text = original['id'].split('-')
            year = int(year_text)
            print('building', original['id'], flush=True)
            result = await sources.upload(filename=original['id']+'.pdf', content=content,
                payload=ReportUploadInput(company_id=identities[code], report_year=year,
                    report_type='annual', basis='PRC_GAAP', period_start=f'{year}-01-01',
                    period_end=f'{year}-12-31', source_url=original['url']))
            doc = result['document_id']
            while True:
                record = await sources.documents.get_document(doc)
                if record.status.value == 'failed':
                    raise RuntimeError(record.error_code)
                if record.status.value == 'ready':
                    break
                await asyncio.sleep(1)
            src = await sources.source(doc)
            gen, manifest = await asyncio.to_thread(pub.verified, 'demo', doc, src['source_revision'])
            selected = await app.state.selection_preparer.prepare_many(document_ids=[doc], query='公司主要业务是什么？')
            hits = await app.state.selected_scope_search.search(selected)
            assert hits
            report['reports'].append(dict(report_id=original['id'], document_id=doc,
                source=src, generation=gen, manifest=manifest, elapsed_seconds=time.monotonic()-t,
                query_hits=[dict(document_id=h.document_id, source_revision=h.source_revision,
                    chunk_id=h.chunk_id, physical_page=h.page, text=h.text) for h in hits]))
            save()
            print('ready', original['id'], len(manifest['rows']), flush=True)
        with closing(pub.registry._connect()) as c:
            report['publication_states'] = [dict(r) for r in c.execute(
                'SELECT generation,document_id,source_revision,state,manifest_sha256 FROM index_publications')]
        report['seconds'] = time.monotonic()-started
        report['status'] = 'built_and_queried'
        save()
    finally:
        app.state.runtime_rag_resources.milvus_client.close()

try:
    asyncio.run(main())
except Exception as exc:
    report['status'] = 'failed'
    report['safe_error_type'] = type(exc).__name__
    save()
    print('FAILED', type(exc).__name__, flush=True)
    sys.exit(1)
