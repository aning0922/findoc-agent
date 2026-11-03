"""Offline synthetic archive checks; no provider, real approvals or full-seed claims."""

import asyncio
from contextlib import closing
import fcntl
import json
import sqlite3
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.demo.seed import materialize, sha256, verify_seed
from app.showcase_research.store import ResearchStore
from app.showcase_reports import Finding, ShowcaseReportService, VerifiedJobSnapshot
from app.showcase_seed.api import create_showcase_archive_router
from app.showcase_seed.archive import ShowcaseArchiveService, canonical, digest_text, read_db
from app.showcase_seed.build import build_full_seed
from tests.test_finance_v2 import assembled, synthetic_pdf


def prepared(tmp_path):
    root = tmp_path / "findoc-integrated-http-test-archive" / "control" / "active" / "1"
    h, company, document, source = assembled(root, synthetic_pdf())
    with sqlite3.connect(h.db) as db:
        db.execute("DELETE FROM companies WHERE company_id != ?", (company,))
    (root / ".demo-manifest.json").write_text("{}")
    (root / "research-execution.lock").touch()
    (root.parents[1] / "controller.lock").touch()
    (root / "milvus.db").mkdir()
    (root / "milvus.db" / "index.bin").write_bytes(b"SYNTHETIC INDEX ONLY")
    _, records = asyncio.run(
        h.service.parsed_evidence(
            document, company_id=company, source_revision=source["source_revision"]
        )
    )
    identity = {
        k: source[k]
        for k in (
            "document_id",
            "company_id",
            "source_revision",
            "content_sha256",
            "parser_version",
            "attempt",
            "report_year",
            "report_type",
            "period_start",
            "period_end",
            "basis",
        )
    }
    identity["workspace_id"] = "demo"
    ref = {**identity, **{k: records[0][k] for k in ("physical_page", "text", "evidence_id")}}
    finding = Finding(
        finding_id="f1",
        kind="sourced_excerpt",
        text="合成样本引文",
        evidence_refs=[ref],
        data_origin="fake",
        source_status="current",
    ).model_dump()
    job_id = str(uuid4())
    scope = {
        "workspace_id": "demo",
        "runtime_instance_id": "expired-original-instance",
        "lease_generation": 19,
        "lease_expires_at": 1,
        "sources": [identity],
        "selected_fact_refs": [],
        "memory_items": [],
        "scope_hash": "original-scope-hash",
    }
    result = {
        "schema_version": "showcase-research-result-v2",
        "job_id": job_id,
        "goal": "合成归档机制测试",
        "mode": "single",
        "findings": [finding],
        "scope_hash": scope["scope_hash"],
        "data_origin": "fake",
    }
    store = ResearchStore(root)
    with store.tx() as db:
        ResearchStore.record(db, "job-result", job_id, result)
        db.execute(
            "INSERT INTO sr_jobs VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                job_id,
                str(uuid4()),
                "explicit-test-history",
                "single",
                "completed",
                canonical(scope),
                canonical(result),
                None,
                "2020-01-01T00:00:00Z",
                "2020-01-01T00:01:00Z",
            ),
        )

    async def reader(job):
        assert job == job_id
        return VerifiedJobSnapshot(
            job_id=job_id,
            workspace_id="demo",
            state="completed",
            company_name="合成企业",
            period_label="2031",
            data_origin="fake",
            findings=[Finding(**finding)],
        )

    async def reports():
        service = ShowcaseReportService(root, workspace_id="demo", verified_job_reader=reader)
        ids = []
        for title in ("合成报告一", "合成报告二"):
            draft = await service.draft(operation_id=str(uuid4()), job_id=job_id)
            ids.append(
                service.save(operation_id=str(uuid4()), draft_id=draft["draft_id"], title=title)[
                    "report_id"
                ]
            )
        return ids

    reports = asyncio.run(reports())
    kwargs = dict(
        public_allowlist={source["content_sha256"]: {"origin": "synthetic_test"}},
        job_ids=[job_id],
        report_ids=reports,
        seed_version="unit-synthetic-v1",
        test_mode=True,
        index_probe=lambda path: [],
    )
    return root, h, kwargs, scope, result


def test_archive_materialization_get_only_current_stale_and_unavailable(tmp_path):
    root, h, kwargs, scope, original = prepared(tmp_path)
    result = build_full_seed(root, tmp_path / "seed", **kwargs)
    seed = tmp_path / "seed"
    manifest, manifest_sha = verify_seed(seed)
    assert set(manifest) == {
        "schema_version",
        "seed_version",
        "data_origin",
        "complete_product_seed",
        "files",
        "sqlite",
        "preset_task_ids",
        "vector_indexes",
    }
    assert manifest["data_origin"] == "preset_demo" and manifest["complete_product_seed"] is False
    assert next(s for s in manifest["sqlite"] if s["path"] == "showcase-archive.db")["tables"] == {
        "archive_items": 3
    }
    assert (
        not (seed / "showcase-research.db").exists() and not (seed / "showcase-reports.db").exists()
    )
    target = tmp_path / "new-generation"
    materialize(seed, target, manifest_sha)
    # Reuse source-service constructors without adding fixture companies or any live job owner.
    from app.companies.service import CompanyService
    from app.companies.sqlite_repository import SQLiteCompanyRepository
    from app.documents.local_object_store import LocalObjectStore
    from app.documents.service import DocumentService
    from app.documents.source_repository import SQLiteSourceRepository
    from app.documents.source_service import DocumentSourceService
    from app.documents.sqlite_repository import SQLiteDocumentRepository
    from unittest.mock import Mock

    registry = SQLiteCompanyRepository(target / "documents.db")
    objects = LocalObjectStore(target / "objects")
    sources = DocumentSourceService(
        documents=DocumentService(
            repository=SQLiteDocumentRepository(target / "documents.db"),
            object_store=objects,
            dispatcher=Mock(),
            workspace_id="demo",
        ),
        objects=objects,
        companies=CompanyService(registry, workspace_id="demo"),
        repository=SQLiteSourceRepository(registry),
    )
    app = FastAPI()
    app.include_router(
        create_showcase_archive_router(ShowcaseArchiveService(target, sources=sources))
    )
    client = TestClient(app)
    jobs = [i for i in result["archive_items"] if i["kind"] == "job"]
    url = "/showcase-archive/jobs/" + jobs[0]["archive_id"]
    saved = client.get(url)
    assert saved.status_code == 200, saved.text
    payload = saved.json()
    assert payload["snapshot"] == original and payload["current_source_status"] == "current"
    assert json.loads(payload["provenance"]["original_scope_json"]) == scope
    assert payload["provenance"]["original_scope_sha256"] == digest_text(canonical(scope))
    assert payload["provenance"]["original_result_sha256"] == digest_text(canonical(original))
    assert payload["data_origin"] == "preset_demo" and payload["original_data_origin"] == "fake"
    assert payload["historical_snapshot"] and not any(payload["capabilities"].values())
    assert client.post(url, json={"resume": True}).status_code == 405
    assert client.get("/showcase-archive/items").headers["cache-control"] == "no-store"
    report = next(i for i in result["archive_items"] if i["kind"] == "report")
    report_url = f"/showcase-archive/reports/{report['archive_id']}/revisions/{report['revision']}"
    assert client.get(report_url).json()["current_source_status"] == "current"
    object_path = next((target / "objects").rglob("*.pdf"))
    original_source_sha = sha256(next((root / "objects").rglob("*.pdf")))
    object_path.write_bytes(b"%PDF-modified")
    changed = client.get(url).json()
    assert changed["current_source_status"] == "stale"
    assert (
        changed["snapshot"] == payload["snapshot"]
        and changed["provenance"] == payload["provenance"]
    )
    assert client.get(report_url).json()["current_source_status"] == "stale"
    object_path.unlink()
    assert client.get(url).json()["current_source_status"] == "unavailable"
    assert sha256(next((root / "objects").rglob("*.pdf"))) == original_source_sha
    with closing(read_db(target / "showcase-archive.db")) as db:
        assert db.execute("SELECT count(*) FROM archive_items").fetchone()[0] == 3


def test_builder_rejects_unselected_data_financial_grants_owned_source_and_overwrite(tmp_path):
    root, _, kwargs, _, _ = prepared(tmp_path)
    target = tmp_path / "seed"
    with pytest.raises(ValueError, match="public-allowlisted"):
        build_full_seed(root, target, **{**kwargs, "public_allowlist": {}})
    with pytest.raises(ValueError, match="conversation IDs"):
        build_full_seed(root, target, **{**kwargs, "conversation_ids": ["unselected-private"]})
    with (root / "research-execution.lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="still owned"):
            build_full_seed(root, target, **kwargs)
    with sqlite3.connect(root / "documents.db") as db:
        db.execute("CREATE TABLE synthetic_receipts (id TEXT)")
        db.execute("INSERT INTO synthetic_receipts VALUES ('simulated-still-forbidden')")
    with pytest.raises(ValueError, match="receipt"):
        build_full_seed(root, target, **kwargs)
    assert not target.exists()
    target.mkdir()
    (target / "preserve.txt").write_text("untouched")
    with pytest.raises(FileExistsError):
        build_full_seed(root, target, **kwargs)
    assert (target / "preserve.txt").read_text() == "untouched"


def test_fake_or_custom_index_cannot_claim_full_inventory(tmp_path):
    root, _, kwargs, _, _ = prepared(tmp_path)
    with pytest.raises(ValueError, match="cannot claim"):
        build_full_seed(root, tmp_path / "seed", complete_product_seed=True, **kwargs)
