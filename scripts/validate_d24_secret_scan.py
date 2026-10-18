"""Scan tracked/non-ignored workspace files; secret values never printed or persisted."""

import json
from pathlib import Path
import subprocess
from dotenv import dotenv_values

root = Path(__file__).resolve().parent.parent
values = [
    v.encode()
    for k, v in dotenv_values(root.parent / "findoc-rag/.env").items()
    if v and (k.endswith("API_KEY") or k.endswith("TOKEN") or k.endswith("SECRET")) and len(v) >= 8
]
files = [
    p
    for p in subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root
    )
    .decode()
    .split("\0")
    if p
]
matched = [
    p for p in files if (root / p).is_file() and any(s in (root / p).read_bytes() for s in values)
]
assert not matched
(root / "product/validation/d24-secret-scan.json").write_text(
    json.dumps(
        dict(
            files_scanned=len(files),
            secret_values_loaded_in_memory_only=True,
            matched_files=matched,
        ),
        indent=2,
    )
    + "\n"
)
print("Secret scan: zero matches")
