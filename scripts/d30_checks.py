"""D30 rerun of unchanged D29-D contract assertions in a fresh isolated root."""

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
run = Path(tempfile.mkdtemp(prefix="findoc-d30-contracts-")).resolve()
reports_only = "--reports-only" in sys.argv
out = Path(os.environ.get("D30_CHECKS_OUT", str(ROOT / "product/d30/evidence/checks"))) / ("reports-final" if reports_only else "")
if "--preflight-only" in sys.argv:
    out = out / "preflight-r2"
out.mkdir(parents=True, exist_ok=False)
connections = set()
protected = [p.resolve() for p in ROOT.parent.glob("findoc-*") if p.resolve() != ROOT]


def audit(event, args):
    if event == "socket.connect":
        raise RuntimeError("D29-D contract tests forbid network/service connections")
    if event == "sqlite3.connect" and args[0] != ":memory:":
        raw = args[0]
        if isinstance(raw, str) and raw.startswith("file:"):
            raw = unquote(urlparse(raw).path)
        path = Path(raw).resolve()
        if not path.is_relative_to(run):
            raise RuntimeError("D29-D tests refuse SQLite outside fresh regression root")
        connections.add(str(path))
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        path = Path(os.fsdecode(args[0])).resolve()
        if any(path.is_relative_to(p) for p in protected) or path.is_relative_to(ROOT / "data/d28"):
            raise RuntimeError("D29-D tests refuse protected or live runtime access")


sys.addaudithook(audit)
tempfile.tempdir = str(run)
os.environ.update(
    TMPDIR=str(run),
    FINDOC_RUNTIME_ROOT=str(run / "runtime"),
    FINDOC_E2E_DISABLE_ENV_FILES="1",
    TIKTOKEN_CACHE_DIR=str(run / "tokenizer-cache"),
)
for key in list(os.environ):
    if key.startswith("LLM_") or key in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
        del os.environ[key]
report_seed_info = None
if reports_only:
    import shutil
    import sqlite3
    seed = Path(os.environ["D29_D_REPORT_SEED"]).resolve()
    record = json.loads((seed / "record.json").read_text())
    assert record["exit_code"] == 0 and record["servers_stopped"] and record["simulated_test"]
    source = Path(record["runtime_root"]).resolve()
    assert source.name.startswith("findoc-d11-d29-d-native-")
    fixture = run / "findoc-d11-d22-seed"
    fixture.mkdir()
    source_copy = run / "native-source-copy.db"
    shutil.copy2(source / "documents.db", source_copy)
    shutil.copytree(source / "objects", fixture / "objects")
    source_db_sha = hashlib.sha256((source / "documents.db").read_bytes()).hexdigest()
    # Build a NEW test DB from the same schema and non-report rows. Never delete
    # immutable report history, disable triggers, or change the stopped source.
    report_tables = ("report_fact_refs", "report_source_refs", "report_operations", "report_revisions", "reports")
    with sqlite3.connect(f"file:{source_copy}?mode=ro", uri=True) as snapshot, sqlite3.connect(fixture / "documents.db") as connection:
        rows = snapshot.execute("SELECT confirmation_kind FROM financial_acceptance_receipts").fetchall()
        assert rows and all(r[0] == "simulated_test" for r in rows)
        names = [r[0] for r in snapshot.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        def hashes(conn):
            return {n: hashlib.sha256(json.dumps(sorted(conn.execute(f'SELECT * FROM "{n}"').fetchall(), key=str), default=str).encode()).hexdigest() for n in names if n not in report_tables}
        before = hashes(snapshot)
        sql = [line for line in snapshot.iterdump() if not any(line.startswith(f'INSERT INTO "{n}"') for n in report_tables)]
        connection.executescript("\n".join(sql))
        assert before == hashes(connection)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        source_triggers = snapshot.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name").fetchall()
        assert source_triggers == connection.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name").fetchall()
        report_seed_info = dict(seed=str(seed), source_db_sha256=source_db_sha,
                                simulated_receipts=len(rows), unchanged_non_report_tables=before,
                                omitted_report_rows_in_new_db_only=list(report_tables),
                                identical_immutable_triggers=True)
    proof = run / "report-proof.json"
    journey = json.loads((seed / "native-integration-proof.json").read_text())
    proof.write_text(json.dumps({"runtime_root": str(fixture), "cases": [{"result": {"task_id": journey["proof"][0]["task"]}}]}))
    os.environ["FINDOC_REPORT_TEST_PROOF"] = str(proof)
import pytest  # noqa: E402

files = [
    "tests/test_d29_c1_answer_focus.py",
    "tests/test_d29_c1_focus_api.py",
    "tests/test_d26_calculation_intent.py",
    "tests/test_d29_acceptance_discovery.py",
    "tests/test_d18_templates.py",
    "tests/test_d21_research.py",
    "tests/test_d11_financial_analysis.py",
    "tests/test_d13_company_comparison.py",
    "tests/test_financial_reviews.py",
    "tests/test_d10_financial_facts.py",
    "tests/test_d16_qa.py",
    "tests/test_d17_history.py",
    "tests/test_d19_tasks.py",
    "tests/test_d26_no_retry.py",
    "tests/test_d26_real_sources.py",
    "tests/test_d26_table_structure.py",
    "tests/test_d27_quality.py",
]
if reports_only:
    files = ["tests/test_d22_reports.py", "tests/test_d23_reports.py"]
if "--preflight-only" in sys.argv:
    files = ["tests/test_d18_templates.py::test_four_real_reports_preflight_readonly_no_human_acceptance"]
args = [
    "-q",
    "-p",
    "no:cacheprovider",
    "--basetemp",
    str(run / "pytest"),
    "--junitxml",
    str(out / "backend-junit.xml"),
    *files,
]
code = int(pytest.main(args))
if reports_only:
    assert hashlib.sha256((source / "documents.db").read_bytes()).hexdigest() == source_db_sha
(out / "backend-isolation.json").write_text(
    json.dumps(
        dict(
            root=str(run),
            report_seed=report_seed_info,
            exit_code=code,
            test_files=files,
            network_blocked=True,
            sqlite_paths=sorted(connections),
            all_sqlite_under_fresh_root=True,
            live_root_access_blocked=True,
            other_worktrees_access_blocked=True,
            confirmation_kind="simulated_test",
            human_acceptances=0,
            runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
        indent=2,
    )
    + "\n"
)
sys.exit(code)
