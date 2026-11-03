import asyncio
from contextlib import nullcontext
import time
from types import SimpleNamespace
from uuid import uuid4
from app.peer_compare import PeerComparisonService
from app.retrieval_v2.models import TrustedIdentity


def test_candidates_comparability_and_idempotency(tmp_path):
    class DB:
        def execute(self, *args):
            return self

        def fetchone(self):
            return ("delete",)

    class Statements:
        root = tmp_path
        sources = SimpleNamespace(documents=SimpleNamespace(workspace_id="demo"))
        mismatch = False

        async def selected(self, refs):
            cells = [
                dict(
                    cell_id=c,
                    company_id=c,
                    metric_key="total_assets",
                    time={
                        "kind": "instant",
                        "as_of_date": "2025-12-31"
                        if not self.mismatch or c == "a"
                        else "2024-12-31",
                    },
                    basis="PRC_GAAP",
                    scope="consolidated",
                    currency="CNY",
                    normalized_unit="CNY_YUAN",
                    normalized_decimal=v,
                    extraction_status="candidate",
                    financial_review="unconfirmed",
                )
                for c, v in [("a", "100.10"), ("b", "120.30")]
            ]
            return [dict(source={"company_id": c["company_id"]}, cells=[c]) for c in cells], []

        def tx(self, **kw):
            return nullcontext(DB())

        def guard(self, *args):
            pass

        def admitted(self, *args):
            return None

    async def run():
        statements = Statements()
        s = PeerComparisonService(
            tmp_path,
            statements=statements,
            identity_validator=lambda i: None,
            publication_guard=lambda i, f: nullcontext(),
            commit_check=lambda i, f: None,
        )
        i = TrustedIdentity(
            workspace_id="demo",
            instance_id="fake",
            generation=1,
            principal_id="test",
            expires_at=float(time.time() + 100),
        )
        b = dict(
            operation_id=str(uuid4()),
            company_ids=["a", "b"],
            collection_refs=[{"collection_id": c, "cell_ids": [c]} for c in ["a", "b"]],
            candidate_view=True,
        )
        r = await s.compare(b, i)
        g = r["result"]["comparisons"][0]
        assert (
            g["state"] == "candidate_observation"
            and g["differences"][0]["delta_decimal"] == "20.20"
        )
        assert await s.compare(b, i) == r
        statements.mismatch = True
        r = await s.compare({**b, "operation_id": str(uuid4())}, i)
        assert r["result"]["comparisons"][0]["state"] == "incomparable"

    asyncio.run(run())
