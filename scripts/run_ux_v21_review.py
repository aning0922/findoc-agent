"""Human review launch: formal UI + production gates in a disposable runtime.

No simulated facts are admitted. No confirmation, persistence, research or report
write is invoked by this launcher. Browser actions belong to the human operator.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
from dotenv import dotenv_values

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument("--empty", action="store_true", help="start with no companies or PDFs")
args = parser.parse_args()
runtime = Path(tempfile.mkdtemp(prefix="findoc-ux-v21-review-"))
if not args.empty:
    baseline = Path(
        json.loads((root / "product/validation/d16-real-index.json").read_text())["runtime_root"]
    )
    shutil.copytree(baseline, runtime, dirs_exist_ok=True)
out = root / "data/ux-v21-review"
out.mkdir(parents=True, exist_ok=True)
base = {k: v for k, v in os.environ.items() if not k.startswith("LLM_") and k != "OPENAI_API_KEY"}
base.update(
    FINDOC_RUNTIME_ROOT=str(runtime),
    FINDOC_API_ORIGIN="http://127.0.0.1:18132",
    FINDOC_E2E_DISABLE_ENV_FILES="1",
    PYTHONDONTWRITEBYTECODE="1",
    OMP_NUM_THREADS="1",
    MKL_NUM_THREADS="1",
    VECLIB_MAXIMUM_THREADS="1",
    HF_HUB_OFFLINE="1",
)
api_env = dict(base)
for k, v in dotenv_values(root.parent / "findoc-rag/.env").items():
    if k.startswith("LLM_") and v is not None:
        api_env[k] = v
api_env["LLM_TIMEOUT_SECONDS"] = "90"
for port in (18132, 14232):
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", port))
node = Path("/Users/aipuli/.nvm/versions/node/v24.19.0/bin/node")
processes, logs = [], []
try:
    for i, (cmd, cwd, env) in enumerate(
        [
            (
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.api.runtime_factory:create_isolated_runtime_app_from_env",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "18132",
                ],
                root,
                api_env,
            ),
            (
                [
                    str(node),
                    str(root / "frontend/node_modules/vite/bin/vite.js"),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "14232",
                    "--strictPort",
                ],
                root / "frontend",
                base,
            ),
        ]
    ):
        log = (out / f"server-{i}.log").open("w")
        logs.append(log)
        processes.append(
            subprocess.Popen(cmd, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
        )
    record = dict(
        url="http://127.0.0.1:14232",
        runtime_root=str(runtime),
        pids=[p.pid for p in processes],
        production_gates=True,
        human_acceptances_by_launcher=0,
        simulated_facts=False,
        seeded_existing_reports=not args.empty,
    )
    (out / "session.json").write_text(json.dumps(record, indent=2))
    print(json.dumps(record), flush=True)
    while all(p.poll() is None for p in processes):
        try:
            processes[0].wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
finally:
    for p in processes:
        if p.poll() is None:
            p.terminate()
    for p in processes:
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
    for log in logs:
        log.close()
