import asyncio
import sqlite3
import threading
from uuid import uuid4

import pytest

from app.conversations.repository import ConversationRepository
from app.research_memory.service import MemoryError, ResearchMemoryService
from tests.test_document_sources import Harness


def op():
    return str(uuid4())


def make(h, embedder=lambda texts: [[1.0, 0.0] for _ in texts]):
    return ResearchMemoryService(
        runtime_root=h.root,
        workspace_id="demo",
        sources=h.service,
        conversations=ConversationRepository(h.registry, "demo"),
        embedder=embedder,
        embedding_model_version="fake-v1",
    )


def test_mutation_replay_revision_and_deletion(tmp_path):
    async def run():
        service = make(Harness(tmp_path))
        oid = op()
        with pytest.raises(MemoryError, match="confirmation_required"):
            await service.mutate(kind="create", operation_id=op(), memory_type="note", text="线索")
        args = dict(
            kind="create", operation_id=oid, memory_type="note", text="线索", confirmed=True
        )
        created = await service.mutate(**args)
        assert await service.mutate(**args) == created
        result = await service.list(q="相关问题")
        assert result["items"][0]["memory_id"] == created["memory_id"]
        generation = result["memory_generation"]
        await service.mutate(
            kind="patch",
            operation_id=op(),
            memory_id=created["memory_id"],
            expected_revision=1,
            text="新线索",
            confirmed=True,
        )
        with pytest.raises(MemoryError, match="memory_context_changed"):
            service.check_generation(generation)
        with pytest.raises(MemoryError, match="memory_revision_conflict"):
            await service.mutate(
                kind="delete",
                operation_id=op(),
                memory_id=created["memory_id"],
                expected_revision=1,
            )
        await service.mutate(
            kind="delete", operation_id=op(), memory_id=created["memory_id"], expected_revision=2
        )
        assert (await service.list(q="相关问题"))["items"] == []
        assert service.operation(oid)["memory_id"] == created["memory_id"]

    asyncio.run(run())


def test_real_source_invalidation(tmp_path):
    async def run():
        h = Harness(tmp_path).ready()
        service = make(h)
        refs = dict(
            company_id=h.company.company_id,
            document_id=h.id,
            source_revision=h.rev,
            evidence_id=h.source["evidence_ids"][0],
        )
        created = await service.mutate(
            kind="create",
            operation_id=op(),
            memory_type="saved_evidence",
            refs=refs,
            confirmed=True,
        )
        row = (await service.list())["items"][0]
        assert row["memory_id"] == created["memory_id"] and row["source_kind"] == "source_evidence"
        with pytest.raises(MemoryError, match="evidence_text_mismatch"):
            await service.mutate(
                kind="create",
                operation_id=op(),
                memory_type="saved_evidence",
                refs=refs,
                text="invented text",
                confirmed=True,
            )
        assert h.correct().status_code == 200
        assert (await service.list())["items"][0]["source_status"] == "stale"
        assert (await service.list(q="example"))["items"] == []

    asyncio.run(run())


def test_late_embedding_cannot_resurrect_deleted_memory(tmp_path):
    async def run():
        started, release = threading.Event(), threading.Event()

        def embed(texts):
            started.set()
            assert release.wait(10)
            return [[1.0, 0.0]]

        service = make(Harness(tmp_path), embed)
        oid = op()
        task = asyncio.create_task(
            service.mutate(
                kind="create",
                operation_id=oid,
                memory_type="note",
                text="late vector",
                confirmed=True,
            )
        )
        assert await asyncio.to_thread(started.wait, 5)
        created = service.operation(oid)
        await service.mutate(
            kind="delete", operation_id=op(), memory_id=created["memory_id"], expected_revision=1
        )
        release.set()
        await task
        with sqlite3.connect(service.path) as db:
            assert db.execute("SELECT vector, embedding_revision FROM items").fetchone() == (
                None,
                None,
            )
        assert (await service.list(q="late"))["items"] == []

    asyncio.run(run())


def test_query_racing_delete_fails_closed(tmp_path):
    async def run():
        started, release = threading.Event(), threading.Event()

        def embed(texts):
            if texts == ["query"]:
                started.set()
                assert release.wait(10)
            return [[1.0, 0.0]]

        service = make(Harness(tmp_path), embed)
        created = await service.mutate(
            kind="create",
            operation_id=op(),
            memory_type="note",
            text="private note",
            confirmed=True,
        )
        task = asyncio.create_task(service.list(q="query"))
        assert await asyncio.to_thread(started.wait, 5)
        await service.mutate(
            kind="delete", operation_id=op(), memory_id=created["memory_id"], expected_revision=1
        )
        release.set()
        with pytest.raises(MemoryError, match="memory_context_changed"):
            await task

    asyncio.run(run())


def test_router_requires_explicit_confirmation(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.research_memory.api import create_research_memory_router

    app = FastAPI()
    app.include_router(create_research_memory_router(make(Harness(tmp_path))))
    client = TestClient(app)
    body = {"operation_id": op(), "type": "note", "text": "synthetic note"}
    assert client.post("/research-memories", json=body).status_code == 422
    assert client.post("/research-memories", json={**body, "confirmed": 1}).status_code == 422
    response = client.post("/research-memories", json={**body, "confirmed": True})
    assert response.status_code == 200
    assert client.get("/research-memories").json()["items"][0]["text"] == "synthetic note"


def test_publication_guard_serializes_delete(tmp_path):
    async def run():
        service = make(Harness(tmp_path))
        item = await service.mutate(
            kind="create", operation_id=op(), memory_type="note", text="memory", confirmed=True
        )
        snapshot = await service.recall_snapshot("query")
        assert snapshot["items"][0]["revision"] == 1
        started, done = threading.Event(), threading.Event()
        failures = []

        def delete():
            started.set()
            try:
                asyncio.run(
                    service.mutate(
                        kind="delete",
                        operation_id=op(),
                        memory_id=item["memory_id"],
                        expected_revision=1,
                    )
                )
            except Exception as exc:
                failures.append(exc)
            finally:
                done.set()

        with service.publication_guard(snapshot["memory_generation"], {item["memory_id"]: 1}):
            thread = threading.Thread(target=delete)
            thread.start()
            assert started.wait(2)
            assert not done.wait(0.2)
            with sqlite3.connect(tmp_path / "job.db") as job:
                job.execute("CREATE TABLE publications (answer TEXT)")
                job.execute("INSERT INTO publications VALUES (?)", ("published",))
            assert not done.is_set()
        assert await asyncio.to_thread(done.wait, 3)
        thread.join()
        assert not failures
        with sqlite3.connect(tmp_path / "job.db") as job:
            assert job.execute("SELECT answer FROM publications").fetchone()[0] == "published"
        with pytest.raises(MemoryError, match="memory_context_changed"):
            with service.publication_guard(snapshot["memory_generation"]):
                pass

    asyncio.run(run())


def test_publication_guard_rejects_wal_and_bad_revisions(tmp_path):
    async def run():
        service = make(Harness(tmp_path))
        item = await service.mutate(
            kind="create", operation_id=op(), memory_type="note", text="memory", confirmed=True
        )
        snapshot = await service.recall_snapshot("query")
        with pytest.raises(MemoryError, match="memory_context_changed"):
            with service.publication_guard(snapshot["memory_generation"], {item["memory_id"]: 2}):
                pass
        with sqlite3.connect(service.path) as db:
            assert db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        with pytest.raises(MemoryError, match="memory_fence_unsupported_journal"):
            with service.publication_guard(snapshot["memory_generation"]):
                pass

    asyncio.run(run())
