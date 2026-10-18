"""Publish compact D15 evidence only after reading actual successful exit records."""
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

root = Path.cwd()
out = root / "product/validation"
archive = root / "data/30d-foundation/d15-raw-records"
archive.mkdir(parents=True, exist_ok=True)


def read(path):
    return json.loads(path.read_text())


checks = read(out / "d15-checks.json")
isolation = read(root / "data/30d-foundation/d15-test-isolation.json")
browsers = read(out / "d15-product-browser-record.json")
protection = read(out / "d15-protection-results.json")
assert isolation["exit_code"] == 0
assert all(c["exit_code"] == 0 for c in checks)
assert len(browsers) == 2 and all(b["exit_code"] == 0 for b in browsers)
assert protection["all_passed"]
targeted = read(root / "data/30d-foundation/d15-targeted-isolation.json")
assert targeted["exit_code"] == 0
target_suite = ET.parse(Path(targeted["test_root"]) / "junit.xml").getroot().find("testsuite")
assert target_suite is not None
targeted["stats"] = {k: int(target_suite.attrib[k])
                     for k in ("tests", "failures", "errors", "skipped")}
targeted["log"] = "product/validation/test-logs/d15-final-scope.log"
targeted.pop("sqlite_paths")
targeted["cases"] = [dict(name=t.attrib["name"], seconds=t.attrib["time"],
                           outcome="passed" if not list(t) else "inspect_junit")
                     for t in target_suite.findall("testcase")]
junit = ET.parse(Path(isolation["test_root"]) / "junit.xml").getroot()
suite = junit.find("testsuite")
assert suite is not None
stats = {k: int(suite.attrib[k]) for k in ("tests", "failures", "errors", "skipped")}
stats["passed"] = stats["tests"] - stats["failures"] - stats["errors"] - stats["skipped"]
skips = [{"test": t.attrib["name"], "reason": t.find("skipped").attrib}
         for t in suite.findall("testcase") if t.find("skipped") is not None]
# Historical product suite responses are revalidated, not recopied as megabytes of D15 artifacts.
p = out / "d15-product-measurements.json"
raw = p.read_bytes()
(archive / p.name).write_bytes(raw)
measurements = json.loads(raw)
observations = measurements["observations"]
measurements["observations"] = [
    {"company": o["company"], "analysis_response_count": len(o["analyses"]),
     "browser_errors": o["errors"]} if "analyses" in o else o for o in observations
]
measurements["historical_responses"] = dict(
    retained_locally=str((archive / p.name).relative_to(root)),
    raw_sha256=hashlib.sha256(raw).hexdigest(),
    explanation="D12 assertions rerun unchanged; retain source mappings, counts and errors only",
)
p.write_text(json.dumps(measurements, ensure_ascii=False, indent=2) + "\n")
# Full Playwright details contain no model secrets, keep per-test outcomes in the final record.
for browser in browsers:
    report = read(Path(browser["report"]))
    browser["stats"] = report["stats"]
source_paths = sorted(set(
    subprocess.check_output(["git", "diff", "--name-only"], text=True).splitlines()
    + subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard"],
                              text=True).splitlines()
))
hashes = {p: hashlib.sha256((root / p).read_bytes()).hexdigest()
          for p in source_paths if p.startswith(("app/", "tests/", "frontend/src/", "frontend/e2e/"))
          and (root / p).is_file()}
record = dict(
    stage="D15", date="2026-10-10", timezone="Asia/Shanghai",
    baseline_sha="5bc9be82c68c113345b04dc6e52bf316ab3c074c",
    repository="aning0922/findoc-analyst-v1", private=True, branch="feat/30d-foundation",
    scope="Trusted multi-document selection/filtering only; D16 not implemented",
    python=dict(exit_code=isolation["exit_code"], **stats, skips=skips,
                command=[isolation["python"], "scripts/run_d15_regression.py"],
                log="product/validation/test-logs/d15-python.log"),
    checks=checks, browsers=browsers,
    frontend_unit_tests=73,
    final_d15_test_rerun=targeted,
    validation_order="Full suite plus final 34-test D15 rerun after catalog identity race hardening; full-suite collection predates the one added catalog race test",
    isolation={k: v for k, v in isolation.items() if k != "sqlite_paths"},
    protection="product/validation/d15-protection-results.json",
    sources="product/validation/d15-targeted-four-pdf-proof.json",
    milvus="product/validation/d15-milvus-proof.json",
    index_audit=dict(pymilvus=version("pymilvus"), milvus_lite=version("milvus-lite"),
                     workspace_id="dynamic scalar", document_id="dynamic scalar",
                     source_revision="absent from current production ingestion",
                     runtime_multidoc_versioned_retrieval="blocked before embedding/search",
                     actual_milvus_filter_test=True, actual_bge=False, actual_llm=False,
                     existing_protected_collections_opened=False),
    boundaries=["Four original PDF SHA / parser / ObjectStore / SQLite / HTTP are real",
                "Milvus Lite filter integration uses synthetic 2-D vectors",
                "Version-aware store tests use controlled metadata, not migrated production index",
                "Browser financial seed remains simulated_test; no human financial acceptance",
                "D16 evidence numbering/snapshot, versioned reindex, real BGE/LLM QA pending"],
    initial_failures=[
        dict(log="product/validation/test-logs/d15-targeted.log", exit_code=1,
             reason="Correction fixture changed no metadata; fixed to explicit basis change"),
        dict(log="product/validation/test-logs/d15-python-initial.log", exit_code=1,
             reason="Three legacy chat setup failures: optional source route read missing fake workspace. Fixed; interrupted initial run also hit pytest teardown KeyError; not a passing full run"),
        dict(log="product/validation/test-logs/d15-compatibility-fix.log", pytest_exit_code=1,
             shell_wrapper_exit_code=0,
             reason="New RAG guard test omitted required budget argument; fixed. Shell tail exit is not pytest success"),
        dict(log="product/validation/test-logs/d15-selection-browser-initial.log", exit_code=1,
             reason="Historical source-correction test ran before four-valid-source test; isolated fresh rerun orders D15 selection first"),
    ],
    screenshots=[f"product/validation/d15-product-screenshots/selection-{w}.png"
                 for w in (1440, 1280, 1024)],
    source_sha256=hashes,
)
(out / "d15-test-record.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(dict(python=stats, browsers=[b["stats"] for b in browsers],
                     checks={c["name"]: c["exit_code"] for c in checks}), indent=2))
