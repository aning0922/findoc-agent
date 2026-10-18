"""Capture actual regression exit code; retain bulky logs only in ignored local data."""
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
os.chdir(root)
command = [sys.executable, "scripts/run_d19_regression.py", *sys.argv[1:]]
name = "targeted" if sys.argv[1:] else "python"
log = root / f"data/30d-foundation/d19-{name}-final.log"
with log.open("w") as output:
    code = subprocess.run(command, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                          stdout=output, stderr=subprocess.STDOUT).returncode
record = dict(command=command, exit_code=code, local_log=str(log.relative_to(root)))
(root / f"data/30d-foundation/d19-{name}-exit.json").write_text(json.dumps(record, indent=2))
print(json.dumps(record))
print(log.read_text()[-5000:])
sys.exit(code)
