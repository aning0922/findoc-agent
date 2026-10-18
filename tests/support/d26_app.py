"""D26 only: real HTTP/PDF/SQLite with controlled retrieval/model and fault hooks."""

import json
import os
from pathlib import Path
from unittest.mock import Mock

from app.api.research_runs import create_research_runs_router
from app.documents.preparation import DocumentTaskPreparer
from app.rag.retriever import SearchHit
from app.rag.selected_scope import SelectedScopeSearch
from app.rag.service import RAGService
from app.research.repository import ResearchRepository
from tests.support.ux_p1_app import create_ux_p1_app
from tests.support.d19_runtime import reopen


def create_app():
    app = create_ux_p1_app()  # Installs SQLite/root and socket guards before assembly.
    h = reopen(Path(os.environ["FINDOC_UX_RUNTIME_ROOT"]))
    mode = {"failure": False, "drop_upload": False, "budget": False}
    last_upload = {}
    calls = {"model": 0, "retrieval": 0}

    class Retriever:
        def retrieve(self, query, *, context, filters, top_k):
            calls["retrieval"] += 1
            if mode["budget"]:
                document_id, revision = filters.source_revisions[0]
                return [SearchHit(score=1.0, chunk_id="controlled-oversized-context",
                    text="经营介绍" * 5000, page=1, source_file=h.docs.get(document_id).source_file,
                    type="paragraph", workspace_id=context.workspace_id,
                    document_id=document_id, source_revision=revision)]
            hits = []
            for document_id, revision in filters.source_revisions:
                records = h.sources.evidence_batch(revision)
                tables = [r for r in records if r["kind"] == "table" and "营业收入" in r["text"]]
                if not tables:
                    continue
                chosen = tables[0]
                doc = h.docs.get(document_id)
                hits.append(
                    SearchHit(
                        score=1.0,
                        chunk_id=chosen["evidence_id"],
                        text="主要会计数据和财务指标",
                        table_md=chosen["text"],
                        type="table",
                        page=chosen["physical_page"],
                        source_file=doc.source_file,
                        workspace_id=context.workspace_id,
                        document_id=document_id,
                        source_revision=revision,
                    )
                )
            return hits

    class Model:
        def generate(self, prompt):
            calls["model"] += 1
            if mode["failure"]:
                raise ConnectionError("D26 injected provider connection failure")
            numbers = [
                json.loads(line)["number"]
                for line in prompt.splitlines()
                if line.startswith('{"number":')
            ]
            return json.dumps({"decision": "answer", "quotes": [{"number": n} for n in numbers]})

    preparer = DocumentTaskPreparer(
        document_service=h.documents, sources=h.service, workspace_id="demo"
    )
    scope = SelectedScopeSearch(preparer, Retriever())
    rag = RAGService(
        retriever=Retriever(),
        llm_client=Model(),
        evidence_gate=Mock(allows=Mock(return_value=True)),
        max_evidence_chars=16000,
    )
    repo = ResearchRepository(h.registry, "demo")
    app.include_router(create_research_runs_router(repo, preparer, scope, rag))

    @app.post("/__test__/d27-budget/{enabled}")
    def budget_fault(enabled: bool):
        mode["budget"] = enabled
        return {"controlled_context_budget_fault": enabled, "actual_model": False}

    @app.middleware("http")
    async def drop_upload_response(request, call_next):
        response = await call_next(request)
        if (
            mode["drop_upload"]
            and request.url.path == "/report-documents"
            and response.status_code == 202
        ):
            mode["drop_upload"] = False
            body = b"".join([part async for part in response.body_iterator])
            last_upload.update(json.loads(body))
            from fastapi.responses import StreamingResponse

            async def interrupted_body():
                yield b"{"
                raise ConnectionResetError(
                    "D26 injected response stream cutoff after actual upload commit"
                )

            return StreamingResponse(
                interrupted_body(), status_code=202, media_type="application/json"
            )
        return response

    @app.post("/__test__/d26-drop-upload")
    def drop_upload():
        mode["drop_upload"] = True
        return {"isolated_test_only": True}

    @app.post("/__test__/d26-model/{failure}")
    def fault(failure: bool):
        mode["failure"] = failure
        return dict(isolated_test_only=True, **mode)

    @app.get("/__test__/d26-counts")
    def inspect():
        with h.registry._connect() as conn:
            tables = [
                "documents",
                "document_sources",
                "financial_acceptance_receipts",
                "financial_fact_sets",
                "confirmed_financial_facts",
                "template_tasks",
                "research_runs",
                "reports",
                "report_revisions",
                "report_operations",
            ]
            return dict(
                tables={t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in tables},
                calls=calls,
                last_upload=last_upload,
            )

    return app
