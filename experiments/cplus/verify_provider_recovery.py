"""One new sourced business answer after an authenticated, non-generating health check.

Never replay an earlier operation or replace the session-wide budget ledger.
"""

import json
from pathlib import Path
import time
from uuid import uuid4

from dotenv import dotenv_values
import httpx

from experiments.cplus.real_model_paths import ledger


def main():
    root = Path(__file__).resolve().parents[2]
    original_budget = (
        root.parent.parent
        / "findoc-showcase-c-integration"
        / "findoc-agent/data/showcase-cost-control/provider-budget.db"
    )
    if not original_budget.is_file():
        raise RuntimeError("existing_shared_ledger_required")
    config = dotenv_values(root / "data/showcase-local.env", interpolate=False)
    output = root / "data/cplus-provider-recovery/result.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    proof = dict(
        tier="REAL_SOCKET_HTTP_PUBLIC_PDF_BGE_MILVUS_ONE_NEW_PROVIDER_OPERATION",
        human_approvals=0,
        provider_calls_allowed=1,
        budget_before=ledger(original_budget),
        origin="http://127.0.0.1:14542",
        previous_unknown_not_replayed=True,
    )

    def save():
        proof["budget_after"] = ledger(original_budget)
        delta = proof["budget_after"]["physical_calls"] - proof["budget_before"]["physical_calls"]
        if delta > 1:
            raise RuntimeError("unexpected_physical_call_count")
        output.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n")

    with httpx.Client(
        base_url=proof["origin"], trust_env=False, timeout=180, headers={"Origin": proof["origin"]}
    ) as client:

        def req(method, path, body=None):
            if method == "POST":
                body = {"operation_id": str(uuid4()), **(body or {})}
            response = client.request(method, "/api" + path, json=body)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"{method} {path}: HTTP {response.status_code}: {response.text[:300]}"
                )
            return response.json()

        try:
            for _ in range(180):
                if req("GET", "/demo/status")["service_state"] == "ready":
                    break
                time.sleep(0.5)
            login = req(
                "POST",
                "/demo/login",
                {"username": config["DEMO_USERNAME"], "password": config["DEMO_PASSWORD"]},
            )
            for _ in range(240):
                if req("GET", "/demo/operations/" + login["operation_id"]).get("claimable"):
                    break
                time.sleep(0.5)
            req("POST", "/demo/claim", {"attempt_operation_id": login["operation_id"]})
            companies = req("GET", "/companies")
            company = next(x for x in companies if x["security_code"] == "000651")
            sources = []
            for doc in req("GET", "/documents"):
                if doc["status"] == "ready":
                    ref = req("GET", f"/cplus/documents/{doc['document_id']}/research-source")
                    if ref["company_id"] == company["company_id"] and ref["report_year"] == 2025:
                        sources.append(ref)
            if len(sources) != 1:
                raise RuntimeError("exact_current_source_required")
            proof["source"] = sources[0]
            req("POST", "/cplus/retrieval/builds", {"sources": sources})
            scope = req(
                "POST",
                "/cplus/research/contexts",
                {"title": "新的真实模型来源研究验收", "selected_sources": sources},
            )["result"]
            operation_id = str(uuid4())
            proof["new_answer_operation_id"] = operation_id
            proof["question"] = (
                "请用简短中文说明营业收入披露的含义，只依据已选年报原文，不计算金额，不提供投资建议。"
            )
            save()
            started = time.monotonic()
            try:
                receipt = req(
                    "POST",
                    "/cplus/research/answers",
                    {
                        "operation_id": operation_id,
                        "context_id": scope["context_id"],
                        "context_revision": scope["revision"],
                        "context_sha256": scope["context_sha256"],
                        "question": proof["question"],
                    },
                )
                proof["receipt"] = receipt
                answer = receipt.get("result", {})
                proof["result"] = (
                    "PASS_REAL_PROVIDER_EXECUTION_UNREVIEWED"
                    if receipt.get("state") == "completed"
                    and answer.get("state") == "completed"
                    and answer.get("interpretation")
                    and answer.get("findings")
                    else "PARTIAL"
                )
            except Exception as exc:
                proof["result"] = "UNKNOWN_NO_REPLAY"
                proof["safe_error"] = str(exc)[:500]
                try:
                    proof["readonly_original_operation"] = req(
                        "GET", "/cplus/research/operations/" + operation_id
                    )
                except Exception as read_exc:
                    proof["readonly_error"] = str(read_exc)[:300]
            proof["elapsed_answer_seconds"] = round(time.monotonic() - started, 3)
            save()
        except Exception as exc:
            proof.setdefault("result", "SETUP_FAILED_NO_REPLAY")
            proof["safe_setup_error"] = str(exc)[:500]
        finally:
            try:
                req("POST", "/demo/logout")
            except Exception as exc:
                proof["cleanup_error"] = str(exc)[:300]
            save()
    print(
        json.dumps(
            {k: proof[k] for k in ["result", "budget_before", "budget_after"]}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
