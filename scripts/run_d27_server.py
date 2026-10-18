"""Serve this round's isolated real data and the built formal frontend."""

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--api-port", type=int, default=18127)
    parser.add_argument("--web-port", type=int, default=14227)
    args = parser.parse_args()
    runtime = args.runtime.resolve()
    assert runtime.is_relative_to(root / "data/d27")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    ports = (args.api_port, args.web_port)
    assert ports in ((18127, 14227), (18128, 14228)), "D27 isolated ports only"
    for port in ports:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", port))
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("LLM_", "FINDOC_")) and k != "OPENAI_API_KEY"
    }
    env.update(
        FINDOC_RUNTIME_ROOT=str(runtime),
        FINDOC_API_ORIGIN=f"http://127.0.0.1:{ports[0]}",
        FINDOC_E2E_DISABLE_ENV_FILES="1",
        D27_SERVER_LOG=str(out / "events.jsonl"),
        OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
        VECLIB_MAXIMUM_THREADS="1",
        HF_HUB_OFFLINE="1",
        TOKENIZERS_PARALLELISM="false",
        TIKTOKEN_CACHE_DIR=str(root / "data/integration-tokenizer-cache"),
    )
    api_env = dict(env)
    from dotenv import dotenv_values

    for k, v in dotenv_values(root.parent / "findoc-rag/.env").items():
        if k.startswith("LLM_") and v:
            api_env[k] = v
    api_env["LLM_TIMEOUT_SECONDS"] = "90"
    node = "/Users/aipuli/.nvm/versions/node/v24.19.0/bin/node"
    commands = [
        (
            [
                sys.executable,
                "-m",
                "uvicorn",
                "scripts.d27_runtime_observer:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(ports[0]),
            ],
            root,
            api_env,
        ),
        (
            [
                node,
                str(root / "frontend/node_modules/vite/bin/vite.js"),
                "preview",
                "--host",
                "127.0.0.1",
                "--port",
                str(ports[1]),
                "--strictPort",
            ],
            root / "frontend",
            env,
        ),
    ]
    processes = []
    logs = []
    start = time.perf_counter()
    try:
        for i, (command, cwd, current_env) in enumerate(commands):
            log = (out / f"server-{i}.log").open("w")
            logs.append(log)
            processes.append(
                subprocess.Popen(
                    command, cwd=cwd, env=current_env, stdout=log, stderr=subprocess.STDOUT
                )
            )
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if any(p.poll() is not None for p in processes):
                raise RuntimeError("D27 server exited")
            try:
                with urlopen(f"http://127.0.0.1:{ports[0]}/health", timeout=2) as r:
                    if r.status == 200:
                        break
            except Exception:
                time.sleep(0.25)
        else:
            raise RuntimeError("D27 startup timeout")
        session = dict(
            runtime=str(runtime),
            ports=ports,
            pids=[p.pid for p in processes],
            launcher_pid=os.getpid(),
            boot_to_http_ready_seconds=time.perf_counter() - start,
            git_sha=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True
            ).strip(),
            built_formal_frontend=True,
            production_gates=True,
            maximum_provider_requests=4,
            url=f"http://127.0.0.1:{ports[1]}",
        )
        (out / "session.json").write_text(json.dumps(session, indent=2) + "\n")
        print(json.dumps(session), flush=True)
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


if __name__ == "__main__":
    main()
