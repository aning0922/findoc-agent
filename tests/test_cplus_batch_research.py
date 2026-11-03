import asyncio
from contextlib import nullcontext
import time
from uuid import uuid4
import pytest
from app.batch_research import BatchResearchService
from app.retrieval_v2.models import TrustedIdentity, RetrievalError


def setup(tmp_path, execute):
    async def prepare(c, i):
        return {
            "selected_sources": [{"company_id": c["company_id"], "workspace_id": "demo"}],
            "memory_generation": 0,
        }

    service = BatchResearchService(
        tmp_path,
        identity_validator=lambda i: None,
        publication_guard=lambda i, f: nullcontext(),
        commit_check=lambda i, f: None,
        prepare_cell=prepare,
        validate_prepared=lambda p, i: None,
        execute_cell=execute,
    )
    identity = TrustedIdentity(
        workspace_id="demo",
        instance_id="fake",
        generation=1,
        principal_id="test",
        expires_at=float(time.time() + 100),
    )
    body = dict(
        operation_id=str(uuid4()),
        preparation_confirmed=True,
        cells=[
            dict(cell_key=c + t, company_id=c, template=t)
            for c in ("a", "b")
            for t in ("risk_excerpt", "annual_changes")
        ],
    )
    return service, identity, body


def approved(plan):
    return dict(
        operation_id=str(uuid4()),
        batch_plan_id=plan["batch_plan_id"],
        batch_plan_revision=1,
        batch_plan_sha256=plan["batch_plan_sha256"],
        confirmed=True,
    )


def test_two_by_two_approval_unknown_no_replay(tmp_path):
    async def run():
        calls = []

        async def execute(c, op, i):
            calls.append(op)
            if len(calls) == 1:
                raise TimeoutError()
            return dict(domain="retrieval_v2", state="completed", payload={"tier": "UNIT_FAKE"})

        s, i, b = setup(tmp_path, execute)
        plan = (await s.plan(b, i))["result"]
        assert not calls
        req = approved(plan)
        with pytest.raises(RetrievalError, match="approval"):
            await s.start({**req, "operation_id": str(uuid4()), "confirmed": False}, i)
        assert not calls
        r = await s.start(req, i)
        assert len(calls) == 4 and r["result"]["state"] == "partial"
        assert [c["state"] for c in r["result"]["cells"]].count("unknown") == 1
        assert await s.start(req, i) == r and len(calls) == 4
        await s.read(r["result"]["batch_id"], i)
        assert len(calls) == 4

    asyncio.run(run())


def test_cancel_queued_and_final_commit_rejection(tmp_path):
    async def run():
        started, release = asyncio.Event(), asyncio.Event()
        calls = []

        async def execute(c, op, i):
            calls.append(op)
            started.set()
            await release.wait()
            return dict(domain="annual_diff", state="completed", payload={"tier": "UNIT_FAKE"})

        s, i, b = setup(tmp_path, execute)
        plan = (await s.plan(b, i))["result"]
        req = approved(plan)
        task = asyncio.create_task(s.start(req, i))
        await started.wait()
        op = s.store.operation(req["operation_id"], await s.owner(i))
        batch = op["result"]["batch_id"]
        current = await s.read(batch, i)
        assert current["state"] == "running"
        await s.cancel(
            batch, dict(operation_id=str(uuid4()), expected_revision=current["revision"]), i
        )
        release.set()
        await task
        matrix = await s.read(batch, i)
        assert len(calls) == 1 and [c["state"] for c in matrix["cells"]].count("cancelled") == 3
        s.commit_check = lambda i, f: False
        with pytest.raises(RetrievalError, match="before_commit"):
            await s.plan({**b, "operation_id": str(uuid4())}, i)

    asyncio.run(run())
