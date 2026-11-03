import asyncio
from app.retrieval_v2 import HybridRetrievalService, SourceRef
from tests.test_document_sources import Harness
from app.rag.retriever import SearchHit


def test_lexical_only_never_fakes_cosine(tmp_path):
    async def run():
        h = Harness(tmp_path).ready()
        s = h.source
        ref = SourceRef(
            kind="fast",
            identity_status="fast_source_verified",
            workspace_id="demo",
            **{
                k: s[k]
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
        service = HybridRetrievalService(tmp_path, h.service, None, None)
        await service.build([ref])
        r = await service.search([ref], "Example report")
        assert r["items"] and all(c["dense_cosine"] is None for c in r["items"])
        assert await service.legacy_fast_adapter([ref], "Example report") == ()
        e = await service.records(ref)
        hit = SearchHit(
            0.6,
            "real-dense-id",
            e[0].text,
            e[0].physical_page,
            "fixture.pdf",
            "paragraph",
            workspace_id="demo",
            document_id=ref.document_id,
            source_revision=ref.source_revision,
        )
        service.dense_search = lambda *args: [hit]
        assert (await service.legacy_fast_adapter([ref], "Example report"))[0].score == 0.6

    asyncio.run(run())
