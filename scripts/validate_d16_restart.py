"""Separate-process actual runtime restart and version change acceptance; no fake models/vectors."""
import asyncio
import json
import os
from pathlib import Path
import sys
import time
from dotenv import dotenv_values

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from app.api.runtime_factory import create_runtime_app  # noqa: E402
from app.rag.retriever import IndexVersionUnverifiedError  # noqa: E402

for key, value in dotenv_values(root.parent / 'findoc-rag/.env').items():
    if value is not None:
        os.environ.setdefault(key, value)
previous = json.loads((root / 'product/validation/d16-real-index.json').read_text())
assert previous['status'] == 'built_and_queried'
report = dict(runtime_root=previous['runtime_root'], checks=[], status='running')
output = root / 'product/validation/d16-real-restart.json'


async def main():
    app = create_runtime_app(Path(previous['runtime_root']))
    selected_search = app.state.selected_scope_search
    prep = app.state.selection_preparer
    sources = app.state.source_service
    all_ids = [r['document_id'] for r in previous['reports']]
    midea = [r['document_id'] for r in previous['reports'] if r['report_id'].startswith('midea')]
    try:
        for ids in [all_ids[:1], midea, all_ids]:
            t = time.monotonic()
            scope = await prep.prepare_many(document_ids=ids, query='公司主营业务和产品是什么？')
            hits = await selected_search.search(scope, top_k=8)
            assert hits and all(h.document_id in ids for h in hits)
            report['checks'].append(dict(kind='restart_search', document_ids=ids,
                seconds=time.monotonic()-t, hit_documents=sorted({h.document_id for h in hits})))
        old = await prep.prepare_many(document_ids=all_ids, query='主要业务')
        target = old.documents[0]
        t = time.monotonic()
        await sources.reindex(target.document_id, target.attempt)
        while True:
            record = await sources.documents.get_document(target.document_id)
            if record.status.value == 'failed':
                raise RuntimeError(record.error_code)
            if record.status.value == 'ready':
                break
            await asyncio.sleep(1)
        new = await prep.prepare_many(document_ids=all_ids, query='主要业务')
        assert new != old
        try:
            await selected_search.search(old)
        except Exception as exc:
            report['checks'].append(dict(kind='old_selection_rejected', error_type=type(exc).__name__))
        else:
            raise AssertionError('old selection admitted')
        retriever = app.state.runtime_rag_resources.retriever
        try:
            await asyncio.to_thread(retriever.retrieve, old.query, context=old.context, filters=old.filters)
        except IndexVersionUnverifiedError:
            pass
        else:
            raise AssertionError('old revision retrieved')
        hits = await selected_search.search(new)
        assert hits
        report['checks'].append(dict(kind='real_reindex', document_id=target.document_id,
            old_revision=target.source_revision,
            new_revision=next(d.source_revision for d in new.documents if d.document_id==target.document_id),
            seconds=time.monotonic()-t, stale_revision_rejected=True))
        report['status'] = 'passed'
    finally:
        app.state.runtime_rag_resources.milvus_client.close()

started = time.monotonic()
try:
    asyncio.run(main())
except Exception as exc:
    report['status'] = 'failed'
    report['safe_error_type'] = type(exc).__name__
finally:
    report['seconds'] = time.monotonic()-started
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n')
print(report['status'], flush=True)
sys.exit(0 if report['status']=='passed' else 1)
