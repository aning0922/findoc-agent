"""Append-only command evidence: each invocation has its own raw log and exit code."""

import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

root = Path(__file__).resolve().parent.parent
name, *command = sys.argv[1:]
folder = (root / os.environ.get("D20_COMMAND_LOG_ROOT", "data/30d-foundation/d20-commands")).resolve()
folder.mkdir(exist_ok=True, parents=True)
identity = f"{time.time_ns()}-{name}-{uuid.uuid4().hex[:6]}"
log = folder / f"{identity}.log"
env = dict(
    os.environ,
    PYTHONDONTWRITEBYTECODE="1",
    GIT_OPTIONAL_LOCKS="0",
    OMP_NUM_THREADS="1",
    MKL_NUM_THREADS="1",
    VECLIB_MAXIMUM_THREADS="1",
    HF_HUB_OFFLINE="1",
)
env["PATH"] = "/Users/aipuli/.nvm/versions/node/v24.19.0/bin:" + env["PATH"]
start = time.monotonic()
with log.open("xb") as output:
    code = subprocess.run(
        command, cwd=root, env=env, stdout=output, stderr=subprocess.STDOUT
    ).returncode
record = dict(
    name=name,
    command=command,
    exit_code=code,
    seconds=time.monotonic() - start,
    log=str(log.relative_to(root)),
)
(folder / f"{identity}.json").write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps(record))
print(log.read_text(errors="replace")[-18000:])
sys.exit(code if code >= 0 else 128 - code)
