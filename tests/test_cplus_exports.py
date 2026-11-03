"""Real files via bundled Python, fake resolver/fences. No model/financial approvals."""

import asyncio
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sys
from uuid import uuid4
import pytest
from app.exports_v2 import ExportService, ExportError
from app.exports_v2.projection import digest

_LOCAL_RENDERER = Path("/Users/aipuli/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3")
BUNDLED = os.environ.get("FINDOC_EXPORT_PYTHON", str(_LOCAL_RENDERER) if _LOCAL_RENDERER.is_file() else sys.executable)


def sample():
    return dict(
        schema_version="showcase-report-v2",
        report_id="report-one",
        revision=2,
        title="双年经营风险研究 · 候选待核对",
        snapshot=dict(
            findings=[
                dict(
                    finding_id="f",
                    kind="model_interpretation",
                    text="=未审核的中文解释，尚未生成新的财务结论。",
                    source_status="current",
                    interpretation_review_status="ai_unreviewed",
                    evidence_refs=[
                        dict(
                            document_id="public-document",
                            source_revision="fixed-source",
                            physical_page=24,
                            text="公开原文引用；需要核对表格口径。",
                        )
                    ],
                )
            ]
        ),
        cells=[
            dict(
                metric_key="revenue",
                raw_decimal="123456789012345678.123456789",
                normalized_decimal="123456789012345678.123456789",
                raw_unit="元",
                time=dict(kind="duration", period_start="2025-01-01", period_end="2025-12-31"),
                financial_review="unconfirmed",
            )
        ],
        limitations=["合成测试样本；未作财务确认。"],
    )


def test_real_csv_xlsx_files_immutable_get_and_permission(tmp_path):
    async def run():
        payload = sample()
        count = []
        allowed = [True]
        valid = [True]

        async def resolve(domain, id, revision, expected_sha, identity):
            count.append(1)
            return dict(
                snapshot=payload,
                selected_sources=[],
                memory_generation=None,
                display_status="stale",
            )

        def check(identity):
            if not valid[0]:
                raise ExportError("expired", 401)

        @contextmanager
        def guard(i, s):
            yield

        service = ExportService(
            tmp_path,
            resolver=resolve,
            identity_validator=check,
            publication_guard=guard,
            before_commit_sync=check,
            authorize_read=lambda i, m: allowed[0],
            renderer_python=BUNDLED,
        )
        identity = {"generation": 1, "principal": "fake"}
        body = dict(
            operation_id=str(uuid4()),
            report_ref=dict(
                domain="showcase_report_v2",
                id="report-one",
                revision=2,
                payload_sha256=digest(payload),
            ),
            formats=["csv", "xlsx", "pptx"],
            export_profile_version="research-v1",
        )
        first = await service.create(body, identity)
        assert first["state"] == "completed" and len(count) == 2
        assert await service.create(body, identity) == first and len(count) == 2
        eid = first["result"]["export_id"]
        for fmt in body["formats"]:
            raw, sha = await service.file(eid, fmt, identity)
            assert hashlib.sha256(raw).hexdigest() == sha
            (tmp_path / f"research.{fmt}").write_bytes(raw)
            assert await service.file(eid, fmt, identity) == (raw, sha)
        assert len(count) == 2
        csv = (tmp_path / "research.csv").read_text(encoding="utf-8-sig")
        assert "123456789012345678.123456789" in csv and "stale" in csv
        # Use the same installed authoring runtime to reopen the real file.
        proc = await asyncio.create_subprocess_exec(
            BUNDLED,
            "-c",
            "import openpyxl,sys; w=openpyxl.load_workbook(sys.argv[1]); assert w.sheetnames==['概览','财务数据','来源证据']; assert not any(c.data_type=='f' for s in w for r in s for c in r); assert any(c.value=='123456789012345678.123456789' for r in w['财务数据'] for c in r)",
            str(tmp_path / "research.xlsx"),
        )
        assert await proc.wait() == 0
        check = await asyncio.create_subprocess_exec(
            BUNDLED,
            "-c",
            "from pptx import Presentation;import sys;p=Presentation(sys.argv[1]);assert len(p.slides)==6;assert not any(s.has_chart for sl in p.slides for s in sl.shapes);assert any('待审阅' in s.text for sl in p.slides for s in sl.shapes if s.has_text_frame)",
            str(tmp_path / "research.pptx"),
        )
        assert await check.wait() == 0
        allowed[0] = False
        with pytest.raises(ExportError, match="display_permission_denied"):
            await service.file(eid, "xlsx", identity)
        assert len(count) == 2
        (tmp_path / "proof.json").write_text(json.dumps(first, ensure_ascii=False))

    asyncio.run(run())


def test_bad_domain_or_hash_leaves_unknown_without_files(tmp_path):
    async def run():
        async def resolver(*args):
            return dict(snapshot=sample(), display_status="current", selected_sources=[])

        @contextmanager
        def guard(*args):
            yield

        s = ExportService(
            tmp_path,
            resolver=resolver,
            identity_validator=lambda i: None,
            publication_guard=guard,
            before_commit_sync=lambda i: None,
            authorize_read=lambda i, m: True,
            renderer_python=BUNDLED,
        )
        body = dict(
            operation_id=str(uuid4()),
            report_ref=dict(
                domain="annual_diff_v1",
                id="report-one",
                revision=1,
                payload_sha256=digest(sample()),
            ),
            formats=["csv"],
            export_profile_version="research-v1",
        )
        with pytest.raises(ValueError, match="resolved_domain"):
            await s.create(body, {"generation": 1})
        assert s.operation(body["operation_id"], {"generation": 1})["state"] == "unknown"
        assert (await s.create(body, {"generation": 1}))["state"] == "unknown"

    asyncio.run(run())


def test_final_fence_failure_keeps_unknown_without_artifacts(tmp_path):
    async def run():
        async def resolver(*args):
            return dict(snapshot=sample(), display_status="current", selected_sources=[])

        @contextmanager
        def guard(*args):
            yield

        commits = []

        def commit(identity):
            commits.append(1)
            if len(commits) == 2:
                raise ExportError("lease_expired", 401)

        s = ExportService(
            tmp_path,
            resolver=resolver,
            identity_validator=lambda i: None,
            publication_guard=guard,
            before_commit_sync=commit,
            authorize_read=lambda i, m: True,
            renderer_python=BUNDLED,
        )
        body = dict(
            operation_id=str(uuid4()),
            report_ref=dict(
                domain="showcase_report_v2",
                id="report-one",
                revision=2,
                payload_sha256=digest(sample()),
            ),
            formats=["csv"],
            export_profile_version="research-v1",
        )
        with pytest.raises(ExportError, match="lease_expired"):
            await s.create(body, {"generation": 1})
        import sqlite3

        with sqlite3.connect(s.path) as db:
            assert db.execute("select count(*) from files").fetchone()[0] == 0
        assert s.operation(body["operation_id"], {"generation": 1})["state"] == "unknown"

    asyncio.run(run())
