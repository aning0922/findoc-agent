"""Verify delivered test evidence, frozen product source and historical byte proof."""

import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "product/d29-c2"
BASE = "43d7badfb6a6eb270c7d233cb9a64926e90f9bd6"


def read(path):
    p = OUT / path
    return (
        p.read_bytes()
        if p.exists()
        else gzip.decompress(p.with_suffix(p.suffix + ".gz").read_bytes())
    )


def load(path):
    return json.loads(read(path))


summary = {"base": BASE, "browser": {}}
for name, count in {
    "after-final": 46,
    "before-final-r2": 15,
    "c1-regression": 68,
    "a-regression": 22,
    "b-regression": 38,
    "s6-regression": 18,
}.items():
    stats = load(f"evidence/{name}/results.json")["stats"]
    assert stats["expected"] == count and all(
        stats[k] == 0 for k in ["unexpected", "flaky", "skipped"]
    )
    record = load(f"evidence/{name}/record.json")
    assert record["exit_code"] == 0 and record["servers_stopped"]
    # The Before code is the fixed C1 archive; all After/regression source must be current.
    for path, digest in record.get("executed_source_sha256", {}).items():
        if name.startswith("before"):
            raw = subprocess.check_output(["git", "show", f"{BASE}:{path}"], cwd=ROOT)
        else:
            raw = (ROOT / path).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == digest, (name, path)
    summary["browser"][name] = stats
    if name == "after-final":
        assert record["isolated_restart_verified"]

proof = load("evidence/after-final/restart-proof.json")
assert proof["before_state"] == proof["after_state"] and len(proof["exact_http_bytes"]) == 25
historical = load("evidence/historical-byte-proof.json")
assert len(historical["runs"]) == 18
for item in historical["unchanged_contracts"] + historical["unchanged_historical_objects"]:
    assert (
        hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest()
        == item["baseline_sha256"]
        == item["current_sha256"]
    )
http = load("evidence/exact-http-history-proof.json")
assert len(http["runs"]) == 18
assert all(r["exact_response_sha256"] == r["historical_response_sha256"] for r in http["runs"])
assert (
    http["reports"][0]["markdown_sha256"]
    == "28ddda7dc495e3396a387ff966d9c56a99679084de8841d9eb57d940fd61b9d0"
)

for item in ET.fromstring(read("evidence/checks/backend-junit.xml")).iter("testsuite"):
    assert (
        int(item.attrib.get("failures", 0))
        == int(item.attrib.get("errors", 0))
        == int(item.attrib.get("skipped", 0))
        == 0
    )
    summary["backend"] = int(item.attrib["tests"])
assert summary["backend"] == 425
frontend = read("evidence/frontend-final.log").decode()
assert re.search(r"pass 208\b", frontend) and re.search(r"fail 0\b", frontend)
summary["frontend"] = 208
summary["historical_http_runs"] = 18
summary["restart_exact_http_reads"] = 25
assert (
    subprocess.check_output(
        ["git", "diff", "--name-only", BASE, "--", "app", "product/d28", "product/d29-c1"], cwd=ROOT
    )
    == b""
)
subprocess.run(
    [str(ROOT / ".venv/bin/python"), "scripts/build_d29_c2_reviews.py", "--check"],
    cwd=ROOT,
    check=True,
)
(OUT / "validation-summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
)
print(
    "Verified exact product source, all final tests, 18 historical HTTP bytes and 25 restart reads."
)
