"""Exact immutable exports, byte/acceptance races, full upstream identity and safe Markdown."""

from contextlib import closing
import copy
import json
from pathlib import Path
import uuid
from unittest.mock import AsyncMock, Mock
import pytest
from markdown_it import MarkdownIt
from app.api.report_drafts import create_report_router
from app.reports.export_service import ReportExportService
from app.reports.markdown import render, filename
from app.reports.persistence_contracts import CreateRevision, ReportRevision
from app.reports.persistence_service import ReportPersistenceService
from app.reports.service import ReportService
from app.research.models import canonical, sha
from app.research.repository import HistoryError
from tests.test_d23_reports import req
from tests.test_d22_reports import reports as d22_reports, run, rewrite  # noqa: F401


@pytest.fixture
def reports(d22_reports):  # noqa: F811
    return d22_reports


def save(reports):
    h, tasks, verifier, task = reports
    saved = run(ReportPersistenceService(verifier).save(req(task)))
    return h, tasks, verifier, task, saved


def test_export_no_execution_no_writes_and_explicit_http_contract(reports, monkeypatch):
    h, _, verifier, _, saved = save(reports)
    from app.agent.financial_analysis import FinancialAnalysisService
    from app.agent.operating_research_graph import PersistentTemplateService
    from app.agent.revenue_confirmation import RevenueConfirmationService
    from app.rag.retriever import Retriever
    from app.rag.openai_compatible_llm import OpenAICompatibleLLMClient

    bombs = []
    for cls, methods in [
        (FinancialAnalysisService, ["analyze", "compare"]),
        (PersistentTemplateService, ["start", "resume", "dispatch"]),
        (RevenueConfirmationService, ["confirm", "confirm_financial", "persist_financial"]),
        (Retriever, ["retrieve"]),
        (OpenAICompatibleLLMClient, ["complete", "generate_once"]),
    ]:
        for method in methods:
            bomb = AsyncMock(side_effect=AssertionError("D24 forbidden execution"))
            monkeypatch.setattr(cls, method, bomb)
            bombs.append(bomb)
    monkeypatch.setattr(
        verifier.builder, "build", Mock(side_effect=AssertionError("no draft generation"))
    )
    h.client.app.include_router(create_report_router(verifier))
    r = saved["report"]
    path = f"/reports/{r['report_id']}/revisions/1/markdown"
    before = h.db.read_bytes()
    a = h.client.get(path)
    b = h.client.get(path)
    assert a.status_code == b.status_code == 200
    assert a.content == b.content == render(r)
    assert a.headers["x-markdown-sha256"] == sha(a.content.decode())
    assert a.headers["x-report-payload-sha256"] == saved["payload_sha256"]
    assert a.headers["x-report-eligibility"] == "simulated_test"
    assert "filename*=UTF-8''" in a.headers["content-disposition"]
    assert a.headers["cache-control"] == "no-store"
    assert a.headers["x-content-type-options"] == "nosniff"
    assert before == h.db.read_bytes() and all(b.call_count == 0 for b in bombs)
    for suffix in ("?revision=2", "?latest=true", "?test_mode=local_operator", "?x=1&x=2"):
        assert h.client.get(path + suffix).status_code == 422
    assert h.client.get(path.replace("/1/", "/0/")).status_code == 422
    assert h.client.get(path.replace("/1/", "/999999999999999999999999/")).status_code == 422
    assert h.client.get(path.replace("/1/", "/999/")).status_code == 404
    assert h.client.get(path.replace(r["report_id"], str(uuid.uuid4()))).status_code == 404
    assert h.client.get("/reports/drafts/revisions/1/markdown").status_code == 422
    assert h.client.get(f"/reports/{r['report_id']}/markdown").status_code == 404


def test_older_version_never_implicitly_exports_new_editor(reports):
    _, _, verifier, task, a = save(reports)
    rid = a["report"]["report_id"]
    b = run(
        ReportPersistenceService(verifier).save(
            CreateRevision(
                **req(
                    task, edits=dict(title="新版标题", conclusions=["新版用户结论"])
                ).model_dump(),
                expected_report_revision=1,
            ),
            rid,
        )
    )
    exporter = ReportExportService(verifier)
    old, old_name, _, _ = run(exporter.export(rid, 1))
    new, new_name, _, _ = run(exporter.export(rid, 2))
    assert old == render(a["report"]) and new == render(b["report"])
    assert "新版用户结论" not in old.decode() and "新版用户结论" in new.decode()
    assert old_name.endswith("-v1.md") and new_name.endswith("-v2.md")


@pytest.mark.parametrize("failure", ["revoke", "source", "bytes", "missing", "task"])
@pytest.mark.parametrize("when", [1, 2])
def test_race_blocks_export_but_keeps_historical_audit(reports, failure, when):
    h, tasks, verifier, task, saved = save(reports)
    original = verifier.pdf_evidence
    calls = 0

    async def change(value):
        nonlocal calls
        await original(value)
        calls += 1
        if calls != when:
            return
        selected = task["final_research_content"]["selected_reports"][0]
        if failure == "revoke":
            h.receipts.revoke_financial_receipt(
                workspace_id="demo",
                receipt_id=task["final_research_content"]["financial_facts"][0]["receipt_id"],
                confirmation_kind="simulated_test",
                reason="D24 export race",
            )
        elif failure == "source":
            h.sources.request_reindex("demo", selected["document_id"], selected["attempt"])
        elif failure == "task":
            changed = copy.deepcopy(task)
            changed["revision"] += 1
            rewrite(tasks, changed)
        else:
            doc = await h.documents.get_document(selected["document_id"])
            path = h.root / "objects" / doc.object_key
            if failure == "bytes":
                path.write_bytes(b"corrupted PDF")
            else:
                path.unlink()

    verifier.pdf_evidence = change
    exporter = ReportExportService(verifier)
    rid = saved["report"]["report_id"]
    if when == 2 and failure in ("bytes", "missing"):
        # External bytes after the last check cannot be fenced by SQLite; test that boundary
        # separately by changing before the last actual byte check.
        async def before_last(value):
            nonlocal calls
            calls += 1
            if calls == 2:
                doc = await h.documents.get_document(
                    task["final_research_content"]["selected_reports"][0]["document_id"]
                )
                path = h.root / "objects" / doc.object_key
                if failure == "bytes":
                    path.write_bytes(b"corrupted PDF")
                else:
                    path.unlink()
            await original(value)

        verifier.pdf_evidence = before_last
    with pytest.raises(HistoryError):
        run(exporter.export(rid, 1))
    assert exporter.repository.get(rid, 1)["report"] == saved["report"]


@pytest.mark.parametrize("damage", ["sha", "schema", "refs", "parent", "business", "formula"])
def test_export_damaged_payload_or_recomputed_projection_fails_closed(reports, damage):
    h, _, verifier, _, saved = save(reports)
    r = saved["report"]
    with closing(h.registry._connect()) as conn, conn:
        conn.execute("DROP TRIGGER d23_report_revisions_update")
        if damage == "sha":
            conn.execute("UPDATE report_revisions SET payload_sha256=?", ("f" * 64,))
        elif damage == "refs":
            conn.execute("DROP TRIGGER d23_report_fact_refs_delete")
            conn.execute("DELETE FROM report_fact_refs WHERE side='first'")
        else:
            if damage == "schema":
                r["trusted_snapshot"]["schema_version"] = "unsupported"
            elif damage == "parent":
                r["parent_revision"] = 1
            elif damage == "formula":
                r["trusted_snapshot"]["financial_analysis"][0]["absolute_expression"] = (
                    "forged formula"
                )
            else:
                r["trusted_snapshot"]["executive_summary"][0] = "篡改摘要"
            if damage in ("business", "formula"):
                snapshot = r["trusted_snapshot"]
                business = {
                    k: v
                    for k, v in snapshot.items()
                    if k
                    not in {
                        "schema_version",
                        "builder_version",
                        "business_content_sha256",
                        "generated_at",
                        "persisted",
                        "human_review_status",
                        "verified_operating_attribution",
                    }
                }
                snapshot["business_content_sha256"] = sha(canonical(business))
            payload = canonical(r)
            conn.execute(
                "UPDATE report_revisions SET canonical_payload=?,payload_sha256=?",
                (payload, sha(payload)),
            )
    with pytest.raises(HistoryError):
        run(ReportExportService(verifier).export(r["report_id"], 1))


def test_production_export_rejects_saved_simulation_and_cross_workspace(reports):
    h, tasks, _, _, saved = save(reports)
    exporter = ReportExportService(ReportService(tasks, h.service))
    with pytest.raises(HistoryError, match="report_production_confirmation_required"):
        run(exporter.export(saved["report"]["report_id"], 1))
    h.client.app.include_router(create_report_router(exporter.verifier))
    response = h.client.get(f"/reports/{saved['report']['report_id']}/revisions/1/markdown")
    assert (
        response.status_code == 409
        and response.json()["error_code"] == "report_production_confirmation_required"
    )
    from app.research.task_repository import TaskRepository

    other = ReportExportService(ReportService(TaskRepository(h.registry, "other"), h.service))
    with pytest.raises(HistoryError, match="resource_not_found"):
        run(other.export(saved["report"]["report_id"], 1))


def test_markdown_reader_complete_safety_units_fences_and_lifecycle(reports):
    _, _, _, _, saved = save(reports)
    r = saved["report"]
    r["editor_revision"].update(
        title="../CON:<script>|测试\r\n标题",
        conclusions=[
            "[运行](javascript:alert(1))\n<img src=x onerror=alert(1)> | ```\n# 假标题\n``` &amp; 中文"
        ],
    )
    md = render(r).decode()
    parser = MarkdownIt("default", {"html": True})
    tokens = parser.parse(md)
    html = parser.render(md)
    assert "<table>" in html and "<script>" not in html and "<img" not in html
    assert 'href="javascript:' not in html and "假标题</h1>" not in html
    assert "未验证" in html and "simulated_test" in html
    assert all(c not in filename(r) for c in '/\\<>:"|?*\r\n')
    audit = [json.loads(t.content) for t in tokens if t.type == "fence" and t.info == "json"]
    assert audit[-1] == r  # exact, lossless immutable payload even with injected fences
    s = r["trusted_snapshot"]
    for f in s["financial_facts"]:
        assert f["raw_value"] in html and f["raw_unit"] in html and f["value_cny_yuan"] in html
    for a in s["financial_analysis"]:
        assert a["absolute_expression"] in html and a["percentage_expression"] in html
    assert "- 草稿尚未保存" not in md.split("## 证据与审计附录")[0]
    assert "生成时的生命周期审计记录" in md
    assert (
        json.loads(Path("product/validation/report-revision-v1.schema.json").read_text())
        == ReportRevision.model_json_schema()
    )
