"""One bounded live QA check: fresh storage, real BGE/Milvus/provider, no financial consent.

Credentials are read from the explicit env file and never written to evidence.
The complete live annual-report workflow is not certified by this single QA check.
"""

import argparse
import os
import sys
import json
import time
import hashlib
import uuid
import tempfile
from pathlib import Path

from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
parser = argparse.ArgumentParser()
parser.add_argument("--out", type=Path, required=True)
parser.add_argument("--env-file", type=Path, required=True)
parser.add_argument("--source-root", type=Path, required=True)
args = parser.parse_args()

cfg = dotenv_values(args.env_file)
for key in ("LLM_API_KEY", "LLM_MODEL", "LLM_BASE_URL"):
    if not cfg.get(key):
        raise RuntimeError("missing live configuration")
    os.environ[key] = cfg[key]
os.environ.update(
    LLM_TIMEOUT_SECONDS="45",
    HF_HUB_OFFLINE="1",
    TOKENIZERS_PARALLELISM="false",
    OMP_NUM_THREADS="1",
    MKL_NUM_THREADS="1",
    VECLIB_MAXIMUM_THREADS="1",
)
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)
runtime = Path(tempfile.mkdtemp(prefix="findoc-ux-live-"))
proof = dict(
    runtime_root=str(runtime),
    actual_model=False,
    actual_bge=False,
    actual_milvus=False,
    human_acceptances=0,
    provider_attempts=0,
    status="starting",
    financial_acceptance_performed=False,
)


def save():
    (out / "proof.json").write_text(json.dumps(proof, ensure_ascii=False, indent=2))


save()
try:
    from openai.resources.chat.completions import Completions

    orig = Completions.create

    def limited(self, *a, **kw):
        if proof["provider_attempts"] >= 1:
            raise RuntimeError("single provider attempt budget exhausted")
        proof["provider_attempts"] += 1
        save()
        kw["max_tokens"] = 2048
        result = orig(self, *a, **kw)
        proof["actual_model"] = True
        save()
        return result

    Completions.create = limited
    from app.api.runtime_factory import create_runtime_app
    from fastapi.testclient import TestClient

    app = create_runtime_app(runtime)
    proof.update(status="runtime_ready", actual_bge=True, actual_milvus=True)
    save()
    with TestClient(app) as client:
        r = client.post(
            "/companies",
            json={"name": "美的集团股份有限公司", "security_code": "000333", "exchange": "SZSE"},
        )
        assert r.status_code in (200, 201), r.status_code
        company = r.json()["company_id"]
        source = next(
            s
            for s in json.loads((root / "product/validation/sources.json").read_text())
            if s["id"] == "midea-2025"
        )
        path = args.source_root.resolve() / source["path"]
        content = path.read_bytes()
        assert hashlib.sha256(content).hexdigest() == source["sha256"]
        r = client.post(
            "/report-documents",
            files={"file": (path.name, content, "application/pdf")},
            data={
                "metadata": json.dumps(
                    {
                        "company_id": company,
                        "report_year": 2025,
                        "report_type": "annual",
                        "basis": "PRC_GAAP",
                        "period_start": "2025-01-01",
                        "period_end": "2025-12-31",
                    }
                )
            },
        )
        assert r.status_code == 202, r.status_code
        doc = r.json()["document_id"]
        proof.update(status="processing", document_id=doc, source_sha256=source["sha256"])
        save()
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            row = client.get(f"/documents/{doc}").json()
            if row["status"] in ("ready", "failed"):
                break
            time.sleep(1)
        assert row["status"] == "ready", row["status"]
        proof.update(status="querying")
        save()
        operation = str(uuid.uuid4())
        r = client.post(
            "/research/runs",
            json={
                "operation_id": operation,
                "document_ids": [doc],
                "query": "请引用年报原文说明美的集团2025年的主要业务，不计算同比。",
            },
        )
        result = r.json()
        proof.update(
            status=result.get("status", "http_failure"),
            http_status=r.status_code,
            run_id=result.get("run_id"),
            error_code=result.get("error_code"),
        )
        (out / "run.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
        save()
        if result.get("run_id"):
            reads = [client.get("/research/runs/" + result["run_id"]).json() for _ in range(2)]
            proof["readonly_result_unchanged"] = all(
                v.get("result") == result.get("result") for v in reads
            )
            proof["provider_attempts_after_reread"] = proof["provider_attempts"]
            save()
except Exception as exc:
    proof.update(status="failed", error_type=type(exc).__name__)
    save()
    print(json.dumps(proof), flush=True)
    sys.exit(1)
print(json.dumps(proof), flush=True)
