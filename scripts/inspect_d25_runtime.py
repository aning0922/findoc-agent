"""Read-only D25 human-operation audit; never sends a POST or saves business data."""

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument("--label", required=True)
args = parser.parse_args()
if not re.fullmatch(r"[a-z0-9-]{1,80}", args.label):
    raise ValueError("Use a plain audit label")
session = json.loads((root / "data/d25/session.json").read_text())
runtime = Path(session["runtime_root"]).resolve()
if runtime != (root / "data/d25/runtime").resolve():
    raise RuntimeError("Refusing any other runtime")
database = runtime / "documents.db"
before = hashlib.sha256(database.read_bytes()).hexdigest()
tables = ["companies", "documents", "report_document_metadata", "document_sources",
          "report_source_origins", "report_binding_corrections", "index_publications",
          "financial_acceptance_receipts", "financial_acceptance_revocations",
          "financial_fact_sets", "confirmed_financial_facts", "template_tasks",
          "template_operations", "template_checkpoints", "research_runs", "reports",
          "report_revisions", "report_operations"]
with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
    connection.row_factory = sqlite3.Row
    connection.execute("BEGIN")
    rows = {name: [dict(row) for row in connection.execute(f'SELECT * FROM "{name}"')]
            for name in tables}
after = hashlib.sha256(database.read_bytes()).hexdigest()
for document in rows["documents"]:
    path = (runtime / "objects" / document["object_key"]).resolve()
    if not path.is_relative_to((runtime / "objects").resolve()):
        raise RuntimeError("Invalid object path")
    document["actual_object_sha256"] = (
        hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    )
receipts = rows["financial_acceptance_receipts"]
log_path = root / "data/d25/logs/execution.jsonl"
events = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
record = dict(at=datetime.now(timezone.utc).isoformat(), label=args.label,
              session=session, database_sha_before=before, database_sha_after=after,
              no_business_writes_by_auditor=True, sqlite_transaction_read_only=True,
              database_bytes_unchanged_during_read=before == after,
              counts={name: len(values) for name, values in rows.items()},
              local_operator_receipts=sum(x["confirmation_kind"] == "local_operator"
                                          for x in receipts),
              simulated_receipts=sum(x["confirmation_kind"] == "simulated_test"
                                     for x in receipts),
              execution_log_sha256=hashlib.sha256(log_path.read_bytes()).hexdigest(),
              execution_events=len(events), rows=rows)
out = root / "data/d25/audits"
out.mkdir(exist_ok=True)
path = out / f"{time.time_ns()}-{args.label}.json"
def serialize_blob(value):
    if isinstance(value, bytes):
        return dict(sqlite_blob_base64=base64.b64encode(value).decode("ascii"),
                    bytes=len(value), sha256=hashlib.sha256(value).hexdigest())
    raise TypeError(f"Unsupported audit value type: {type(value).__name__}")


path.write_text(json.dumps(record, ensure_ascii=False, indent=2, default=serialize_blob) + "\n")
print(json.dumps(dict(path=str(path), counts=record["counts"],
                      local_operator_receipts=record["local_operator_receipts"],
                      simulated_receipts=record["simulated_receipts"],
                      database_bytes_unchanged_during_read=before == after)))
