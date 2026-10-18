"""D20 regression with real originals, actual SQLite and audited isolated writes."""

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

product = Path.cwd().resolve()
if product != Path(__file__).resolve().parent.parent:
    raise RuntimeError("Run from the Analyst product cwd")
source = product.parent / "findoc-rag"
original_product = product.parent / "findoc-v1-product-design"
test_root = Path(tempfile.mkdtemp(prefix="findoc-d20-")).resolve()
sqlite_paths = set()


def audit(event, args):
    if event == "sqlite3.connect" and args[0] != ":memory:":
        path = Path(args[0]).resolve()
        if not path.is_relative_to(test_root):
            raise RuntimeError(f"D20 rejected SQLite path: {path}")
        sqlite_paths.add(str(path))
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        path = Path(os.fsdecode(args[0])).resolve()
        mode, flags = args[1], args[2]
        writes = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
            isinstance(flags, int)
            and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        )
        if writes and any(
            path.is_relative_to(root)
            for root in (
                source,
                original_product,
                product / "data/runtime",
            )
        ):
            raise RuntimeError(f"D20 rejected protected write: {path}")


sys.addaudithook(audit)
os.environ["TMPDIR"] = str(test_root)
os.environ["FINDOC_RUNTIME_ROOT"] = str(test_root / "runtime")
import pytest  # noqa: E402

files = sys.argv[1:] or ["tests"]
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
print(f"D20 cwd: {product}\nD20 isolated root: {test_root}", flush=True)
code = int(pytest.main(args))
report = dict(
    test_root=str(test_root),
    cwd=str(product),
    python=sys.executable,
    python_version=sys.version.split()[0],
    pytest_args=args,
    exit_code=code,
    sqlite_path_count=len(sqlite_paths),
    all_sqlite_paths_under_test_root=all(Path(p).is_relative_to(test_root) for p in sqlite_paths),
    sqlite_paths=sorted(sqlite_paths),
    source_write_guard=True,
    original_product_write_guard=True,
    default_runtime_write_guard=True,
    runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
)
(product / ("data/30d-foundation/d20-test-isolation.json" if files == ["tests"]
            else "data/30d-foundation/d20-targeted-isolation.json")).write_text(
    json.dumps(report, indent=2) + "\n"
)
for filename in ("d20-four-pdf-proof.json",):
    proofs = [json.loads(p.read_text()) for p in test_root.rglob(filename)]
    if proofs:
        (product / "product/validation" / (filename if files == ["tests"]
                                         else filename.replace("d20-", "d20-targeted-"))).write_text(
            json.dumps(proofs, indent=2, ensure_ascii=False) + "\n"
        )
sys.exit(code)
