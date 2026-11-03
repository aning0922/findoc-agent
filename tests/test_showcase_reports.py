import asyncio
import sqlite3
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.showcase_reports import (
    Finding,
    ShowcaseReportService,
    VerifiedJobSnapshot,
    create_showcase_report_router,
)
from app.showcase_reports.printing import render_print
from app.showcase_reports.service import ReportError


def oid():
    return str(uuid4())


def fixture_service(root):
    sqlite3.connect(root / "documents.db").close()

    async def reader(job_id):
        return VerifiedJobSnapshot(
            job_id=job_id,
            workspace_id="demo",
            state="completed",
            company_name="模拟企业 · 非真实 LLM",
            period_label="2025 年度示例",
            data_origin="fake",
            findings=[
                Finding(
                    finding_id="f1",
                    kind="model_interpretation",
                    text="<script>alert(1)</script>经营解释仍需人工核查。",
                    data_origin="fake",
                    source_status="current",
                )
            ],
            limitations=["全部为合成样本，无真实财务确认。"],
        )

    return ShowcaseReportService(root, workspace_id="demo", verified_job_reader=reader)


def test_versions_idempotency_and_immutability(tmp_path):
    async def run():
        service = fixture_service(tmp_path)
        args = dict(operation_id=oid(), job_id="job-1")
        draft = await service.draft(**args)
        assert await service.draft(**args) == draft
        args = dict(operation_id=oid(), draft_id=draft["draft_id"], title="模拟年度概览")
        first = service.save(**args)
        assert service.save(**args) == first
        service.save(
            operation_id=oid(),
            report_id=first["report_id"],
            expected_revision=1,
            title="新标题",
            notes="用户备注不确认金额",
        )
        assert (await service.revision(first["report_id"], 1))["title"] == "模拟年度概览"
        with pytest.raises(ReportError, match="report_revision_conflict"):
            service.save(
                operation_id=oid(), report_id=first["report_id"], expected_revision=1, title="冲突"
            )
        with sqlite3.connect(service.path) as db:
            with pytest.raises(sqlite3.IntegrityError, match="immutable revision"):
                db.execute("UPDATE revisions SET payload='{}'")
        assert service.list()[0]["revision"] == 2

    asyncio.run(run())


def test_clients_cannot_supply_findings(tmp_path):
    app = FastAPI()
    app.include_router(create_showcase_report_router(fixture_service(tmp_path)))
    client = TestClient(app)
    response = client.post(
        "/showcase-reports/drafts",
        json={"operation_id": oid(), "job_id": "job-1", "findings": [{"amount": "999"}]},
    )
    assert response.status_code == 422
    assert client.get("/showcase-reports").json() == []


def test_print_escapes_and_revalidates_history(tmp_path):
    async def run():
        service = fixture_service(tmp_path)
        draft = await service.draft(operation_id=oid(), job_id="job-1")
        report = service.save(
            operation_id=oid(), draft_id=draft["draft_id"], title="<img src=x onerror=alert(1)>"
        )

        async def unavailable(job_id):
            raise ReportError("source_stale")

        service.reader = unavailable
        historical = await service.revision(report["report_id"], 1)
        assert historical["current_source_status"] == "unavailable"
        html = render_print(historical)
        assert "<script>alert" not in html and "<img src=x" not in html
        assert "&lt;script&gt;" in html and "模拟数据 / 非真实 LLM" in html
        assert "打印/保存PDF" in html and "当前未覆盖" in html

    asyncio.run(run())
