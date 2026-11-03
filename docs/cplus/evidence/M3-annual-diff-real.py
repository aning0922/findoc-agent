"""Run with repository on PYTHONPATH; offline cached BGE and temp seed copy only."""

import asyncio
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from app.demo.seed import materialize, verify_seed
from app.rag.embed import embed
from app.rag.store import get_client, MilvusSearchStore
from app.rag.publications import IndexPublications
from app.rag.retriever import Retriever, SearchFilters, TrustedContext
from app.retrieval_v2 import HybridRetrievalService, SourceRef
from tests.test_document_sources import Harness


from contextlib import nullcontext
import time
from uuid import uuid4
from app.annual_diff import AnnualDiffService, AnnualDiffRequest
from app.retrieval_v2 import TrustedIdentity


async def main():
    seed = Path(
        "/Users/aipuli/.codex/worktrees/findoc-showcase-cplus-integration/findoc-agent/data/showcase-seed-v1"
    )
    _, digest = verify_seed(seed)
    with TemporaryDirectory(prefix="findoc-cplus-annual-") as directory:
        root = Path(directory) / "runtime"
        materialize(seed, root, digest)
        h = Harness(root)
        company = next(c for c in h.companies.list() if c.security_code == "000651")
        refs = []
        for document in h.docs.list_by_workspace("demo"):
            try:
                source = await h.service.source(document.document_id)
            except Exception:
                continue
            if source["company_id"] == company.company_id and source["report_year"] in (2024, 2025):
                refs.append(
                    SourceRef(
                        kind="fast",
                        identity_status="fast_source_verified",
                        workspace_id=h.documents.workspace_id,
                        **{
                            k: source[k]
                            for k in (
                                "company_id",
                                "document_id",
                                "source_revision",
                                "content_sha256",
                                "parser_version",
                                "report_year",
                                "attempt",
                                "report_type",
                                "basis",
                                "period_start",
                                "period_end",
                            )
                        },
                    )
                )
        assert len(refs) == 2 and len({r.report_year for r in refs}) == 2
        refs.sort(key=lambda r: r.report_year)
        client = get_client(str(root / "milvus.db"))
        try:
            pubs = IndexPublications(h.registry, client)
            retriever = Retriever(
                embed,
                MilvusSearchStore(
                    client,
                    "findoc_runtime_documents_v1",
                    include_scope_metadata=True,
                    publications=pubs,
                ),
            )

            def dense(q, refs, k):
                ids = tuple(sorted(r.document_id for r in refs))
                revisions = tuple(sorted((r.document_id, r.source_revision) for r in refs))
                return retriever.retrieve(
                    q,
                    context=TrustedContext("demo"),
                    filters=SearchFilters(document_ids=ids, source_revisions=revisions),
                    top_k=k,
                )

            hybrid = HybridRetrievalService(root, h.service, None, dense)
            await hybrid.build(refs)
            service = AnnualDiffService(
                root,
                hybrid=hybrid,
                sources=h.service,
                identity_validator=lambda i: None,
                publication_guard=lambda i, f: nullcontext(),
            )
            identity = TrustedIdentity(
                workspace_id="demo",
                instance_id="proof-local",
                generation=1,
                principal_id="proof",
                expires_at=float(time.time() + 600),
            )
            request = AnnualDiffRequest(
                operation_id=str(uuid4()), left_source=refs[0], right_source=refs[1]
            )
            result = (await service.create(request, identity))["result"]
            proof = dict(
                tier="REAL_PDF_BGE_MILVUS_LOCAL_NO_LLM",
                seed_manifest_sha256=digest,
                implementation_sha256=hashlib.sha256(
                    Path("app/annual_diff/service.py").read_bytes()
                ).hexdigest(),
                sources=[r.model_dump() for r in refs],
                topics=[
                    dict(
                        topic=p["topic"],
                        program_label=p["program_label"],
                        left=dict(
                            state=p["left"]["state"],
                            pages=[e["physical_page"] for e in p["left"]["evidence_refs"]],
                        ),
                        right=dict(
                            state=p["right"]["state"],
                            pages=[e["physical_page"] for e in p["right"]["evidence_refs"]],
                        ),
                        interpretation_review_status=p["interpretation_review_status"],
                    )
                    for p in result["topics"]
                ],
                provider_outcome=result["provider_outcome"],
                llm_calls=0,
                human_financial_approvals=0,
                limitations=[
                    "Local nullcontext guard does not verify root lease/source concurrency wiring",
                    "Topic markers/ranking do not establish semantic comparison accuracy",
                    "No AI change/new-disclosure labels generated",
                ],
            )
            verify_seed(seed, digest)
            Path("docs/cplus/evidence/M3-annual-diff-real.json").write_text(
                json.dumps(proof, ensure_ascii=False, indent=2)
            )
            print(json.dumps(proof, ensure_ascii=False))
        finally:
            client.close()


if __name__ == "__main__":
    asyncio.run(main())
