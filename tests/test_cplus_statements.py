"""Synthetic/nohuman service checks plus explicit opt-in readonly public PDF candidate proof."""

import asyncio
import json
import os
from pathlib import Path
import time
from uuid import uuid4
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.finance_v2.service import OwnerAuthorization
from app.finance_v2.contracts import FinanceError
from app.financial_statements_v3 import StatementService, create_statement_router
from app.financial_statements_v3.extraction import extract
from app.financial_statements_v3.models import time_adapter
from app.checkup import CheckupService
from tests.test_finance_v2 import assembled, synthetic_pdf


def op():
    return str(uuid4())


def test_synthetic_nohuman_collection_receipt_trend_revocation_source(tmp_path):
    h, company, doc, source = assembled(tmp_path, synthetic_pdf())
    s = StatementService(tmp_path, h.service)

    async def run():
        c = await s.collect(op(), doc, source["source_revision"])
        assert len(c["cells"]) == 4
        refs = [
            {k: cell[k] for k in ("cell_id", "cell_revision", "payload_sha256")}
            for cell in c["cells"]
        ]
        review = await s.review(op(), refs)
        assert review["acceptable"]
        with pytest.raises(FinanceError, match="owner_authorization_required"):
            await s.confirm(op(), review["id"], review["review_sha256"], True, None)
        absent = await s.trends(op(), [c["id"]], ["total_assets"])
        assert absent["points"] == []
        auth = OwnerAuthorization(tmp_path, "SIMULATED_NO_HUMAN", time.time() + 30)
        receipt = await s.confirm(op(), review["id"], review["review_sha256"], True, auth)
        projected = await s.trends(op(), [c["id"]], ["total_assets"])
        assert len(projected["points"]) == 2
        assert all(p["financial_review"] == "local_operator_confirmed" for p in projected["points"])
        check = await CheckupService(s).create(op(), [c["id"]])
        assert len(check["rules"]) == 3
        await s.revoke(receipt["id"], op(), "synthetic revoke", auth)
        assert (await s.trends(op(), [c["id"]], ["total_assets"]))["points"] == []
        candidate = await s.trends(op(), [c["id"]], ["total_assets"], True)
        assert len(candidate["points"]) == 2
        with pytest.raises(FinanceError, match="explicit_disclosure_selection_required"):
            await s.trends(op(), [c["id"], c["id"]], ["total_assets"], True)
        record = h.docs.get(doc)
        h.objects._resolve_object_path(record.object_key).write_bytes(b"%PDF-corrupt-fixture")
        assert (await s.collection(c["id"]))["source_status"] == "unavailable"
        with pytest.raises(Exception):
            await s.trends(op(), [c["id"]], ["total_assets"], True)

    asyncio.run(run())
    app = FastAPI()
    app.include_router(create_statement_router(s))
    client = TestClient(app)
    assert (
        client.post(
            "/cplus/financial/collections",
            json={
                "operation_id": op(),
                "document_id": doc,
                "expected_source_revision": source["source_revision"],
                "value": 10,
            },
        ).status_code
        == 422
    )
    with pytest.raises(Exception):
        time_adapter.validate_python(
            {"kind": "instant", "as_of_date": "2025-01-01", "period_start": "2024-01-01"}
        )
    with pytest.raises(Exception):
        time_adapter.validate_python(
            {
                "kind": "duration",
                "period_start": "2025-12-31",
                "period_end": "2025-01-01",
                "period_type": "annual",
            }
        )


def test_synthetic_final_owner_expiry_and_unknown(tmp_path):
    h, _, doc, src = assembled(tmp_path, synthetic_pdf())
    s = StatementService(tmp_path, h.service)

    async def run():
        c = await s.collect(op(), doc, src["source_revision"])
        r = await s.review(
            op(),
            [{k: x[k] for k in ("cell_id", "cell_revision", "payload_sha256")} for x in c["cells"]],
        )
        auth = OwnerAuthorization(tmp_path, "SIMULATED_NO_HUMAN", time.time() + 5)
        original = s.guard

        def expired(db, contexts):
            original(db, contexts)
            object.__setattr__(auth, "expires_at", 0)

        s.guard = expired
        oid = op()
        with pytest.raises(FinanceError):
            await s.confirm(oid, r["id"], r["review_sha256"], True, auth)
        assert s.operation(oid)["state"] == "unknown"
        with s.tx() as db:
            assert (
                db.execute("SELECT count(*) FROM records WHERE kind='receipt'").fetchone()[0] == 0
            )

    asyncio.run(run())


def test_readonly_public_two_pdf_candidates():
    mapping = os.environ.get("CPLUS_PUBLIC_PAGE_MAP")
    if not mapping:
        pytest.skip("explicit readonly public PDF map required")
    proof = []
    for f in json.loads(Path(mapping).read_text())["files"][:2]:
        source = dict(
            company_id="public-proof-only",
            document_id=f["document_id"],
            source_revision="a" * 64,
            content_sha256=f["sha256"],
            parser_version="fast-pdf-public-proof",
            report_year=int(f["public_id"][-4:]),
            basis="PRC_GAAP",
        )
        cells = extract(source, Path(f["object_path"]).read_bytes())
        assert len(cells) >= 10
        year = int(f["public_id"][-4:])
        expected = {
            2025: {
                "revenue": "170447058533.57",
                "net_profit_parent": "29003103411.66",
                "operating_cash_flow": "46383114754.02",
                "total_assets": "391371999819.49",
                "total_liabilities": "241580719144.79",
            },
            2024: {
                "revenue": "189163654064.64",
                "net_profit_parent": "32184570372.28",
                "operating_cash_flow": "29369250570.66",
                "total_assets": "368031704522.86",
                "total_liabilities": "226518009574.89",
            },
        }[year]
        for key, amount in expected.items():
            matching = [
                c
                for c in cells
                if c["metric_key"] == key
                and (c["time"].get("as_of_date") or c["time"].get("period_end")) == f"{year}-12-31"
            ]
            assert len(matching) == 1 and matching[0]["normalized_decimal"] == amount
        assert any(c["time"].get("as_of_date") == f"{year}-01-01" for c in cells)

        assert {
            "total_assets",
            "total_liabilities",
            "revenue",
            "net_profit_parent",
            "operating_cash_flow",
        } <= {x["metric_key"] for x in cells}
        assert {x["statement_kind"] for x in cells} == {
            "balance_sheet",
            "income_statement",
            "cash_flow_statement",
        }
        assert all(x["financial_review"] == "unconfirmed" for x in cells)
        proof.append({"public_id": f["public_id"], "pdf_sha256": f["sha256"], "cells": cells})
    destination = os.environ.get("CPLUS_CANDIDATE_PROOF")
    if destination:
        Path(destination).write_text(
            json.dumps(
                {
                    "tier": "REAL_PUBLIC_PDF_CANDIDATES",
                    "human_approvals": 0,
                    "llm_calls": 0,
                    "note": "source_revision/parser/company in direct extractor proof are synthetic adapter identities, not current runtime admission",
                    "files": proof,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
