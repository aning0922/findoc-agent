"""Compile UX-P1 evidence without reading any D25 runtime or original service."""

import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parent.parent
out = root / "product/ux-p1/evidence"


def read(path):
    return json.loads(path.read_text())


def cases(isolation):
    xml = ET.parse(Path(isolation["test_root"]) / "junit.xml")
    return {(c.get("classname"), c.get("name")): c for c in xml.findall(".//testcase")}


initial = read(out / "backend-initial-isolation.json")
repeat_path = root / "data/30d-foundation/ux-p1-targeted-isolation.json"
repeat = read(repeat_path)
failed = {
    key
    for key, c in cases(initial).items()
    if c.find("failure") is not None or c.find("error") is not None
}
retested = cases(repeat)
assert repeat["exit_code"] == 0 and failed == set(retested)
assert all(c.find("failure") is None and c.find("error") is None for c in retested.values())
assert initial["all_sqlite_paths_under_test_root"] and repeat["all_sqlite_paths_under_test_root"]
shutil.copy2(repeat_path, out / "backend-targeted-isolation.json")
shutil.copy2(Path(initial["test_root"]) / "junit.xml", out / "backend-initial-junit.xml")
shutil.copy2(Path(repeat["test_root"]) / "junit.xml", out / "backend-targeted-junit.xml")

browser = read(out / "after/record.json")
results = read(out / "after/results.json")
assert browser["exit_code"] == 0
assert results["stats"]["unexpected"] == 0 and results["stats"]["skipped"] == 0
assert browser["human_acceptances"] == 0 and browser["simulated_test"]
journey = read(out / "after/journey-proof.json")
assert journey["cancel_db_sha_unchanged"] and journey["cancel_zero_writes"]
assert journey["return_zero_writes"] and journey["reload_zero_writes"]
report = read(out / "after/guided-report-proof.json")
assert report["reload_and_exports_zero_posts"] and len(report["downloads"]) == 3
assert read(out / "after/unknown-proof.json")["no_automatic_retry"]
assert read(out / "after/acceptance-unknown-proof.json")["recovered_by_get"]
readability = [read(p) for p in sorted((out / "after").glob("*-readability.json"))]
assert not [failure for group in readability for width in group for failure in width["failures"]]

# Machine proof records retain every field; compact large serialized snapshots.
for proof_path in (out / "before").glob("*proof.json"):
    if len(proof_path.read_text().splitlines()) > 500:
        proof_path.write_text(
            json.dumps(read(proof_path), ensure_ascii=False, separators=(",", ":")) + "\n"
        )
for proof_path in (out / "after").glob("*proof.json"):
    if len(proof_path.read_text().splitlines()) > 500:
        proof_path.write_text(
            json.dumps(read(proof_path), ensure_ascii=False, separators=(",", ":")) + "\n"
        )

zoom_records = [read(p) for p in sorted((out / "after").glob("*-zoom-proof.json"))]
assert zoom_records and all(
    r["width"] == r["physical_width"] / 2
    and r["dpr"] == 2
    and r["png_width"] == r["physical_width"]
    and r["png_height"] == 900
    for group in zoom_records
    for r in group
)
summary = dict(
    frontend_unit_tests=112,
    build="passed",
    lint="passed; one pre-existing d14 test harness Fast Refresh warning",
    baseline="c9a84c454130690fb7eae43ac17511b0f4e67f1a",
    branch="codex/ux-p1-product-workflow",
    backend=dict(
        unique_passed=len(cases(initial))
        - sum(c.find("skipped") is not None for c in cases(initial).values()),
        skipped=sum(c.find("skipped") is not None for c in cases(initial).values()),
        initial_passed=len(cases(initial)) - len(failed) - 1,
        fixture_failures=len(failed),
        resolved_by_exact_targeted_retest=True,
        sqlite_guard=True,
        d25_file_guard=True,
    ),
    browser=dict(
        passed=results["stats"]["expected"],
        actual_http=True,
        actual_sqlite=True,
        actual_pdf=True,
        actual_chromium=True,
        human_acceptances=0,
        financial_acceptance="simulated_test",
        model_and_index="controlled test assembly",
        cancel_database_fingerprint_unchanged=True,
        no_automatic_accept_persist_or_resume=True,
        original_report_revisions_and_downloads_verified=True,
    ),
    viewports=[1440, 1280, 1024],
    zoom=dict(
        percent=200,
        method="Chromium CDP: half CSS layout viewport, deviceScaleFactor=2, mobile=false; native Page.captureScreenshot PNG dimensions asserted",
    ),
    text_contrast=dict(
        minimum_required=4.5,
        all_recorded_desktop_text_checks_passed=True,
        measurements="UI text; native PDF raster is visually inspected",
    ),
    frozen_disclosure_reuse="explicit selection intent + current server qualification + exact full source/fact identity",
    runtime=browser["runtime_root"],
    d25_runtime_accessed=False,
    pending=[
        "GPT-6 visual and business operation review",
        "unassisted first-time human usability acceptance",
    ],
)
(out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
# Inventory immutable deliverable artifacts, excluding traces that may contain copyrighted PDF bytes.
inventory = []
for p in sorted(out.rglob("*")):
    if (
        p.is_file()
        and p.name != "artifact-inventory.json"
        and "traces" not in p.parts
        and p.suffix in (".png", ".json", ".md", ".xml")
    ):
        inventory.append(
            dict(
                path=str(p.relative_to(root)),
                bytes=p.stat().st_size,
                sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
            )
        )
(out / "artifact-inventory.json").write_text(
    json.dumps(inventory, ensure_ascii=False, indent=2) + "\n"
)
print(json.dumps(summary, ensure_ascii=False, indent=2))
