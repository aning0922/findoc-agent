"""Reproducible D28 local lifecycle, real HTTP preparation and evidence collection.

No confirmation, financial persistence, resume or report-save action is available here.
Secrets enter only the API child environment; only allowlisted metadata is exported.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parent.parent
BASELINE = "c0eaf78044b462284bcb02939ee32268e796a561"


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_root(raw):
    root = raw.expanduser().resolve()
    if not (root / "d28-root.json").is_file():
        raise ValueError("Use init to create a new D28 root first")
    marker = json.loads((root / "d28-root.json").read_text())
    if marker.get("schema") != "d28-clean-root-v1" or marker.get("root") != str(root):
        raise ValueError("D28 root identity mismatch")
    return root


def events(root):
    path = root / "events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def serve(args, root):
    from dotenv import dotenv_values
    allowed = ("LLM_API_KEY", "LLM_MODEL", "LLM_BASE_URL", "LLM_TIMEOUT_SECONDS")
    config = {k: v for k, v in dotenv_values(args.credentials).items() if k in allowed and v}
    if any(not config.get(k) for k in allowed[:3]):
        raise ValueError("Credential file must supply LLM_API_KEY, LLM_MODEL, LLM_BASE_URL")
    config.setdefault("LLM_TIMEOUT_SECONDS", "90")
    if args.api_port == args.web_port:
        raise ValueError("API and web ports must differ")
    for port in (args.api_port, args.web_port):
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(("127.0.0.1", port))
            probe.listen(1)
    node = shutil.which("node")
    if not node or not subprocess.check_output([node, "--version"], text=True).startswith("v24."):
        raise ValueError("Put Node 24 on PATH")
    if not (ROOT / "frontend/dist/index.html").is_file():
        raise ValueError("Build the formal frontend first")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("LLM_", "FINDOC_"))
           and k not in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY")}
    env.update(FINDOC_RUNTIME_ROOT=str(root / "runtime"),
               FINDOC_API_ORIGIN=f"http://127.0.0.1:{args.api_port}",
               FINDOC_E2E_DISABLE_ENV_FILES="1", FINDOC_D28_EVENT_LOG=str(root / "events.jsonl"),
               OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", VECLIB_MAXIMUM_THREADS="1",
               TOKENIZERS_PARALLELISM="false", HF_HUB_OFFLINE="1")
    if args.hf_home:
        env["HF_HOME"] = str(args.hf_home.expanduser().resolve())
    children, pumps = [], []
    secrets = [config["LLM_API_KEY"], config["LLM_BASE_URL"]]

    def pump(stream, destination):
        with destination.open("w") as log:
            for line in stream:
                for secret in secrets:
                    line = line.replace(secret, "[redacted]")
                log.write(line)
                log.flush()

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    session = root / f"session-{uuid.uuid4().hex[:12]}"
    session.mkdir()
    commands = [
        ([sys.executable, "-m", "uvicorn", "scripts.d28_runtime_observer:create_app", "--factory",
          "--host", "127.0.0.1", "--port", str(args.api_port), "--no-access-log"], ROOT,
         {**env, **config}),
        ([node, str(ROOT / "frontend/node_modules/vite/bin/vite.js"), "preview", "--host",
          "127.0.0.1", "--port", str(args.web_port), "--strictPort"], ROOT / "frontend", env),
    ]
    try:
        for index, (command, cwd, child_env) in enumerate(commands):
            child = subprocess.Popen(command, cwd=cwd, env=child_env, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, start_new_session=True)
            children.append(child)
            thread = threading.Thread(target=pump, args=(child.stdout, session / f"server-{index}.log"))
            thread.start()
            pumps.append(thread)
        import httpx
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            if any(p.poll() is not None for p in children):
                raise RuntimeError("Service exited; inspect the redacted local session logs")
            try:
                if httpx.get(f"http://127.0.0.1:{args.web_port}/api/health", timeout=2,
                             trust_env=False).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError("Startup timed out; services will be stopped")
        state = dict(schema="d28-session-v1", runtime=str(root / "runtime"),
                     session=str(session), url=f"http://127.0.0.1:{args.web_port}",
                     api_port=args.api_port, web_port=args.web_port, pids=[p.pid for p in children],
                     git_sha=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                     model=config["LLM_MODEL"], python=sys.version, platform=platform.platform(),
                     node=subprocess.check_output([node, "--version"], text=True).strip(),
                     dist={str(p.relative_to(ROOT)): sha(p) for p in (ROOT / "frontend/dist").rglob("*") if p.is_file()},
                     production_gates=True, copied_business_data=False, human_acceptance="pending")
        write(session / "session.json", state)
        write(root / "active-session.json", state)
        print(json.dumps(dict(url=state["url"], session=str(session), ready=True)), flush=True)
        while all(p.poll() is None for p in children):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for child in children:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
        for child in children:
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        for thread in pumps:
            thread.join(timeout=5)
        write(session / "stopped.json", dict(stopped_at=time.time(), exit_codes=[p.returncode for p in children]))


def prepare(root, client, out):
    sources = json.loads((ROOT / "product/validation/sources.json").read_text())
    companies = {}
    # This action is intentionally one-time. Unknown upload/create outcomes require GET inspection.
    current = client.get("/companies")
    current.raise_for_status()
    if current.json():
        raise ValueError("prepare requires a fresh empty runtime; use existing identity evidence after restart")
    for code, name, security in (("midea", "美的集团股份有限公司", "000333"),
                                 ("gree", "珠海格力电器股份有限公司", "000651")):
        response = client.post("/companies", json=dict(name=name, security_code=security, exchange="SZSE"))
        response.raise_for_status()
        companies[code] = response.json()["company_id"]
        write(out / "companies.json", companies)
    pdfs = root / "pdf-inputs"
    pdfs.mkdir(exist_ok=True)
    reports = []
    for source in sources:
        content = __import__("httpx").get(source["url"], timeout=120, follow_redirects=True)
        content.raise_for_status()
        path = pdfs / (source["id"] + ".pdf")
        path.write_bytes(content.content)
        if sha(path) != source["sha256"]:
            raise ValueError("Public source SHA mismatch; no upload permitted")
        code, year = source["id"].split("-")
        metadata = dict(company_id=companies[code], report_year=int(year), report_type="annual",
                        basis="PRC_GAAP", period_start=f"{year}-01-01", period_end=f"{year}-12-31",
                        source_url=source["url"])
        response = client.post("/report-documents", data={"metadata": json.dumps(metadata)},
                               files={"file": (path.name, path.read_bytes(), "application/pdf")})
        response.raise_for_status()
        doc = response.json()["document_id"]
        entry = dict(report=source["id"], document_id=doc, upload=response.json(), pdf_sha256=sha(path))
        reports.append(entry)
        write(out / "reports.json", reports)
        deadline = time.monotonic() + 1800
        while time.monotonic() < deadline:
            result = client.get(f"/documents/{doc}")
            result.raise_for_status()
            if result.json()["status"] in ("ready", "failed"):
                break
            time.sleep(1)
        entry["document"] = result.json()
        response = client.get(f"/documents/{doc}/source")
        entry["source_http"] = response.status_code
        entry["source"] = response.json()
        write(out / "reports.json", reports)
        print(json.dumps(dict(report=entry["report"], status=entry["document"]["status"])), flush=True)
        if entry["document"]["status"] != "ready":
            raise RuntimeError("Document preparation failed; preserve evidence and inspect before new action")


def qa(root, client, out, reports_path):
    import csv
    reports = {r["report"]: r for r in json.loads(reports_path.read_text())}
    for report in reports.values():
        response = client.get(f"/documents/{report['document_id']}/source")
        response.raise_for_status()
        current = response.json()
        for field in ("company_id", "document_id", "source_revision", "content_sha256", "parser_version"):
            if current[field] != report["source"][field]:
                raise ValueError("Question evidence is not from this runtime's current source")
    questions = list(csv.DictReader((ROOT / "product/ux-global-s6/human/semantic-18.csv").open()))
    results = []
    for question in questions:
        before = len(events(root))
        operation = str(uuid.uuid4())
        body = dict(operation_id=operation, query=question["question"], document_ids=[
            reports[key]["document_id"] for key in question["source_reports"].split(";")])
        item = dict(question_id=question["question_id"], request=body, human_result="not_reviewed")
        # Save identity before POST. Never auto-repeat a request after a transport failure.
        write(out / (question["question_id"] + "-request.json"), item)
        start = time.monotonic()
        try:
            response = client.post("/research/runs", json=body,
                                   headers={"X-D28-Evidence": question["question_id"]})
            item.update(http_status=response.status_code, response=response.json(),
                        response_bytes_sha256=hashlib.sha256(response.content).hexdigest())
        except __import__("httpx").HTTPError as exc:
            item.update(transport_error=type(exc).__name__, outcome="unknown")
            try:
                recovery = client.get(f"/research/runs/by-operation/{operation}")
                item.update(recovery_http=recovery.status_code, recovery=recovery.json())
            except __import__("httpx").HTTPError as recovery_error:
                item["recovery_error"] = type(recovery_error).__name__
        item["seconds"] = time.monotonic() - start
        item["events"] = events(root)[before:]
        item["sources"] = [reports[k]["source"] for k in question["source_reports"].split(";")]
        item["response_sha256"] = hashlib.sha256(json.dumps(item.get("response"), ensure_ascii=False,
                                                            sort_keys=True).encode()).hexdigest()
        answer = item.get("response", {}).get("result", {}).get("content") or ""
        item["answer_utf8_sha256"] = hashlib.sha256(answer.encode("utf-8")).hexdigest()
        write(out / (question["question_id"] + ".json"), item)
        results.append(item)
        write(out / "results.json", results)
        print(json.dumps(dict(question=question["question_id"],
                              status=item.get("response", {}).get("status", "unknown"))), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "serve", "prepare", "qa", "snapshot"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--credentials", type=Path)
    parser.add_argument("--hf-home", type=Path)
    parser.add_argument("--api-port", type=int, default=18168)
    parser.add_argument("--web-port", type=int, default=14268)
    parser.add_argument("--reports", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.action == "init":
        root = args.root.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=False)
        write(root / "d28-root.json", dict(schema="d28-clean-root-v1", root=str(root),
                                           baseline=BASELINE, created_at=time.time(),
                                           copied_business_data=False))
        print(json.dumps(dict(root=str(root), empty=True)))
        return
    root = checked_root(args.root)
    if args.action == "serve":
        if args.credentials is None:
            parser.error("serve requires --credentials (path only; never pass secret values)")
        serve(args, root)
        return
    if args.out is None:
        parser.error("evidence actions require a fresh --out directory")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    import httpx
    with httpx.Client(base_url=f"http://127.0.0.1:{args.web_port}/api", timeout=240,
                      trust_env=False) as client:
        client.get("/health").raise_for_status()
        if args.action == "prepare":
            prepare(root, client, out)
        elif args.action == "qa":
            if args.reports is None:
                parser.error("qa requires this root's --reports identity evidence")
            qa(root, client, out, args.reports)
        else:
            before = len(events(root))
            for name, url in (("companies", "/companies"), ("runs", "/research/runs"),
                              ("tasks", "/research/tasks"), ("reports", "/reports")):
                response = client.get(url)
                write(out / f"{name}.json", dict(http_status=response.status_code, body=response.json()))
            write(out / "events.json", events(root)[before:])


if __name__ == "__main__":
    main()
