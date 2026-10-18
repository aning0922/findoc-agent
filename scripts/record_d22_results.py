"""Compact final D22 evidence without replacing predecessor records or failure attempts."""

import hashlib
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent.parent
validation = root / "product/validation"
commands = [
    json.loads(p.read_text())
    for p in sorted((root / "data/30d-foundation/d22-commands").glob("*.json"))
]
latest = {c["name"]: c for c in commands}
required = [
    "python-full",
    "targeted-final",
    "frontend-final",
    "build-final",
    "lint-final",
    "ruff-final",
    "mypy-final",
    "real-final",
    "browser-final",
    "qa-regression-final",
    "qa-history-regression",
    "operating-regression",
    "capture-final",
]
assert all(latest[name]["exit_code"] == 0 for name in required)
legacy = json.loads(
    (root / "data/30d-foundation/d22-browser/d22-product-browser-record.json").read_text()
)
latest_suites = {p["suite"]: p for p in legacy}
assert all(v["exit_code"] == 0 for v in latest_suites.values())
critical = [
    "app/research/operating_result.py",
    "app/research/task_repository.py",
    "app/research/task_contracts.py",
    "app/research/templates.py",
    "app/agent/financial_analysis.py",
    "app/agent/sqlite_financial_facts.py",
    "app/agent/operating_research_graph.py",
    "app/documents/source_service.py",
    "app/companies/migrations.py",
    "product/validation/d21-real-research.json",
    "product/validation/d21-test-record.json",
]
checks = []
for name in critical:
    before = subprocess.check_output(["git", "show", "2f382ca:" + name], cwd=root)
    after = (root / name).read_bytes()
    assert before == after
    checks.append(dict(path=name, sha256=hashlib.sha256(after).hexdigest(), unchanged=True))
isolation = []
for file in ["d22-test-isolation.json", "d22-targeted-isolation.json"]:
    value = json.loads((root / "data/30d-foundation" / file).read_text())
    isolation.append(
        {
            k: value[k]
            for k in (
                "test_root",
                "exit_code",
                "sqlite_path_count",
                "all_sqlite_paths_under_test_root",
                "source_write_guard",
                "original_product_write_guard",
                "default_runtime_write_guard",
            )
        }
    )
proof = json.loads((validation / "d22-real-reports.json").read_text())
record = dict(
    requested_baseline="4be0e1f2c79feaf5227a58e052f206bfafc370e8",
    actual_start="2f382ca7ce61578a11d4d3f0bb7539d10ffdac4b",
    repository="aning0922/findoc-analyst-v1",
    branch="feat/30d-foundation",
    scope="D22 only; no report storage/migration/history/title editing or Markdown export",
    final_commit="See final Git delivery; a commit cannot embed its own SHA",
    all_required_checks_passed=True,
    commands=commands,
    latest_required_commands=required,
    python_full=dict(
        passed=1346,
        skipped=1,
        skip="Existing day43 local evidence unavailable; all four annual originals were exercised",
        seconds=940.09,
        collection_note="Full collection included the initial 24 D22 cases. Final contract/admission changes and three added cases are covered by the separate final 27-case run; counts are not combined.",
    ),
    d22_final_targeted=27,
    frontend=dict(
        passed=100,
        failed=0,
        node="24.19.0",
        lint="exit 0; only predecessor D14 Fast Refresh warning",
    ),
    browser=dict(
        unique_passed=82,
        d22_report_previews_and_boundaries=14,
        financial_review_and_facts=18,
        legacy_agent=2,
        comparison=8,
        charts=11,
        product_navigation=9,
        d16_behaviors_through_current_d17_contract=4,
        d17_history=5,
        d20_wait_resume_and_invalid=11,
        viewport_widths=[1024, 1280, 1440],
        legacy_suite_records=legacy,
        legacy_latest_suites=list(latest_suites),
        report_record="d22-browser-record.json",
        post_preview_fault="Last report browser case deliberately revokes a receipt only in the disposable D22 copy; all 12 previews were qualified when generated, then the UI withdrew the current draft. QA JSON files are audit captures, not permanently qualified saved reports.",
    ),
    mypy_source_files=105,
    isolation=isolation,
    preserved_d21_core=checks,
    four_report_proof="d22-real-reports.json",
    strict_schema="report-draft-v1.schema.json",
    complete_validation_payloads=[c["preview_file"] for c in proof["cases"]],
    screenshots=[
        str(p.relative_to(root)) for p in sorted((validation / "d22-screenshots").glob("*.png"))
    ],
    generation_execution_calls=proof["execution_calls"],
    generation_database_unchanged=proof["database_unchanged"],
    financial_slots_checked=24,
    analysis_results_checked=12,
    simulated_test=True,
    human_acceptances=0,
    human_review="pending",
    ac30_19="pending",
    protection="d22-protection-results.json",
    limitations=[
        "All four financial acceptances remain simulated_test, not human acceptance.",
        "Citation identity proves exact source support, not semantic causality.",
        "SQLite and external PDF bytes have no distributed transaction; PDF open and UI recheck remain necessary.",
        "No protection against an administrator rewriting both stored payloads and their digests.",
    ],
    early_failures_and_repairs=[
        dict(
            issue="Initial PDF verification required whole-block equality for every paragraph",
            repair="Respect D16 frozen chunk text and same-page membership, while preserving complete table page context",
        ),
        dict(
            issue="Host default Node 20 could not execute TypeScript unit tests",
            repair="Use installed project-compatible Node 24.19.0",
        ),
        dict(
            issue="tempfile cached the host temp directory before the audited runner set TMPDIR",
            repair="Reset tempfile.tempdir to the audited D22 root; no SQLite escape permitted",
        ),
        dict(
            issue="Receipt race test omitted the required confirmation_kind argument",
            repair="Use the real simulated_test revocation API and assert actual current publication eligibility invalidated",
        ),
        dict(
            issue="Stability test used nonexistent CompanyUpdate",
            repair="Use CompanyPatch; pure builder stays frozen and current D6 rejects conflicting directory identity",
        ),
        dict(
            issue="TypedDict inline config triggered mypy",
            repair="Use Pydantic with_config; preserve strict fixed-key appendix",
        ),
        dict(
            issue="Legacy navigation expected report placeholder",
            repair="Update only the now-replaced report navigation/heading/explicit generation assertions; remaining tests preserved",
        ),
        dict(
            issue="Archived D16 browser cases intercepted obsolete /research/questions",
            repair="Retain old file; adapt equivalent controlled cases to D17 /research/runs and persisted response/unknown-status contracts; all four pass",
        ),
    ],
)
(validation / "d22-test-record.json").write_text(
    json.dumps(record, ensure_ascii=False, indent=2) + "\n"
)
print(
    "D22 final evidence: all required checks passed; 82 unique browser cases; 27 final report cases."
)
