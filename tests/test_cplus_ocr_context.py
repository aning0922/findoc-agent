import asyncio
from contextlib import nullcontext
import time
from uuid import uuid4
import pytest
from app.retrieval_v2 import HybridRetrievalService, TrustedIdentity
from app.retrieval_v2.models import RetrievalError
from tests.test_parse_v2 import fixture, run


def test_ocr_enrollment_context_immutable_answer_and_parent_delete(tmp_path):
    h, doc, _, _, revision, engine, parse = fixture(tmp_path)
    run(parse.retry(doc, str(uuid4()), revision))
    artifact = run(parse.quality(doc))
    calls = []

    def provider(q, e):
        calls.append(q)
        return {"text": "候选转录需要核对原图。"}

    alive = [True]

    def parent(cid):
        if not alive[0]:
            raise RetrievalError("parent_deleted")

    service = HybridRetrievalService(
        tmp_path,
        h.service,
        parse,
        None,
        provider_once=provider,
        identity_validator=lambda i: None,
        publication_guard=lambda i, c: nullcontext(),
        parent_validator=parent,
    )
    identity = TrustedIdentity(
        workspace_id="demo",
        instance_id="test",
        generation=1,
        principal_id="test",
        expires_at=float(time.time() + 100),
    )

    async def run_case():
        enrollment = (
            await service.mutate(
                "enrollment",
                dict(
                    operation_id=str(uuid4()),
                    document_id=doc,
                    artifact_id=artifact["artifact_id"],
                    expected_source_revision=revision,
                    expected_artifact_sha256=artifact["output_sha256"],
                    selected_pages=[1],
                    confirmed=True,
                ),
                identity,
            )
        )["result"]
        ref = enrollment["source_ref"]
        context = (
            await service.mutate(
                "context",
                dict(
                    operation_id=str(uuid4()),
                    title="OCR",
                    selected_sources=[ref],
                    parent_conversation_id="parent",
                ),
                identity,
            )
        )["result"]
        from app.retrieval_v2.models import SourceRef

        await service.build([SourceRef.model_validate(ref)])
        body = dict(
            operation_id=str(uuid4()),
            context_id=context["context_id"],
            context_revision=1,
            context_sha256=context["context_sha256"],
            question="营业收入候选未核对",
        )
        answer = await service.mutate("answer", body, identity)
        assert answer["result"]["state"] == "completed" and len(calls) == 1
        assert await service.mutate("answer", body, identity) == answer and len(calls) == 1
        assert answer["result"]["financial_authority"] is False
        alive[0] = False
        with pytest.raises(RetrievalError, match="parent_deleted"):
            await service.mutate("answer", {**body, "operation_id": str(uuid4())}, identity)
        assert len(calls) == 1
        assert (await h.documents.get_document(doc)).status.value == "failed"

    asyncio.run(run_case())


def test_provider_unknown_is_not_replayed(tmp_path):
    h, doc, _, _, revision, _, parse = fixture(tmp_path)
    run(parse.retry(doc, str(uuid4()), revision))
    a = run(parse.quality(doc))
    calls = []

    def provider(*args):
        calls.append(1)
        raise TimeoutError("fixture unknown")

    service = HybridRetrievalService(
        tmp_path,
        h.service,
        parse,
        None,
        provider_once=provider,
        identity_validator=lambda i: None,
        publication_guard=lambda i, c: nullcontext(),
    )
    identity = TrustedIdentity(
        workspace_id="demo",
        instance_id="test",
        generation=1,
        principal_id="test",
        expires_at=float(time.time() + 100),
    )

    async def execute():
        e = (
            await service.mutate(
                "enrollment",
                dict(
                    operation_id=str(uuid4()),
                    document_id=doc,
                    artifact_id=a["artifact_id"],
                    expected_source_revision=revision,
                    expected_artifact_sha256=a["output_sha256"],
                    selected_pages=[1],
                    confirmed=True,
                ),
                identity,
            )
        )["result"]
        c = (
            await service.mutate(
                "context",
                dict(operation_id=str(uuid4()), title="OCR", selected_sources=[e["source_ref"]]),
                identity,
            )
        )["result"]
        from app.retrieval_v2 import SourceRef

        await service.build([SourceRef.model_validate(e["source_ref"])])
        b = dict(
            operation_id=str(uuid4()),
            context_id=c["context_id"],
            context_revision=1,
            context_sha256=c["context_sha256"],
            question="营业收入候选未核对",
        )
        with pytest.raises(TimeoutError):
            await service.mutate("answer", b, identity)
        assert (await service.mutate("answer", b, identity))["state"] == "unknown"
        assert len(calls) == 1

    asyncio.run(execute())
