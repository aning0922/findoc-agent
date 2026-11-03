"""Durable async acknowledgement, visible progress and cancellation while a tool waits."""

import asyncio
from uuid import uuid4

from tests.test_cplus_batch_research import setup, approved


def test_background_start_exposes_matrix_and_cancel_before_tool_finishes(tmp_path):
    async def run():
        started, release = asyncio.Event(), asyncio.Event()
        calls = []

        async def execute(cell, op, identity):
            calls.append(op)
            started.set()
            await release.wait()
            return dict(domain="retrieval_v2", state="completed", payload={"tier": "UNIT_FAKE"})

        service, identity, body = setup(tmp_path, execute)
        plan = (await service.plan(body, identity))["result"]
        request = approved(plan)
        receipt = await asyncio.wait_for(service.start(request, identity, background=True), 0.5)
        assert receipt["state"] == "completed"
        assert receipt["result"]["dispatch_acknowledged"] is True
        batch = receipt["result"]["batch_id"]
        await started.wait()
        current = await service.read(batch, identity)
        assert [c["state"] for c in current["cells"]] == [
            "dispatching",
            "queued",
            "queued",
            "queued",
        ]
        assert await service.start(request, identity, background=True) == receipt
        assert len(calls) == 1
        await service.cancel(
            batch, dict(operation_id=str(uuid4()), expected_revision=receipt["result"]["revision"]), identity
        )
        release.set()
        await asyncio.gather(*service._tasks)
        matrix = await service.read(batch, identity)
        assert [c["state"] for c in matrix["cells"]] == [
            "completed",
            "cancelled",
            "cancelled",
            "cancelled",
        ]
        assert len(calls) == 1
        assert (
            service.store.operation(request["operation_id"], await service.owner(identity))
            == receipt
        )
        await service.read(batch, identity)
        assert len(calls) == 1

    asyncio.run(run())


def test_interrupted_background_is_unknown_and_never_read_replayed(tmp_path):
    async def run():
        started, release = asyncio.Event(), asyncio.Event()
        calls = []

        async def execute(cell, op, identity):
            calls.append(op)
            started.set()
            await release.wait()
            return dict(domain="retrieval_v2", state="completed", payload={})

        service, identity, body = setup(tmp_path, execute)
        plan = (await service.plan(body, identity))["result"]
        request = approved(plan)
        receipt = await service.start(request, identity, background=True)
        await started.wait()
        tasks = list(service._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        matrix = await service.read(receipt["result"]["batch_id"], identity)
        assert all(c["state"] == "unknown" for c in matrix["cells"])
        assert matrix["state"] == "partial"
        assert len(calls) == 1
        assert await service.start(request, identity, background=True) == receipt
        assert len(calls) == 1

    asyncio.run(run())
