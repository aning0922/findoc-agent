"""Capture every D15 quality command's actual return code, including failures."""
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
os.chdir(root)
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
env["PATH"] = "/Users/aipuli/.nvm/versions/node/v24.19.0/bin:" + env["PATH"]
python = str(root.parent / "findoc-rag/.venv/bin/python")
commands = {
    "build": ["npm", "--prefix", "frontend", "run", "build"],
    "frontend": ["npm", "--prefix", "frontend", "test"],
    "lint": ["npm", "--prefix", "frontend", "run", "lint"],
    "ruff": [python, "-m", "ruff", "check", "app", "tests", "scripts"],
    "mypy": [python, "-m", "mypy", "app"],
    "diff": ["git", "diff", "--check"],
}
results = []
for name, command in commands.items():
    log = root / f"product/validation/test-logs/d15-{name}.log"
    with log.open("w") as output:
        code = subprocess.run(command, env=env, stdout=output, stderr=subprocess.STDOUT).returncode
    results.append(dict(name=name, command=command, exit_code=code, log=str(log.relative_to(root))))
    print(name, code, flush=True)
(root / "product/validation/d15-checks.json").write_text(json.dumps(results, indent=2) + "\n")
sys.exit(int(any(r["exit_code"] for r in results)))
