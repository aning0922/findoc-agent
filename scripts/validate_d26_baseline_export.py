"""Prove pre-D26 GET-only factory lacks export using this run's own saved report."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

product = Path(__file__).resolve().parents[1]
old = json.loads((product / "product/d26/evidence/b-baseline-verified/record.json").read_text())
record = json.loads((product / "product/d26/evidence/b-reports/record.json").read_text())
assert record["servers_stopped"] and record["simulated_test"]
proof = json.loads((product / "product/d26/evidence/b-reports/report-fault-proof.json").read_text())
root = Path(tempfile.mkdtemp(prefix="findoc-d26-baseline-export-")).resolve()
shutil.copy2(Path(record["runtime_root"]) / "documents.db", root / "documents.db")
code = """import json,sys,hashlib\nfrom pathlib import Path\nfrom fastapi.testclient import TestClient\nfrom app.api.report_history import create_report_history_app\ndb=Path(sys.argv[1]);rid=sys.argv[2]\nbefore=hashlib.sha256(db.read_bytes()).hexdigest()\nc=TestClient(create_report_history_app(db))\nassert c.get(f"/reports/{rid}/revisions/1").status_code==200\nr=c.get(f"/reports/{rid}/revisions/1/markdown")\nassert r.status_code==404\nassert hashlib.sha256(db.read_bytes()).hexdigest()==before\nprint(json.dumps(dict(export_status=r.status_code,history_status=200,database_unchanged=True,source_ref="7b3f9ec26a2c82b0b90c76c8152236dc577585e0")))\n"""
result = subprocess.check_output(
    [sys.executable, "-c", code, str(root / "documents.db"), proof["saved"]["report"]["report_id"]],
    cwd=old["root"],
    text=True,
)
(product / "product/d26/evidence/b-export-before.json").write_text(result)
