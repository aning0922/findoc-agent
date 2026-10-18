"""D29-A dependency/contract regression with fresh temporary SQLite and no network."""

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
run = Path(tempfile.mkdtemp(prefix="findoc-d29-contracts-")).resolve()
out = ROOT / "product/d29-a/evidence/checks"
out.mkdir(parents=True, exist_ok=True)
connections = set()
protected = [p.resolve() for p in ROOT.parent.glob("findoc-*") if p.resolve() != ROOT]


def audit(event, args):
    if event == "socket.connect":
        raise RuntimeError("D29-A contract tests forbid network/service connections")
    if event == "sqlite3.connect" and args[0] != ":memory:":
        raw = args[0]
        if isinstance(raw, str) and raw.startswith("file:"):
            raw = unquote(urlparse(raw).path)
        path = Path(raw).resolve()
        if not path.is_relative_to(run):
            raise RuntimeError(
                "D29-A tests refuse SQLite outside fresh regression root"
            )
        connections.add(str(path))
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        path = Path(os.fsdecode(args[0])).resolve()
        if any(path.is_relative_to(p) for p in protected) or path.is_relative_to(
            ROOT / "data/d28"
        ):
            raise RuntimeError("D29-A tests refuse protected or live runtime access")


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
import pytest  # noqa: E402

files = [
    "tests/test_d29_acceptance_discovery.py",
    "tests/test_d18_templates.py",
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
(out / "backend-isolation.json").write_text(
    json.dumps(
        dict(
            root=str(run),
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
