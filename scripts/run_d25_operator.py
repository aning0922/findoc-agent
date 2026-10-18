"""Launch an empty, persistent D25 runtime and the built formal frontend.

No test harness, copied database/index, acceptance, fact, task or report seed.
Re-running opens the same isolated runtime for human-requested restart checks.
"""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys

from dotenv import dotenv_values

root = Path(__file__).resolve().parent.parent
out = root / "data/d25"
runtime = out / "runtime"
out.mkdir(exist_ok=True)
runtime.mkdir(exist_ok=True)
api_port, web_port = 18125, 14225
for port in (api_port, web_port):
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("127.0.0.1", port))
base = {k: v for k, v in os.environ.items()
        if not k.startswith(("LLM_", "FINDOC_")) and k != "OPENAI_API_KEY"}
base.update(FINDOC_RUNTIME_ROOT=str(runtime),
            FINDOC_API_ORIGIN=f"http://127.0.0.1:{api_port}",
            FINDOC_D25_EXECUTION_LOG=str(out / "logs/execution.jsonl"),
            FINDOC_E2E_DISABLE_ENV_FILES="1", PYTHONDONTWRITEBYTECODE="1",
            OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", VECLIB_MAXIMUM_THREADS="1",
            HF_HUB_OFFLINE="1")
api_env = dict(base)
for key, value in dotenv_values(root.parent / "findoc-rag/.env").items():
    if key.startswith("LLM_") and value is not None:
        api_env[key] = value
api_env["LLM_TIMEOUT_SECONDS"] = "90"
if any(not api_env.get(k) for k in ("LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY")):
    raise RuntimeError("D25 requires configured real LLM")
node = Path("/Users/aipuli/.nvm/versions/node/v24.19.0/bin/node")
git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
commands = [
    ([sys.executable, "-m", "uvicorn", "scripts.d25_runtime_observer:create_app",
      "--factory", "--host", "127.0.0.1", "--port", str(api_port)], root, api_env),
    ([str(node), str(root / "frontend/node_modules/vite/bin/vite.js"), "preview",
      "--host", "127.0.0.1", "--port", str(web_port), "--strictPort"],
     root / "frontend", base),
]
processes, logs = [], []
try:
    for i, (command, cwd, env) in enumerate(commands):
        log = (out / f"logs/server-{i}.log").open("a")
        logs.append(log)
        processes.append(subprocess.Popen(command, cwd=cwd, env=env,
                                          stdout=log, stderr=subprocess.STDOUT))
    session = dict(url=f"http://127.0.0.1:{web_port}", api_port=api_port,
                   runtime_root=str(runtime), git_sha=git_sha,
                   pids=[p.pid for p in processes], launcher_pid=os.getpid(),
                   production_gates=True, formal_built_frontend=True,
                   real_bge=True, real_milvus=True, llm_model=api_env["LLM_MODEL"],
                   copied_business_data=False, human_acceptances_by_launcher=0)
    (out / "session.json").write_text(json.dumps(session, indent=2) + "\n")
    print(json.dumps(session), flush=True)
    while all(p.poll() is None for p in processes):
        try:
            processes[0].wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
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
    for log in logs:
        log.close()
