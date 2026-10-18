"""Compact final evidence; full logs/DBs/legacy screenshots remain ignored local files."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parent.parent
local = root / "data/30d-foundation"
output = root / "product/validation"


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


isolation = read(local / "d18-test-isolation.json")
python_exit = read(local / "d18-python-exit.json")
assert isolation["exit_code"] == python_exit["exit_code"] == 0
junit = ET.parse(Path(isolation["test_root"]) / "junit.xml").getroot()
cases = list(junit.iter("testcase"))
new = [c for c in cases if c.attrib["classname"] == "tests.test_d18_templates"]
assert len(new) == 64 and not any(list(c) for c in new)
checks = read(local / "d18-checks.json")
assert all(r["exit_code"] == 0 for r in checks)
browsers = read(local / "d18-browser/d18-product-browser-record.json")
for row in browsers:
    stats = read(Path(row["report"]))["stats"]
    assert row["exit_code"] == 0 and stats["unexpected"] == stats["flaky"] == stats["skipped"] == 0
    row["stats"] = stats
    row["local_report_sha256"] = digest(Path(row["report"]))
restart = read(local / "d18-restart.json")
assert not any(restart["execution_calls"].values())
protection = read(output / "d18-protection-results.json")
assert protection["all_passed"]
for row in checks:
    row["local_log_sha256"] = digest(root / row["log"])
source_files = [
    "app/agent/execution_budget.py", "app/agent/financial_analysis.py", "app/agent/tool_loop.py",
    "app/api/runtime_factory.py", "app/api/research_templates.py",
    "app/research/templates.py", "app/research/template_contracts.py", "tests/test_d18_templates.py",
]
frontend_log = (local / "d18-check-frontend.log").read_text()
frontend_count = int(re.search(r"tests (\d+)", frontend_log).group(1))
record = dict(
    stage="D18", date="2026-10-10 Asia/Shanghai", baseline="0fafea74e351f1bc3593d5798dd914e31ac015dc",
    repository="aning0922/findoc-analyst-v1", private=True, branch="feat/30d-foundation",
    code_sha256={p: digest(root / p) for p in source_files},
    python=dict(**python_exit, passed=len(cases)-sum(c.find("skipped") is not None for c in cases),
                skipped=sum(c.find("skipped") is not None for c in cases),
                d18_cases=len(new), seconds=float(junit.find("testsuite").attrib["time"]),
                skipped_cases=[dict(**c.attrib, reason=c.find("skipped").attrib.get("message", ""))
                               for c in cases if c.find("skipped") is not None],
                local_log_sha256=digest(local / "d18-python-final.log")),
    isolation={k: isolation[k] for k in ("test_root", "python", "python_version", "sqlite_path_count",
                                       "all_sqlite_paths_under_test_root", "source_write_guard",
                                       "original_product_write_guard", "default_runtime_write_guard")},
    frontend_tests=frontend_count, checks=checks, mypy_source_files=94,
    lint_known_warning="Existing d14-chart-boundaries.tsx Fast Refresh export warning; exit 0.",
    browser_total=sum(r["stats"]["expected"] for r in browsers), browsers=browsers,
    d17_fresh_process_restart=dict(exit_code=0, command=[isolation["python"], "scripts/validate_d18_restart.py"],
                                  proof=restart),
    real_template_preflight=dict(proof="d18-four-pdf-proof.json", four_fixed_sha_pdfs=True,
                                 legal_cases=5, status="awaiting_human_confirmation",
                                 deterministic_analysis_calls=0, actual_model_calls=0,
                                 actual_bge=False, human_acceptance_created=False),
    controlled_financial_execution="isolated simulated_test only; production requests cannot opt in",
    boundaries=dict(d19_checkpointer=False, persistent_wait=False, automatic_resume=False,
                    d20_template_ui=False, d21_real_model_research=False,
                    final_research_content=None, verified_operating_attribution=False,
                    d17_contract_changed=False, database_migration_added=False),
    key_failures="d18-key-failures.json", protection="d18-protection-results.json",
    artifact_budget="Only this record, four-PDF summary, key failures and protection are committed; logs/DBs/legacy screenshots remain ignored.",
)
(output / "d18-test-record.json").write_text(json.dumps(record, indent=2, ensure_ascii=False)+"\n")
# The all-tests runner supplies the final four-PDF proof; discard the earlier duplicate proof.
(output / "d18-targeted-four-pdf-proof.json").unlink(missing_ok=True)
print(json.dumps(dict(python=record["python"]["passed"], skipped=record["python"]["skipped"],
                     d18=len(new), frontend=frontend_count, browsers=record["browser_total"])))
assert subprocess.run(["git", "diff", "--check"], cwd=root).returncode == 0
