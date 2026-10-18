"""Compact D20 delivery evidence; bulky logs/DB/PDFs remain isolated and ignored."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parent.parent
baseline = "369ebcf1e75c863c27937ac950552ca92a10945c"
data = root / "data/30d-foundation"
output = root / "product/validation"


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def browser_summary(path):
    stats = read(path)["stats"]
    assert stats["unexpected"] == 0 and stats["flaky"] == 0, (path, stats)
    return dict(report=str(path.relative_to(root)), expected=stats["expected"],
                unexpected=stats["unexpected"], skipped=stats["skipped"],
                duration_ms=stats["duration"], report_sha256=digest(path))


latest = read(data / "d20-history-browser-latest.json")
artifacts = Path(latest["artifact_dir"])
assert all(r["exit_code"] == 0 for r in latest["records"])
new_browser = [browser_summary(artifacts / f"{r['phase']}-results.json") for r in latest["records"]]
legacy = read(data / "d20-browser/d20-product-browser-record.json")
assert all(r["exit_code"] == 0 for r in legacy)
legacy_summaries = [dict(suite=r["suite"], exit_code=r["exit_code"], runtime_root=r["runtime_root"],
                         **browser_summary(Path(r["report"]))) for r in legacy]
qa = read(data / "d20-qa-history-browser-latest.json")
assert all(r["exit_code"] == 0 for r in qa["records"])
qa_summaries = [browser_summary(Path(qa["artifact_dir"]) / f"{r['phase']}-results.json") for r in qa["records"]]
isolation = read(data / "d20-test-isolation.json")
assert isolation["exit_code"] == 0 and isolation["all_sqlite_paths_under_test_root"]
xml = ET.parse(Path(isolation["test_root"]) / "junit.xml").getroot().find("testsuite")
assert xml is not None and int(xml.attrib["failures"]) == 0 and int(xml.attrib["errors"]) == 0
checks = read(data / "d20-checks.json")
assert all(c["exit_code"] == 0 for c in checks)
for c in checks:
    log = root / c["log"]
    c["log_sha256"] = digest(log)
    if c["name"] == "frontend":
        c["passed"] = int(re.search(r"ℹ pass (\d+)", log.read_text()).group(1))
    if c["name"] == "lint":
        c["warnings"] = [line for line in log.read_text().splitlines() if "warning " in line]
commands = []
for path in sorted((data / "d20-commands").glob("*.json")):
    c = read(path)
    c["log_sha256"] = digest(root / c["log"])
    commands.append(c)

# Exact predecessor core/benchmark evidence, rather than duplicated D19 logs.
core = ["app/agent/operating_research_graph.py", "app/research/task_repository.py",
        "app/agent/execution_budget.py", "app/agent/revenue_confirmation.py",
        "app/agent/finance_tools.py", "app/research/templates.py", "app/api/research_tasks.py",
        "app/agent/financial_analysis.py", "app/rag/selected_scope.py", "app/rag/retriever.py",
        "app/api/runtime_factory.py", "frontend/src/product/CompanyComparison.tsx", "frontend/src/product/FinancialChart.tsx",
        "product/validation/sources.json", "product/validation/manual-benchmark.json",
        "product/validation/d19-persistent-recovery-proof.json"]
invariants = []
for name in core:
    original = subprocess.check_output(["git", "show", f"{baseline}:{name}"], cwd=root)
    invariants.append(dict(path=name, sha256=digest(root / name),
                           unchanged=hashlib.sha256(original).hexdigest() == digest(root / name)))
assert all(i["unchanged"] for i in invariants)

screens = output / "d20-screenshots"
screens.mkdir(exist_ok=True)
images = []
for path in sorted(artifacts.glob("*.png")):
    dest = screens / path.name
    shutil.copy2(path, dest)
    images.append(dict(path=str(dest.relative_to(root)), sha256=digest(dest)))
waiting, resumed = read(artifacts / "waiting-tasks.json"), read(artifacts / "resumed-tasks.json")
assert len(waiting) == len(resumed) == 4
compact_tasks = []
for before, after in zip(waiting, resumed, strict=True):
    assert before["task_id"] == after["task_id"] and after["status"] == "collecting_explanation"
    compact_tasks.append(dict(task_id=after["task_id"], template=after["input"]["template"],
       input=after["input"], waiting_revision=before["revision"], resumed_revision=after["revision"],
       waiting_status=before["status"], resumed_status=after["status"],
       waiting_budget=before["budget"], resumed_budget=after["budget"],
       fact_ids=[dict(side=side, **c) for side in ("first", "second")
                 for c in after["active_input"][side]["choices"]],
       result_count=len(after["snapshot"]["analysis_results"]),
       final_content=after["final_research_content"],
       verified_operating_attribution=after["snapshot"]["verified_operating_attribution"]))
proof_names = ["restart-proof", "production-refusal", "production-waiting", "unknown-proof",
               "resume-unknown-history-proof", "empty-proof", "ownership-proof", "injected-states",
               "invalidated-proof", "results-read-proof", "invalid-reason-proof"]
proof = dict(tasks=compact_tasks, scenarios={name: read(artifacts / f"{name}.json") for name in proof_names},
             process_records=latest["records"], acceptance_kind="simulated_test",
             human_acceptance="pending", real=["four fixed-SHA PDFs", "parser", "SQLite", "ObjectStore", "FastAPI", "Chromium", "D19 LangGraph/checkpointer", "D9/D10 explicit UI"],
             substitutes=["embedding/index/chunk IDs in isolated seed", "empty operating retrieval", "explicit response injections for selected UI faults"],
             operating_model_calls=0, original_d19_proof="product/validation/d19-persistent-recovery-proof.json")
(output / "d20-browser-proof.json").write_text(json.dumps(proof, indent=2, ensure_ascii=False) + "\n")
failures = [
    "First build TS6133 unused import, then unused E2E imports; removed, failures retained locally.",
    "Isolated harness initially lacked findoc-d11-* required prefix; corrected the test root, never weakened production gate.",
    "Test helper attempted storage on about:blank and shim overrode /evidence; corrected navigation and reused existing evidence entry.",
    "1440 first screen initially hid current task status below configuration; added a real status/budget summary.",
    "Production StrictMode restoration retained an aborted request claim; cleanup now releases it and restores with GET.",
    "Known operation query button was inside a collapsed identity detail and history is an aside; corrected test actions/role.",
    "Production start with unqualified simulated facts legitimately waits; explicit production resume refuses. Tests corrected to D19 contract, backend unchanged.",
    "Stale revision was safely rejected but surfaced a generic read error; now exposes safe late_task_response.",
    "A supplemental screenshot attempt referenced the wrong isolated runtime; retained failure and reran using the recorded original root. No production/default runtime affected.",
    "A broad editing replacement added an unintended CompanyComparison prop; removed before delivery and build/legacy comparison remained valid.",
]
record = dict(date="2026-10-10", stage="D20 only", baseline_sha=baseline,
              repository="aning0922/findoc-analyst-v1", private=True, branch="feat/30d-foundation",
              python=dict(passed=int(xml.attrib["tests"]) - int(xml.attrib["skipped"]), skipped=int(xml.attrib["skipped"]), exit_code=0,
                          seconds=float(xml.attrib["time"]), sqlite_path_count=isolation["sqlite_path_count"], all_sqlite_paths_under_isolated_root=True),
              backend_build=next(c for c in reversed(commands) if c["name"]=="backend-compile" and c["exit_code"]==0),
              checks=checks, new_browser=new_browser, legacy_browser=legacy_summaries, qa_history_browser=qa_summaries,
              browser_passed_total=sum(s["expected"] for s in [*new_browser,*legacy_summaries,*qa_summaries]),
              browser_unique_passed_total=sum(s["expected"] for s in [*legacy_summaries,*qa_summaries]) + sum(s["expected"] for s,r in zip(new_browser,latest["records"],strict=True) if r["phase"] in ("wait","recovery-resume","screenshots","invalid-reasons")),
              supplemental_browser_executions=sum(s["expected"] for s,r in zip(new_browser,latest["records"],strict=True) if r["phase"] in ("production-proof","screenshots-final")),
              screenshots=images, core_invariants=invariants, commands=commands, failures_and_repairs=failures,
              protection="product/validation/d20-protection-results.json", browser_proof="product/validation/d20-browser-proof.json",
              budget_audit="product/d21-budget-capacity-audit.md", human_acceptance="pending", d21_executed=False,
              d22_or_d23_executed=False, model_calls=0,
              source_validity_detection="on open, refresh, focus or 30s + request latency; not instantaneous push",
              retained_data="Raw failed/successful logs, databases and PDFs remain in ignored isolated data; only D20 screenshots and compact evidence committed.")
(output / "d20-test-record.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
print(json.dumps(dict(python=record["python"], browser_passed_total=record["browser_passed_total"], screenshots=len(images), all_checks_passed=True), indent=2))
