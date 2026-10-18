"""Four real frozen D23 scenarios; exact exports across fresh processes and invalidation."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import AsyncMock, Mock
import asyncio

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))


def worker(runtime, phase):
    from scripts.validate_d23_real import bombs
    from tests.support.d19_runtime import reopen
    from app.agent.financial_analysis import IsolatedAnalysisTestConfig
    from app.agent.operating_research_graph import PersistentTemplateService
    from app.agent.revenue_confirmation import RevenueConfirmationService
    from app.research.task_repository import TaskRepository
    from app.reports.service import ReportService
    from app.reports.builder import ReportBuilder
    from app.api.report_drafts import create_report_router
    from markdown_it import MarkdownIt

    h = reopen(runtime)
    verifier = ReportService(
        TaskRepository(h.registry, "demo"),
        h.service,
        isolated_test=IsolatedAnalysisTestConfig(runtime),
    )
    blocked = bombs()
    for cls, methods in [
        (PersistentTemplateService, ["start", "resume", "dispatch"]),
        (RevenueConfirmationService, ["confirm", "confirm_financial", "persist_financial"]),
        (ReportBuilder, ["build"]),
    ]:
        for method in methods:
            bomb = (AsyncMock if asyncio.iscoroutinefunction(getattr(cls, method)) else Mock)(
                side_effect=AssertionError("D24 forbidden execution")
            )
            setattr(cls, method, bomb)
            blocked[cls.__name__ + "." + method] = bomb
    h.client.app.include_router(create_report_router(verifier))
    before = (runtime / "documents.db").read_bytes()
    saved = json.loads((runtime / "saved-proof.json").read_text())
    results = []
    for case in saved["cases"]:
        for version in case["versions"]:
            r = version["report"]
            rev = r["revision"]
            rid = r["report_id"]
            path = f"/reports/{rid}/revisions/{rev}/markdown"
            response = h.client.get(path)
            if phase in ("source", "revoked", "missing"):
                assert response.status_code == 409, response.text
                audit = h.client.get(path.removesuffix("/markdown")).json()
                assert audit["report"] == r
                if phase != "missing":
                    assert audit["current_eligibility"]["status"] == "invalidated"
                results.append(
                    dict(
                        report_id=rid,
                        revision=rev,
                        blocked=True,
                        error=response.json()["error_code"],
                        audit_unchanged=True,
                    )
                )
                continue
            assert response.status_code == 200, response.text
            body = response.content
            md = body.decode("utf8")
            digest = hashlib.sha256(body).hexdigest()
            parser = MarkdownIt("default", {"html": True})
            tokens = parser.parse(md)
            audits = [
                json.loads(t.content) for t in tokens if t.type == "fence" and t.info == "json"
            ]
            assert audits[-1] == r
            html = parser.render(md)
            assert "<table>" in html
            for f in r["trusted_snapshot"]["financial_facts"]:
                for k in ("raw_value", "raw_unit", "value_cny_yuan"):
                    assert f[k] in html
            assert "simulated_test" in html and "pending_semantic_review" in html
            if rev == 1:
                assert "用户结论仅作为待审断言" not in md
            else:
                assert "用户结论仅作为待审断言" in md
            name = f"{rid}-v{rev}.md"
            target = runtime / "exports" / name
            target.parent.mkdir(exist_ok=True)
            if phase == "restart":
                assert target.read_bytes() == body
            else:
                target.write_bytes(body)
            again = h.client.get(path)
            assert again.content == body
            results.append(
                dict(
                    report_id=rid,
                    revision=rev,
                    markdown_sha256=digest,
                    payload_sha256=version["payload_sha256"],
                    financial_fact_count=6,
                    analysis_count=3,
                    complete_audit_equal=True,
                    reader_table_valid=True,
                    repeat_equal=True,
                    restart_equal=phase == "restart",
                    simulated_test=True,
                    download_file=str(target),
                )
            )
    assert before == (runtime / "documents.db").read_bytes()
    assert all(b.call_count == 0 for b in blocked.values())
    record = dict(
        phase=phase,
        results=results,
        db_unchanged=True,
        execution_calls={k: b.call_count for k, b in blocked.items()},
    )
    (runtime / f"{phase}-exports.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(dict(phase=phase, versions=len(results), passed=True)))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        worker(Path(sys.argv[2]), sys.argv[1])
    else:
        original = Path(
            json.loads((root / "product/validation/d21-real-research.json").read_text())[
                "runtime_root"
            ]
        )
        runtime = Path(tempfile.mkdtemp(prefix="findoc-d11-d22-d24-real-"))
        shutil.copy2(original / "documents.db", runtime / "documents.db")
        shutil.copytree(original / "objects", runtime / "objects")
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        subprocess.run(
            [sys.executable, str(root / "scripts/validate_d23_real.py"), "save", str(runtime)],
            env=env,
            check=True,
        )
        for phase in ("live", "restart"):
            subprocess.run([sys.executable, __file__, phase, str(runtime)], env=env, check=True)
        records = [
            json.loads((runtime / f"{p}-exports.json").read_text()) for p in ("live", "restart")
        ]
        for phase in ("source", "revoked", "missing"):
            audit = Path(tempfile.mkdtemp(prefix=f"findoc-d11-d22-d24-{phase}-"))
            shutil.copy2(runtime / "documents.db", audit / "documents.db")
            shutil.copy2(runtime / "saved-proof.json", audit / "saved-proof.json")
            if phase != "missing":
                shutil.copytree(runtime / "objects", audit / "objects")
            saved = json.loads((audit / "saved-proof.json").read_text())
            from tests.support.d19_runtime import reopen

            h = reopen(audit)
            for case in saved["cases"]:
                r = case["versions"][0]["report"]["trusted_snapshot"]
                if phase == "source":
                    item = r["evidence_appendix"]["selected_reports"][0]
                    # Shared documents may have already been reindexed by another case.
                    try:
                        h.sources.request_reindex("demo", item["document_id"], item["attempt"])
                    except Exception as exc:
                        if getattr(exc, "code", "") not in (
                            "source_changed",
                            "source_not_ready",
                            "attempt_conflict",
                            "reindex_conflict",
                        ):
                            raise
                elif phase == "revoked":
                    receipt = r["financial_facts"][0]["receipt_id"]
                    h.receipts.revoke_financial_receipt(
                        workspace_id="demo",
                        receipt_id=receipt,
                        confirmation_kind="simulated_test",
                        reason="D24 export qualification check",
                    )
            subprocess.run([sys.executable, __file__, phase, str(audit)], env=env, check=True)
            records.append(json.loads((audit / f"{phase}-exports.json").read_text()))
        summary = dict(
            start_commit="0c2417e3e08a220ab51257b68ed844833b15310b",
            runtime_root=str(runtime),
            original_runtime=str(original),
            cases=[
                {k: v for k, v in c.items() if k != "versions"}
                for c in json.loads((runtime / "saved-proof.json").read_text())["cases"]
            ],
            records=records,
            human_acceptances=0,
            simulated_test=True,
        )
        (root / "product/validation/d24-real-exports.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
        )
        print(json.dumps(dict(runtime_root=str(runtime), cases=4, versions=8, passed=True)))
