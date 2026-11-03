"""Disposable actual UI → gateway → BGE/Milvus smoke; provider calls require explicit config."""
import argparse
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import tempfile

from app.demo.config import password_hash
from app.demo.seed import build_synthetic_seed, verify_seed
from scripts.showcase_demo_http_check import free_port, launch, wait_http


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--flow', choices=('demo', 'disclosure', 'parsing', 'finance', 'memory', 'research', 'eval', 'archive'), default='demo')
    parser.add_argument('--seed-root', type=Path)
    parser.add_argument("--llm-config", type=Path, help="Ignored local server config; never echoed or sent to frontend")
    parser.add_argument("--research-ui", action="store_true")
    parser.add_argument("--prepare-full-seed", action="store_true")
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[2]
    evidence = Path(tempfile.mkdtemp(prefix="findoc-integrated-http-")).resolve()
    seed, control = args.seed_root.resolve() if args.seed_root else evidence / "seed", evidence / "control"
    manifest, digest = verify_seed(seed) if args.seed_root else build_synthetic_seed(seed)
    backend_port, vite_port = free_port(), free_port()
    origin = f"http://127.0.0.1:{vite_port}"
    username, password, owner = "isolated-ui-check", secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    env = {**os.environ, "DEMO_CONTROL_ROOT": str(control), "DEMO_SEED_ROOT": str(seed),
           "DEMO_USERNAME": username, "DEMO_PASSWORD_HASH": password_hash(password),
           "DEMO_OWNER_PASSWORD_HASH": password_hash(owner), "DEMO_ALLOWED_ORIGINS": origin,
           "DEMO_COOKIE_SECURE": "false", "DEMO_CONFLICT_POLICY": "takeover_enabled", "DEMO_CHILD_MODE": "real",
           "DEMO_CHILD_STARTUP_TIMEOUT": "90", "LLM_API_KEY": "disabled-isolated-check-only",
           "LLM_MODEL": "disabled-no-calls", "LLM_BASE_URL": "http://127.0.0.1:9/v1", "LLM_TIMEOUT_SECONDS": "1",
           "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "TOKENIZERS_PARALLELISM": "false"}
    budget = None
    if args.llm_config:
        if args.flow not in ('research', 'eval'):
            raise ValueError('Provider config is restricted to the explicit research validation')
        from dotenv import dotenv_values
        from app.demo.provider_budget import ProviderBudget
        from urllib.parse import urlsplit
        values = dotenv_values(args.llm_config, interpolate=False)
        names = ('LLM_API_KEY', 'LLM_MODEL', 'LLM_BASE_URL', 'LLM_TIMEOUT_SECONDS')
        if any(not values.get(name) for name in names):
            raise ValueError('Missing server LLM configuration')
        url = urlsplit(values['LLM_BASE_URL'])
        if url.scheme != 'https' or url.hostname != 'api.deepseek.com' or url.username or url.password or url.query or values['LLM_MODEL'] != 'deepseek-flash':
            raise ValueError('Unverified provider price/configuration')
        ledger = project / 'data/showcase-cost-control/provider-budget.db'
        budget = ProviderBudget(ledger)
        env.update({name: values[name] for name in names})
        env.update(FINDOC_PROVIDER_BUDGET_DB=str(ledger), FINDOC_PROVIDER_CAP_CNY='5')
    frontend_env = {k: v for k, v in env.items() if not k.startswith(('LLM_', 'FINDOC_PROVIDER_'))}
    processes = []
    try:
        with (evidence / "runtime.log").open("wb") as log:
            gateway = launch([sys.executable, "-m", "uvicorn", "app.demo.entrypoint:create_app", "--factory",
                              "--host", "127.0.0.1", "--port", str(backend_port), "--no-access-log"], env, project, log)
            processes.append(gateway)
            wait_http(f"http://127.0.0.1:{backend_port}/demo/status", gateway)
            frontend = project / "frontend"
            vite = launch(["node", str(frontend / "node_modules/vite/bin/vite.js"), "--host", "127.0.0.1",
                           "--port", str(vite_port), "--strictPort"], {**frontend_env, "VITE_FINDOC_DEMO_MODE": "1",
                           "FINDOC_E2E_DISABLE_ENV_FILES": "1", "FINDOC_API_ORIGIN": f"http://127.0.0.1:{backend_port}"}, frontend, log)
            processes.append(vite)
            wait_http(origin, vite)
            script = {'demo': 'showcase-integrated-http.mjs', 'disclosure': 'showcase-disclosure-http.mjs',
                      'parsing': 'showcase-parsing-http.mjs', 'finance': 'showcase-finance-http.mjs', 'memory': 'showcase-memory-http.mjs', 'research': 'showcase-research-http.mjs', 'eval': 'showcase-eval-http.mjs', 'archive': 'showcase-archive-http.mjs'}[args.flow]
            result = subprocess.run(["node", str(frontend / 'e2e' / script)], cwd=frontend,
                                    env={**frontend_env, "DEMO_CHECK_ORIGIN": origin, "DEMO_CHECK_OUTPUT": str(evidence),
                                         "DEMO_CHECK_OCR_DOCUMENT_ID": next((doc["document_id"] for doc in json.loads((seed / "seed-inventory.json").read_text())["documents"] if doc["public_provenance"]["origin"] == "derived_public"), "") if (seed / "seed-inventory.json").is_file() else "",
                                         "DEMO_CHECK_EXPECTED_COMPANIES": str(next(spec for spec in manifest["sqlite"] if spec["path"] == "documents.db")["tables"]["companies"]),
                                         "DEMO_CHECK_EXPECTED_READY": str(sum(1 for doc in json.loads((seed / "seed-inventory.json").read_text())["documents"] if doc["legacy_status"] == "ready")) if (seed / "seed-inventory.json").is_file() else "0",
                                         "DEMO_CHECK_USERNAME": username,
                                         "DEMO_CHECK_RESEARCH_UI": "1" if args.research_ui else "0",
                                         "DEMO_CHECK_PREPARE_SEED": "1" if args.prepare_full_seed else "0", "DEMO_CHECK_PASSWORD": password,
                                         "DEMO_CHECK_OWNER_PASSWORD": owner,
                                         "DEMO_CHECK_SCAN_PATH": str(project / 'data/showcase-ocr-spike-20261103/derived-scan-page-9.pdf')},
                                    capture_output=True, text=True, timeout=600 if args.flow in ('research', 'eval') else 360 if args.flow == 'disclosure' else 180)
            (evidence / "browser.log").write_text(result.stdout + result.stderr)
            if result.returncode:
                raise RuntimeError("Actual UI HTTP check failed; inspect browser.log")
            verify_seed(seed, digest)
            print(json.dumps({"evidence_directory": str(evidence), "checks": json.loads(result.stdout.strip().splitlines()[-1]),
                              "seed_unchanged": True}, ensure_ascii=False))
    finally:
        if budget:
            (evidence / 'provider-cost-summary.json').write_text(json.dumps(budget.summary(), indent=2))
        for process in reversed(processes):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
        print(f"Isolated evidence retained: {evidence}")


if __name__ == "__main__":
    main()
