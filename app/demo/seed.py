"""Immutable manifest seed → a fresh directory; never overwrites a live database."""
from contextlib import closing
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_file(root: Path, relative: str) -> Path:
    parts = PurePosixPath(relative)
    if not relative or parts.is_absolute() or ".." in parts.parts or "\\" in relative or str(parts) != relative:
        raise ValueError("Invalid manifest path")
    candidate = root / relative
    if root.is_symlink() or any(p.is_symlink() for p in [candidate, *candidate.parents]
                                if p == root or root in p.parents):
        raise ValueError("Symlinks are forbidden")
    if root.resolve() not in candidate.resolve().parents or not candidate.is_file():
        raise ValueError("Manifest file missing or outside root")
    if candidate.stat().st_nlink != 1:
        raise ValueError("Hardlinked seed files are forbidden")
    return candidate


def load_manifest(seed: Path, expected_sha: str | None = None) -> tuple[dict, str]:
    manifest_file = safe_file(seed, "manifest.json")
    digest = sha256(manifest_file)
    if expected_sha is not None and digest != expected_sha:
        raise ValueError("Seed manifest changed")
    manifest = json.loads(manifest_file.read_text())
    required = {"schema_version", "seed_version", "data_origin", "complete_product_seed", "files", "sqlite", "preset_task_ids"}
    if set(manifest) - (required | {"vector_indexes"}) or not required.issubset(manifest):
        raise ValueError("Invalid seed manifest fields")
    if manifest["schema_version"] != "demo-seed-v1" or not manifest["seed_version"]:
        raise ValueError("Invalid seed version")
    paths = [f["path"] for f in manifest["files"]]
    if len(set(paths)) != len(paths) or "manifest.json" in paths or not paths:
        raise ValueError("Empty/duplicate seed files")
    # A finalized SQLite backup must not depend on uncheckpointed WAL/journal sidecars.
    if any(p.endswith(("-wal", "-shm", "-journal")) for p in paths):
        raise ValueError("Seed requires a closed, consistent SQLite snapshot")
    return manifest, digest


def verify_seed(seed: Path, expected_sha: str | None = None) -> tuple[dict, str]:
    manifest, digest = load_manifest(seed, expected_sha)
    expected = {f["path"] for f in manifest["files"]} | {"manifest.json"}
    actual = set()
    for path in [seed, *seed.rglob("*")]:
        if path.is_symlink() or path.stat().st_mode & 0o222:
            raise ValueError("Seed must be read-only and contain no symlinks")
        if path.is_file():
            actual.add(path.relative_to(seed).as_posix())
    if actual != expected:
        raise ValueError("Unmanifested/missing seed files")
    for entry in manifest["files"]:
        if set(entry) != {"path", "sha256"} or sha256(safe_file(seed, entry["path"])) != entry["sha256"]:
            raise ValueError("Seed file checksum failed")
    check_sqlite(seed, manifest)
    return manifest, digest


def identifier(value):
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value) is None:
        raise ValueError("Invalid manifest SQLite identifier")
    return '"' + value + '"'


def check_sqlite(root: Path, manifest: dict):
    counts = {}
    for spec in manifest["sqlite"]:
        path = safe_file(root, spec["path"])
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("SQLite integrity check failed")
            tables = {}
            for table, expected in spec["tables"].items():
                count = db.execute(f"SELECT COUNT(*) FROM {identifier(table)}").fetchone()[0]
                if count != expected:
                    raise ValueError("Seed table count mismatch")
                tables[table] = count
            for index in spec["indexes"]:
                identifier(index)
                if not db.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name=?", (index,)).fetchone():
                    raise ValueError("Required SQLite index missing")
        counts[spec["path"]] = tables
    return counts


def verify_materialized(root: Path, manifest: dict):
    """DB files may gain registered migrations, but seeded tables/counts/objects must match."""
    sqlite_paths = {item["path"] for item in manifest["sqlite"]}
    objects = {}
    for entry in manifest["files"]:
        if entry["path"] not in sqlite_paths:
            digest = sha256(safe_file(root, entry["path"]))
            if digest != entry["sha256"]:
                raise ValueError("Materialized object checksum failed")
            objects[entry["path"]] = digest
    return {"sqlite_counts": check_sqlite(root, manifest), "object_hashes": objects}


def materialize(seed: Path, destination: Path, manifest_sha: str):
    manifest, _ = verify_seed(seed, manifest_sha)
    # parents may exist; the generation directory must never have existed before.
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    for entry in manifest["files"]:
        source = safe_file(seed, entry["path"])
        target = destination / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copyfile(source, target, follow_symlinks=False)
        target.chmod(0o600)
        if target.stat().st_nlink != 1 or sha256(target) != entry["sha256"]:
            raise ValueError("Copied seed checksum failed")
    # Child consumes exactly the pinned manifest, never a mutable source path.
    shutil.copyfile(safe_file(seed, "manifest.json"), destination / ".demo-manifest.json")
    (destination / ".demo-manifest.json").chmod(0o400)
    verify_materialized(destination, manifest)
    return manifest


def build_synthetic_seed(destination: Path):
    """Mechanism-only seed: one explicitly fictional company, no PDF/facts/model history."""
    from app.companies.models import CompanyCreate
    from app.companies.sqlite_repository import SQLiteCompanyRepository

    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    repository = SQLiteCompanyRepository(destination / "documents.db")
    repository.create("demo", CompanyCreate(name="合成机制测试企业（非真实资料）", security_code="SYNTHETIC", exchange="DEMO"))
    (destination / "objects").mkdir()
    (destination / "objects" / "mechanism-note.txt").write_text(
        "SYNTHETIC MECHANISM TEST ONLY. No financial facts, PDF, real research or human approvals.\n")
    db_path = destination / "documents.db"
    with closing(sqlite3.connect(db_path)) as db:
        # Existing migration functions were used on this newly created DB, never changed.
        tables = {row[0]: db.execute(f"SELECT COUNT(*) FROM {identifier(row[0])}").fetchone()[0]
                  for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        indexes = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='index'")]
    files = [{"path": path.relative_to(destination).as_posix(), "sha256": sha256(path)}
             for path in sorted(destination.rglob("*")) if path.is_file()]
    manifest = {"schema_version": "demo-seed-v1", "seed_version": "synthetic-mechanism-v1",
                "data_origin": "synthetic_mechanism_only", "complete_product_seed": False,
                "files": files, "sqlite": [{"path": "documents.db", "tables": tables, "indexes": indexes}],
                "preset_task_ids": [], "vector_indexes": []}
    (destination / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    for path in sorted(destination.rglob("*"), reverse=True):
        path.chmod(0o500 if path.is_dir() else 0o400)
    destination.chmod(0o500)
    return verify_seed(destination)
