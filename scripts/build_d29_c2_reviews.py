"""Compile only the pinned D28 external decisions into a read-only UI sidecar.

No runtime roots, SQLite, acceptance import or native review writes. --check
reproduces the shipped artifact and refuses changed original evidence bytes.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = "43d7badfb6a6eb270c7d233cb9a64926e90f9bd6"
VERSION = "d28-external-review-reading-v1"
OUT = ROOT / "frontend/src/product/d28ExternalReviews.ts"
FIELDS = [
    "schema_version",
    "execution_config_version",
    "execution_config",
    "run_id",
    "operation_id",
    "workspace_id",
    "query",
    "document_ids",
    "selection_id",
    "documents",
    "created_at",
    "ended_at",
    "status",
    "result",
]


def sha(raw):
    return hashlib.sha256(raw if isinstance(raw, bytes) else raw.encode()).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def original(path):
    raw = (ROOT / path).read_bytes()
    pinned = subprocess.check_output(["git", "show", f"{BASE}:{path}"], cwd=ROOT)
    assert raw == pinned, f"original evidence changed: {path}"
    return raw


def reference(path):
    return dict(path=path, sha256=sha(original(path)), commit=BASE)


def load(path):
    return json.loads(original(path))


def operating_target(task):
    content = task["final_research_content"]
    return dict(
        workspace_id=task["workspace_id"],
        task_id=task["task_id"],
        task_revision=task["revision"],
        sources=task["snapshot"]["documents"],
        descriptions=content["operating_descriptions"],
        model_interpretations=content["model_interpretations"],
        test_mode=content["test_mode"],
    )


def build():
    csv_path = "product/d28/human/semantic-18.csv"
    rows = list(csv.DictReader(original(csv_path).decode().splitlines()))
    records = []
    for row in rows:
        case = row["question_id"]
        run_path = f"product/d28/evidence/qa-real/{case}.json"
        review_path = f"product/d28/evidence/human-followup/{case}-owner-semantic-pass.json"
        run = load(run_path)["response"]
        review = load(review_path)
        envelope = {k: run[k] for k in FIELDS}
        assert sha(canonical(envelope)) == run["integrity_sha256"]
        assert review["actual_get"]["payload"] == run
        assert row["human_result"] == review["human_result"] == "pass"
        assert row["actual_run_id"] == review["actual_run_id"] == run["run_id"]
        assert row["actual_operation_id"] == review["actual_operation_id"] == run["operation_id"]
        assert row["question"] == review["question"] == run["query"]
        assert row["answer_sha256"] == review["answer_sha256"] == sha(run["result"]["content"])
        assert run["result"]["human_review"] == ("pending" if run["status"] == "answered" else None)
        records.append(
            dict(
                kind="qa",
                record_id=f"D28-{case}",
                question_id=case,
                run_id=run["run_id"],
                operation_id=run["operation_id"],
                workspace_id=run["workspace_id"],
                query_sha256=sha(run["query"]),
                answer_sha256=sha(run["result"]["content"]),
                target_sha256=run["integrity_sha256"],
                sources=run["documents"],
                decision="pass",
                reviewer_name=review["human_name"] or None,
                original_words=review["user_exact_words"],
                opinion=review["human_opinion"],
                recorded_at=review["recorded_at"],
                scope=f"仅 {case} 的历史问题与回答"
                if case.startswith("A")
                else f"仅 {case} 的历史拒答及所示提示；不代表所请求能力已实现",
                evidence=[reference(csv_path), reference(review_path), reference(run_path)],
            )
        )
    review_path = "product/d28/evidence/human-followup/operating-semantic-review.json"
    task_path = "product/d28/evidence/human-followup/midea-user-resume-completed.json"
    review = load(review_path)
    task = load(task_path)["task"]
    target = operating_target(task)
    assert review["task_id"] == task["task_id"] and review["task_revision"] == task["revision"]
    assert task["final_research_content"]["verified_operating_attribution"] is False
    for item in review["interpretations"]:
        index = item["number"] - 1
        model = target["model_interpretations"][index]
        (event,) = item["human_review_events"]
        assert item["text"] == event["original_text"] == model["text"]
        assert item["citations"] == event["citations"] == model["citations"]
        assert event["original_text_sha256"] == sha(model["text"])
        records.append(
            dict(
                kind="operating",
                record_id=f"D28-midea-{index + 1}",
                workspace_id=task["workspace_id"],
                task_id=task["task_id"],
                task_revision=task["revision"],
                statement_index=index,
                statement_sha256=sha(model["text"]),
                citations=model["citations"],
                target_sha256=sha(canonical(target)),
                sources=target["sources"],
                decision=item["human_review_status"],
                original_words=event["user_exact_words"],
                opinion=event["approval_scope"],
                scope=f"仅美的 Task revision 4 第 {index + 1} 条；不核准经营因果或用户新增断言",
                recorded_at=event["recorded_at"],
                reviewer_name=None,
                rewrite=item.get("approved_rewrite"),
                evidence=[
                    reference(review_path),
                    reference(task_path),
                    reference("product/d28/APPROVED-OPERATING-NOTES.md"),
                ],
            )
        )
    assert len(records) == 22 and len({r["record_id"] for r in records}) == 22
    return dict(schema_version=VERSION, source_commit=BASE, records=records)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    value = build()
    output = (
        "// Generated by scripts/build_d29_c2_reviews.py from pinned external evidence.\n"
        "// Read-only; this is not a native approval or report body.\n"
        + "export const externalReviewManifest = "
        + json.dumps(value, ensure_ascii=False, indent=2)
        + ";\n"
        + f"export const externalReviewManifestSha256 = '{sha(canonical(value))}';\n"
    )
    if args.check:
        assert OUT.read_text() == output, "sidecar differs from pinned external evidence"
    else:
        OUT.write_text(output)
    print(f"{len(value['records'])} exact external records; sha256={sha(canonical(value))}")


if __name__ == "__main__":
    main()
