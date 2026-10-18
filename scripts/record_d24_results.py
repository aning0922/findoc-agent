"""Consolidate exact command outcomes and actual downloads, retaining repaired failures."""

import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parent.parent
commands = [
    json.loads(p.read_text())
    for p in sorted((root / "data/30d-foundation/d24-commands").glob("*.json"))
]
logs = root / "product/validation/d24-test-logs"
logs.mkdir(exist_ok=True)
for entry in commands:
    source = root / entry["log"]
    target = logs / source.name
    shutil.copy2(source, target)
    entry["committed_log"] = str(target.relative_to(root))
    assert hashlib.sha256(target.read_bytes()).hexdigest() == entry["sha256"]
required = [
    "targeted-2",
    "http-bounds-final",
    "real-four-2",
    "backend-full",
    "frontend-unit",
    "frontend-build-2",
    "frontend-lint-final",
    "ruff-final",
    "mypy",
    "browser-2",
    "legacy-browser",
    "markdown-reader",
    "protection-after",
    "secret-scan",
]
assert all(any(c["name"] == name and c["exit_code"] == 0 for c in commands) for name in required)
isolation = json.loads((root / "data/30d-foundation/d24-test-isolation.json").read_text())
junit = ET.parse(Path(isolation["test_root"]) / "junit.xml").getroot()
suites = list(junit.iter("testsuite"))
backend = {
    key: sum(int(s.attrib.get(key, 0)) for s in suites)
    for key in ("tests", "failures", "errors", "skipped")
}
backend["passed"] = backend["tests"] - backend["failures"] - backend["errors"] - backend["skipped"]
assert (
    backend["failures"] == backend["errors"] == 0 and isolation["all_sqlite_paths_under_test_root"]
)
browser = json.loads((root / "product/validation/d24-browser-record.json").read_text())
assert len(browser["records"]) == 3 and all(r["exit_code"] == 0 for r in browser["records"])
actual = []
for r in browser["records"]:
    result = json.loads((Path(browser["artifacts"]) / f"{r['phase']}-results.json").read_text())
    actual.append(dict(phase=r["phase"], stats=result["stats"]))
legacy = json.loads(
    (root / "data/30d-foundation/d24-browser/d24-product-browser-record.json").read_text()
)
for item in legacy:
    stats = json.loads(Path(item["report"]).read_text())["stats"]
    item["stats"] = stats
assert len(legacy) == 6 and all(item["exit_code"] == 0 for item in legacy)
(root / "product/validation/d24-legacy-browser-record.json").write_text(
    json.dumps(legacy, ensure_ascii=False, indent=2) + "\n"
)
reader = json.loads((root / "product/validation/d24-markdown-reader.json").read_text())
files = [f for c in browser["file_checks"] for f in c.get("downloads", [])]
assert len(files) == 16 and len(reader["records"]) == 8
report = dict(
    date="2026-10-11 Asia/Shanghai",
    start_commit="0c2417e3e08a220ab51257b68ed844833b15310b",
    final_commit="See final Git delivery; commit cannot embed its own SHA",
    repository="aning0922/findoc-analyst-v1",
    branch="feat/30d-foundation",
    scope="D24 only; D25 handoff, no D25 execution or Visual integration",
    all_required_checks_passed=True,
    commands=commands,
    backend=backend,
    frontend_unit=dict(passed=103, failed=0),
    d24_targeted=dict(passed=20, failed=0),
    actual_browser=actual,
    downloaded_files=16,
    download_file_checks=browser["file_checks"],
    actual_markdown_reader_versions=8,
    legacy_browser_stats=[dict(suite=i["suite"], stats=i["stats"]) for i in legacy],
    isolation=dict(
        test_root=isolation["test_root"],
        sqlite_path_count=isolation["sqlite_path_count"],
        all_sqlite_paths_under_test_root=True,
    ),
    repairs=[
        "Initial D23-runner invocation without PYTHONDONTWRITEBYTECODE rejected protected pycache write; subsequent D24 recorder enforces no bytecode writes.",
        "Initial targeted fixture import depended on unregistered nested fixture; direct D22 fixture wrapper fixed.",
        "Repeated selected document reindex in four-scenario verification correctly returned reindex_conflict; shared-document conflict handled and all eight versions independently verified blocked.",
        "Production simulation browser assertion expected a simulation-specific message; aligned with existing D23 fail-closed report-identity message, preserving D22/D23 UI contract.",
    ],
    limits=[
        "All four scenarios simulated_test; human financial acceptance and semantic attribution review pending.",
        "No cross-store transaction prevents PDF changes after final byte check.",
        "Relative version-pinned PDF links require the original FinDoc service; PDF bytes are not embedded.",
        "Browser anchor API cannot attest final filesystem save; UI reports handoff only. Actual tests verify download failure() and saved files.",
        "No defense against administrator rewriting upstream data and all hashes/refs consistently.",
        "Markdown includes a large complete audit appendix, rendered in memory.",
    ],
)
(root / "product/validation/d24-test-record.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n"
)
print(
    json.dumps(
        dict(
            backend=backend,
            browser_passed=sum(s["stats"]["expected"] for s in actual),
            legacy_passed=sum(i["stats"]["expected"] for i in legacy),
            downloaded_files=16,
            all_required_checks_passed=True,
        )
    )
)
