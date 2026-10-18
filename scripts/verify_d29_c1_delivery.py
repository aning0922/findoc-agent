"""Verify actual final results, exact executed source, identity and lossless evidence."""

import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import re
import xml.etree.ElementTree as ET
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "product/d29-c1"


def read(path):
    p = OUT / path
    return json.loads(
        p.read_bytes()
        if p.exists()
        else gzip.decompress(p.with_suffix(p.suffix + ".gz").read_bytes())
    )


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


names = {
    "c1": "after-final-r5",
    "before": "before-r3",
    "d29_a": "d29-a-final-r2",
    "d29_b": "d29-b-final",
    "s6": "s6-final",
}
expected = {"c1": 68, "before": 9, "d29_a": 22, "d29_b": 38, "s6": 18}
summary = {}
for key, name in names.items():
    stats = read(Path("evidence") / name / "results.json")["stats"]
    assert (
        stats["expected"] == expected[key]
        and stats["unexpected"] == stats["skipped"] == stats["flaky"] == 0
    )
    record = read(Path("evidence") / name / "record.json")
    assert record["exit_code"] == 0 and record["servers_stopped"]
    matched = 0
    for p, digest in record.get("executed_source_sha256", {}).items():
        raw = (
            subprocess.check_output(
                ["git", "show", "0cf97c376ca675815ae51e6af1408953bdee7f46:" + p], cwd=ROOT
            )
            if key == "before"
            else (ROOT / p).read_bytes()
        )
        assert sha(raw) == digest, (key, p)
        matched += 1
    summary[key] = dict(
        pass_count=stats["expected"],
        fail_count=stats["unexpected"],
        skip_count=stats["skipped"],
        seconds=stats["duration"] / 1000,
        exact_source_files=matched,
        runtime_root=record["runtime_root"],
    )
final = read(Path("evidence") / names["c1"] / "manifest.json")
fixtures = json.loads((ROOT / "frontend/tests/fixtures/answer-focus.json").read_bytes())
assert [v["projection"] for v in fixtures] == [v["projection"] for v in final["runs"][:12]]
for item in final["runs"][:12]:
    f = item["projection"]["focus"]
    assert (f["raw_value"], f["raw_unit"], f["financial_year"], f["row_index"]) == (
        item["expected_value"],
        item["expected_unit"],
        item["expected_year"],
        item["expected_row"],
    )
assert len({v["projection"]["projection_sha256"] for v in final["runs"][:12]}) == 12
assert len({v["projection"]["answer_sha256"] for v in final["runs"][:12]}) == 4
for item in final["distractors"]:
    p = item["projection"]
    f = p["focus"]
    if item["expected_value"] is None:
        assert p["status"] == "unlocated" and f is None
    else:
        assert (f["raw_value"], f["raw_unit"], f["financial_year"]) == (
            item["expected_value"],
            item["expected_unit"],
            item["expected_year"],
        )
proof = read("evidence/historical-byte-proof.json")
assert len(proof) == 18 and all(
    p["http_response_bytes_equal"]
    and p["result_equal"]
    and p["answer_sha256"] == p["original_answer_sha256"]
    and p["run_integrity_sha256"] == p["original_integrity_sha256"]
    and p["original_excerpt_sha256"] == p["current_excerpt_sha256"]
    for p in proof
)
audits = []
folder = OUT / "evidence" / names["c1"]
for p in sorted(folder.glob("*-audit.json*")):
    value = json.loads(gzip.decompress(p.read_bytes()) if p.suffix == ".gz" else p.read_bytes())
    assert value["start"] == value["end"]
    assert all(m["method"] == "GET" for m in value["methods"])
    audits.append(dict(path=str(p.relative_to(OUT)), gets=len(value["methods"])))
assert len(audits) == 67
record = read(Path("evidence") / names["c1"] / "record.json")
runtime = Path(record["runtime_root"]).resolve()
assert runtime.name.startswith("findoc-d11-d29-c1-") and runtime.is_relative_to(
    Path(tempfile.gettempdir()).resolve()
)
with sqlite3.connect(
    f"file:{Path(record['runtime_root']) / 'documents.db'}?mode=ro", uri=True
) as c:
    tables = [
        r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    ]
    hashes = {
        t: sha(
            json.dumps(
                sorted(c.execute(f'SELECT * FROM "{t}"').fetchall(), key=str), default=list
            ).encode()
        )
        for t in tables
    }
changed = [t for t in tables if hashes[t] != record["seed_tables"][t]]
assert set(changed) == {"documents", "document_sources", "report_binding_corrections"}
suite = ET.parse(OUT / "evidence/checks/backend-junit.xml").getroot()[0]
assert int(suite.attrib["tests"]) == 425 and all(
    int(suite.attrib[k]) == 0 for k in ("failures", "errors", "skipped")
)
front = (OUT / "frontend-final-r3.log").read_text()
assert re.search(r"ℹ pass 183\b", front) and re.search(r"ℹ fail 0\b", front)
summary.update(
    backend=dict(pass_count=425, fail_count=0, skip_count=0),
    frontend=dict(pass_count=183, fail_count=0, skip_count=0),
    focus=dict(
        fixed_questions=12,
        distinct_answer_sha=4,
        distinct_projection_sha=12,
        additional_pdf_questions=12,
        located_additional=8,
        unlocated_additional=4,
        wrong_amount=0,
        wrong_year=0,
        wrong_unit=0,
    ),
    history=dict(http_byte_hashes_unchanged=18, result_objects_unchanged=18),
    readonly=dict(
        audits=audits,
        gets=sum(a["gets"] for a in audits),
        non_gets=0,
        only_preparation_changed_tables=changed,
        all_read_snapshots_unchanged=True,
    ),
    human_acceptances=0,
    c1_model_calls=0,
    c1_retrieval_calls=0,
)
(OUT / "validation-summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
)
print(
    json.dumps({k: v for k, v in summary.items() if k != "readonly"}, ensure_ascii=False, indent=2)
)
print(
    "C1 UI GETs:",
    summary["readonly"]["gets"],
    "non-GETs: 0; unchanged per-read table snapshots: 67.",
)
