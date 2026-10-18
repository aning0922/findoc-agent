"""D7 local isolation/protection evidence; run from the product worktree."""

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

product = Path.cwd().resolve()
if product.resolve() != Path(__file__).resolve().parent.parent:
    raise RuntimeError("Run D7 validation from the product worktree cwd")
source = product.parent / "findoc-rag"
test_root = Path(tempfile.mkdtemp(prefix="findoc-d7-")).resolve()
sqlite_paths = set()


def audit(event, args):
    if event == "sqlite3.connect":
        raw = args[0]
        if raw != ":memory:":
            path = Path(raw).resolve()
            if not path.is_relative_to(test_root):
                raise RuntimeError(f"D7 isolation rejected SQLite path: {path}")
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
            raise RuntimeError(f"D7 isolation rejected write: {path}")


sys.addaudithook(audit)
os.environ["TMPDIR"] = str(test_root)
os.environ["FINDOC_RUNTIME_ROOT"] = str(test_root / "runtime")
# Keep all persistent test fixtures beneath the same new temporary root.
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
print(f"D7 product cwd: {product}\nD7 isolated test root: {test_root}", flush=True)
code = int(pytest.main(args))
proofs = [json.loads(p.read_text()) for p in sorted(test_root.rglob("d7-report-proof.json"))]
if proofs:
    reports = []
    results = []
    for proof in proofs:
        results += proof.pop("results")
        proof["source"].pop("evidence_ids")
        reports.append(proof)
    output = dict(
        reports=reports,
        results=results,
        summary=dict(
            benchmark_count=len(results),
            successes=sum(r["success"] for r in results),
            main_count=sum("2025:" in r["id"] for r in results),
            main_successes=sum(r["success"] and "2025:" in r["id"] for r in results),
        ),
        boundaries=[
            "Real fast PDF parser, SQLite, ObjectStore and HTTP sources/candidates",
            "Controlled embedding/index/chunk segmentation; no actual RAG/LLM or human acceptance",
        ],
    )
    (product / "product/validation/d7-real-reports.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n"
    )
if code == 0 and files == ["tests"]:
    assert len(proofs) == 4, "Full D7 regression requires all four originals"
    assert len(results) == 18 and all(r["success"] for r in results)
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
(product / "data/30d-foundation/d7-test-isolation.json").write_text(
    json.dumps(report, indent=2) + "\n"
)
sys.exit(code)
