"""Fresh guarded historical-reader fixture. Public committed Run envelopes only.

No D28 database, credentials, human_result or acceptance records are imported.
PDFs are uploaded/parsed afresh. Old identities are fixtures, not new real runs.
"""

from contextlib import closing
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
from urllib.parse import unquote, urlparse


def create_d29_c2_app():
    root = Path(os.environ["FINDOC_UX_RUNTIME_ROOT"]).resolve()
    allowed = Path(os.environ["D29_ALLOWED_WORKTREE"]).resolve()
    protected = [p.resolve() for p in allowed.parent.glob("findoc-*") if p.resolve() != allowed]

    def guard(event, args):
        if event == "socket.connect":
            raise RuntimeError("C1 forbids outgoing model/service sockets")
        if event == "sqlite3.connect" and args[0] != ":memory:":
            p = Path(
                unquote(urlparse(args[0]).path) if str(args[0]).startswith("file:") else args[0]
            ).resolve()
            if not p.is_relative_to(root):
                raise RuntimeError("C1 refuses foreign SQLite")
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            p = Path(os.fsdecode(args[0])).resolve()
            if any(p.is_relative_to(q) for q in protected) or p.is_relative_to(
                allowed / "data/d28"
            ):
                raise RuntimeError("C1 refuses live/foreign worktree files")

    sys.addaudithook(guard)
    from tests.test_document_sources import Harness
    from app.companies.models import CompanyCreate
    from app.documents.in_process_dispatcher import InProcessTaskDispatcher
    from app.documents.preparation import DocumentTaskPreparer
    from app.api.research_runs import create_research_runs_router
    from app.research.repository import ResearchRepository
    from app.research.models import Envelope, canonical, request_sha, sha
    from fastapi import HTTPException

    from app.companies.service import CompanyService

    original_create = CompanyService.create

    def fixture_create_or_read(self, payload):
        existing = next(
            (
                c
                for c in self.list()
                if c.security_code == payload.security_code
                and c.exchange == payload.exchange
                and c.name == payload.name
            ),
            None,
        )
        return existing or original_create(self, payload)

    # Fixture initialization can reopen its own root without adding companies.
    CompanyService.create = fixture_create_or_read
    try:
        h = Harness(root)
    finally:
        CompanyService.create = original_create
    for cid, name, code in [
        ("335a4c49-b3b3-4150-adea-c6c6fc8720f4", "珠海格力电器股份有限公司", "000651"),
        ("3e794ed2-1145-4c9f-937b-547208b2de8f", "美的集团股份有限公司", "000333"),
    ]:
        company = next((c for c in h.companies.list() if c.company_id == cid), None)
        if company is None:
            company = h.companies.create(
                CompanyCreate(name=name, security_code=code, exchange="SZSE")
            )
        with closing(h.registry._connect()) as c, c:
            c.execute(
                "UPDATE companies SET company_id=? WHERE company_id=?", (cid, company.company_id)
            )
    dispatcher = InProcessTaskDispatcher(h.processor.process)
    h.documents._dispatcher = dispatcher
    repository = ResearchRepository(h.registry, "demo")
    verifier = DocumentTaskPreparer(
        document_service=h.documents, sources=h.service, workspace_id="demo"
    )
    app = h.client.app
    app.include_router(create_research_runs_router(repository, focus_preparer=verifier))

    @app.post("/__test__/seed-public-run")
    async def seed(payload: dict):
        # Only the strict immutable Run; extra external human acceptance fields rejected.
        run = Envelope.model_validate(payload)
        selection = await verifier.prepare_many(document_ids=run.document_ids, query=run.query)
        if selection.selection_id != run.selection_id:
            raise HTTPException(409, "fixture_source_identity_mismatch")
        for citation in run.result.citations:
            if (
                await h.service.page_context(
                    citation.document_id, citation.source_revision, citation.physical_page
                )
                != citation.text
            ):
                raise HTTPException(409, "fixture_original_page_mismatch")
        value = canonical(run.model_dump())
        with closing(h.registry._connect()) as c, c:
            c.execute(
                "INSERT INTO research_runs(run_id,workspace_id,operation_id,request_sha,created_at,status,payload,payload_sha) VALUES(?,?,?,?,?,?,?,?)",
                (
                    run.run_id,
                    run.workspace_id,
                    run.operation_id,
                    request_sha(run.document_ids, run.query),
                    run.created_at,
                    run.status,
                    value,
                    sha(value),
                ),
            )
        return repository.public(run)

    @app.get("/__test__/c1-readonly-state")
    def state():
        with closing(h.registry._connect()) as c:
            names = [
                r[0]
                for r in c.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                )
            ]
            return {
                n: sha(
                    json.dumps(
                        sorted(
                            [tuple(r) for r in c.execute(f'SELECT * FROM "{n}"').fetchall()],
                            key=str,
                        ),
                        default=list,
                    )
                )
                for n in names
            }

    @app.middleware("http")
    async def audit(request, call_next):
        response = await call_next(request)
        with (root / "http.jsonl").open("a") as f:
            f.write(
                json.dumps(
                    dict(
                        method=request.method,
                        path=request.url.path,
                        query=request.url.query,
                        status=response.status_code,
                    )
                )
                + "\n"
            )
        return response

    from app.research.task_contracts import TaskRecordV2
    from app.reports.persistence_contracts import ReportRevision
    from app.reports.markdown import render
    from fastapi.responses import JSONResponse, Response

    # Public archived snapshots only; no Task/fact/acceptance/report rows inserted.
    archive_tasks = {}
    archive_reports = {}
    evidence = allowed / "product/d28/evidence/human-followup"
    for name in ["midea", "gree", "comparison"]:
        task = json.loads((evidence / f"{name}-user-resume-completed.json").read_text())["task"]
        TaskRecordV2.model_validate({k: task[k] for k in TaskRecordV2.model_fields})
        archive_tasks[task["task_id"]] = task
    for revision in [1, 2]:
        detail = json.loads((evidence / f"midea-report-v{revision}-user-saved.json").read_text())[
            "detail"
        ]
        ReportRevision.model_validate(detail["report"])
        assert sha(canonical(detail["report"])) == detail["payload_sha256"]
        archive_reports[revision] = detail
    assert (
        render(archive_reports[1]["report"])
        == (evidence / "midea-report-v1-user-downloaded.md").read_bytes()
    )

    @app.get("/__test__/archive/tasks/{task_id}")
    async def archive_task(task_id: str):
        task = archive_tasks.get(task_id)
        if task is None:
            raise HTTPException(404, "archive_not_found")
        selection = await verifier.prepare_many(
            document_ids=[r["document_id"] for r in task["input"]["reports"]],
            query="archive verification",
        )
        assert [asdict(x) for x in selection.documents] == task["snapshot"]["documents"]
        await verifier.revalidate(selection)
        return JSONResponse(
            task, headers={"Cache-Control": "no-store", "X-Test-Archive": "public-readonly"}
        )

    @app.get("/__test__/archive/reports/{revision}")
    async def archive_report(revision: int):
        if revision not in archive_reports:
            raise HTTPException(404, "archive_not_found")
        detail = archive_reports[revision]
        await archive_task(detail["report"]["trusted_snapshot"]["task_id"])
        return JSONResponse(
            detail, headers={"Cache-Control": "no-store", "X-Test-Archive": "public-readonly"}
        )

    @app.get("/__test__/archive/reports/{revision}/markdown")
    async def archive_markdown(revision: int):
        await archive_report(revision)
        return Response(render(archive_reports[revision]["report"]), media_type="text/markdown")

    app.add_event_handler("shutdown", dispatcher.wait_for_idle)
    return app
