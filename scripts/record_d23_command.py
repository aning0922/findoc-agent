"""Capture each validation exit independently without overwriting earlier failures."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

root = Path(__file__).resolve().parent.parent
out = root / "data/30d-foundation/d23-commands"
out.mkdir(exist_ok=True)
name = sys.argv[1]
command = sys.argv[2:]
log = out / f"{time.time_ns()}-{name}.log"
started = time.monotonic()
with log.open("x") as stream:
    result = subprocess.run(
        command,
        cwd=root,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        stdout=stream,
        stderr=subprocess.STDOUT,
    )
entry = dict(
    name=name,
    command=command,
    exit_code=result.returncode,
    seconds=time.monotonic() - started,
    log=str(log.relative_to(root)),
    sha256=hashlib.sha256(log.read_bytes()).hexdigest(),
)
(out / f"{log.stem}.json").write_text(json.dumps(entry, indent=2) + "\n")
print(json.dumps(entry))
print(log.read_text()[-2000:])
sys.exit(result.returncode)
