"""Finish public seed artifacts in a stopped disposable test runtime. Zero LLM/signatures.

Evidence tier: real local engines through in-process ASGI; not a public HTTP UI test.
Never accepts a developer runtime or overwrites original PDF bytes.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4

import httpx


async def complete(root):
    evidence = root.parents[2]
    if (not evidence.is_relative_to(Path(tempfile.gettempdir()).resolve())
            or not evidence.name.startswith('findoc-integrated-http-')
            or root.parent.name != 'active' or (root.parents[1] / 'child.json').exists()
            or not (root / '.demo-manifest.json').is_file()):
        raise ValueError('Only stopped disposable controller runtimes are allowed')
    os.environ.update(LLM_API_KEY='disabled-seed-material-only', LLM_MODEL='disabled-no-calls',
                      LLM_BASE_URL='http://127.0.0.1:9/v1', LLM_TIMEOUT_SECONDS='1',
                      HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', TOKENIZERS_PARALLELISM='false')
    os.environ.pop('FINDOC_PROVIDER_BUDGET_DB', None)
    from app.api.runtime_factory import create_runtime_app
    from app.demo.seed import sha256
    project = Path(__file__).resolve().parents[2]
    scan = project / 'data/showcase-ocr-spike-20261103/derived-scan-page-9.pdf'
    if sha256(scan) != '175235d1122aec489a6c943ec8c1f8f9fcb5ffdd0e75f938f5ce6080c8ed163a':
        raise ValueError('Derived public scan identity mismatch')
    app = create_runtime_app(root)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://isolated-seed') as client:
            async def api(path, body=None):
                response = await (client.post(path, json=body) if body else client.get(path))
                if response.status_code >= 400:
                    raise RuntimeError(f'{path} HTTP{response.status_code}: {response.text}')
                return response.json()
            companies = await api('/companies')
            midea = next(c for c in companies if c['security_code'] == '000333')
            gree = next(c for c in companies if c['security_code'] == '000651')
            docs = await api('/documents')
            identities = {d['document_id']: await api(f"/documents/{d['document_id']}/parse-identity") for d in docs}
            derived = next((d for d in docs if identities[d['document_id']]['content_sha256'] == sha256(scan)), None)
            if derived is None:
                metadata = dict(company_id=midea['company_id'], report_year=2025, report_type='annual',
                                basis='PRC_GAAP', period_start='2025-01-01', period_end='2025-12-31')
                response = await client.post('/report-documents', files={'file': ('美的2025_公开原文第9页_派生扫描示例.pdf', scan.read_bytes(), 'application/pdf')},
                                             data={'metadata': json.dumps(metadata)})
                if response.status_code != 202:
                    raise RuntimeError(f'derived_upload HTTP{response.status_code}: {response.text}')
                derived = response.json()
            for _ in range(150):
                current = await api('/documents/' + derived['document_id'])
                if current['status'] in ('ready', 'failed'):
                    break
                await asyncio.sleep(.1)
            identity = await api(f"/documents/{derived['document_id']}/parse-identity")
            parsed = await api(f"/documents/{derived['document_id']}/parse-retry", dict(
                operation_id=str(uuid4()), expected_source_revision=identity['source_revision']))
            artifact = await api(f"/documents/{derived['document_id']}/parse-quality?artifact_id={parsed['artifact_id']}")
            if parsed['state'] != 'completed' or artifact['ocr_pages'] != 1 or len(artifact['pages'][0]['lines']) < 20:
                raise ValueError('Real OCR artifact incomplete')
            memory_ids = []
            for text in ('预置演示研究线索：后续关注经营现金流与回款质量；这不是财务确认或投资结论。',
                         '预置演示研究问题：原材料价格与海外汇率变化如何影响经营风险？请回到年报原文。'):
                receipt = await api('/research-memories', dict(operation_id=str(uuid4()), type='note', text=text,
                                                              company_id=gree['company_id'], confirmed=True))
                memory_ids.append(receipt['memory_id'])
            docs = await api('/documents')
            identities = {d['document_id']: await api(f"/documents/{d['document_id']}/parse-identity") for d in docs}
            result = dict(evidence_tier='REAL_LOCAL_VISION_BGE_IN_PROCESS_ASGI', documents=[dict(document_id=d['document_id'],
                status=d['status'], sha256=identities[d['document_id']]['content_sha256']) for d in docs], memory_ids=memory_ids,
                ocr=dict(document_id=derived['document_id'], artifact_id=artifact['artifact_id'], lines=len(artifact['pages'][0]['lines']),
                         cells=len(artifact['pages'][0]['tables'][0]['cells']), legacy_source_verified=artifact['legacy_source_verified']),
                report_ids=[r['report_id'] for r in await api('/showcase-reports')], llm_calls=0, human_financial_approvals=0)
            (evidence / 'completed-seed-material.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
            print(json.dumps(result, ensure_ascii=False))
    finally:
        await app.router.shutdown()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    asyncio.run(complete(parser.parse_args().root.resolve()))
