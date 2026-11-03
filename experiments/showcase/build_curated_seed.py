"""Build the curated closed public seed and verify a fresh copy; no model/engine calls.

Selection comes from the root-owned research-progress/completed-seed-material JSON.
The runner's own completion/failure stays independent of this inventory verification.
"""

import argparse
import asyncio
from contextlib import closing
import json
from pathlib import Path
import tempfile

from app.companies.service import CompanyService
from app.companies.sqlite_repository import SQLiteCompanyRepository
from app.demo.seed import materialize, sha256, verify_seed
from app.documents.local_object_store import LocalObjectStore
from app.documents.service import DocumentService
from app.documents.source_repository import SQLiteSourceRepository
from app.documents.source_service import DocumentSourceService
from app.documents.sqlite_repository import SQLiteDocumentRepository
from app.parsing.service import ParseV2Service
from app.showcase_seed.archive import ShowcaseArchiveService, digest, read_db
from app.showcase_seed.build import build_full_seed, stopped_source


class DisabledExecution:
    def dispatch(self, *args, **kwargs):
        raise RuntimeError("Verification cannot dispatch work")


def fingerprint(root):
    with stopped_source(root) as source:
        return {
            p.relative_to(source).as_posix(): sha256(p) for p in source.rglob("*") if p.is_file()
        }


async def verify_copy(seed, material, source):
    manifest, manifest_sha = verify_seed(seed)
    root = Path(tempfile.mkdtemp(prefix="findoc-full-seed-verification-")) / "generation"
    materialize(seed, root, manifest_sha)
    registry = SQLiteCompanyRepository(root / "documents.db")
    objects = LocalObjectStore(root / "objects")
    documents = DocumentService(
        repository=SQLiteDocumentRepository(root / "documents.db"),
        object_store=objects,
        dispatcher=DisabledExecution(),
        workspace_id="demo",
    )
    sources = DocumentSourceService(
        documents=documents,
        objects=objects,
        companies=CompanyService(registry, workspace_id="demo"),
        repository=SQLiteSourceRepository(registry),
    )
    parse = ParseV2Service(runtime_root=root, documents=documents, sources=sources, engine=None)
    statuses = []
    for doc in material["documents"]:
        record = await documents.get_document(doc["document_id"])
        assert record.status.value == doc["status"] and record.content_sha256 == doc["sha256"]
        assert sha256(root / "objects" / record.object_key) == doc["sha256"]
        if doc["status"] == "ready":
            current = await sources.source(doc["document_id"])
            assert current["content_sha256"] == doc["sha256"]
            statuses.append(
                {
                    "document_id": doc["document_id"],
                    "legacy_status": "ready",
                    "source_read": "verified",
                }
            )
        else:
            statuses.append(
                {
                    "document_id": doc["document_id"],
                    "legacy_status": doc["status"],
                    "source_read": "not_legacy_verified",
                }
            )
    ocr = material["ocr"]
    artifact = await parse.quality(ocr["document_id"], ocr["artifact_id"])
    assert artifact["state"] == "completed" and artifact["source_status"] == "current"
    assert artifact["legacy_source_verified"] is False
    lines = sum(len(p["lines"]) for p in artifact["pages"])
    cells = sum(len(t["cells"]) for p in artifact["pages"] for t in p["tables"])
    assert lines == ocr["lines"] and cells == ocr["cells"]
    archive = ShowcaseArchiveService(root, sources=sources, parse_service=parse)
    listing = await archive.list()
    assert len(listing["items"]) == 5
    archives = []
    with (
        closing(read_db(source / "showcase-research.db")) as original_jobs,
        closing(read_db(source / "showcase-reports.db")) as original_reports,
    ):
        for item in listing["items"]:
            saved = (
                await archive.job(item["archive_id"])
                if item["kind"] == "job"
                else await archive.report(item["archive_id"], item["revision"])
            )
            assert saved["current_source_status"] == "current" and not any(
                saved["capabilities"].values()
            )
            provenance = saved["provenance"]
            original = original_jobs.execute(
                "SELECT scope,result FROM sr_jobs WHERE id=?", (provenance["original_job_id"],)
            ).fetchone()
            assert (
                provenance["original_scope_json"] == original["scope"]
                and provenance["original_result_json"] == original["result"]
            )
            if item["kind"] == "job":
                assert saved["snapshot"] == json.loads(original["result"])
            else:
                original_report = original_reports.execute(
                    "SELECT payload FROM revisions WHERE report_id=? AND revision=?",
                    (item["original_id"], item["revision"]),
                ).fetchone()[0]
                assert provenance["original_report_payload_json"] == original_report and saved[
                    "snapshot"
                ] == json.loads(original_report)
            archives.append(
                {
                    "kind": item["kind"],
                    "original_id": item["original_id"],
                    "revision": item["revision"],
                    "current_source_status": saved["current_source_status"],
                    "original_scope_sha256": provenance["original_scope_sha256"],
                    "original_result_sha256": provenance["original_result_sha256"],
                    "original_report_payload_sha256": provenance.get(
                        "original_report_payload_sha256"
                    ),
                }
            )
    with closing(read_db(root / "research-memory.db")) as db:
        notes = db.execute("SELECT id,revision,revoked_at,vector FROM items").fetchall()
        assert {n["id"] for n in notes} == set(material["memory_ids"]) and all(
            not n["revoked_at"] and n["vector"] for n in notes
        )
    assert (
        not (root / "showcase-research.db").exists() and not (root / "showcase-reports.db").exists()
    )
    verify_seed(seed, manifest_sha)
    return {
        "verification_tier": "LOCAL_MATERIALIZED_COPY_SERVICE_READS",
        "materialized_root": str(root),
        "documents": statuses,
        "archives": archives,
        "ocr": {
            "state": artifact["state"],
            "source_status": artifact["source_status"],
            "legacy_source_verified": artifact["legacy_source_verified"],
            "lines": lines,
            "cells": cells,
            "output_sha256": artifact["output_sha256"],
        },
        "active_notes": len(notes),
        "live_execution_databases_absent": True,
        "source_provenance_exact": True,
        "new_model_calls": 0,
        "complete_product_seed": manifest["complete_product_seed"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--allowlist", type=Path, required=True)
    parser.add_argument("--verification-output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    evidence = source.parents[2]
    progress = json.loads((evidence / "research-progress.json").read_text())
    material = json.loads((evidence / "completed-seed-material.json").read_text())
    jobs = [j["job"] for j in progress["jobs"]]
    assert len(jobs) == 2 and all(j["state"] == "completed" for j in jobs)
    before = fingerprint(source)
    built = build_full_seed(
        source,
        args.destination,
        public_allowlist=json.loads(args.allowlist.read_text()),
        job_ids=[j["job_id"] for j in jobs],
        report_ids=material["report_ids"],
        conversation_ids=sorted({j["conversation_id"] for j in jobs}),
        memory_ids=material["memory_ids"],
        seed_version="showcase-seed-v1",
        complete_product_seed=True,
    )
    verification = asyncio.run(verify_copy(args.destination.resolve(), material, source))
    assert before == fingerprint(source)
    manifest, _ = verify_seed(args.destination.resolve(), built["manifest_sha256"])
    result = {
        **built,
        "verification": verification,
        "source_files_unchanged": True,
        "source_files_checked": len(before),
        "source_tree_sha256": digest(before),
        "manifest_file_count": len(manifest["files"]),
        "manifest_sqlite": manifest["sqlite"],
        "vector_indexes": manifest["vector_indexes"],
        "original_runner": {k: progress.get(k) for k in ("evidence", "completed", "failure")},
        "material_completion_tier": material["evidence_tier"],
        "human_financial_approvals": 0,
    }
    args.verification_output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
