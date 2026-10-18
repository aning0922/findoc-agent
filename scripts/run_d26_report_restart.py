"""Restart only the integration's own stopped test DB; production history factory."""

import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

product = Path(__file__).resolve().parent.parent


def create_app():
    from app.api.report_history import create_report_history_app

    runtime = Path(os.environ["INTEGRATION_HISTORY_ROOT"]).resolve()
    protected = [p.resolve() for p in product.parent.glob("findoc-*") if p.resolve() != product]

    def audit(event, args):
        if event == "socket.connect":
            raise RuntimeError("History test cannot connect to services")
        if event == "sqlite3.connect" and args[0] != ":memory:":
            from urllib.parse import unquote, urlparse

            raw = args[0]
            p = Path(unquote(urlparse(raw).path) if str(raw).startswith("file:") else raw).resolve()
            if not p.is_relative_to(runtime):
                raise RuntimeError("History DB outside integration runtime")
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            p = Path(os.fsdecode(args[0])).resolve()
            if any(p.is_relative_to(d) for d in protected):
                raise RuntimeError("Protected worktree access forbidden")

    sys.addaudithook(audit)
    return create_report_history_app(runtime / "documents.db")


def main():
    evidence = Path(os.environ.get("D26_EVIDENCE_ROOT", product / "product/d26/evidence")).resolve()
    browser = Path(os.environ.get("D26_REPORT_EVIDENCE_DIR", evidence / "b-reports")).resolve()
    record = json.loads((browser / "record.json").read_text())
    assert record["exit_code"] == 0 and record["servers_stopped"] and record["simulated_test"]
    runtime = Path(record["runtime_root"]).resolve()
    import tempfile

    assert runtime.name.startswith("findoc-d11-d21-ux-p1-") and runtime.is_relative_to(
        Path(tempfile.gettempdir()).resolve()
    )
    proof = json.loads((browser / "report-fault-proof.json").read_text())

    def manifest():
        return {
            str(p.relative_to(runtime)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in runtime.rglob("*")
            if p.is_file()
        }

    before = manifest()
    node = os.environ["FINDOC_NODE"]
    env = {
        k: v for k, v in os.environ.items() if not k.startswith("LLM_") and k != "OPENAI_API_KEY"
    }
    env.update(
        INTEGRATION_HISTORY_ROOT=str(runtime),
        FINDOC_UX_RUNTIME_ROOT=str(runtime),
        FINDOC_E2E_DISABLE_ENV_FILES="1",
        PYTHONDONTWRITEBYTECODE="1",
        INTEGRATION_REPORT_PROOF=str(browser / "report-fault-proof.json"),
    )
    phases = []
    for phase in ["reopen", "restart"]:
        out = evidence / (os.environ.get("D26_RESTART_PREFIX", "b-report") + "-" + phase)
        out.mkdir(parents=True)
        ports = []
        for _ in range(2):
            with socket.socket() as s:
                s.bind(("127.0.0.1", 0))
                ports.append(s.getsockname()[1])
        api = f"http://127.0.0.1:{ports[0]}"
        web = f"http://127.0.0.1:{ports[1]}"
        env.update(FINDOC_API_ORIGIN=api, INTEGRATION_RESTART_OUT=str(out))
        config = product / "frontend/test-results/d26-restart.config.mjs"
        config.write_text(
            'import {defineConfig} from "@playwright/test"; export default defineConfig('
            + json.dumps(
                dict(
                    testDir=str(product / "frontend/e2e"),
                    testMatch="d26-restart.spec.ts",
                    workers=1,
                    retries=0,
                    timeout=60000,
                    reporter=[["line"], ["json", {"outputFile": str(out / "results.json")}]],
                    use={
                        "baseURL": web,
                        "viewport": {"width": 1280, "height": 900},
                        "trace": "retain-on-failure",
                    },
                    outputDir=str(out / "traces"),
                )
            )
            + ");"
        )
        handles = []
        processes = []
        try:
            for name, cmd, cwd in [
                (
                    "api",
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "tests.support.d26_report_app:create_readonly_app",
                        "--factory",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(ports[0]),
                    ],
                    product,
                ),
                (
                    "web",
                    [
                        node,
                        str(product / "frontend/node_modules/vite/bin/vite.js"),
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(ports[1]),
                        "--strictPort",
                    ],
                    product / "frontend",
                ),
            ]:
                f = (out / f"{name}.log").open("w")
                handles.append(f)
                processes.append(
                    subprocess.Popen(cmd, cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT)
                )
            for url in [api + "/companies", web]:
                deadline = time.monotonic() + 60
                while True:
                    assert all(p.poll() is None for p in processes)
                    try:
                        with urlopen(url, timeout=1) as r:
                            assert r.status == 200
                        break
                    except Exception:
                        if time.monotonic() > deadline:
                            raise
                        time.sleep(0.2)
            payloads = []
            for version in [proof["saved"], proof["v2"]]:
                original = version["report"]
                rid = original["report_id"]
                rev = original["revision"]
                with urlopen(f"{api}/reports/{rid}/revisions/{rev}", timeout=5) as r:
                    actual = json.load(r)
                assert actual["report"] == original
                payloads.append(
                    {
                        "revision": rev,
                        "payload_sha256": version["payload_sha256"],
                        "snapshot_exact": True,
                    }
                )
            with (out / "browser.log").open("w") as f:
                code = subprocess.run(
                    [
                        node,
                        str(product / "frontend/node_modules/@playwright/test/cli.js"),
                        "test",
                        "--config",
                        str(config),
                    ],
                    cwd=product / "frontend",
                    env=env,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                ).returncode
            assert code == 0
        finally:
            for p in processes:
                p.terminate()
            for p in processes:
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()
            for f in handles:
                f.close()
        assert manifest() == before
        phases.append(
            {
                "phase": phase,
                "ports": ports,
                "exact_report_snapshots": payloads,
                "runtime_files_unchanged": True,
                "servers_stopped": True,
            }
        )
    (
        evidence / (os.environ.get("D26_RESTART_PREFIX", "b-report") + "-restart-proof.json")
    ).write_text(
        json.dumps(
            {
                "runtime": str(runtime),
                "files_before_and_after": before,
                "phases": phases,
                "readonly_factory": "app.api.report_history.create_report_history_app",
                "no_model_or_index_assembly": True,
                "simulated_test": True,
                "human_acceptances": 0,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
