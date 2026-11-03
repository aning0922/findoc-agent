"""Read stored browser-result/research-progress JSON; never calls a service.

Usage: python eval/summarize_showcase_run.py RESULT.json --cost-summary COST.json
"""

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path


def summarize(value, cost=None):
    rows = []
    for entry in value.get("jobs", []):
        job = entry.get("job", {})
        findings = (job.get("result") or {}).get("findings", [])
        usage, scope = job.get("usage", {}), job.get("scope", {})
        refs = [r for f in findings for r in f.get("evidence_refs", [])]
        pages = sorted(
            {
                (r.get("document_id", ""), r.get("source_revision", ""), r.get("physical_page"))
                for r in refs
                if isinstance(r.get("physical_page"), int)
            }
        )
        source_ids = sorted(
            {(r.get("document_id", ""), r.get("source_revision", "")) for r in refs}
        )
        try:
            duration = round(
                (
                    datetime.fromisoformat(job["ended_at"])
                    - datetime.fromisoformat(job["created_at"])
                ).total_seconds()
                * 1000
            )
        except (KeyError, ValueError, TypeError):
            duration = None
        rows.append(
            dict(
                mode=entry.get("mode", job.get("mode")),
                question=entry.get("intent", {}).get("goal"),
                job_id=job.get("job_id"),
                state=job.get("state", "unknown"),
                failure_code=job.get("error_code"),
                data_origin=(job.get("result") or {}).get("data_origin"),
                provider_attempts=usage.get("attempts"),
                tool_calls=usage.get("tools"),
                unknown_attempts=usage.get("unknown_attempts"),
                job_duration_ms=duration,
                observed_elapsed_ms=entry.get("elapsed_ms"),
                findings_count=len(findings),
                finding_kinds=dict(Counter(f.get("kind", "unknown") for f in findings)),
                source_pages=[
                    dict(document_id=d, source_revision=r, physical_page=p) for d, r, p in pages
                ],
                cited_source_count=len(source_ids),
                frozen_source_denominator=None,
                source_scope_sha=scope.get("source_scope_sha"),
                fact_selection_sha=scope.get("fact_selection_sha"),
                memory_generation=scope.get("memory_generation"),
                cost_cny=None,
                cost_status="per_job_billing_not_observed",
            )
        )
    groups = {}
    for row in rows:
        # Different questions, source scopes, fact selections or memory generations are not a paired comparison.
        key = (
            row["question"],
            row["source_scope_sha"],
            row["fact_selection_sha"],
            row["memory_generation"],
        )
        groups.setdefault(key, []).append(row["job_id"])
    outcomes = Counter(r["state"] for r in rows)
    return dict(
        schema_version="showcase-stored-summary-v1",
        evidence_label=value.get("evidence", "unknown"),
        provenance_notice="Input evidence label is preserved, not independently verified by this reader.",
        stored_jobs_denominator=len(rows),
        fixed_case_denominator=15,
        fixed_case_pass_count=None,
        state_counts=dict(outcomes),
        rows=rows,
        comparison_groups=list(groups.values()),
        cost_summary=cost,
        cost_notice="Global proxy reservation is not per-job cost or observed billed CNY; do not allocate it across jobs.",
        fixed_eval=value.get("denominators"),
        limitations=[
            "No semantic quality judgment or single/multi advantage inferred.",
            "Distinct cited sources are not verified coverage; frozen source denominator is absent.",
            "Stored jobs are not results for the 15 fixed cases unless explicitly mapped.",
        ],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--cost-summary", type=Path)
    args = parser.parse_args()
    value = json.loads(args.result.read_text())
    cost = json.loads(args.cost_summary.read_text()) if args.cost_summary else None
    print(json.dumps(summarize(value, cost), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
