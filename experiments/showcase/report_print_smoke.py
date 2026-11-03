"""Synthetic report only; render resulting HTML with Playwright, then inspect PDF."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
import sqlite3
from app.showcase_reports import Finding, VerifiedJobSnapshot, ShowcaseReportService
from app.showcase_reports.printing import render_print


async def main():
    out = Path("output/pdf")
    out.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as directory:
        root = Path(directory)
        sqlite3.connect(root / "documents.db").close()

        async def reader(job_id):
            findings = [
                Finding(
                    finding_id="risk",
                    kind="model_interpretation",
                    text="模拟经营解释：账面盈利与现金收支需结合原文核查，当前没有已核准财务金额。",
                    data_origin="fake",
                    source_status="current",
                )
            ]
            for i in range(5):
                findings.append(
                    Finding(
                        finding_id=f"e{i}",
                        kind="sourced_excerpt",
                        text=(
                            "模拟原文摘录：本段仅用于检查中文打印、分页及引用。资料可能存在缺项，需要对照原 PDF 核查。"
                            * 6
                        ),
                        evidence_refs=[
                            {
                                "document_id": "synthetic-document",
                                "source_revision": "synthetic-revision",
                                "physical_page": i + 1,
                            }
                        ],
                        data_origin="fake",
                        source_status="current",
                        transcription_review_status="ocr_transcription_unreviewed",
                    )
                )
            findings.append(
                Finding(
                    finding_id="u",
                    kind="unresolved_question",
                    text="缺少已核准财务回执。请在正式研究流程中完成独立核查。",
                    data_origin="fake",
                    source_status="current",
                )
            )
            return VerifiedJobSnapshot(
                job_id=job_id,
                workspace_id="demo",
                state="completed",
                company_name="模拟企业",
                period_label="2025 年度示例",
                data_origin="fake",
                findings=findings,
                limitations=["模拟引用仅用于版式检查，没有真实年报附件。"],
            )

        service = ShowcaseReportService(root, workspace_id="demo", verified_job_reader=reader)
        draft = await service.draft(operation_id=str(uuid4()), job_id="synthetic-job")
        report = service.save(
            operation_id=str(uuid4()),
            draft_id=draft["draft_id"],
            title="模拟年度研究报告",
            notes="打印检视样本，不构成金融签核。",
        )
        report = await service.revision(report["report_id"], 1)
        (out / "showcase-report-synthetic.html").write_text(render_print(report))


if __name__ == "__main__":
    asyncio.run(main())
