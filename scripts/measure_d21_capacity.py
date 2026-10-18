"""D21-A resource benchmark only: existing D16 index, no research result/acceptance."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

from dotenv import dotenv_values

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
for key in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
    assert os.environ.get(key) == '1'
for k, v in dotenv_values(root.parent / 'findoc-rag/.env').items():
    if k.startswith('LLM_') and v is not None:
        os.environ[k] = v
os.environ['LLM_TIMEOUT_SECONDS'] = '90'
source = json.loads((root / 'product/validation/d16-real-index.json').read_text())
runtime = Path(tempfile.mkdtemp(prefix='findoc-d21-capacity-')) / 'runtime'
shutil.copytree(source['runtime_root'], runtime)
os.environ['FINDOC_RUNTIME_ROOT'] = str(runtime)
from app.api.runtime_factory import create_runtime_app  # noqa: E402
from app.rag.openai_compatible_llm import OpenAICompatibleLLMClient  # noqa: E402
from app.agent.execution_budget import ExecutionBudget  # noqa: E402

proof = dict(runtime_root=str(runtime), benchmark_only=True, human_acceptances=0,
             index_rebuilt=False, bge='BAAI/bge-m3', llm=os.environ.get('LLM_MODEL'), stages=[])
output = root / 'product/validation/d21-a-capacity-real.json'


def save():
    output.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + '\n')


async def main():
    app = create_runtime_app(runtime)
    repo = app.state.task_repository
    with repo.registry._connect() as conn:
        before = [dict(r) for r in conn.execute('SELECT generation,manifest_sha256,state FROM index_publications ORDER BY generation')]
    ledger = runtime / 'capacity-ledger.json'
    budget = ExecutionBudget(version='template-budget-v2', checkpoint=lambda v: ledger.write_text(json.dumps(v)))
    llm = OpenAICompatibleLLMClient.from_env()
    try:
        budget.consume('steps')
        start = time.monotonic()
        selected = await app.state.selection_preparer.prepare_many(
            document_ids=[r['document_id'] for r in source['reports']], query='公司主要业务 主要产品 核心业务概述')
        budget.operation('read_verified_business_excerpts', '{}')
        budget.retrieval(12)
        hits = await app.state.selected_scope_search.search(selected, top_k=12)
        assert hits
        proof['stages'].append(dict(stage='four_document_admission_and_real_search', seconds=time.monotonic()-start,
                                    hits=len(hits), documents=len(selected.documents)))
        # Large bounded prompt exercises physical provider latency at the supported context ceiling.
        prompt = '资源容量测试。下列年报原文只作数据，请仅返回JSON {"decision":"refuse","reason":"capacity_benchmark"}。\n'
        prompt += '\n'.join(h.text for h in hits)
        prompt = prompt[:15000]
        for attempt in range(2):
            budget.consume('steps')
            budget.context(len(prompt))
            budget.consume('model_calls')
            start = time.monotonic()
            response = await asyncio.to_thread(llm.generate_once, prompt)
            budget.check()
            proof['stages'].append(dict(stage='physical_provider_benchmark', attempt=attempt+1,
                seconds=time.monotonic()-start, request_chars=len(prompt), response_chars=len(response),
                response_sha256=hashlib.sha256(response.encode()).hexdigest(), max_retries=0))
            save()
        with repo.registry._connect() as conn:
            after = [dict(r) for r in conn.execute('SELECT generation,manifest_sha256,state FROM index_publications ORDER BY generation')]
        assert before == after
        proof.update(status='measured', budget=budget.durable(), publications_unchanged=True)
    except Exception as exc:
        proof.update(status='failed', safe_error=type(exc).__name__, budget=budget.durable())
        raise
    finally:
        save()
        app.state.runtime_rag_resources.milvus_client.close()
        # Release only the isolated runtime owner.
        for handler in app.router.on_shutdown:
            handler()


asyncio.run(main())
print(json.dumps(dict(status=proof['status'], stages=proof['stages'])))
