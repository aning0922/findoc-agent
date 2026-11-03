"""C frozen dense retrieval baseline in an owned materialized seed; no provider calls."""
import asyncio
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time

PROJECT = Path(__file__).resolve().parents[2]


async def observe(app, inventory):
    document = next(x for x in inventory['documents'] if x['public_provenance']['id'] == 'gree-2025')
    questions = [
        ('risk-general', '2025年报主要经营风险有哪些'),
        ('risk-material', '年报中如何描述原材料价格波动风险'),
        ('risk-competition', '公司面临的市场竞争风险'),
        ('risk-overseas', '海外市场与汇率波动风险'),
        ('business', '公司主要业务和主要产品'),
        ('cashflow', '摘录经营活动产生的现金流量净额原文'),
    ]
    results = []
    for key, question in questions:
        start = time.monotonic()
        scope = await app.state.selection_preparer.prepare_many(document_ids=[document['document_id']], query=question)
        hits = await app.state.selected_scope_search.search(scope, top_k=5)
        rows = []
        for n, hit in enumerate(hits, 1):
            value = asdict(hit)
            value.update(rank=n, known_irrelevant_risk_table_diagnostic=(key.startswith('risk') and any(x in hit.text for x in ('委托理财概况', '委托理财发生额', '委托理财余额'))))
            rows.append(value)
        results.append(dict(case_id=key, query=question, source_scope_sha=scope.selection_id,
                            sources=[asdict(d) for d in scope.documents], duration_seconds=round(time.monotonic()-start, 3), hits=rows,
                            human_relevance_labels='not_reviewed', precision_at_5=None, mrr_at_5=None))
    return results


def main():
    os.environ.update(LLM_API_KEY='disabled-baseline-no-provider', LLM_MODEL='disabled-no-calls',
                      LLM_BASE_URL='http://127.0.0.1:9/v1', LLM_TIMEOUT_SECONDS='1',
                      HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', TOKENIZERS_PARALLELISM='false')
    # The old shared provider budget is never opened or replaced by this observation.
    os.environ.pop('FINDOC_PROVIDER_BUDGET_DB', None)
    from app.demo.seed import materialize, verify_seed
    from app.api.runtime_factory import create_runtime_app
    from fastapi.testclient import TestClient
    seed = PROJECT / 'data/showcase-seed-v1'
    _, digest = verify_seed(seed)
    inventory = json.loads((seed/'seed-inventory.json').read_text())
    runtime = Path(tempfile.mkdtemp(prefix='findoc-cplus-dense-baseline-')).resolve()/'runtime'
    materialize(seed, runtime, digest)
    app = create_runtime_app(runtime, showcase_generation=1, showcase_seed_version='cplus-baseline-observation')
    with TestClient(app):
        results = asyncio.run(observe(app, inventory))
    verify_seed(seed, digest)
    evidence = dict(schema_version='cplus-retrieval-before-v1', baseline_commit='45d55d75662f01d9bc78da1a946d845a01a27480',
                    implementation_sha256=hashlib.sha256((PROJECT/'app/rag/selected_scope.py').read_bytes()).hexdigest(),
                    tier='REAL_PDF_BGE_MILVUS_IN_PROCESS', llm_calls=0, human_financial_approvals=0,
                    seed_manifest_sha256=digest, seed_unchanged=True, owned_runtime=str(runtime),
                    questions=len(results), results=results, relevance_metrics='not_human_labelled; diagnostic phrases are not quality scores')
    target=PROJECT/'docs/cplus/evidence/M0-retrieval-before.json'
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'evidence':str(target),'questions':len(results),'llm_calls':0,'seed_unchanged':True,
                      'known_irrelevant_risk_table_hits':sum(h['known_irrelevant_risk_table_diagnostic'] for r in results for h in r['hits'])}))


if __name__ == '__main__':
    main()
