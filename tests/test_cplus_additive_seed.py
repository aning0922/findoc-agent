"""Owned test seeds and fake vectors only. Never touches active/developer runtime."""

import asyncio
from contextlib import contextmanager
import json
import tarfile

import pytest
from app.demo.seed import sha256, verify_seed
from app.companies.sqlite_repository import SQLiteCompanyRepository
from app.companies.models import CompanyCreate
from app.cplus_seed.build import build_additive_seed, validate_inputs
from app.company_discovery.contracts import DiscoveryError
from app.showcase_seed.build import sqlite_spec
from tests.test_cplus_discovery import pdf
from tests.test_document_sources import Harness, metadata


def fixture(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    SQLiteCompanyRepository(base / "documents.db")
    (base / "objects").mkdir()
    (base / "milvus.db").mkdir()
    (base / "milvus.db/index.bin").write_bytes(b"UNIT_FAKE")
    manifest = dict(
        schema_version="demo-seed-v1",
        seed_version="test-base",
        data_origin="synthetic_test",
        complete_product_seed=False,
        files=[
            dict(path=p.relative_to(base).as_posix(), sha256=sha256(p))
            for p in base.rglob("*")
            if p.is_file()
        ],
        sqlite=[sqlite_spec(base / "documents.db", base)],
        preset_task_ids=[],
        vector_indexes=[],
    )
    (base / "manifest.json").write_text(json.dumps(manifest))
    for p in sorted(base.rglob("*"), reverse=True):
        p.chmod(0o500 if p.is_dir() else 0o400)
    base.chmod(0o500)
    source = tmp_path / "approved.pdf"
    source.write_bytes(pdf())
    item = dict(
        path=str(source),
        sha256=sha256(source),
        source_url="https://static.cninfo.com.cn/finalpage/2026-03-27/1225038336.PDF",
        security_code="600690",
        exchange="SSE",
        report_year=2025,
        official_name="海尔智家股份有限公司",
    )
    state = {"closed": False}

    @contextmanager
    def pipeline(root):
        h = Harness(root)

        class Fake:
            async def add(self, item, raw):
                company = h.companies.create(
                    CompanyCreate(
                        name=item["official_name"],
                        security_code=item["security_code"],
                        exchange=item["exchange"],
                    )
                )
                result = h.upload(raw, {**metadata(company.company_id, 2025), "basis": "unknown"})
                doc = result.json()["document_id"]
                assert h.processor.process(doc).status.value == "ready"
                return await h.service.source(doc)

        try:
            yield Fake()
        finally:
            state["closed"] = True

    def probe(path):
        assert state["closed"]
        return [{"collection": "unit_fake", "rows": 1}]

    return base, item, state, pipeline, probe


def test_new_frozen_seed_closes_writers_preserves_base_and_never_overwrites(tmp_path):
    base, item, state, pipeline, probe = fixture(tmp_path)
    baseline = sha256(base / "manifest.json")
    target = tmp_path / "new-seed"
    bundle = tmp_path / "bundle.tar.gz"
    result = asyncio.run(
        build_additive_seed(
            base,
            target,
            [item],
            bundle_path=bundle,
            pipeline_factory=pipeline,
            index_probe=probe,
            test_mode=True,
        )
    )
    assert (
        state["closed"] and result["base_unchanged"] and sha256(base / "manifest.json") == baseline
    )
    manifest, _ = verify_seed(target, result["manifest_sha256"])
    assert manifest["complete_product_seed"] is False
    assert (
        not (target / ".demo-manifest.json").exists()
        and result["inventory"]["test_substitutions"] is True
    )
    with tarfile.open(bundle) as archive:
        assert all(not m.issym() and not m.islnk() for m in archive.getmembers())
        assert all(
            not any(x in m.name for x in ["secret", "controller", "lease"])
            for m in archive.getmembers()
        )
    with pytest.raises(FileExistsError):
        asyncio.run(
            build_additive_seed(
                base, target, [item], pipeline_factory=pipeline, index_probe=probe, test_mode=True
            )
        )


def test_bad_inputs_and_live_writer_sidecar_fail_without_destination(tmp_path):
    base, item, state, pipeline, probe = fixture(tmp_path)
    with pytest.raises(DiscoveryError):
        validate_inputs([{**item, "source_url": "https://evil.test/private.pdf"}])
    with pytest.raises(ValueError, match="sha"):
        validate_inputs([{**item, "sha256": "0" * 64}])
    with pytest.raises(ValueError):
        validate_inputs([item, item, item])
    with pytest.raises(ValueError, match="test_ports"):
        asyncio.run(
            build_additive_seed(
                base, tmp_path / "forbidden", [item], pipeline_factory=pipeline, index_probe=probe
            )
        )

    @contextmanager
    def unclosed(root):
        with pipeline(root) as p:
            yield p
        (root / "documents.db-wal").write_bytes(b"UNSAFE")

    with pytest.raises(ValueError, match="writer_sidecar"):
        asyncio.run(
            build_additive_seed(
                base,
                tmp_path / "never-created",
                [item],
                pipeline_factory=unclosed,
                index_probe=probe,
                test_mode=True,
            )
        )
    assert state["closed"] and not (tmp_path / "never-created").exists()
