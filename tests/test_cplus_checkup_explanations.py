import asyncio
from contextlib import contextmanager, nullcontext
import copy
import time
from types import SimpleNamespace
from uuid import uuid4
import pytest
from app.checkup.explanations import CheckupExplanationService, ExplanationRequest
from app.retrieval_v2.models import TrustedIdentity, RetrievalError
from app.retrieval_v2.service import sha


def setup(root, provider):
    class DB:
        def execute(self, *args):
            return self

        def fetchone(self):
            return ("delete",)

    class Statements:
        def __init__(self):
            self.root = root
            self.sources = SimpleNamespace(documents=SimpleNamespace(workspace_id="demo"))
            self.locks = 0
            self.receipt = None
            self.checkup = dict(
                id="old",
                schema_version="checkup-v1",
                candidate_view=True,
                collection_refs=["collection"],
                rules=[
                    dict(
                        rule_id="cash_profit_divergence",
                        status="candidate_observation",
                        observation="direction_diverges",
                        input_refs=["cell"],
                    )
                ],
            )

        def read(self, *args):
            return copy.deepcopy(self.checkup)

        async def selected(self, refs):
            return [
                dict(
                    source={"document_id": "doc"},
                    cells=[
                        dict(
                            cell_id="cell", normalized_decimal="10", financial_review="unconfirmed"
                        )
                    ],
                )
            ], []

        @contextmanager
        def tx(self, **kw):
            self.locks += 1
            try:
                yield DB()
            finally:
                self.locks -= 1

        def guard(self, *args):
            pass

        def admitted(self, *args):
            return self.receipt

    s = Statements()
    service = CheckupExplanationService(
        root,
        statements=s,
        identity_validator=lambda i: None,
        publication_guard=lambda i, f: nullcontext(),
        commit_check=lambda i, f: None,
        provider_json=provider,
    )
    identity = TrustedIdentity(
        workspace_id="demo",
        instance_id="fake",
        generation=1,
        principal_id="test",
        expires_at=float(time.time() + 100),
    )

    def request():
        return ExplanationRequest(
            operation_id=str(uuid4()),
            checkup_id="old",
            expected_payload_sha256=sha(s.checkup),
            confirmed=True,
        )

    return service, s, identity, request


def test_snapshot_one_call_no_read_locks_and_history(tmp_path):
    async def run():
        calls = []

        async def provider(snapshot, identity):
            assert s.locks == 0
            assert snapshot["input_cells"][0]["financial_review"] == "unconfirmed"
            calls.append(snapshot)
            return {
                "explanations": [
                    dict(
                        rule_id="cash_profit_divergence",
                        text="观察提示变化方向，需对照原文核查。",
                        input_refs=["cell"],
                    )
                ]
            }

        service, s, i, request = setup(tmp_path, provider)
        before = copy.deepcopy(s.checkup)
        r = request()
        result = await service.create(r, i)
        assert (
            result["result"]["interpretation_review_status"] == "ai_unreviewed" and len(calls) == 1
        )
        assert await service.create(r, i) == result
        await service.read(result["result"]["explanation_id"], i)
        assert len(calls) == 1 and s.checkup == before

    asyncio.run(run())


def test_insufficient_no_call_and_unknown_no_retry(tmp_path):
    async def run():
        calls = []

        def provider(*args):
            calls.append(1)
            raise TimeoutError()

        service, s, i, request = setup(tmp_path, provider)
        r = request()
        with pytest.raises(TimeoutError):
            await service.create(r, i)
        assert (await service.create(r, i))["state"] == "unknown" and len(calls) == 1
        s.checkup["rules"][0].update(status="insufficient", observation=None)
        result = await service.create(request(), i)
        assert result["result"]["provider_outcome"] == "not_called_insufficient" and len(calls) == 1

    asyncio.run(run())


def test_receipt_change_and_final_identity_reject_publication(tmp_path):
    async def run():
        def provider(*args):
            s.receipt = "changed"
            return {"explanations": []}

        service, s, i, request = setup(tmp_path, provider)
        with pytest.raises(RetrievalError, match="inputs_changed"):
            await service.create(request(), i)
        service.provider = lambda *args: {
            "explanations": [
                dict(
                    rule_id="cash_profit_divergence",
                    text="利润增加123，因为需求增长",
                    input_refs=["cell"],
                )
            ]
        }
        with pytest.raises(RetrievalError, match="numeric_or_causal"):
            await service.create(request(), i)
        service.provider = None
        service.commit_check = lambda i, f: False
        with pytest.raises(RetrievalError, match="before_commit"):
            await service.create(request(), i)
        with service.store.tx() as db:
            assert db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 0

    asyncio.run(run())
