"""Freeze only closed disposable demo data. Never rebind an archived execution scope."""

from contextlib import closing, contextmanager
import fcntl
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
from uuid import NAMESPACE_URL, uuid5

from app.demo.seed import identifier, sha256, verify_seed
from app.showcase_seed.archive import canonical, digest, digest_text, read_db

FINANCIAL_TABLE_TERMS = (
    "acceptance",
    "accepted",
    "receipt",
    "fact_sets",
    "factsets",
    "confirmed_financial",
    "revenue_confirmations",
)
COPY_DATABASES = ("documents.db", "parse-v2.db", "finance-v2.db", "research-memory.db")


@contextmanager
def stopped_source(source):
    source = Path(source)
    if source.is_symlink():
        raise ValueError("Symlink runtime forbidden")
    source = source.resolve()
    evidence = source.parents[2]
    if (
        not evidence.is_relative_to(Path(tempfile.gettempdir()).resolve())
        or not evidence.name.startswith("findoc-integrated-http-")
        or source.parent.name != "active"
        or not source.name.isdecimal()
        or not (source / ".demo-manifest.json").is_file()
    ):
        raise ValueError(
            "Only disposable controller-owned findoc-integrated-http-* runtime allowed"
        )
    control = source.parents[1]
    locks = []
    try:
        for path in (control / "controller.lock", source / "research-execution.lock"):
            if not path.is_file() or path.is_symlink():
                raise ValueError("Closed source lock evidence missing")
            stream = path.open("rb")
            locks.append(stream)
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise ValueError("Source controller/runtime is still owned") from None
        if (control / "child.json").exists():
            raise ValueError("Verified child retirement required")
        for path in source.rglob("*"):
            if path.is_symlink() or (path.is_file() and path.stat().st_nlink != 1):
                raise ValueError("Source symlink/hardlink forbidden")
            if path.is_file() and path.name.endswith(("-wal", "-shm", "-journal")):
                raise ValueError("Source must be closed with checkpointed databases")
        yield source
    finally:
        for stream in reversed(locks):
            stream.close()


def table_counts(db):
    return {
        row[0]: db.execute(f"SELECT COUNT(*) FROM {identifier(row[0])}").fetchone()[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def reject_grants(source):
    for path in source.glob("*.db"):
        if not path.is_file():
            continue
        with path.open("rb") as stream:
            if stream.read(16) != b"SQLite format 3\x00":
                continue
        with closing(read_db(path)) as db:
            for name, count in table_counts(db).items():
                if count and (
                    any(term in name.lower() for term in FINANCIAL_TABLE_TERMS)
                    or name.lower() == "financial_facts"
                ):
                    raise ValueError(
                        "Financial acceptance/receipt/factset source forbidden: " + name
                    )


def backup(source, target):
    with closing(read_db(source)) as db, closing(sqlite3.connect(target)) as copied:
        db.backup(copied)


def validate_selection(source, conversation_ids, memory_ids, preference_keys):
    with closing(read_db(source / "documents.db")) as db:
        tables = table_counts(db)
        for name in ("research_runs", "template_tasks", "reports"):
            if tables.get(name, 0):
                raise ValueError("Unselected legacy execution history forbidden: " + name)
        actual = {row[0] for row in db.execute("SELECT conversation_id FROM conversations")}
        if actual != set(conversation_ids):
            raise ValueError(
                "Explicit demo conversation IDs must exactly cover source conversations"
            )
        operation_conversations = {
            row[0]
            for row in db.execute("SELECT DISTINCT conversation_id FROM conversation_operations")
        }
        if operation_conversations - actual:
            raise ValueError("Deleted/private conversation operations forbidden")
        preferences = db.execute("SELECT key,value FROM memory_items").fetchall()
        if {row["key"] for row in preferences} != set(preference_keys):
            raise ValueError("Explicit demo preference keys required")
        from app.memory.models import allowed_value

        for row in preferences:
            allowed_value(row["key"], row["value"])
    memory_path = source / "research-memory.db"
    if memory_path.exists():
        with closing(read_db(memory_path)) as db:
            notes = db.execute("SELECT * FROM items").fetchall()
            if {row["id"] for row in notes} != set(memory_ids) or any(
                row["revoked_at"] for row in notes
            ):
                raise ValueError("Only explicitly selected active demo memory may be seeded")
    elif memory_ids:
        raise ValueError("Selected memory database missing")


def validate_documents(source, allowlist, *, test_mode):
    with closing(read_db(source / "documents.db")) as db:
        docs = [dict(row) for row in db.execute("SELECT * FROM documents ORDER BY document_id")]
        if not docs:
            raise ValueError("Public PDF inventory required")
        for doc in docs:
            entry = allowlist.get(doc["content_sha256"])
            permitted = (
                ("public_official", "derived_public", "synthetic_test")
                if test_mode
                else ("public_official", "derived_public")
            )
            if not isinstance(entry, dict) or entry.get("origin") not in permitted:
                raise ValueError("PDF SHA not explicitly public-allowlisted")
            if entry["origin"] == "derived_public" and (
                entry.get("derived_from_sha256") not in allowlist
                or allowlist[entry["derived_from_sha256"]].get("origin") != "public_official"
            ):
                raise ValueError("Derived PDF needs an allowlisted official parent SHA")
            path = source / doc["object_key"]
            # Object keys are relative to objects/, unlike manifest file paths.
            if not path.is_file():
                path = source / "objects" / doc["object_key"]
            if (
                not path.resolve().is_relative_to(source / "objects")
                or not path.is_file()
                or sha256(path) != doc["content_sha256"]
            ):
                raise ValueError("Public PDF object/hash mismatch")
            with path.open("rb") as stream:
                if stream.read(5) != b"%PDF-":
                    raise ValueError("Non-PDF object forbidden")
            if entry["origin"] != "derived_public" and doc["status"] != "ready":
                raise ValueError("Official text PDF must be READY")
            doc["seed_object_path"] = path.relative_to(source).as_posix()
            doc["public_provenance"] = entry
        bound_companies = {
            row[0] for row in db.execute("SELECT DISTINCT company_id FROM report_document_metadata")
        }
        if (
            not bound_companies
            or {row[0] for row in db.execute("SELECT company_id FROM companies")} != bound_companies
        ):
            raise ValueError("Only public-document-bound companies may be seeded")
    return docs


def checked_records(db, record_id, kind):
    row = db.execute("SELECT * FROM sr_records WHERE id=? AND kind=?", (record_id, kind)).fetchone()
    if row is None or digest(json.loads(row["payload"])) != row["sha"]:
        raise ValueError("Original immutable job result missing/corrupt")
    return row


def archive_payloads(source, job_ids, report_ids, docs, memory_ids):
    allowed = {doc["document_id"]: doc for doc in docs}
    items, jobs = [], {}
    with closing(read_db(source / "showcase-research.db")) as db:
        for job_id in job_ids:
            row = db.execute(
                "SELECT * FROM sr_jobs WHERE id=? AND state='completed'", (job_id,)
            ).fetchone()
            if row is None or not row["result"]:
                raise ValueError("Only explicitly selected completed jobs may be archived")
            scope, result = json.loads(row["scope"]), json.loads(row["result"])
            frozen = checked_records(db, job_id, "job-result")
            if json.loads(frozen["payload"]) != result or result.get("job_id") != job_id:
                raise ValueError("Original job result identity mismatch")
            if not scope.get("sources") or scope.get("selected_fact_refs"):
                raise ValueError("Archive cannot import financial authority or unknown sources")
            for identity in scope["sources"]:
                doc = allowed.get(identity["document_id"])
                if doc is None or doc["content_sha256"] != identity["content_sha256"]:
                    raise ValueError("Job outside allowlisted public sources")
            if {m["memory_id"] for m in scope.get("memory_items", [])} - set(memory_ids):
                raise ValueError("Archive scope contains unselected private memory")
            if any(
                f.get("kind") == "confirmed_financial" or f.get("financial_refs")
                for f in result.get("findings", [])
            ):
                raise ValueError("Archived findings cannot carry financial grants")
            provenance = {
                "original_job_id": job_id,
                "original_scope_json": row["scope"],
                "original_scope_sha256": digest_text(row["scope"]),
                "original_result_json": row["result"],
                "original_result_sha256": digest_text(row["result"]),
                "application_result_sha256": frozen["sha"],
                "original_created_at": row["created_at"],
                "original_ended_at": row["ended_at"],
            }
            item = {
                "archive_id": str(
                    uuid5(NAMESPACE_URL, "preset-job:" + job_id + ":" + frozen["sha"])
                ),
                "kind": "job",
                "original_id": job_id,
                "revision": 0,
                "workspace": scope["workspace_id"],
                "saved_at": row["ended_at"] or row["created_at"],
                "original_data_origin": result.get("data_origin", "unknown"),
                "snapshot": result,
                "provenance": provenance,
            }
            jobs[job_id] = item
            items.append(item)
    if report_ids:
        with closing(read_db(source / "showcase-reports.db")) as db:
            for report_id in report_ids:
                rows = db.execute(
                    "SELECT v.payload,v.revision FROM revisions v JOIN reports r ON r.id=v.report_id WHERE r.id=? ORDER BY v.revision",
                    (report_id,),
                ).fetchall()
                if not rows:
                    raise ValueError("Explicit report not found")
                for row in rows:
                    payload = json.loads(row["payload"])
                    job = jobs.get(payload.get("snapshot", {}).get("job_id"))
                    if (
                        job is None
                        or payload.get("report_id") != report_id
                        or payload.get("revision") != row["revision"]
                    ):
                        raise ValueError("Report is not linked to selected completed archive job")
                    original_findings = {f["finding_id"]: f for f in job["snapshot"]["findings"]}
                    for finding in payload["snapshot"].get("findings", []):
                        original = original_findings.get(finding["finding_id"])
                        if (
                            not original
                            or finding["kind"] != original["kind"]
                            or finding["text"] != original["text"]
                            or finding.get("financial_refs")
                            or finding.get("evidence_refs", []) != original.get("evidence_refs", [])
                            or finding.get("data_origin") != job["snapshot"].get("data_origin")
                            or finding.get("source_status")
                            != {
                                "current_valid": "current",
                                "not_applicable": "current",
                                "current": "current",
                            }.get(original.get("source_status"), "unavailable")
                            or any(
                                finding.get(axis) != original.get(axis)
                                for axis in (
                                    "transcription_review_status",
                                    "interpretation_review_status",
                                )
                            )
                        ):
                            raise ValueError("Report findings differ from original verified job")
                    provenance = {
                        **job["provenance"],
                        "original_report_id": report_id,
                        "original_report_payload_json": row["payload"],
                        "original_report_payload_sha256": digest_text(row["payload"]),
                    }
                    items.append(
                        {
                            "archive_id": str(uuid5(NAMESPACE_URL, "preset-report:" + report_id)),
                            "kind": "report",
                            "original_id": report_id,
                            "revision": row["revision"],
                            "workspace": job["workspace"],
                            "saved_at": payload["created_at"],
                            "original_data_origin": payload["snapshot"].get(
                                "data_origin", "unknown"
                            ),
                            "snapshot": payload,
                            "provenance": provenance,
                        }
                    )
    return items


def write_archive(path, items):
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript("""
            CREATE TABLE archive_items(archive_id TEXT NOT NULL,kind TEXT NOT NULL,original_id TEXT NOT NULL,
                revision INTEGER NOT NULL,workspace TEXT NOT NULL,saved_at TEXT NOT NULL,payload TEXT NOT NULL,sha256 TEXT NOT NULL,
                PRIMARY KEY(archive_id,revision));
            CREATE TRIGGER archive_no_update BEFORE UPDATE ON archive_items BEGIN SELECT RAISE(ABORT,'immutable preset archive'); END;
            CREATE TRIGGER archive_no_delete BEFORE DELETE ON archive_items BEGIN SELECT RAISE(ABORT,'immutable preset archive'); END;
        """)
        for item in items:
            db.execute(
                "INSERT INTO archive_items VALUES (?,?,?,?,?,?,?,?)",
                (
                    item["archive_id"],
                    item["kind"],
                    item["original_id"],
                    item["revision"],
                    item["workspace"],
                    item["saved_at"],
                    canonical(item),
                    digest(item),
                ),
            )


def sqlite_spec(path, root):
    with closing(read_db(path)) as db:
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("Copied SQLite check failed")
        return {
            "path": path.relative_to(root).as_posix(),
            "tables": table_counts(db),
            "indexes": [
                row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='index'")
            ],
        }


def probe_index(path):
    from pymilvus import MilvusClient

    client = MilvusClient(str(path))
    try:
        return [
            {
                "collection": name,
                "rows": int(client.get_collection_stats(collection_name=name)["row_count"]),
            }
            for name in sorted(client.list_collections())
        ]
    finally:
        client.close()


def build_full_seed(
    source_runtime,
    destination,
    *,
    public_allowlist,
    job_ids,
    report_ids,
    conversation_ids=(),
    memory_ids=(),
    preference_keys=(),
    seed_version,
    complete_product_seed=False,
    index_probe=None,
    test_mode=False,
):
    target = Path(destination)
    if target.exists() or target.is_symlink():
        raise FileExistsError("Seed destination must never have existed")
    if not seed_version or not job_ids:
        raise ValueError("Explicit seed version and archive job selection required")
    if (test_mode or index_probe is not None) and complete_product_seed:
        raise ValueError("Test substitutions cannot claim a complete product seed")
    with stopped_source(source_runtime) as source:
        if test_mode and not source.parents[2].name.startswith("findoc-integrated-http-test-"):
            raise ValueError(
                "Synthetic test mode requires an explicitly named disposable test source"
            )
        reject_grants(source)
        docs = validate_documents(source, public_allowlist, test_mode=test_mode)
        validate_selection(source, conversation_ids, memory_ids, preference_keys)
        items = archive_payloads(source, tuple(job_ids), tuple(report_ids), docs, memory_ids)
        target.mkdir(parents=True, exist_ok=False, mode=0o700)
        copied_dbs = []
        for name in COPY_DATABASES:
            path = source / name
            if path.is_file():
                backup(path, target / name)
                copied_dbs.append(target / name)
        # Pagination signing material is local runtime state, never source provenance.
        with closing(sqlite3.connect(target / "documents.db")) as db, db:
            db.execute("UPDATE research_cursor_key SET secret=randomblob(32)")
        for doc in docs:
            copied = target / doc["seed_object_path"]
            copied.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / doc["seed_object_path"], copied, follow_symlinks=False)
            if sha256(copied) != doc["content_sha256"]:
                raise ValueError("Copied public PDF changed")
        if not (source / "milvus.db").exists():
            raise ValueError("Closed source Milvus index required")
        if (source / "milvus.db").is_dir():
            shutil.copytree(source / "milvus.db", target / "milvus.db")
        else:
            shutil.copyfile(source / "milvus.db", target / "milvus.db")
        vectors = (index_probe or probe_index)(target / "milvus.db")
        write_archive(target / "showcase-archive.db", items)
        copied_dbs.append(target / "showcase-archive.db")
        ocr_completed = 0
        if (target / "parse-v2.db").exists():
            with closing(read_db(target / "parse-v2.db")) as db:
                allowed = {doc["document_id"]: doc for doc in docs}
                for row in db.execute("SELECT payload FROM artifacts"):
                    artifact = json.loads(row[0])
                    original_digest = artifact.get("output_sha256")
                    without_digest = {k: v for k, v in artifact.items() if k != "output_sha256"}
                    if (
                        digest(without_digest) != original_digest
                        or artifact["document_id"] not in allowed
                        or artifact["content_sha256"]
                        != allowed[artifact["document_id"]]["content_sha256"]
                    ):
                        raise ValueError("Parse artifact not bound to allowed public PDF")
                    if artifact["state"] == "completed" and artifact.get("ocr_pages", 0) > 0:
                        ocr_completed += 1
        inventory = {
            "schema_version": "showcase-seed-inventory-v1",
            "data_origin": "preset_demo",
            "documents": [
                {
                    "document_id": d["document_id"],
                    "sha256": d["content_sha256"],
                    "legacy_status": d["status"],
                    "public_provenance": d["public_provenance"],
                }
                for d in docs
            ],
            "archived_jobs": list(job_ids),
            "archived_reports": list(report_ids),
            "conversation_ids": list(conversation_ids),
            "memory_ids": list(memory_ids),
            "preference_keys": list(preference_keys),
            "completed_ocr_artifacts": ocr_completed,
            "test_substitutions": ["index_probe", "synthetic_data"]
            if test_mode or index_probe is not None
            else [],
            "financial_grants": 0,
            "new_model_calls": 0,
        }
        official_count = sum(d["public_provenance"]["origin"] == "public_official" for d in docs)
        live_jobs = sum(i["kind"] == "job" and i["original_data_origin"] == "live" for i in items)
        if complete_product_seed and not (
            official_count >= 3
            and ocr_completed
            and live_jobs
            and len(set(report_ids)) >= 2
            and conversation_ids
            and memory_ids
            and vectors
        ):
            raise ValueError("Full inventory not proven; leave complete_product_seed=false")
        (target / "seed-inventory.json").write_text(
            json.dumps(inventory, ensure_ascii=False, indent=2) + "\n"
        )
        files = [
            {"path": path.relative_to(target).as_posix(), "sha256": sha256(path)}
            for path in sorted(target.rglob("*"))
            if path.is_file()
        ]
        manifest = {
            "schema_version": "demo-seed-v1",
            "seed_version": seed_version,
            "data_origin": "preset_demo",
            "complete_product_seed": bool(complete_product_seed),
            "files": files,
            "sqlite": [sqlite_spec(path, target) for path in copied_dbs],
            "preset_task_ids": [],
            "vector_indexes": vectors,
        }
        (target / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        )
        for path in sorted(target.rglob("*"), reverse=True):
            path.chmod(0o500 if path.is_dir() else 0o400)
        target.chmod(0o500)
        _, digest_value = verify_seed(target)
        return {
            "seed_root": str(target),
            "manifest_sha256": digest_value,
            "complete_product_seed": bool(complete_product_seed),
            "inventory": inventory,
            "archive_items": [
                {"archive_id": i["archive_id"], "kind": i["kind"], "revision": i["revision"]}
                for i in items
            ],
        }
