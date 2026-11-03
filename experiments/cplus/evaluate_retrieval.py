"""Reproduce the exact M0 six queries against an owned real C+ runtime, no provider.

Run from this checkout with PYTHONPATH=. and the existing BGE/Milvus Python env.
No dotenv, login config, provider budget, or original runtime is read. A verified
public seed is copied into a never-before-existing TemporaryDirectory child.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from uuid import uuid4

PROJECT = Path(__file__).resolve().parents[2]
BUSINESS_BASELINE = "fcefb12"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text())


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def offline_environment():
    # Remove these names without inspecting their previous values.
    for name in (
        "FINDOC_PROVIDER_BUDGET_DB",
        "FINDOC_PROVIDER_CAP_CNY",
        "FINDOC_RUNTIME_ROOT",
        "DEMO_OWNER_PASSWORD",
        "DEMO_OWNER_PASSWORD_HASH",
        "DEMO_ACCESS_PASSWORD",
    ):
        os.environ.pop(name, None)
    os.environ.update(
        LLM_API_KEY="disabled-public-retrieval-evaluation",
        LLM_MODEL="disabled-no-calls",
        LLM_BASE_URL="http://127.0.0.1:9/v1",
        LLM_TIMEOUT_SECONDS="1",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        TOKENIZERS_PARALLELISM="false",
        FINDOC_CPLUS_ENABLED="1",
        DEMO_INTERNAL_INSTANCE="public-retrieval-evaluation",
    )


def post(client, path, body):
    operation = str(uuid4())
    response = client.post(path, json=dict(operation_id=operation, **body))
    if response.status_code != 200:
        raise RuntimeError(f"{path}: {response.status_code}: {response.text[:500]}")
    result = response.json()
    if "state" in result and "result" in result:
        assert result["state"] == "completed"
        return result["result"]
    return result


def run(coro):
    return asyncio.run(coro)


def agent_note(case_id, text):
    """Agent-only descriptive comments; never a human ground truth or metric."""
    if case_id.startswith("risk"):
        if "委托理财" in text:
            return "委托理财披露；对广义经营风险问题可能偏题，需人工判断。"
        if any(t in text for t in ("主要风险", "市场竞争加剧风险", "生产要素价格波动风险")):
            return "含经营风险章节/风险类别措辞；是否覆盖问题仍需人工审读。"
        return "含风险相关语句；是否为所问经营风险及其覆盖度尚未人工审读。"
    return "已核验来源原文；问题相关性与答案完整性尚未人工审读。"


async def dense_rows(app, refs, selection, hits):
    from app.retrieval_v2.models import EvidenceRef

    hybrid = app.state.cplus_retrieval_service
    records = [e for ref in refs for e in await hybrid.records(ref)]
    rows = []
    for rank, hit in enumerate(hits, 1):
        value = asdict(hit) if not isinstance(hit, dict) else hit
        page = value.get("page")
        text = value["text"]
        matches = [e for e in records if e.physical_page == page and text in e.text]
        verified = False
        error = None
        if len(matches) == 1:
            candidate = EvidenceRef(**{**matches[0].model_dump(), "text": text})
            try:
                await hybrid.verify(candidate)
                verified = True
            except Exception as exc:
                error = type(exc).__name__
        else:
            error = f"matching_source_records:{len(matches)}"
        rows.append(
            dict(
                rank=rank,
                physical_page=page,
                snippet=text[:500],
                full_text=text,
                dense_cosine=value["score"],
                score_type="COSINE",
                chunk_id=value.get("chunk_id"),
                document_id=value.get("document_id"),
                source_revision=value.get("source_revision"),
                exact_verified=verified,
                verification_error=error,
            )
        )
    return rows


def evaluate_six(app, client, before, output):
    from app.cplus.runtime import fast_ref
    from app.retrieval_v2.models import EvidenceRef

    hybrid = app.state.cplus_retrieval_service
    assert hybrid.provider is None and hybrid.guard is not None and hybrid.before_commit is not None
    refs_by_scope, results = {}, []
    for case in before["results"]:
        print("QUERY", case["case_id"], case["query"], flush=True)
        start = time.monotonic()
        selection = run(
            app.state.selection_preparer.prepare_many(
                document_ids=[s["document_id"] for s in case["sources"]], query=case["query"]
            )
        )
        assert [asdict(d) for d in selection.documents] == case["sources"], (
            "M0 source identity drift"
        )
        assert selection.selection_id == case["source_scope_sha"], "M0 exact scope hash drift"
        refs = [fast_ref(d) for d in selection.documents]
        key = selection.selection_id
        if key not in refs_by_scope:
            built = post(
                client, "/cplus/retrieval/builds", {"sources": [r.model_dump() for r in refs]}
            )
            refs_by_scope[key] = built
        dense = run(app.state.selected_scope_search.search(selection, top_k=5))
        dense_recheck = run(dense_rows(app, refs, selection, dense))
        old_rows = run(dense_rows(app, refs, selection, case["hits"]))
        after = post(
            client,
            "/cplus/retrieval/searches",
            {"sources": [r.model_dump() for r in refs], "query": case["query"], "top_k": 5},
        )
        assert after["index_status"] == "ready" and len(after["items"]) <= 5
        rows = []
        for rank, item in enumerate(after["items"], 1):
            evidence = EvidenceRef.model_validate(item["evidence_ref"])
            run(hybrid.verify(evidence))
            assert evidence.source_ref in refs
            assert item["text"] == evidence.text
            rows.append(
                dict(
                    rank=rank,
                    physical_page=evidence.physical_page,
                    snippet=evidence.text[:500],
                    full_text=evidence.text,
                    evidence_ref=evidence.model_dump(),
                    lexical_rank=item["lexical_rank"],
                    dense_rank=item["dense_rank"],
                    dense_cosine=item["dense_cosine"],
                    fusion_score=item["fusion_score"],
                    rerank_score=item["rerank_score"],
                    retrieval_version=item["retrieval_version"],
                    exact_verified=True,
                    agent_relevance_comment=agent_note(case["case_id"], evidence.text),
                )
            )
        old_ids = [h.get("chunk_id") for h in case["hits"]]
        current_ids = [h.chunk_id for h in dense]
        result = dict(
            case_id=case["case_id"],
            query=case["query"],
            source_scope_sha=selection.selection_id,
            sources=case["sources"],
            source_scope_exact_match=True,
            before=old_rows,
            current_dense_recheck=dense_recheck,
            dense_recheck_same_chunk_order=old_ids == current_ids,
            dense_recheck_max_cosine_difference=(
                max(abs(h.score - b["score"]) for h, b in zip(dense, case["hits"]))
                if len(dense) == len(case["hits"])
                else None
            ),
            after=rows,
            duration_seconds=round(time.monotonic() - start, 3),
            human_relevance_labels="not_reviewed",
            precision_at_5=None,
            mrr_at_5=None,
            answer_completeness="not_evaluated_no_model_no_human",
        )
        results.append(result)
        write_json(
            output / "six-query-progress.json", {"completed": len(results), "results": results}
        )
    return results


def historical_probe(app, client, before):
    from app.cplus.runtime import fast_ref
    from app.retrieval_v2.models import EvidenceRef

    historical_path = PROJECT / "docs/cplus/evidence/M0-historical-risk-failure.json"
    historic = read_json(historical_path)["examples"][0]
    selection = run(
        app.state.selection_preparer.prepare_many(
            document_ids=[s["document_id"] for s in before["results"][0]["sources"]],
            query=historic["original_question"],
        )
    )
    refs = [fast_ref(d).model_dump() for d in selection.documents]
    result = post(
        client,
        "/cplus/retrieval/searches",
        {"sources": refs, "query": historic["original_question"], "top_k": 5},
    )
    for item in result["items"]:
        run(
            app.state.cplus_retrieval_service.verify(
                EvidenceRef.model_validate(item["evidence_ref"])
            )
        )
    old = historic["evidence_ref"]
    return dict(
        original_artifact=str(historical_path.relative_to(PROJECT)),
        artifact_sha256=digest(historical_path),
        original_job_id=historic["job_id"],
        exact_query=historic["original_question"],
        original_failure_physical_page=70,
        original_failure_text=old["text"],
        current_search=result,
        exact_historical_text_reproduced=any(old["text"] in c["text"] for c in result["items"]),
        entrusted_finance_phrase_in_current_top5=any(
            "委托理财" in c["text"] for c in result["items"]
        ),
        exact_quote_verified=True,
        provider_calls=0,
        original_real_model_job_rerun=False,
    )


def tool_probes(app, client, cases, inventory):
    from app.cplus.runtime import fast_ref
    from app.retrieval_v2.models import EvidenceRef

    docs = {d["public_provenance"]["id"]: d for d in inventory["documents"]}
    sources, results = {}, {}
    for name, document in docs.items():
        if document.get("legacy_status") != "ready":
            continue
        selection = run(
            app.state.selection_preparer.prepare_many(
                document_ids=[document["document_id"]], query="固定公开来源核验"
            )
        )
        sources[name] = fast_ref(selection.documents[0]).model_dump()
    for case in cases["cases"]:
        names = {
            "E01-01": ["gree-2025"],
            "E01-06": ["gree-2025"],
            "E01-07": ["gree-2024", "gree-2025"],
            "E01-02": ["midea-2024", "midea-2025"],
        }.get(case["id"])
        if not names:
            continue
        if not all(name in sources for name in names):
            results[case["id"]] = {
                "execution": "NOT_RUN_MISSING_SEED_SOURCE",
                "missing_sources": [n for n in names if n not in sources],
            }
            continue
        print("FIXED_TOOL_PROBE", case["id"], flush=True)
        refs = [sources[n] for n in names]
        post(client, "/cplus/retrieval/builds", {"sources": refs})
        context = post(
            client,
            "/cplus/research/contexts",
            {"title": "fixed-case tool excerpt probe", "selected_sources": refs},
        )
        answer = post(
            client,
            "/cplus/research/answers",
            dict(
                context_id=context["context_id"],
                context_revision=context["revision"],
                context_sha256=context["context_sha256"],
                question=case["question"],
            ),
        )
        assert answer["financial_authority"] is False and answer["interpretation"] is None
        for finding in answer["findings"]:
            run(
                app.state.cplus_retrieval_service.verify(
                    EvidenceRef.model_validate(finding["evidence_ref"])
                )
            )
        results[case["id"]] = dict(
            execution="REAL_ROOT_HTTP_TOOL_COMPONENT_ONLY",
            exact_question=case["question"],
            requested_mode_not_executed=case["mode"],
            answer=answer,
            model_called=False,
            full_case_status="NOT_VERIFIED_MODEL_DISABLED",
            human_review="pending",
        )
    collections = []
    for name in ("gree-2024", "gree-2025"):
        ref = sources[name]
        collections.append(
            post(
                client,
                "/cplus/financial/collections",
                {
                    "document_id": ref["document_id"],
                    "expected_source_revision": ref["source_revision"],
                },
            )
        )
    results["CP-18"] = dict(
        execution="REAL_ROOT_HTTP_PDF_CANDIDATES",
        collections=collections,
        full_case_status="PARTIAL_CANDIDATES_ONLY_HUMAN_PENDING",
        human_review="pending",
    )
    selections = []
    for collection in collections:
        year = collection["source"]["report_year"]
        picked = [
            cell["cell_id"]
            for cell in collection["cells"]
            if cell["extraction_status"] == "candidate"
            and (
                cell["time"].get("as_of_date") == f"{year}-12-31"
                or (
                    cell["time"].get("period_start") == f"{year}-01-01"
                    and cell["time"].get("period_end") == f"{year}-12-31"
                )
            )
        ]
        selections.append({"collection_id": collection["id"], "cell_ids": picked})
    checkup = post(
        client,
        "/cplus/checkups",
        {"collection_refs": selections, "candidate_view": True, "generate_explanation": False},
    )
    results["CP-20"] = dict(
        execution="REAL_ROOT_HTTP_PDF_CANDIDATE_RULES",
        checkup=checkup,
        full_case_status="PARTIAL_CANDIDATE_AXIS_ONLY",
        confirmed_axis="human_pending",
    )
    annual = post(
        client,
        "/cplus/annual-diffs",
        {
            "left_source": sources["gree-2024"],
            "right_source": sources["gree-2025"],
            "topics": ["经营风险", "主要业务", "研发"],
            "generate_explanation": False,
        },
    )
    results["CP-19"] = dict(
        execution="REAL_ROOT_HTTP_PDF_BILATERAL_EXCERPTS_ONLY",
        annual_diff=annual,
        full_case_status="NOT_VERIFIED_REAL_LLM_REQUIRED",
        human_review="pending",
    )
    return results


def write_query_comparison(output, report):
    def clean(value):
        return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")

    lines = [
        "# Six exact queries: before and after",
        "",
        "Before = immutable M0 stored dense hits; current dense recheck is recorded separately. After = actual current root hybrid HTTP.",
        "All page numbers are physical PDF pages. Snippets below are truncated; full original text and source identities are in retrieval-evaluation.json.",
        "Cosine, rank-only RRF, and heuristic rerank scores are separate quantities; no human relevance accuracy is claimed.",
        "",
    ]
    for row in report.get("results", []):
        lines += [
            f"## {row['case_id']}",
            "",
            f"Exact query: {row['query']}",
            "",
            f"Exact source scope: `{row['source_scope_sha']}`. Dense recheck same chunk order: {row['dense_recheck_same_chunk_order']}; max cosine difference: {row['dense_recheck_max_cosine_difference']}.",
            "",
            "| Side/rank | Physical page | Cosine | Lexical/dense rank | RRF | Heuristic rerank | Current exact gate | Snippet |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for side in ("before", "after"):
            for hit in row[side]:
                score = hit.get("dense_cosine")
                lines.append(
                    f"| {side}/{hit['rank']} | {hit['physical_page']} | {score} | {hit.get('lexical_rank')}/{hit.get('dense_rank')} | {hit.get('fusion_score')} | {hit.get('rerank_score')} | {hit['exact_verified']} {hit.get('verification_error') or ''} | {clean(hit['snippet'][:250])}… |"
                )
        lines += [
            "",
            "Agent comments (not human ground truth): "
            + " / ".join(
                f"p{h['physical_page']}: {h['agent_relevance_comment']}" for h in row["after"]
            ),
            "",
        ]
    historical = report.get("historical_exact_query_probe", {})
    lines += [
        "## Historical page 70 wrong-class evidence",
        "",
        f"Exact original query: {historical.get('exact_query')}",
        "",
        f"Original failure is retained separately. Current top5 pages: {[c['evidence_ref']['physical_page'] for c in historical.get('current_search', {}).get('items', [])]}.",
        f"Exact historical full text reproduced: {historical.get('exact_historical_text_reproduced')}; entrusted-finance phrase in current top5: {historical.get('entrusted_finance_phrase_in_current_top5')}.",
        "Original real model job was not rerun. A query-only no-provider diagnostic is not a rerun of its answer pipeline.",
        "",
    ]
    (output / "six-query-before-after.md").write_text("\n".join(lines) + "\n")


def summarize_existing(output):
    """Write all 24 exact frozen questions with evidence tier and explicit gaps."""
    report_path = output / "retrieval-evaluation.json"
    report = read_json(report_path)
    fixed_path = PROJECT / "docs/cplus/eval/fixed-cases.json"
    fixed = read_json(fixed_path)
    probes = report.get("fixed_case_tool_probes", {})
    write_query_comparison(output, report)
    gap = {
        "E01-01": "Exact-question excerpt tool probe only; no real model answer or human completeness review.",
        "E01-02": "Midea two-year plan and synthesis require real model; original v1 lacks Midea 2024.",
        "E01-03": "Multi-turn pronoun resolution requires its preceding user turn and structured focus; not simulated by standalone retrieval.",
        "E01-04": "Ambiguous comparison clarification and no-investment-judgment behavior require a real model conversation.",
        "E01-05": "Deep multi-company annual-ratio task needs frozen selected inputs, routing evidence and model explanation; confirmed input axis is human_pending.",
        "E01-06": "Exact-question excerpt tool probe only; requested deep roles and model interpretation were not executed.",
        "E01-07": "Exact-question excerpt tool probe only; no synthesis agent/plan was executed and no human approval was granted.",
        "E01-08": "Isolated injection model fixture was not run; no secrets were read or fabricated as test material.",
        "E01-09": "Original v1 lacks selected Midea 2024; no real-model refusal/scope-limitation answer was executed.",
        "E01-10": "Controlled stale-source/history fence tested independently in M3, not this exact conversational case or race schedule.",
        "E01-11": "Real BGE two-session note recall and model answer not executed by this retrieval suite.",
        "E01-12": "Real BGE two-session deletion/late-embedding race and model answer not executed by this suite.",
        "E01-13": "No fault-provider run or retry was authorized here; existing UNKNOWN is preserved rather than replayed.",
        "E01-14": "Trusted completed-job report contract exists separately; exact client tampering scenario was not executed here.",
        "E01-15": "No pair of independent approved synthesis/deep plans or successful real-model results was executed; no agent superiority claim.",
        "CP-16": "Exact M0 six-query before/after and exact historical question executed; human semantic labels pending, precision/MRR remain null.",
        "CP-17": "This suite does not rerun native Vision/OCR or assert real OCR+BGE from an API response alone.",
        "CP-18": "Real PDF candidate collections executed; per-cell human review and positive financial confirmation are pending.",
        "CP-19": "Bilateral risk/business/R&D excerpts executed with generation disabled; real-model explanation and human semantics unverified.",
        "CP-20": "Three candidate rules executed using program inputs; confirmed and missing-input axes are not all validated here, no causal explanation accepted.",
        "CP-21": "Real-model 2x2 partial-failure/cancel/recovery batch was not run; older serial tool/fake tests do not satisfy this case.",
        "CP-22": "Existing official-import/cache evidence is separate; this evaluation never downloads or imports a new company.",
        "CP-23": "Actual multiformat same-revision file opening/render is outside this retrieval suite; no export endpoint status is counted as full pass.",
        "CP-24": "M3 actual-React mocked point/favorite checks and real SQLite quote verification are separate tiers; full real-browser deletion/highlight flow not run here.",
    }
    capabilities = {
        "E01-01": ["exact_source_selection", "real_BGE_Milvus", "exact_excerpt_verification"],
        "E01-02": [
            "two_year_fixed_sources_if_READY",
            "candidate_cash_flow_cells",
            "bilateral_excerpts",
        ],
        "E01-03": ["conversation_selection_contract", "server_resolved_financial_focus"],
        "E01-04": ["explicit_company_and_metric_contract"],
        "E01-05": [
            "real_candidate_statement_cells",
            "explicit_peer_comparability",
            "candidate_checkup",
        ],
        "E01-06": ["real_BGE_Milvus", "exact_risk_excerpt_verification"],
        "E01-07": ["candidate_authority_labels", "no_financial_confirmation"],
        "E01-08": ["allowlist_and_owner_contract_tests_only"],
        "E01-09": ["frozen_source_scope_validation"],
        "E01-10": ["active_revision_rejection", "historical_read_projection", "publication_fences"],
        "E01-11": ["real_BGE_memory_service_available_not_executed"],
        "E01-12": ["memory_tombstone_service_available_not_executed"],
        "E01-13": ["bounded_provider_unknown_contract_available_not_called"],
        "E01-14": ["trusted_report_snapshot_contract_available_not_executed"],
        "E01-15": ["stored_result_comparison_only_when_both_results_exist"],
        "CP-16": [
            "six_exact_queries",
            "source_scope_hash",
            "score_type_separation",
            "historical_exact_query",
        ],
        "CP-17": ["stored_artifact_SHA_bbox_routes_available_not_executed"],
        "CP-18": ["real_PDF_statement_candidates", "explicit_time_unit_scope"],
        "CP-19": ["dual_year_exact_excerpts", "missing_in_retrieval_preserved"],
        "CP-20": ["real_HTTP_candidate_rule_observations"],
        "CP-21": ["serial_tool_batch_operations_available_not_executed"],
        "CP-22": ["previous_official_import_evidence_only"],
        "CP-23": ["previous_export_artifact_evidence_only"],
        "CP-24": ["previous_mock_React_plus_SQLite_evidence_only"],
    }
    refs = {
        "E01-10": ["docs/cplus/reviews/M3-fixes-verification.md"],
        "E01-13": ["docs/cplus/evidence/M3-http/diagnostic.json"],
        "CP-16": [
            "docs/cplus/evidence/M0-retrieval-before.json",
            "docs/cplus/evidence/M0-historical-risk-failure.json",
        ],
        "CP-17": ["docs/cplus/EVIDENCE.md"],
        "CP-18": ["docs/cplus/reviews/M2-finance-public-candidates.json"],
        "CP-19": ["docs/cplus/evidence/M3-http/corrected-no-provider.json"],
        "CP-20": ["docs/cplus/evidence/M3-http/corrected-no-provider.json"],
        "CP-21": ["docs/cplus/reviews/M3-batch-handoff.md"],
        "CP-22": ["docs/cplus/evidence/M1-official-import.json"],
        "CP-23": ["docs/cplus/reviews/M4-export-handoff.md"],
        "CP-24": ["docs/cplus/reviews/M3-fixes-verification.md"],
    }
    entries = []
    for case in fixed["cases"]:
        case_id = case["id"]
        probe = probes.get(case_id)
        execution = probe.get("execution") if probe else "NOT_RUN_BY_THIS_SUITE"
        if case_id == "CP-16":
            execution = "REAL_ROOT_HTTP_BGE_MILVUS_SIX_EXACT_QUERIES_AND_HISTORICAL_QUERY"
        entries.append(
            dict(
                id=case_id,
                exact_question=case["question"],
                required_tier=case["evidence_tier_required"],
                source_fixture=case.get("source_fixture"),
                this_run_execution=execution,
                this_run_evidence=(
                    "retrieval-evaluation.json#results,historical_exact_query_probe"
                    if case_id == "CP-16"
                    else f"retrieval-evaluation.json#fixed_case_tool_probes.{case_id}"
                    if probe
                    else None
                ),
                full_answer_acceptance="NOT_CLAIMED",
                human_semantic_review="pending",
                human_financial_acceptance="pending",
                tool_components_available_or_observed=capabilities[case_id],
                remaining_gap=gap[case_id],
                existing_checkout_evidence=[
                    dict(
                        path=ref,
                        sha256=digest(PROJECT / ref),
                        provenance="previous_checkout_artifact_read_only_not_new_execution",
                    )
                    for ref in refs.get(case_id, [])
                    if (PROJECT / ref).is_file()
                ],
            )
        )
    assert len(entries) == fixed["case_count"] == 24
    value = dict(
        schema_version="cplus-fixed24-execution-tiers-v1",
        fixed_cases_sha256=digest(fixed_path),
        retrieval_receipt_sha256=digest(report_path),
        entries=entries,
        provider_calls=0,
        human_approvals=0,
        full_answer_pass_count=0,
        full_answer_pass_count_meaning="No full model/human acceptance is claimed; not an accuracy metric",
        model_gap="Provider disabled here. Root's retained bounded diagnostic has ReadTimeout/UNKNOWN; no retry or ledger access in this suite.",
        existing_evidence_policy="Previous artifacts are separately identified, never counted as this worker's actual executions.",
    )
    write_json(output / "fixed24-execution-tiers.json", value)
    lines = [
        "# Fixed 24 cases: actual execution tiers",
        "",
        "No full answer PASS or accuracy is claimed. Provider is disabled; human semantic/financial acceptance is pending.",
        "",
        "| Case | Required tier | This run | Remaining gap |",
        "| --- | --- | --- | --- |",
    ]
    lines += [
        f"| {e['id']} | {e['required_tier']} | {e['this_run_execution']} | {e['remaining_gap']} |"
        for e in entries
    ]
    (output / "fixed24-execution-tiers.md").write_text("\n".join(lines) + "\n")
    print("FIXED24_INVENTORY", str(output / "fixed24-execution-tiers.json"), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--summarize-existing",
        action="store_true",
        help="Only inventory an existing receipt; do not rerun tools",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    assert args.output.resolve().is_relative_to(PROJECT / "docs/cplus/eval/results")
    if args.summarize_existing:
        summarize_existing(args.output)
        return
    if any(args.output.iterdir()):
        raise FileExistsError("Use a fresh empty output directory; preserve existing run receipts")
    offline_environment()
    from app.demo.seed import materialize, verify_seed
    from app.api.runtime_factory import create_runtime_app, _runtime_bge_version
    from fastapi.testclient import TestClient

    before_file = PROJECT / "docs/cplus/evidence/M0-retrieval-before.json"
    before = read_json(before_file)
    fixed_file = PROJECT / "docs/cplus/eval/fixed-cases.json"
    manifest, seed_sha = verify_seed(args.seed.resolve())
    inventory = read_json(args.seed / "seed-inventory.json")
    report = dict(
        schema_version="cplus-m5-retrieval-evaluation-v1",
        business_baseline=BUSINESS_BASELINE,
        checkout_head=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True
        ).strip(),
        generated_at=datetime.now(UTC).isoformat(),
        tier="REAL_CPLUS_ROOT_HTTP_PUBLIC_PDF_BGE_MILVUS",
        private_identity_transport="test-only marker for disposable runtime, no real gateway/login",
        provider_calls=0,
        human_financial_approvals=0,
        baseline_artifact_sha256=digest(before_file),
        seed_manifest_sha256=seed_sha,
        original_m0_seed_manifest_sha256=before["seed_manifest_sha256"],
        fixed_cases_sha256=digest(fixed_file),
        source_scope_policy="exact M0 source snapshots and scope hash or fail",
        public_seed_path=str(args.seed.resolve()),
        top_k=5,
        internal_candidate_limit=20,
        score_types={
            "dense_cosine": "Milvus COSINE, may be null for lexical-only",
            "fusion_score": "rank-only reciprocal rank fusion sum(1/(60+rank)), NOT cosine",
            "rerank_score": "RRF plus bounded lexical topic/table heuristic, NOT cosine",
        },
        precision_at_5=None,
        mrr_at_5=None,
        human_relevance_labels="not_reviewed",
        implementation_sha256={
            str(p.relative_to(PROJECT)): digest(p)
            for p in (
                PROJECT / "app/retrieval_v2/service.py",
                PROJECT / "app/cplus/runtime.py",
                PROJECT / "app/rag/selected_scope.py",
                PROJECT / "app/rag/embed.py",
            )
        },
        script_sha256=digest(Path(__file__)),
    )
    target = args.output / "retrieval-evaluation.json"
    write_json(target, {**report, "execution": "STARTED"})
    with tempfile.TemporaryDirectory(prefix="findoc-cplus-m5-eval-") as directory:
        runtime = Path(directory) / "runtime"
        materialize(args.seed.resolve(), runtime, seed_sha)
        report["owned_runtime"] = str(runtime)
        print("START_REAL_ROOT_OFFLINE_BGE", flush=True)
        app = create_runtime_app(
            runtime, showcase_generation=1, showcase_seed_version="m5-evaluation-public-copy"
        )

        @app.middleware("http")
        async def test_only_marker(request, call_next):
            request.scope["findoc_private_identity"] = (
                request.headers.get("X-Findoc-Generation"),
                request.headers.get("X-Findoc-Instance"),
            )
            return await call_next(request)

        headers = {
            "X-Findoc-Generation": "1",
            "X-Findoc-Instance": "public-retrieval-evaluation",
            "X-Findoc-Lease-Expires-At": (datetime.now(UTC) + timedelta(minutes=45)).isoformat(),
        }
        try:
            with TestClient(app, headers=headers) as client:
                report["bge_version"] = _runtime_bge_version()
                report["seed_vector_indexes"] = manifest.get("vector_indexes", [])
                report["m0_model_revision_comparability"] = (
                    "M0 did not record BGE weight revision; exact weight identity cannot be proven retrospectively"
                )
                report["results"] = evaluate_six(app, client, before, args.output)
                report["historical_exact_query_probe"] = historical_probe(app, client, before)
                report["fixed_case_tool_probes"] = tool_probes(
                    app, client, read_json(fixed_file), inventory
                )
                report["execution"] = "COMPLETED_TOOL_EVIDENCE_ONLY"
        except Exception as exc:
            report["execution"] = "FAILED_RETAINED"
            report["error"] = {"type": type(exc).__name__, "message": str(exc)[:1000]}
            write_json(target, report)
            raise
        finally:
            verify_seed(args.seed.resolve(), seed_sha)
            report["seed_unchanged"] = True
            write_json(target, report)
    report["owned_runtime_removed"] = not runtime.exists()
    write_json(target, report)
    summarize_existing(args.output)
    print("COMPLETED", str(target), flush=True)


if __name__ == "__main__":
    main()
