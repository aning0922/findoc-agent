"""Publication races against real temporary SQLite databases; zero provider/approval."""

import asyncio
from contextlib import contextmanager
import sqlite3
from threading import Thread
import time
from uuid import uuid4

import pytest
from app.financial_statements_v3 import StatementService
from app.finance_v2.contracts import FinanceError
from app.retrieval_v2 import HybridRetrievalService, TrustedIdentity
from app.retrieval_v2.models import RetrievalError
from tests.test_finance_v2 import assembled, synthetic_pdf
from tests.test_parse_v2 import fixture, run


def test_finance_source_shared_lock_blocks_real_writer_and_wal_refused(tmp_path, monkeypatch):
    h, company, doc, src = assembled(tmp_path, synthetic_pdf())
    s = StatementService(tmp_path, h.service)
    original = s.guard
    outcome = []

    def guard(db, contexts):
        original(db, contexts)

        def writer():
            with sqlite3.connect(tmp_path / "documents.db", timeout=0.05) as other:
                try:
                    other.execute(
                        "UPDATE companies SET name=? WHERE company_id=?", ("racing writer", company)
                    )
                    other.commit()
                    outcome.append("WRONG committed")
                except sqlite3.OperationalError:
                    other.rollback()
                    outcome.append("blocked")

        thread = Thread(target=writer)
        thread.start()
        thread.join(2)
        assert not thread.is_alive()

    s.guard = guard
    asyncio.run(s.collect(str(uuid4()), doc, src["source_revision"]))
    assert outcome == ["blocked"]
    connect = sqlite3.connect
    switches = []

    def instrument(*args, **kwargs):
        connection = connect(*args, **kwargs)
        attached = [False]

        def trace(sql):
            if sql.startswith("ATTACH DATABASE"):
                attached[0] = True
            if attached[0] and sql == "BEGIN" and not switches:

                def switch():
                    with connect(tmp_path / "documents.db", timeout=0.1) as writer:
                        switches.append(writer.execute("PRAGMA journal_mode=WAL").fetchone()[0])

                thread = Thread(target=switch)
                thread.start()
                thread.join(2)
                assert not thread.is_alive()

        connection.set_trace_callback(trace)
        return connection

    monkeypatch.setattr(sqlite3, "connect", instrument)
    op = str(uuid4())
    with pytest.raises(FinanceError, match="wal_source_fence_unsupported"):
        asyncio.run(s.collect(op, doc, src["source_revision"]))
    assert switches == ["wal"]
    assert s.operation(op)["state"] == "unknown"


@pytest.mark.parametrize("kind", ["build", "search", "enrollment", "context", "answer"])
def test_each_retrieval_write_rolls_back_before_commit_on_real_expiry(tmp_path, kind):
    h, doc, _, _, revision, _, parse = fixture(tmp_path)
    run(parse.retry(doc, str(uuid4()), revision))
    artifact = run(parse.quality(doc))

    @contextmanager
    def guard(i, c):
        yield

    checks = []
    service = HybridRetrievalService(
        tmp_path,
        h.service,
        parse,
        None,
        identity_validator=lambda i: None,
        publication_guard=guard,
        before_commit=lambda i: checks.append(i.generation),
    )
    identity = TrustedIdentity(
        workspace_id="demo",
        instance_id="test",
        generation=1,
        principal_id="fake",
        expires_at=time.time() + 100,
    )

    async def test():
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
        context = (
            await service.mutate(
                "context",
                dict(
                    operation_id=str(uuid4()),
                    title="test",
                    selected_sources=[enrollment["source_ref"]],
                ),
                identity,
            )
        )["result"]
        bodies = dict(
            build=dict(sources=[enrollment["source_ref"]]),
            search=dict(sources=[enrollment["source_ref"]], query="营业收入", top_k=5),
            enrollment=dict(
                document_id=doc,
                artifact_id=artifact["artifact_id"],
                expected_source_revision=revision,
                expected_artifact_sha256=artifact["output_sha256"],
                selected_pages=[1],
                confirmed=True,
            ),
            context=dict(title="test", selected_sources=[enrollment["source_ref"]]),
            answer=dict(
                context_id=context["context_id"],
                context_revision=1,
                context_sha256=context["context_sha256"],
                question="营业收入",
            ),
        )
        original = service.tx

        @contextmanager
        def delayed(*, before_commit=None):
            # Wrap the SAME writer connection. Final objects INSERT makes the deadline elapse.
            with original(before_commit=before_commit) as db:

                def expire():
                    object.__setattr__(identity, "expires_at", time.time() + 0.02)
                    time.sleep(0.04)
                    return 0

                db.create_function("expire_test", 0, expire)
                yield db

        service.tx = delayed
        with original() as db:
            db.executescript(
                "CREATE TRIGGER slow_final AFTER INSERT ON objects BEGIN SELECT expire_test(); END;"
            )
            before = db.execute("SELECT count(*) FROM objects").fetchone()[0]
            passages = db.execute("SELECT count(*) FROM passages").fetchone()[0]
        oid = str(uuid4())
        with pytest.raises(RetrievalError, match="lease_expired"):
            await service.mutate(kind, dict(operation_id=oid, **bodies[kind]), identity)
        # Read with SQLite directly: an expired caller cannot use authenticated reads.
        with sqlite3.connect(service.path) as db:
            assert db.execute("SELECT count(*) FROM objects").fetchone()[0] == before
            assert db.execute("SELECT count(*) FROM passages").fetchone()[0] == passages
            assert (
                db.execute("SELECT state FROM operations WHERE id=?", (oid,)).fetchone()[0]
                == "unknown"
            )
        assert checks

    asyncio.run(test())
