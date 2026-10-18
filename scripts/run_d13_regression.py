"""D13 regression with real originals, actual SQLite and audited isolated writes."""

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
test_root = Path(tempfile.mkdtemp(prefix="findoc-d11-")).resolve()
sqlite_paths = set()


def audit(event, args):
    if event == "sqlite3.connect" and args[0] != ":memory:":
        path = Path(args[0]).resolve()
        if not path.is_relative_to(test_root):
            raise RuntimeError(f"D13 rejected SQLite path: {path}")
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
            raise RuntimeError(f"D13 rejected protected write: {path}")


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
print(f"D13 cwd: {product}\nD13 isolated root: {test_root}", flush=True)
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
(product / "data/30d-foundation/d13-test-isolation.json").write_text(
    json.dumps(report, indent=2) + "\n"
)
proofs = [json.loads(p.read_text()) for p in sorted(test_root.rglob("d11-analysis-proof.json"))]
if proofs:
    (product / "product/validation/d13-real-analyses.json").write_text(
        json.dumps(
            dict(
                reports=proofs,
                human_acceptance="pending",
                confirmation_kind="simulated_test",
                production_api_accepts_simulation=False,
                boundaries=[
                    "Real original PDF/parser/ObjectStore/SQLite/HTTP fact creation",
                    "Isolated test application service calculation; production HTTP rejects simulation",
                    "Controlled embedding/index/chunk IDs; no actual RAG/LLM or human acceptance",
                ],
            ),
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
comparison_proofs = [
    json.loads(p.read_text()) for p in test_root.rglob("d13-comparison-proof.json")
]
if comparison_proofs:
    (product / "product/validation/d13-real-comparisons.json").write_text(
        json.dumps(
            dict(
                reports=comparison_proofs,
                human_acceptance="pending",
                confirmation_kind="simulated_test",
                production_api_accepts_simulation=False,
            ),
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
if code == 0 and files == ["tests"]:
    assert len(proofs) == 2 and sum(len(p["analyses"]) for p in proofs) == 6
    for pattern in ("d7-report-proof.json", "d9-review-proof.json", "d10-fact-proof.json"):
        old_proofs = [json.loads(p.read_text()) for p in test_root.rglob(pattern)]
        assert len(old_proofs) == 4 and sum(len(p["results"]) for p in old_proofs) == 18
sys.exit(code)
