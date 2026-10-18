"""D5 local isolation/protection evidence; run from the product worktree."""

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

product = Path.cwd().resolve()
if product.resolve() != Path(__file__).resolve().parent.parent:
    raise RuntimeError("Run D5 validation from the product worktree cwd")
source = product.parent / "findoc-rag"
test_root = Path(tempfile.mkdtemp(prefix="findoc-d5-")).resolve()
sqlite_paths = set()


def audit(event, args):
    if event == "sqlite3.connect":
        raw = args[0]
        if raw != ":memory:":
            path = Path(raw).resolve()
            if not path.is_relative_to(test_root):
                raise RuntimeError(f"D5 isolation rejected SQLite path: {path}")
            sqlite_paths.add(str(path))
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        path = Path(os.fsdecode(args[0])).resolve()
        mode, flags = args[1], args[2]
        writes = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
            isinstance(flags, int)
            and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        )
        if writes and (
            path.is_relative_to(source) or path.is_relative_to(product / "data/runtime")
        ):
            raise RuntimeError(f"D5 isolation rejected write: {path}")


sys.addaudithook(audit)
os.environ["TMPDIR"] = str(test_root)
os.environ["FINDOC_RUNTIME_ROOT"] = str(test_root / "runtime")
# Keep all persistent test fixtures beneath the same new temporary root.
import pytest  # noqa: E402

files = [
    "tests/test_companies_api.py",
    "tests/test_companies_migrations.py",
    "tests/test_companies_runtime.py",
    "tests/test_revenue_research_api.py",
    "tests/test_runtime_revenue.py",
    "tests/test_agent_api.py",
    "tests/test_agent_runtime.py",
    "tests/test_runtime_startup.py",
    "tests/test_document_api.py",
    "tests/test_chat_api.py",
    "tests/test_revenue_confirmation.py",
    "tests/test_revenue_extraction.py",
    "tests/test_revenue_graph.py",
    "tests/test_revenue_graph_routing.py",
    "tests/test_finance_tools.py",
    "tests/test_document_preparation.py",
]
args = [
    "-q",
    "-p",
    "no:cacheprovider",
    "--basetemp",
    str(test_root / "pytest"),
    "--junitxml",
    str(test_root / "junit.xml"),
    *files,
]
print(f"D5 product cwd: {product}\nD5 isolated test root: {test_root}", flush=True)
code = int(pytest.main(args))
report = dict(
    test_root=str(test_root),
    python=sys.executable,
    python_version=sys.version.split()[0],
    cwd=str(product),
    pytest_args=args,
    exit_code=code,
    sqlite_path_count=len(sqlite_paths),
    all_sqlite_paths_under_test_root=all(Path(p).is_relative_to(test_root) for p in sqlite_paths),
    sqlite_paths=sorted(sqlite_paths),
    source_write_guard=True,
    default_runtime_write_guard=True,
    runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
)
(product / "data/30d-foundation/d5-test-isolation.json").write_text(
    json.dumps(report, indent=2) + "\n"
)
sys.exit(code)
