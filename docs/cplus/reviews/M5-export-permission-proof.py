"""Controlled root-wiring reproduction; temporary CSV, fake permission/source service."""

import asyncio
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from app.cplus.exports import register_exports
from app.exports_v2.projection import digest
from app.retrieval_v2 import TrustedIdentity
from app.retrieval_v2.models import RetrievalError
import time


async def main(root):
    allowed = [True]
    snapshot = dict(
        schema_version="cplus-research-answer-v1",
        answer_id="answer",
        context_id="context",
        question="fixture",
        findings=[],
        financial_authority=False,
    )
    context = dict(parent_conversation_id="parent", selected_sources=[])

    async def authorize(identity):
        return "fixture-owner"

    def selection(*args):
        if not allowed[0]:
            raise RetrievalError("parent_display_revoked", 403)

    @contextmanager
    def guard(*args):
        yield

    identity = TrustedIdentity(
        workspace_id="demo",
        instance_id="fixture",
        generation=1,
        principal_id="fixture",
        expires_at=time.time() + 300,
    )
    app = FastAPI()
    register_exports(
        app,
        root,
        hybrid=SimpleNamespace(
            authorize=authorize,
            read=lambda kind, identifier, owner: snapshot if kind == "answer" else context,
        ),
        annual=None,
        peer=None,
        statements=None,
        identity_provider=lambda request: identity,
        validate=lambda identity: None,
        guard=guard,
        conversations=SimpleNamespace(selection=selection),
    )
    service = app.state.cplus_export_service
    body = dict(
        operation_id=str(uuid4()),
        report_ref=dict(
            domain="research_answer_v1", id="answer", revision=1, payload_sha256=digest(snapshot)
        ),
        formats=["csv"],
        export_profile_version="research-v1",
    )
    created = await service.create(body, identity)
    eid = created["result"]["export_id"]
    first, first_sha = await service.file(eid, "csv", identity)
    allowed[0] = False
    try:
        await service.create({**body, "operation_id": str(uuid4())}, identity)
    except RetrievalError as exc:
        assert exc.code == "parent_display_revoked"
    else:
        raise AssertionError("expected new export permission denial")
    raw, sha = await service.file(eid, "csv", identity)
    assert raw == first and sha == first_sha
    print(
        "REPRODUCED: new export rejects revoked parent display permission; existing file returns identical bytes"
    )


if __name__ == "__main__":
    with TemporaryDirectory(prefix="m5-permission-review-") as tmp:
        asyncio.run(main(Path(tmp)))
