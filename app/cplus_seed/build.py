"""Add root-approved official PDFs to a fresh materialized seed; original never mutated."""

from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3
import tarfile
import tempfile

from app.demo.seed import verify_seed, materialize, sha256, identifier
from app.showcase_seed.build import sqlite_spec, probe_index, reject_grants
from app.public_pdf_cache.broker import cover_identity
from app.public_pdf_cache.download import validate_url, MAX_BYTES
from .pipeline import real_pipeline

BASE_MANIFEST_SHA = "efc10a4b48584747130af71ec82171a4e5f766fc53eb1ea92c21fe319e7b3ff4"
DATABASES = {
    "documents.db",
    "parse-v2.db",
    "finance-v2.db",
    "research-memory.db",
    "showcase-archive.db",
}
BASE_JSON = {"seed-inventory.json", "cplus-seed-inventory.json"}
FIELDS = {
    "path",
    "sha256",
    "source_url",
    "security_code",
    "exchange",
    "report_year",
    "official_name",
}


def validate_inputs(items):
    if not isinstance(items, list) or not 1 <= len(items) <= 2:
        raise ValueError("one_or_two_explicit_public_inputs_required")
    verified = []
    for item in items:
        if not isinstance(item, dict) or set(item) != FIELDS:
            raise ValueError("invalid_input_manifest_fields")
        validate_url(item["source_url"])
        path = Path(item["path"])
        if (
            not path.is_absolute()
            or any(p.is_symlink() for p in [path, *path.parents])
            or not path.is_file()
            or path.stat().st_nlink != 1
        ):
            raise ValueError("input_requires_plain_absolute_pdf")
        if path.stat().st_size > MAX_BYTES or sha256(path) != item["sha256"]:
            raise ValueError("input_sha_or_size_mismatch")
        raw = path.read_bytes()
        if not raw.startswith(b"%PDF-"):
            raise ValueError("input_not_pdf")
        candidate = dict(
            security_identity=dict(
                supported=True, security_code=item["security_code"], exchange=item["exchange"]
            ),
            kind="annual_fulltext",
            language="zh",
            report_year=item["report_year"],
        )
        resolved = cover_identity(raw, candidate)
        if resolved["official_name"] != item["official_name"]:
            raise ValueError("input_cover_name_mismatch")
        verified.append((dict(item), raw))
    if len({i["sha256"] for i, _ in verified}) != len(verified):
        raise ValueError("duplicate_addition")
    return verified


def allowed_file(name):
    return (
        name in DATABASES | BASE_JSON
        or name.startswith("objects/documents/")
        and name.endswith(".pdf")
        or name.startswith("milvus.db/")
    )


def operation_snapshot(root):
    """Only hashes are retained: inherited public operations may remain, no new ones."""
    result = {}
    for name in DATABASES:
        path = root / name
        if not path.is_file():
            continue
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            tables = [
                r[0]
                for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
                if "operation" in r[0].lower()
            ]
            for table in tables:
                rows = db.execute(
                    "SELECT * FROM " + identifier(table) + " ORDER BY rowid"
                ).fetchall()
                if rows:
                    result[name + ":" + table] = (
                        __import__("hashlib").sha256(repr(rows).encode()).hexdigest()
                    )
    return result


async def build_additive_seed(
    base,
    destination,
    items,
    *,
    bundle_path=None,
    pipeline_factory=real_pipeline,
    index_probe=probe_index,
    test_mode=False,
):
    base = Path(base)
    target = Path(destination)
    if (
        any(p.is_symlink() for p in target.parents)
        or target.resolve().is_relative_to(base.resolve())
        or any(p.name == "active" for p in target.parents)
    ):
        raise ValueError("unsafe_seed_destination")
    if bundle_path is not None:
        bundle = Path(bundle_path)
        if (
            any(p.is_symlink() for p in bundle.parents)
            or bundle.resolve().is_relative_to(base.resolve())
            or any(p.name == "active" for p in bundle.parents)
        ):
            raise ValueError("unsafe_bundle_destination")
    if target.exists() or target.is_symlink():
        raise FileExistsError("seed_destination_must_be_new")
    if bundle_path is not None and (Path(bundle_path).exists() or Path(bundle_path).is_symlink()):
        raise FileExistsError("bundle_destination_must_be_new")
    if not test_mode and (pipeline_factory is not real_pipeline or index_probe is not probe_index):
        raise ValueError("test_ports_cannot_create_real_seed")
    manifest, base_sha = verify_seed(base, None if test_mode else BASE_MANIFEST_SHA)
    if any(not allowed_file(e["path"]) for e in manifest["files"]):
        raise ValueError("base_file_not_allowlisted")
    verified = validate_inputs(items)
    inherited_operations = operation_snapshot(base)
    with closing(
        sqlite3.connect((base.resolve() / "documents.db").as_uri() + "?mode=ro", uri=True)
    ) as db:
        existing_sha = {r[0] for r in db.execute("SELECT content_sha256 FROM documents")}
    if any(item["sha256"] in existing_sha for item, _ in verified):
        raise ValueError("addition_already_in_base_seed")
    before = {e["path"]: sha256(base / e["path"]) for e in manifest["files"]}
    with tempfile.TemporaryDirectory(prefix="findoc-cplus-additive-owned-") as temporary:
        owned = Path(temporary)
        runtime = owned / "materialized"
        materialize(base, runtime, base_sha)
        reject_grants(runtime)
        added = []
        # Private temp created here, no forged stop markers or borrowed active runtime.
        with pipeline_factory(runtime) as pipeline:
            for item, raw in verified:
                identity = await pipeline.add(item, raw)
                if (
                    identity.get("content_sha256") != item["sha256"]
                    or identity.get("basis") != "unknown"
                ):
                    raise ValueError("pipeline_identity_mismatch")
                added.append(
                    dict(input={k: v for k, v in item.items() if k != "path"}, source=identity)
                )
        if operation_snapshot(runtime) != inherited_operations:
            raise ValueError("new_or_changed_operations_forbidden")
        # All writer contexts have exited before inventory/probe/backup; this is actual owned closure.
        reject_grants(runtime)
        for p in runtime.rglob("*"):
            if p.is_symlink() or p.is_file() and p.stat().st_nlink != 1:
                raise ValueError("unsafe_materialized_link")
            if p.is_file() and p.name.endswith(("-wal", "-shm", "-journal")):
                raise ValueError("writer_sidecar_remains")
            rel = p.relative_to(runtime).as_posix()
            if p.is_file() and rel != ".demo-manifest.json" and not allowed_file(rel):
                raise ValueError("unexpected_runtime_file:" + rel)
        vectors = index_probe(runtime / "milvus.db")  # probe opens/then closes its own client.
        if not vectors and not test_mode:
            raise ValueError("vector_inventory_missing")
        frozen = owned / "frozen"
        frozen.mkdir()
        for name in DATABASES:
            if (runtime / name).is_file():
                with (
                    closing(
                        sqlite3.connect((runtime / name).as_uri() + "?mode=ro", uri=True)
                    ) as src,
                    closing(sqlite3.connect(frozen / name)) as dst,
                ):
                    src.backup(dst)
        for name in ["objects", "milvus.db"]:
            if (runtime / name).exists():
                shutil.copytree(runtime / name, frozen / name)
        for name in BASE_JSON:
            if (runtime / name).is_file():
                shutil.copyfile(runtime / name, frozen / name)
        if (base / "showcase-archive.db").is_file() and sha256(
            base / "showcase-archive.db"
        ) != sha256(frozen / "showcase-archive.db"):
            # SQLite backup can change physical encoding; require exact stored rows instead.
            def rows(path):
                with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
                    return db.execute(
                        "SELECT * FROM archive_items ORDER BY archive_id,revision"
                    ).fetchall()

            if rows(base.resolve() / "showcase-archive.db") != rows(frozen / "showcase-archive.db"):
                raise ValueError("original_archive_changed")
        inventory = dict(
            schema_version="cplus-additive-seed-v2",
            data_origin="preset_demo",
            base_manifest_sha256=base_sha,
            additions=added,
            owned_writers_closed=True,
            new_operation_rows=0,
            new_provider_calls=0,
            human_financial_approvals=0,
            test_substitutions=test_mode,
        )
        (frozen / "cplus-seed-inventory.json").write_text(
            json.dumps(inventory, ensure_ascii=False, indent=2) + "\n"
        )
        output = {
            **manifest,
            "seed_version": "showcase-cplus-seed-v2",
            "data_origin": "preset_demo",
            "complete_product_seed": False if test_mode else manifest["complete_product_seed"],
            "files": [
                dict(path=p.relative_to(frozen).as_posix(), sha256=sha256(p))
                for p in sorted(frozen.rglob("*"))
                if p.is_file()
            ],
            "sqlite": [
                sqlite_spec(frozen / n, frozen) for n in sorted(DATABASES) if (frozen / n).is_file()
            ],
            "vector_indexes": vectors,
        }
        (frozen / "manifest.json").write_text(
            json.dumps(output, ensure_ascii=False, indent=2) + "\n"
        )
        for p in sorted(frozen.rglob("*"), reverse=True):
            p.chmod(0o500 if p.is_dir() else 0o400)
        frozen.chmod(0o500)
        _, new_sha = verify_seed(frozen)
        # Exclusive destination creation; no overwrite, no export of staging/control files.
        shutil.copytree(frozen, target)
        verify_seed(target, new_sha)
        if (
            before != {e["path"]: sha256(base / e["path"]) for e in manifest["files"]}
            or sha256(base / "manifest.json") != base_sha
        ):
            raise ValueError("original_seed_changed")
    result = dict(
        seed_root=str(target), manifest_sha256=new_sha, base_unchanged=True, inventory=inventory
    )
    if bundle_path is not None:
        with Path(bundle_path).open("xb") as stream:
            with tarfile.open(fileobj=stream, mode="w:gz") as archive:
                archive.add(target, arcname="showcase-cplus-seed-v2")
        result["bundle_sha256"] = sha256(Path(bundle_path))
        result["bundle_path"] = str(bundle_path)
    return result
