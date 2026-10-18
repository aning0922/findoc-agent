"""Full integration regression; fresh seed only, no protected runtime access."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from urllib.parse import unquote, urlparse

product = Path(__file__).resolve().parent.parent
os.environ["TIKTOKEN_CACHE_DIR"] = str(product / "data/integration-tokenizer-cache")
evidence = Path(os.environ.get("D26_EVIDENCE_ROOT", product / "product/d26/evidence")).resolve()
evidence.mkdir(parents=True, exist_ok=True)
seed = Path(os.environ.get("D26_SEED_DIR", product / "product/d26/evidence/seed")).resolve()
record = json.loads((seed / "record.json").read_text())
assert record["exit_code"] == 0 and record["simulated_test"] and record["servers_stopped"]
source = Path(record["runtime_root"]).resolve()
assert source.name.startswith("findoc-d11-d21-ux-p1-")
assert source.is_relative_to(Path(tempfile.gettempdir()).resolve())
root = Path(tempfile.mkdtemp(prefix="findoc-d26-regression-")).resolve()
protected = [p.resolve() for p in product.parent.glob("findoc-*") if p.resolve() != product]
connections = set()


def audit(event, args):
    if event == "socket.connect":
        raise RuntimeError("Integration backend forbids service connections")
    if event == "sqlite3.connect" and args[0] != ":memory:":
        value = args[0]
        if isinstance(value, str) and value.startswith("file:"):
            value = unquote(urlparse(value).path)
        p = Path(value).resolve()
        if not p.is_relative_to(root):
            raise RuntimeError(f"SQLite outside fresh regression root: {p}")
        connections.add(str(p))
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        p = Path(os.fsdecode(args[0])).resolve()
        if any(p.is_relative_to(d) for d in protected):
            raise RuntimeError(f"Protected worktree access rejected: {p}")


sys.addaudithook(audit)
os.environ["TMPDIR"] = str(root)
tempfile.tempdir = str(root)
os.environ["FINDOC_RUNTIME_ROOT"] = str(root / "runtime")
os.environ["FINDOC_E2E_DISABLE_ENV_FILES"] = "1"
for key in list(os.environ):
    if key.startswith("LLM_") or key == "OPENAI_API_KEY":
        del os.environ[key]
# Only the freshly generated simulated seed is copied. No D25 DB is opened.
fixture = root / "findoc-d11-d22-seed"
fixture.mkdir()
shutil.copy2(source / "documents.db", fixture / "documents.db")
shutil.copytree(source / "objects", fixture / "objects")
with sqlite3.connect(fixture / "documents.db") as conn:
    assert conn.execute("SELECT count(*) FROM reports").fetchone()[0] == 0
    receipts = conn.execute("SELECT * FROM financial_acceptance_receipts").fetchall()
    assert receipts and all("simulated_test" in str(row) for row in receipts)
journey = json.loads((seed / "journey-proof.json").read_text())
proof = root / "report-proof.json"
proof.write_text(
    json.dumps({"runtime_root": str(fixture), "cases": [{"result": journey["result"]}]})
)
os.environ["FINDOC_REPORT_TEST_PROOF"] = str(proof)
# Reconstruct v8 ONLY in another disposable copy, keeping all populated v1-v8
# tables byte-for-byte in row/schema comparison; the empty v9 report schema is removed.
v8 = root / "v8"
v8.mkdir()
shutil.copy2(fixture / "documents.db", v8 / "documents.db")
with sqlite3.connect(v8 / "documents.db") as conn:
    tables = [
        "reports",
        "report_revisions",
        "report_operations",
        "report_source_refs",
        "report_fact_refs",
    ]
    old = {
        n: (
            conn.execute("SELECT sql FROM sqlite_master WHERE name=?", (n,)).fetchone(),
            conn.execute(f'SELECT * FROM "{n}" ORDER BY rowid').fetchall(),
        )
        for (n,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        if n not in tables + ["analyst_schema_migrations", "sqlite_sequence"]
    }
    for n in tables:
        assert conn.execute(f"SELECT count(*) FROM {n}").fetchone()[0] == 0
        conn.execute(f"DROP TABLE {n}")
    conn.execute("DELETE FROM analyst_schema_migrations WHERE version=9")
    assert max(r[0] for r in conn.execute("SELECT version FROM analyst_schema_migrations")) == 8
    for n, before in old.items():
        assert (
            conn.execute("SELECT sql FROM sqlite_master WHERE name=?", (n,)).fetchone(),
            conn.execute(f'SELECT * FROM "{n}" ORDER BY rowid').fetchall(),
        ) == before
v8proof = root / "migration-proof.json"
v8proof.write_text(json.dumps({"runtime_root": str(v8)}))
os.environ["FINDOC_MIGRATION_TEST_PROOF"] = str(v8proof)
import pytest  # noqa: E402

code = int(
    pytest.main(
        [
            "-q",
            "-p",
            "no:cacheprovider",
            "--basetemp",
            str(root / "pytest"),
            "--junitxml",
            str(evidence / "backend-junit.xml"),
            *(sys.argv[1:] or ["tests"]),
        ]
    )
)
(evidence / "backend-isolation.json").write_text(
    json.dumps(
        {
            "root": str(root),
            "seed": record,
            "exit_code": code,
            "sqlite_paths": sorted(connections),
            "all_sqlite_under_fresh_root": True,
            "service_connections_blocked": True,
            "protected_worktree_access_blocked": True,
            "simulated_test": True,
            "human_acceptances": 0,
            "v8_projection_preserves_all_pre_report_tables": True,
            "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        },
        indent=2,
    )
    + "\n"
)
sys.exit(code)
