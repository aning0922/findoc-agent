"""Fresh process reads real D27 saved reports with execution paths disabled."""

import argparse
import hashlib
import json
from pathlib import Path
import time
from tempfile import gettempdir


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    runtime = args.runtime.resolve()
    assert runtime.name.startswith("findoc-d11-d27-business-")
    assert runtime.is_relative_to(Path(gettempdir()).resolve())
    from scripts.validate_d23_real import bombs
    from tests.support.d19_runtime import reopen
    from app.agent.financial_analysis import IsolatedAnalysisTestConfig
    from app.research.task_repository import TaskRepository
    from app.reports.service import ReportService
    from app.api.report_drafts import create_report_router

    blocked = bombs(history=False)
    from unittest.mock import Mock, AsyncMock
    from app.documents import fast_pdf_parser
    from app.reports.builder import ReportBuilder

    blocked["parse_fast_pdf_bytes"] = Mock(side_effect=AssertionError("new parsing on history"))
    fast_pdf_parser.parse_fast_pdf_bytes = blocked["parse_fast_pdf_bytes"]
    blocked["ReportBuilder.build"] = AsyncMock(side_effect=AssertionError("new report on history"))
    ReportBuilder.build = blocked["ReportBuilder.build"]

    def fingerprint():
        return {
            str(p.relative_to(runtime)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in runtime.rglob("*")
            if p.is_file()
        }

    before = fingerprint()
    h = reopen(runtime)
    snapshot_reads = AsyncMock(wraps=h.service.parsed_evidence)
    h.service.parsed_evidence = snapshot_reads
    h.client.app.include_router(
        create_report_router(
            ReportService(
                TaskRepository(h.registry, "demo"),
                h.service,
                isolated_test=IsolatedAnalysisTestConfig(runtime),
            )
        )
    )
    proof = json.loads((runtime / "d27-business-proof.json").read_text())
    results = []
    for case in proof["cases"]:
        if not case.get("reports"):
            continue
        for expected in case["reports"]:
            report = expected["report"]
            path = f"/reports/{report['report_id']}/revisions/{report['revision']}"
            t = time.perf_counter()
            response = h.client.get(path)
            assert response.status_code == 200 and response.json()["report"] == report
            detail_seconds = time.perf_counter() - t
            t = time.perf_counter()
            response = h.client.get(path + "/markdown")
            assert response.status_code == 200
            digest = hashlib.sha256(response.content).hexdigest()
            expected_sha = next(
                v["markdown_sha256"] for v in case["exports"] if v["revision"] == report["revision"]
            )
            assert digest == expected_sha
            results.append(
                dict(
                    report_id=report["report_id"],
                    revision=report["revision"],
                    detail_seconds=detail_seconds,
                    export_seconds=time.perf_counter() - t,
                    markdown_sha256=digest,
                    exact_snapshot_equal=True,
                )
            )
    after = fingerprint()
    assert before == after
    assert all(v.call_count == 0 for v in blocked.values())
    args.out.write_text(
        json.dumps(
            dict(
                runtime=str(runtime),
                results=results,
                runtime_files_unchanged=True,
                files=before,
                execution_calls={k: v.call_count for k, v in blocked.items()},
                simulated_test=True,
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
