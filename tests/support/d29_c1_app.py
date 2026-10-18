"""Fresh guarded historical-reader fixture. Public committed Run envelopes only.

No D28 database, credentials, human_result or acceptance records are imported.
PDFs are uploaded/parsed afresh. Old identities are fixtures, not new real runs.
"""

from contextlib import closing
import json
import os
from pathlib import Path
import sys
from urllib.parse import unquote, urlparse


def create_d29_c1_app():
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

    h = Harness(root)
    for cid, name, code in [
        ("335a4c49-b3b3-4150-adea-c6c6fc8720f4", "珠海格力电器股份有限公司", "000651"),
        ("3e794ed2-1145-4c9f-937b-547208b2de8f", "美的集团股份有限公司", "000333"),
    ]:
        company = h.companies.create(CompanyCreate(name=name, security_code=code, exchange="SZSE"))
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
    app.include_router(
        create_research_runs_router(repository)
        if os.environ.get("C1_BEFORE") == "1"
        else create_research_runs_router(repository, focus_preparer=verifier)
    )

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

    app.add_event_handler("shutdown", dispatcher.wait_for_idle)
    return app
