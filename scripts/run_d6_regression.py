"""D6 local isolation/protection evidence; run from the product worktree."""

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

product = Path.cwd().resolve()
if product.resolve() != Path(__file__).resolve().parent.parent:
    raise RuntimeError("Run D6 validation from the product worktree cwd")
source = product.parent / "findoc-rag"
test_root = Path(tempfile.mkdtemp(prefix="findoc-d6-")).resolve()
sqlite_paths = set()


def audit(event, args):
    if event == "sqlite3.connect":
        raw = args[0]
        if raw != ":memory:":
            path = Path(raw).resolve()
            if not path.is_relative_to(test_root):
                raise RuntimeError(f"D6 isolation rejected SQLite path: {path}")
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
            raise RuntimeError(f"D6 isolation rejected write: {path}")


sys.addaudithook(audit)
os.environ["TMPDIR"] = str(test_root)
os.environ["FINDOC_RUNTIME_ROOT"] = str(test_root / "runtime")
# Keep all persistent test fixtures beneath the same new temporary root.
import pytest  # noqa: E402

files = [
    "tests/test_document_sources.py",
    "tests/test_document_service.py",
    "tests/test_parse.py",
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
print(f"D6 product cwd: {product}\nD6 isolated test root: {test_root}", flush=True)
code = int(pytest.main(args))
proofs = [json.loads(p.read_text()) for p in sorted(test_root.rglob("report-proof.json"))]
if code == 0:
    assert len(proofs) == 4, (
        "D6 acceptance requires all four original local PDFs (no skipped originals)"
    )
    batch_paths = {item.pop("batch_database") for item in proofs}
    assert len(batch_paths) == 1, "Import all four originals into the same isolated workspace DB"
    assert len({item["company_id"] for item in proofs}) == 2
    import sqlite3
    from contextlib import closing

    with closing(sqlite3.connect(next(iter(batch_paths)))) as conn:
        batch_checks = dict(
            integrity=conn.execute("PRAGMA integrity_check").fetchone()[0],
            foreign_key_violations=conn.execute("PRAGMA foreign_key_check").fetchall(),
            document_count=conn.execute("SELECT count(*) FROM documents").fetchone()[0],
            source_count=conn.execute("SELECT count(*) FROM document_sources").fetchone()[0],
            evidence_count=conn.execute("SELECT count(*) FROM document_evidence").fetchone()[0],
            migration_versions=[
                r[0] for r in conn.execute("SELECT version FROM analyst_schema_migrations")
            ],
        )
    assert batch_checks["integrity"] == "ok" and not batch_checks["foreign_key_violations"]
    assert batch_checks["document_count"] == batch_checks["source_count"] == 4
    (product / "product/validation/d6-real-reports.json").write_text(
        json.dumps(dict(reports=proofs, batch_checks=batch_checks), indent=2, ensure_ascii=False)
        + "\n"
    )
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
(product / "data/30d-foundation/d6-test-isolation.json").write_text(
    json.dumps(report, indent=2) + "\n"
)
sys.exit(code)
