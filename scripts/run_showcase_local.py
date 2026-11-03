"""Loopback-only showcase launcher. No package installation or automatic model requests.

Run from the independent integration checkout using its existing Python environment.
Credentials are written only by --init-config into an ignored, private local file.
"""

import argparse
import fcntl
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import sqlite3
import stat
import subprocess
import sys
import time
from urllib.parse import urlsplit

PROJECT = Path(__file__).resolve().parents[1]
LLM_KEYS = ("LLM_API_KEY", "LLM_MODEL", "LLM_BASE_URL", "LLM_TIMEOUT_SECONDS")
# Positive allowlist, used for BOTH children; never inherit arbitrary provider/password/VITE keys.
HOST_KEYS = ("PATH", "HOME", "USER", "LANG", "LC_ALL", "TMPDIR", "TMP", "TEMP", "SYSTEMROOT")


def safe_path(path):
    path = Path(os.path.abspath(path))
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("symlink_path_rejected")
    return path


def ignored(path, project=PROJECT):
    if not path.is_relative_to(project):
        raise ValueError("private_config_must_be_in_checkout")
    r = subprocess.run(
        ["git", "check-ignore", "-q", "--", str(path)],
        cwd=project,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if r.returncode != 0:
        raise ValueError("private_config_must_be_git_ignored")


def init_config(path, project=PROJECT):
    path = safe_path(path)
    ignored(path, project)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(
            "DEMO_USERNAME=showcase-local\nDEMO_PASSWORD="
            + secrets.token_urlsafe(32)
            + "\nDEMO_OWNER_PASSWORD="
            + secrets.token_urlsafe(32)
            + "\n"
        )


def private_values(path, project=PROJECT):
    from dotenv import dotenv_values

    path = safe_path(path)
    ignored(path, project)
    if (
        not path.is_file()
        or path.stat().st_nlink != 1
        or stat.S_IMODE(path.stat().st_mode) != 0o600
    ):
        raise ValueError("config_requires_private_600_regular_file")
    return dotenv_values(path, interpolate=False)


def provider_values(path, project=PROJECT):
    values = private_values(path, project)
    if any(not values.get(k) for k in LLM_KEYS):
        raise ValueError("missing_provider_configuration")
    url = urlsplit(values["LLM_BASE_URL"])
    if (
        url.scheme != "https"
        or url.hostname != "api.deepseek.com"
        or url.port not in (None, 443)
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path.rstrip("/") not in ("", "/v1")
        or values["LLM_MODEL"] != "deepseek-flash"
    ):
        raise ValueError("unsupported_provider_price_configuration")
    if not 0 < float(values["LLM_TIMEOUT_SECONDS"]) <= 240:
        raise ValueError("invalid_provider_timeout")
    return {k: values[k] for k in LLM_KEYS}


def environments(config, provider, seed, control, ledger, origin, backend_port, python, takeover):
    from app.demo.config import password_hash

    host = {k: os.environ[k] for k in HOST_KEYS if k in os.environ}
    backend = {
        **host,
        **provider,
        "DEMO_CONTROL_ROOT": str(control),
        "DEMO_SEED_ROOT": str(seed),
        "DEMO_USERNAME": config["DEMO_USERNAME"],
        "DEMO_PASSWORD_HASH": password_hash(config["DEMO_PASSWORD"]),
        "DEMO_OWNER_PASSWORD_HASH": password_hash(config["DEMO_OWNER_PASSWORD"]),
        "DEMO_ALLOWED_ORIGINS": origin,
        "DEMO_COOKIE_SECURE": "false",
        "DEMO_CONFLICT_POLICY": "takeover_enabled" if takeover else "wait_only",
        "DEMO_CHILD_MODE": "real",
        "DEMO_CHILD_PYTHON": python,
        "DEMO_CHILD_STARTUP_TIMEOUT": "120",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "TOKENIZERS_PARALLELISM": "false",
    }
    if provider:
        backend.update(FINDOC_PROVIDER_BUDGET_DB=str(ledger), FINDOC_PROVIDER_CAP_CNY="5")
    else:
        backend.update(
            LLM_API_KEY="disabled-local",
            LLM_MODEL="disabled-no-calls",
            LLM_BASE_URL="http://127.0.0.1:9/v1",
            LLM_TIMEOUT_SECONDS="1",
        )
    frontend = {
        **host,
        "VITE_FINDOC_DEMO_MODE": "1",
        "VITE_FINDOC_SHOWCASE_PREVIEW_CHARTS": "1",
        "FINDOC_E2E_DISABLE_ENV_FILES": "1",
        "FINDOC_API_ORIGIN": f"http://127.0.0.1:{backend_port}",
    }
    return backend, frontend


def port_available(port):
    if not 1 <= port <= 65535:
        raise ValueError("invalid_port")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", port))


def wait_ready(url, process):
    import httpx

    with httpx.Client(trust_env=False, timeout=1) as client:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("local_process_exited")
            try:
                if client.get(url).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
    raise RuntimeError("local_startup_timeout")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--init-config", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--config", type=Path, default=PROJECT / "data/showcase-local.env")
    parser.add_argument(
        "--llm-config",
        type=Path,
        help="Optional private ignored server dotenv; deepseek-flash only",
    )
    parser.add_argument("--seed", type=Path, default=PROJECT / "data/showcase-seed-v1")
    parser.add_argument(
        "--control", type=Path, default=PROJECT / "data/showcase-local-controller-v1"
    )
    parser.add_argument("--port", type=int, default=14530)
    parser.add_argument("--gateway-port", type=int, default=0)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--node", default=shutil.which("node"))
    parser.add_argument(
        "--owner-takeover",
        action="store_true",
        help="Enable takeover only with separate owner password",
    )
    args = parser.parse_args(argv)
    if args.init_config:
        init_config(args.config, PROJECT)
        print("Private local config created; inspect it locally. Credentials are not printed.")
        return
    from app.demo.seed import verify_seed

    seed, control = safe_path(args.seed), safe_path(args.control)
    data = safe_path(PROJECT / "data")
    ledger = safe_path(data / "showcase-cost-control/provider-budget.db")
    if (
        not seed.is_relative_to(data)
        or not control.is_relative_to(data)
        or control == data
        or control == seed
        or control in seed.parents
        or seed in control.parents
        or control == ledger.parent
        or control in ledger.parents
        or ledger.parent in control.parents
        or control.name != "showcase-local-controller-v1"
    ):
        raise ValueError("isolated_data_paths_required")
    config = private_values(args.config, PROJECT)
    if any(not config.get(k) for k in ("DEMO_USERNAME", "DEMO_PASSWORD", "DEMO_OWNER_PASSWORD")):
        raise ValueError("missing_login_configuration")
    if config["DEMO_PASSWORD"] == config["DEMO_OWNER_PASSWORD"]:
        raise ValueError("distinct_owner_password_required")
    provider = provider_values(args.llm_config, PROJECT) if args.llm_config else {}
    if provider:
        # This entry consumes an existing root allowance, never creates a fresh budget.
        if not ledger.is_file() or ledger.stat().st_nlink != 1:
            raise ValueError("existing_shared_budget_required")
        with sqlite3.connect(ledger.as_uri() + "?mode=ro", uri=True) as db:
            if db.execute("SELECT cap FROM config WHERE id=1").fetchone() != ("5",):
                raise ValueError("shared_budget_cap_mismatch")
    manifest, digest = verify_seed(seed)
    python, node = shutil.which(args.python), shutil.which(args.node or "")
    if not python or not node or not (PROJECT / "frontend/node_modules/vite/bin/vite.js").is_file():
        raise ValueError("existing_python_node_vite_required")
    port_available(args.port)
    if args.gateway_port:
        port_available(args.gateway_port)
        if args.gateway_port == args.port:
            raise ValueError("distinct_ports_required")
    summary = dict(
        origin=f"http://127.0.0.1:{args.port}",
        seed_version=manifest["seed_version"],
        manifest_sha256=digest,
        llm="budgeted-deepseek-flash" if provider else "disabled",
        conflict_policy="owner-password-only" if args.owner_takeover else "wait_only",
    )
    if args.check:
        print(json.dumps(summary))
        return
    # Never truncate or replenish the shared allowance. Existing cap is checked by the guard.
    if provider:
        from app.demo.provider_budget import ProviderBudget

        ProviderBudget(ledger, "5")
    control.mkdir(parents=True, exist_ok=True, mode=0o700)
    lockfd = os.open(control / "launcher.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    processes = []

    def stop(signum, frame):
        raise KeyboardInterrupt()

    previous = signal.signal(signal.SIGTERM, stop)
    try:
        fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", args.gateway_port))
            gateway_port = sock.getsockname()[1]
        backend, frontend = environments(
            config,
            provider,
            seed,
            control,
            ledger,
            summary["origin"],
            gateway_port,
            python,
            args.owner_takeover,
        )
        logfd = os.open(
            control / "launcher.log", os.O_CREAT | os.O_APPEND | os.O_WRONLY | os.O_NOFOLLOW, 0o600
        )
        os.fchmod(logfd, 0o600)
        with os.fdopen(logfd, "ab") as log:
            commands = [
                (
                    [
                        python,
                        "-m",
                        "uvicorn",
                        "app.demo.entrypoint:create_app",
                        "--factory",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(gateway_port),
                        "--no-access-log",
                    ],
                    backend,
                    PROJECT,
                    f"http://127.0.0.1:{gateway_port}/demo/status",
                ),
                (
                    [
                        node,
                        str(PROJECT / "frontend/node_modules/vite/bin/vite.js"),
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(args.port),
                        "--strictPort",
                    ],
                    frontend,
                    PROJECT / "frontend",
                    summary["origin"],
                ),
            ]
            for cmd, env, cwd, url in commands:
                process = subprocess.Popen(
                    cmd,
                    env=env,
                    cwd=cwd,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                    start_new_session=True,
                )
                processes.append(process)
                wait_ready(url, process)
            print(json.dumps(summary))
            print(
                "Local preview ready; credentials remain in private config. Ctrl+C stops owned processes."
            )
            while all(p.poll() is None for p in processes):
                time.sleep(0.2)
            raise RuntimeError("local_process_exited")
    except KeyboardInterrupt:
        pass
    finally:
        for p in reversed(processes):
            if p.poll() is None:
                os.killpg(p.pid, signal.SIGTERM)
                try:
                    p.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid, signal.SIGKILL)
                    p.wait(timeout=5)
        os.close(lockfd)
        signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    # Support both `python -m scripts.run_showcase_local` and direct script execution.
    sys.path.insert(0, str(PROJECT))
    try:
        main()
    except Exception:
        print(
            "Local showcase command failed; check private config, isolated paths, seed, dependencies and ports. No process was adopted.",
            file=sys.stderr,
        )
        sys.exit(1)
