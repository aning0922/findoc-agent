"""Measure real cached BGE/Milvus startup in a disposable, isolated runtime.

No provider call is made; the configured provider URL is loopback and offline.
Run with an existing full-dependency Python environment, from the repository root.
"""
import json
import os
from pathlib import Path
import tempfile
import time


def main() -> None:
    os.environ.update({
        'LLM_MODEL': 'startup-spike-no-provider-call',
        'LLM_API_KEY': 'not-a-real-key',
        'LLM_BASE_URL': 'http://127.0.0.1:9/v1',
        'LLM_TIMEOUT_SECONDS': '1',
        'HF_HUB_OFFLINE': '1',
        'TRANSFORMERS_OFFLINE': '1',
        'TOKENIZERS_PARALLELISM': 'false',
    })
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='findoc-showcase-startup-') as temporary:
        root = Path(temporary)
        try:
            from app.api.runtime_factory import create_runtime_app
            app = create_runtime_app(root, showcase_generation=1,
                                     showcase_seed_version="startup-empty")
            ready_seconds = round(time.monotonic() - started, 3)
            from fastapi.testclient import TestClient
            with TestClient(app) as client:
                health = client.get('/health')
                companies = client.get('/companies')
                dashboard = client.get('/dashboard/overview')
                sample = client.get('/dashboard/charts?sample_mode=true')
                assert dashboard.status_code == 200
                assert dashboard.json()['lease_generation'] == 1
                assert all(value == 0 for value in dashboard.json()['kpis'].values())
                assert sample.status_code == 200 and sample.json()['origin'] == 'illustrative'
            print(json.dumps({'status': 'pass', 'data_level': 'REAL_BGE_MILVUS_EMPTY_RUNTIME',
                'llm_calls': 0, 'ready_seconds': ready_seconds,
                'total_seconds': round(time.monotonic() - started, 3),
                'health_status': health.status_code, 'company_status': companies.status_code,
                'dashboard_status': dashboard.status_code, 'kpis': dashboard.json()['kpis'],
                'sample_chart_origin': sample.json()['origin'], 'lease_generation': 1,
                'files': sorted(p.name for p in root.iterdir())}))
        except Exception as error:
            print(json.dumps({'status': 'failed', 'exception_type': type(error).__name__,
                'elapsed_seconds': round(time.monotonic() - started, 3), 'llm_calls': 0,
                'note': 'Inspect local stderr; do not replace with a fake startup success.'}))
            raise


if __name__ == '__main__':
    main()
