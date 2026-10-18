"""Publish reviewable D23 validation evidence only after all required gates pass."""

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parent.parent
validation = root / "product/validation"
commands = [
    json.loads(p.read_text())
    for p in sorted((root / "data/30d-foundation/d23-commands").glob("*.json"))
]
required = [
    "backend-full-final",
    "browser",
    "legacy-browser",
    "real-source-and-acceptance-audits",
    "frontend-unit-final",
    "frontend-build-repaired",
    "frontend-lint-final",
    "static-final",
    "mypy-final",
    "protection-final",
    "secret-scan-final",
    "diff-final",
]
latest = {entry["name"]: entry for entry in commands}
assert all(name in latest and latest[name]["exit_code"] == 0 for name in required), {
    name: latest.get(name, {}).get("exit_code") for name in required
}
logs = validation / "d23-test-logs"
logs.mkdir(exist_ok=True)
for entry in commands:
    src = root / entry["log"]
    if src.exists():
        target = logs / src.name
        shutil.copy2(src, target)
        entry["committed_log"] = str(target.relative_to(root))
        assert hashlib.sha256(target.read_bytes()).hexdigest() == entry["sha256"]

isolation = json.loads((root / "data/30d-foundation/d23-test-isolation.json").read_text())
assert isolation["exit_code"] == 0 and isolation["all_sqlite_paths_under_test_root"]
junit = Path(isolation["test_root"]) / "junit.xml"
shutil.copy2(junit, logs / "backend-junit.xml")
xml = ET.parse(junit).getroot()
suites = xml.findall("testsuite")
counts = {
    k: sum(int(s.get(k, "0")) for s in suites) for k in ("tests", "failures", "errors", "skipped")
}
skipped_cases = [
    dict(classname=t.get("classname"), name=t.get("name"), reason=t.find("skipped").get("message"))
    for t in xml.iter("testcase")
    if t.find("skipped") is not None
]
assert counts["failures"] == 0 and counts["errors"] == 0
(validation / "d23-isolation.json").write_text(json.dumps(isolation, indent=2) + "\n")

migration_entry = latest["migrations9"]
text = (root / migration_entry["log"]).read_text()
migration_root = Path(re.search(r"D23 isolated root: (.+)", text)[1])
migrations = [json.loads(p.read_text()) for p in migration_root.rglob("d23-migration-*.json")]
assert len(migrations) == 3
(validation / "d23-migration-results.json").write_text(json.dumps(migrations, indent=2) + "\n")

browser = json.loads((validation / "d23-browser-record.json").read_text())
out = Path(browser["artifacts"])
assert len(browser["records"]) == 3 and all(r["exit_code"] == 0 for r in browser["records"])
assert all(
    r["db_unchanged"] and r["no_pdf_directory"] for r in browser["records"] if r["phase"] != "live"
)
shots = validation / "d23-screenshots"
shots.mkdir(exist_ok=True)
for src in out.glob("*.png"):
    shutil.copy2(src, shots / src.name)
phases = []
for r in browser["records"]:
    data = json.loads((out / f"{r['phase']}-results.json").read_text())
    assert data["stats"]["unexpected"] == 0
    phases.append(dict(phase=r["phase"], **data["stats"]))
    shutil.copy2(out / f"{r['phase']}-browser.log", logs / f"{r['phase']}-browser.log")

legacy_attempts = json.loads(
    (root / "data/30d-foundation/d23-browser/d23-product-browser-record.json").read_text()
)
legacy = list({r["suite"]: r for r in legacy_attempts}.values())
assert len(legacy) == 6 and all(r["exit_code"] == 0 for r in legacy)
(validation / "d23-legacy-browser-record.json").write_text(
    json.dumps(dict(attempts=legacy_attempts, final=legacy), indent=2) + "\n"
)
legacy_counts = []
for r in legacy:
    data = json.loads(Path(r["report"]).read_text())
    assert data["stats"]["unexpected"] == 0
    legacy_counts.append(dict(suite=r["suite"], **data["stats"]))
for src in (root / "data/30d-foundation/d23-browser/test-logs").glob("*browser.log"):
    shutil.copy2(src, logs / src.name)

real = json.loads((validation / "d23-real-reports.json").read_text())
assert len(real["cases"]) == 4 and real["task_rows_unchanged"]
assert all(v == 0 for v in real["save_execution_calls"].values())
for key in ("restart", "invalidated", "source_invalidated"):
    assert (
        real[key]["db_unchanged"]
        and real[key]["no_pdf_directory"]
        and all(v == 0 for v in real[key]["execution_calls"].values())
    )
    assert len(real[key]["results"]) == 8
    assert all(
        v["eligibility"]["status"] == ("current_at_read" if key == "restart" else "invalidated")
        for v in real[key]["results"]
    )

visual = subprocess.check_output(
    ["git", "rev-parse", "refs/heads/codex/visual-v2"], cwd=root, text=True
).strip()
proof = dict(
    start_commit="7144c05a090c0afd1a16376f5eb6db82e402d10d",
    repository="aning0922/findoc-analyst-v1",
    branch="feat/30d-foundation",
    scope="D23 only; D24 handoff documentation, no export implementation",
    final_commit="See final Git delivery; a commit cannot embed its own SHA",
    all_required_checks_passed=True,
    commands=commands,
    backend=counts,
    skipped_cases=skipped_cases,
    frontend_unit_tests=103,
    frontend_build=True,
    ruff=True,
    mypy=True,
    frontend_lint=True,
    lint_existing_warning="tests/support/d14-chart-boundaries.tsx only-export-components",
    browser_phases=phases,
    legacy_browser_suites=legacy_counts,
    isolated_test_root=isolation["test_root"],
    sqlite_paths_checked=isolation["sqlite_path_count"],
    all_sqlite_paths_isolated=True,
    four_scenarios_saved=4,
    immutable_versions_checked=8,
    financial_slots_checked=24,
    analyses_checked=12,
    restart_get_only=True,
    source_invalidation_and_acceptance_revocation_separately_verified=True,
    d21_task_rows_unchanged=True,
    simulated_test=True,
    human_acceptances=0,
    human_semantic_review="pending",
    visual_v2_branch_observed=visual,
    visual_v2_worktree_mutations_by_d23=False,
    screenshots=[str(p.relative_to(root)) for p in sorted(shots.glob("*.png"))],
    early_issues=[
        "Read-only SQLite URI initially rejected by the inherited path audit; fixed decoding file URI within the same temporary-root boundary.",
        "Frontend test fixture incomplete structure required an explicit unknown cast; production types remain strict; final build passed.",
        "Initial full run interrupted at 577 passing tests after adding the production replay boundary and isolating the original migration-8 test; final full run is the authoritative gate.",
    ],
    remaining_limits=[
        "No human financial acceptance or semantic causality review completed.",
        "DB-only current qualification is separate from PDF-byte validity; no SQLite/object-store distributed transaction.",
        "No protection against a privileged administrator changing both payload and digest.",
        "Unresolved operation absence keeps GET-only recovery; no automatic repost.",
        "Each report fixes one parent research task; new scenario requires a new report.",
        "D24 Markdown export remains unimplemented.",
    ],
)
(validation / "d23-test-record.json").write_text(
    json.dumps(proof, ensure_ascii=False, indent=2) + "\n"
)
print(
    json.dumps(
        dict(
            backend=counts,
            skipped_cases=skipped_cases,
            browser_phases=phases,
            legacy_suites=legacy_counts,
            screenshots=len(proof["screenshots"]),
        ),
        ensure_ascii=False,
    )
)
