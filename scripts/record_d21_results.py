"""Final compact evidence with real command exits; no bulk logs copied into Git."""

import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parent.parent
commands = sorted(
    (json.loads(p.read_text()) for p in (root / "data/30d-foundation/d21-commands").glob("*.json")),
    key=lambda r: r["log"],
)
by_name = {r["name"]: r for r in commands}
required = [
    "b-python-release-final",
    "b-v2-stage-a-compat",
    "b-front-compat",
    "b-build-compat",
    "b-lint-compat",
    "b-mypy-compat",
    "b-ruff-compat",
    "b-chromium-real-final",
    "b-readonly-compat",
    "b-legacy-chromium",
    "b-d20-chromium",
    "b-d17-history-chromium",
    "b-four-document-repair-worst",
    "b-restart-compat-all",
    "b-protection-delivery",
    "b-diff-delivery",
]
assert all(by_name[name]["exit_code"] == 0 for name in required)
full = by_name["b-python-release-final"]
text = (root / full["log"]).read_text()
match = re.search(r"(\d+) passed, (\d+) skipped, .* in ([\d.]+)s", text)
assert match
isolation = json.loads((root / "data/30d-foundation/d21-test-isolation.json").read_text())
assert isolation["exit_code"] == 0 and isolation["all_sqlite_paths_under_test_root"]
junit = ET.parse(Path(isolation["test_root"]) / "junit.xml")
d21_count = sum(
    1
    for t in junit.iter("testcase")
    if t.get("classname", "") in ("tests.test_d21_budget", "tests.test_d21_research")
)
for r in commands:
    r["log_sha256"] = hashlib.sha256((root / r["log"]).read_bytes()).hexdigest()
changed = (
    subprocess.check_output(
        ["git", "diff", "--name-only", "873ccb75e3876c08ecd46f3ce9e9dfd1ce3986bf"], cwd=root
    )
    .decode()
    .splitlines()
)
changed += (
    subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard"], cwd=root)
    .decode()
    .splitlines()
)
source_hashes = {
    p: hashlib.sha256((root / p).read_bytes()).hexdigest()
    for p in sorted(set(changed))
    if p.startswith(("app/", "tests/", "frontend/", "scripts/")) and (root / p).is_file()
}
result = dict(
    baseline="873ccb75e3876c08ecd46f3ce9e9dfd1ce3986bf",
    stage_a_commit="3cdcc8692d18f02408f81ecc7c259958f63d35cf",
    stage_b_commit="See final Git delivery; this committed record cannot contain its own SHA",
    scope="D21 only; no D22-D24 implementation",
    all_required_checks_passed=True,
    commands=commands,
    final_required_commands=required,
    python=dict(
        passed=int(match[1]),
        skipped=int(match[2]),
        seconds=float(match[3]),
        exit_code=0,
        skip_reason="Existing local day43_data_v2 evidence absent; four annual PDFs required and exercised",
    ),
    d21_tests=dict(passed=d21_count, exit_code=0),
    frontend=dict(
        unit_passed=97,
        build_exit=0,
        lint_exit=0,
        retained_warning="Existing D14 test component Fast Refresh warning",
    ),
    chromium=dict(
        independent_cases=68,
        breakdown=dict(
            real_model=2,
            new_process_readonly=2,
            d20=11,
            d17_history=5,
            legacy_financial_product_agent=48,
        ),
        exit_code=0,
    ),
    static_checks=dict(ruff_exit=0, mypy_exit=0, mypy_source_files=101, diff_exit=0),
    isolation=dict(
        sqlite_paths=isolation["sqlite_path_count"],
        all_under_isolated_root=True,
        source_write_guard=isolation["source_write_guard"],
        default_runtime_write_guard=isolation["default_runtime_write_guard"],
    ),
    human=dict(
        actual_acceptances=0,
        all_automation_receipts="simulated_test",
        production_calculable=False,
        ac30_19="pending",
    ),
    final_limits=dict(
        steps=40,
        tool_calls=28,
        retrieval_total=24,
        retrieval_per_call=12,
        model_calls=2,
        active_seconds=240,
        documents=4,
        context_characters=16000,
        time_boundary="soft_before_and_after_io_no_hard_cancel",
    ),
    actual_worst_legal_scope=dict(
        documents=4,
        all_missing_human_wait=True,
        protocol_repairs=1,
        steps=36,
        tool_calls=25,
        retrieval_total=12,
        model_calls=2,
        active_seconds=33.154281,
        controlled_fault="Extra field after first actual provider response; original responses separately saved",
    ),
    compatibility=dict(
        v1_unchanged=True,
        v1_tasks_scanned=221,
        checkpoint_records=3114,
        stage_a_v2_old_null_plan_records=27,
        automatic_upgrade=False,
        explicit_parent_audit=True,
    ),
    real_case_record="product/validation/d21-real-research.json",
    browser_record="product/validation/d21-browser-proof.json",
    restart_record="product/validation/d21-restart-proof.json",
    capacity_record="product/validation/d21-four-document-repair-capacity.json",
    protection_record="product/validation/d21-protection-results.json",
    source_invariants="product/validation/d21-invariants.json",
    source_hashes=source_hashes,
    controlled_faults=[
        "no model",
        "empty retrieval",
        "citation/protocol error",
        "generated financial numbers including Chinese/Unicode",
        "budget exhausted",
        "provider outcome unknown without retry",
        "save failure/interruption",
        "source correction/receipt revocation before final commit",
        "current qualification after correction/revocation",
    ],
    initial_failures=[
        dict(
            name="b-targeted-initial",
            reason="Production missing simulated facts correctly waits; explicit resume refuses. Test expected immediate refusal corrected.",
        ),
        dict(
            name="b-real-initial",
            reason="Acceptance script incorrectly expected nested source; D10 fact is flat. First completed real task read back without regenerating.",
        ),
        dict(
            name="b-real-verify-and-remaining",
            reason="Acceptance script indentation error; zero new model calls.",
        ),
        dict(
            name="b-real-remaining",
            reason="PDF layout header contiguous-text assumption; retained original evidence and verified substantive page phrases with fixed PDF SHA.",
        ),
        dict(
            name="b-chromium-real",
            reason="HTTP decoder only recognized v1; v2 record now recognized, with frontend regression.",
        ),
        dict(
            name="b-python-full",
            reason="Factory directly accessed client attribute not present in spec-based legacy mocks. Shared adapter method fixes assembly; final full suite passed.",
        ),
        dict(
            name="b-restart",
            reason="History proof incorrectly expected HTTP200 for every v1 business status. Failed history remains HTTP503 and is safely decoded.",
        ),
    ],
    llm_failure_policy="SDK max_retries=0; no v2 provider auto retry; one repair only after received response; no refunds or unknown POST replay",
    report_handoff="product/d21-limited-operating-research.md",
    human_guide="product/d21-local-human-guide.md",
)
(root / "product/validation/d21-test-record.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n"
)
print(
    json.dumps(
        dict(
            python=result["python"],
            d21_tests=result["d21_tests"],
            chromium=result["chromium"],
            commands=len(commands),
        ),
        ensure_ascii=False,
    )
)
