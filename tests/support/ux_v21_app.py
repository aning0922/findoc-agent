"""Disposable UI contract acceptance, actual PDF/SQLite, simulated consent only.

Controlled mode uses actual parsing with controlled embedding/index/model. Live
mode delegates to the original D21 BGE/Milvus/provider assembly over a copy.
There is no production URL or request field enabling simulated consent.
"""

import os
import json
from pathlib import Path
from tempfile import gettempdir

from app.api.research_tasks import create_task_router
from app.api.report_drafts import create_report_router
from app.agent.financial_analysis import IsolatedAnalysisTestConfig
from app.companies.models import CompanyCreate
from app.documents.in_process_dispatcher import InProcessTaskDispatcher
from app.reports.service import ReportService
from tests.test_document_sources import Harness
from tests.test_financial_reviews import assemble
from tests.test_d21_research import configured, response
from tests.test_d18_templates import final
from app.agent.execution_budget import ExecutionBudget
from app.rag.retriever import SearchHit
from unittest.mock import AsyncMock
from typing import Literal


def create_ux_v21_app():
    root = Path(os.environ["FINDOC_UX_RUNTIME_ROOT"]).resolve()
    if not root.name.startswith("findoc-d11-") or not root.is_relative_to(
        Path(gettempdir()).resolve()
    ):
        raise ValueError("isolated_ux_runtime_required")
    if os.environ.get("FINDOC_UX_LIVE") == "1":
        from tests.support.d21_live_app import create_d21_app

        app = create_d21_app()
        source = app.state.live_runtime.state.source_service
        app.include_router(
            create_report_router(
                ReportService(
                    app.state.task_repository,
                    source,
                    isolated_test=IsolatedAnalysisTestConfig(root),
                )
            )
        )
        return app
    h = assemble(Harness(root))
    for name, code in [("美的集团股份有限公司", "000333"), ("珠海格力电器股份有限公司", "000651")]:
        h.companies.create(CompanyCreate(name=name, security_code=code, exchange="SZSE"))
    dispatcher = InProcessTaskDispatcher(h.processor.process)
    h.documents._dispatcher = dispatcher
    templates, repository, graph = configured(h, (1,))

    async def original_pdf_search(selection, top_k):
        # Controlled selection, actual parser text. D24 independently rereads
        # the pinned PDF and rejects placeholder excerpts at report admission.
        hits = []
        for document in selection.documents:
            _, records = await h.service.parsed_evidence(
                document.document_id,
                company_id=document.company_id,
                source_revision=document.source_revision,
            )
            paragraphs = [r for r in records if r["kind"] == "paragraph" and r["text"]]
            chosen = next(
                (r for r in paragraphs if any(
                    word in r["text"] for word in ("主营业务", "主要业务", "经营模式")
                )),
                paragraphs[0],
            )
            original = await h.documents.get_document(document.document_id)
            hits.append(SearchHit(
                chunk_id=chosen["evidence_id"], text=chosen["text"],
                page=chosen["physical_page"], score=1.0,
                source_file=original.source_file, type="paragraph",
                workspace_id=document.workspace_id, document_id=document.document_id,
                source_revision=document.source_revision,
            ))
        return tuple(hits)

    templates.scope.search = original_pdf_search

    class ControlledModel:
        def complete(self, messages, tools):
            evidence = str(messages[-1]["content"]).split("本次选定来源与编号原文：\n", 1)[1]
            numbers = tuple(
                json.loads(line)["number"] for line in evidence.splitlines() if line.startswith("{")
            )
            return final(response(numbers))

    templates.model = ControlledModel()
    normal_model, normal_search, normal_start = (
        templates.model,
        templates.scope.search,
        repository.start,
    )
    app = h.client.app

    @app.post("/__test__/ux-state/{kind}")
    async def failure_state(kind: Literal["normal", "failed", "refused", "budget"]):
        templates.model, templates.scope.search, repository.start = (
            normal_model,
            normal_search,
            normal_start,
        )
        if kind == "failed":

            class InvalidModel:
                def complete(self, messages, tools):
                    return final("invalid JSON")

            templates.model = InvalidModel()
        elif kind == "refused":
            templates.scope.search = AsyncMock(return_value=())
        elif kind == "budget":

            def exhausted(request):
                record, claim = normal_start(request)
                if claim:
                    budget = ExecutionBudget.restore(
                        record["budget"],
                        checkpoint=lambda v: repository.reserve(record["task_id"], claim, v),
                    )
                    budget.model_calls = budget.limits.model_calls
                    budget.checkpoint()
                    record = repository.get(record["task_id"])
                return record, claim

            repository.start = exhausted
        return {"isolated_test_only": True, "kind": kind}

    app.include_router(create_task_router(repository, graph))
    app.include_router(
        create_report_router(
            ReportService(repository, h.service, isolated_test=IsolatedAnalysisTestConfig(root))
        )
    )
    app.add_event_handler("shutdown", dispatcher.wait_for_idle)
    return app
