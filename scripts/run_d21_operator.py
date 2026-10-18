"""Local human operator server: existing secure settings, stable isolated root, production gates."""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile

from dotenv import dotenv_values
import uvicorn

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
pointer = root / 'data/30d-foundation/d21-operator-runtime.json'
if pointer.exists():
    runtime = Path(json.loads(pointer.read_text())['runtime_root'])
else:
    source = Path(json.loads((root / 'product/validation/d16-real-index.json').read_text())['runtime_root'])
    runtime = Path(tempfile.mkdtemp(prefix='findoc-d21-operator-'))
    shutil.copytree(source, runtime, dirs_exist_ok=True)
    with sqlite3.connect(runtime / 'documents.db') as conn:
        # A clean D16 source copy must never import simulated acceptances as human facts.
        if conn.execute('SELECT count(*) FROM financial_acceptance_receipts').fetchone()[0]:
            raise RuntimeError('operator_requires_clean_source_copy')
    pointer.write_text(json.dumps(dict(runtime_root=str(runtime)), indent=2) + '\n')
for name in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
    os.environ[name] = '1'
for name, value in dotenv_values(root.parent / 'findoc-rag/.env').items():
    if name.startswith('LLM_') and value is not None:
        os.environ.setdefault(name, value)
os.environ['FINDOC_RUNTIME_ROOT'] = str(runtime)
print('D21 formal operator runtime:', runtime, flush=True)
print('Open http://127.0.0.1:14191/research?mode=operating after starting frontend.', flush=True)
uvicorn.run('app.api.runtime_factory:create_isolated_runtime_app_from_env',
            factory=True, host='127.0.0.1', port=18091, workers=1)
