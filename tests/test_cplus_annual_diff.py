import asyncio
from contextlib import nullcontext
import sqlite3
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.annual_diff import AnnualDiffRequest, AnnualDiffService
from app.annual_diff.models import AnnualDiffError
from app.retrieval_v2.models import SourceRef, EvidenceRef, TrustedIdentity


def setup(root, provider=None):
    sqlite3.connect(root / "documents.db").close()
    sources = SimpleNamespace(
        documents=SimpleNamespace(
            workspace_id="demo", _repository=SimpleNamespace(_database_path=root / "documents.db")
        )
    )

    class Hybrid:
        memory = None

        def __init__(self):
            self.root, self.sources, self.missing, self.stale = root, sources, False, False

        async def records(self, ref):
            if self.stale:
                raise AnnualDiffError("source_changed")
            return []

        async def verify(self, ref):
            await self.records(ref.source_ref)

        async def search(self, refs, q, top_k):
            ref = refs[0]
            text = (
                "主要风险：原材料与市场竞争。"
                if "风险" in q
                else "主要业务：测试产品。"
                if "业务" in q
                else "研发项目：测试技术。"
            )
            e = EvidenceRef(
                source_ref=ref, evidence_id=ref.document_id + q, physical_page=2, text=text
            )
            return {
                "items": []
                if self.missing and ref.report_year == 2024
                else [
                    dict(
                        evidence_ref=e.model_dump(),
                        lexical_rank=1,
                        dense_cosine=None,
                        rerank_score=0.03,
                    )
                ],
                "index_status": "ready",
            }

    hybrid = Hybrid()
    service = AnnualDiffService(
        root,
        hybrid=hybrid,
        sources=sources,
        identity_validator=lambda i: None,
        publication_guard=lambda i, f: nullcontext(),
        commit_check=lambda i, f: None,
        provider_json=provider,
    )
    identity = TrustedIdentity(
        workspace_id="demo",
        instance_id="fixture",
        generation=1,
        principal_id="test",
        expires_at=float(time.time() + 100),
    )

    def source(y):
        return SourceRef(
            kind="fast",
            workspace_id="demo",
            company_id="c",
            document_id=str(y),
            source_revision=f"rev{y}",
            content_sha256="sha",
            parser_version="fake",
            report_year=y,
            identity_status="fast_source_verified",
        )

    request = AnnualDiffRequest(
        operation_id=str(uuid4()), left_source=source(2024), right_source=source(2025)
    )
    return service, hybrid, identity, request


def test_alignment_missing_immutable_and_replay(tmp_path):
    async def run():
        s, h, i, r = setup(tmp_path)
        out = await s.create(r, i)
        assert all(p["program_label"] == "continued" for p in out["result"]["topics"])
        assert await s.create(r, i) == out
        with sqlite3.connect(s.path) as db:
            with pytest.raises(sqlite3.IntegrityError):
                db.execute("UPDATE results SET payload='{}'")
        h.missing = True
        out = await s.create(r.model_copy(update={"operation_id": str(uuid4())}), i)
        assert all(p["program_label"] == "insufficient" for p in out["result"]["topics"])
        h.stale = True
        assert (await s.read(out["result_id"], i))[
            "current_source_status"
        ] == "stale_or_unavailable"

    asyncio.run(run())


def test_cross_company_rejected_and_guard_final_change(tmp_path):
    async def run():
        s, h, i, r = setup(tmp_path)
        other = r.right_source.model_copy(update={"company_id": "other"})
        with pytest.raises(AnnualDiffError, match="same_company"):
            await s.create(r.model_copy(update={"right_source": other}), i)

        def reject(identity, fence):
            raise AnnualDiffError("lease_changed")

        s.guard = reject
        with pytest.raises(AnnualDiffError, match="lease_changed"):
            await s.create(r.model_copy(update={"operation_id": str(uuid4())}), i)
        assert not sqlite3.connect(s.path).execute("SELECT * FROM results").fetchall()
        s.guard = lambda i, f: nullcontext()
        s.commit_check = lambda i, f: False
        with pytest.raises(AnnualDiffError, match="before_commit"):
            await s.create(r.model_copy(update={"operation_id": str(uuid4())}), i)
        assert not sqlite3.connect(s.path).execute("SELECT * FROM results").fetchall()

    asyncio.run(run())


def test_provider_unknown_never_retries(tmp_path):
    async def run():
        calls = []

        def provider(*args):
            calls.append(1)
            raise TimeoutError()

        s, h, i, r = setup(tmp_path, provider)
        old = h.search

        async def search(refs, q, top_k):
            out = await old(refs, q, top_k)
            out["items"][0]["evidence_ref"]["text"] += str(refs[0].report_year)
            return out

        h.search = search
        r = r.model_copy(update={"generate_explanation": True})
        with pytest.raises(TimeoutError):
            await s.create(r, i)
        assert (await s.create(r, i))["state"] == "unknown" and len(calls) == 1

    asyncio.run(run())
