"""Concrete read-only template adapters over existing services. No LLM client."""

from app.retrieval_v2.models import SourceRef, RetrievalError
from app.retrieval_v2.service import sha
from app.annual_diff import AnnualDiffRequest


class ExistingToolAdapter:
    def __init__(self, *, hybrid, annual_diff):
        self.hybrid, self.annual = hybrid, annual_diff

    async def prepare_cell(self, cell, identity):
        refs = [SourceRef.model_validate(r) for r in cell["sources"]]
        if any(
            r.company_id != cell["company_id"] or r.workspace_id != identity.workspace_id
            for r in refs
        ):
            raise RetrievalError("cell_scope_mismatch")
        if cell["template"] == "annual_changes" and (
            len(refs) != 2 or refs[0].report_year == refs[1].report_year
        ):
            raise RetrievalError("two_year_sources_required", 422)
        for r in refs:
            await self.hybrid.records(r)
        generation = None
        if self.hybrid.memory is not None:
            with self.hybrid.memory.tx() as db:
                generation = self.hybrid.memory._generation(db)
        return dict(
            selected_sources=[r.model_dump() for r in refs],
            memory_generation=generation,
            source_scope_sha256=sha([r.model_dump() for r in refs]),
            generate_explanation=cell.get("generate_explanation",False),
        )

    async def validate_prepared(self, p, identity):
        if sha(p["selected_sources"]) != p["source_scope_sha256"]:
            raise RetrievalError("cell_scope_changed")
        await self.hybrid.authorize(identity)
        for r in p["selected_sources"]:
            await self.hybrid.records(SourceRef.model_validate(r))
        if self.hybrid.memory is not None:
            self.hybrid.memory.check_generation(p["memory_generation"])

    async def execute_cell(self, cell, operation_id, identity):
        p = cell["prepared"]
        await self.validate_prepared(p, identity)
        if cell["template"] == "risk_excerpt" and p.get("generate_explanation"):
            context=await self.hybrid.mutate("context",dict(operation_id=cell["child_context_operation_id"],
                title="批次固定范围研究",selected_sources=p["selected_sources"]),identity)
            if context["state"]!="completed":
                return dict(domain="research_answer_v1",state="partial",payload={"reason":"context_unknown_no_replay"})
            scope=context["result"]
            result=await self.hybrid.mutate("answer",dict(operation_id=operation_id,context_id=scope["context_id"],
                context_revision=scope["revision"],context_sha256=scope["context_sha256"],question=cell["question"]),identity)
            return dict(domain="research_answer_v1",state=result["state"],payload=result.get("result") or {})
        if cell["template"] == "risk_excerpt":
            r = await self.hybrid.mutate(
                "search",
                dict(
                    operation_id=operation_id,
                    sources=p["selected_sources"],
                    query=cell["question"],
                    top_k=5,
                ),
                identity,
            )
            return dict(domain="retrieval_v2", state=r["state"], payload=r.get("result") or {})
        r = await self.annual.create(
            AnnualDiffRequest(
                operation_id=operation_id,
                left_source=SourceRef.model_validate(p["selected_sources"][0]),
                right_source=SourceRef.model_validate(p["selected_sources"][1]),
                generate_explanation=p.get("generate_explanation",False),
            ),
            identity,
        )
        return dict(domain="annual_diff", state=r["state"], payload=r.get("result") or {})
