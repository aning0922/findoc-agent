"""Restart the isolated browser server and read facts by known receipt IDs only."""

from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from urllib.request import urlopen

from app.agent.sqlite_financial_facts import SQLiteRevenueConfirmationRepository

product = Path.cwd().resolve()
root = Path((product / "data/30d-foundation/d10-runtime-path.txt").read_text()).resolve()
if not root.name.startswith("findoc-d10-") or root.is_relative_to(product):
    raise RuntimeError("Only an isolated D10 browser runtime can be restarted")
database = root / "documents.db"
repo = SQLiteRevenueConfirmationRepository(database)
with closing(sqlite3.connect(database)) as c:
    tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    before = {
        table: c.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall() for table in tables
    }
    ids = c.execute(
        "SELECT receipt_id, confirmation_kind FROM financial_fact_sets ORDER BY receipt_id"
    ).fetchall()
assert ids and {kind for _, kind in ids} == {"simulated_test"}
expected = {
    receipt_id: repo.load_financial_facts(
        workspace_id="demo", receipt_id=receipt_id, confirmation_kind=kind, include_invalid=True
    ).to_payload()
    for receipt_id, kind in ids
}
env = dict(
    os.environ,
    PYTHONDONTWRITEBYTECODE="1",
    FINDOC_D10_RUNTIME_ROOT=str(root),
    FINDOC_D10_ALLOW_REOPEN="1",
)
log = product / "product/validation/test-logs/d10-api-restart.log"
if (
    subprocess.run(
        ["lsof", "-nP", "-iTCP:18083", "-sTCP:LISTEN"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode
    == 0
):
    raise RuntimeError("D10 restart port is occupied")
with log.open("w") as output:
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "tests.support.real_financial_facts_app:create_real_financial_facts_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            "18083",
        ],
        env=env,
        stdout=output,
        stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                with urlopen("http://127.0.0.1:18083/health", timeout=1) as response:
                    assert response.status == 200
                break
            except Exception:
                if server.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("D10 restart startup failed; inspect log")
                time.sleep(0.2)
        results = []
        for receipt_id, kind in ids:
            with urlopen(
                f"http://127.0.0.1:18083/financial-facts/persisted/{receipt_id}?include_invalid=true",
                timeout=10,
            ) as response:
                actual = json.load(response)
            assert actual == expected[receipt_id]
            if actual["current_valid"]:
                with urlopen(
                    f"http://127.0.0.1:18083/financial-facts/acceptances/{receipt_id}", timeout=10
                ) as response:
                    accepted = json.load(response)
                assert (
                    accepted
                    == repo.acceptance_by_id(
                        workspace_id="demo", receipt_id=receipt_id, confirmation_kind=kind
                    ).to_payload()
                )
            results.append(
                dict(
                    receipt_id=receipt_id,
                    kind=kind,
                    count=len(actual["facts"]),
                    current_valid=actual["current_valid"],
                    evidence_and_snapshot_equal=True,
                )
            )
    finally:
        server.terminate()
        server.wait(timeout=10)
with closing(sqlite3.connect(database)) as c:
    after = {
        table: c.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall() for table in tables
    }
    counts = {table: len(rows) for table, rows in after.items()}
assert before == after
proof = dict(
    runtime=str(root),
    server_restarted=True,
    queries="GET by previously known receipt ID only",
    no_seed_no_extraction=True,
    all_database_rows_unchanged=True,
    results=results,
    counts=counts,
    human_acceptance="pending",
    automated_kind="simulated_test",
    local_operator_receipts=0,
)
(product / "product/validation/d10-browser-restart-results.json").write_text(
    json.dumps(proof, indent=2, ensure_ascii=False) + "\n"
)
print(json.dumps(proof, indent=2, ensure_ascii=False))
