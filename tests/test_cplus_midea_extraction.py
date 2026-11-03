"""Explicit public seed test only; no developer DB, owner approval, BGE or LLM.

Run: CPLUS_PUBLIC_SEED=<readonly public seed> pytest -q tests/test_cplus_midea_extraction.py
Writes public candidate/Decimal diagnostics to /tmp/cplus-midea-extraction-proof.json.
Midea combined four-column statements: physical 132/133/135/137, consolidated
2025 columns, RMB thousands. Frozen original Gree payloads for both years must
remain byte-equivalent after canonical serialization. Peer endpoint itself still
requires root's duplicate-financial_review-keyword correction; no endpoint PASS
is inferred from this candidate arithmetic proof.
"""

import asyncio
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess

import pymupdf
import pytest
from app.demo.seed import materialize, verify_seed
from app.financial_statements_v3 import StatementService
from app.financial_statements_v3.extraction import extract
from tests.test_document_sources import Harness

CORE = {"total_assets", "total_liabilities", "revenue", "net_profit_parent", "operating_cash_flow"}


def test_real_midea_core_five_and_gree_regression(tmp_path):
    value = os.environ.get("CPLUS_PUBLIC_SEED")
    if not value:
        pytest.skip("explicit readonly public seed required")
    seed = Path(value).resolve()
    _, digest = verify_seed(seed)
    root = tmp_path / "runtime"
    materialize(seed, root, digest)
    h = Harness(root)
    service = StatementService(root, h.service)
    # Frozen trusted baseline executes only the original extractor for exact Gree regression.
    original = subprocess.run(
        ["git", "show", "76ec04f:app/financial_statements_v3/extraction.py"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    namespace = {"__package__": "app.financial_statements_v3"}
    exec(compile(original, "baseline-extraction.py", "exec"), namespace)
    baseline = namespace["extract"]

    async def run():
        samples = []
        for record in h.docs.list_by_workspace("demo"):
            try:
                source = await h.service.source(record.document_id)
            except Exception:
                continue
            context, _ = await service.context(record.document_id, source["source_revision"])
            raw = await h.service.file(
                record.document_id,
                source_revision=source["source_revision"],
                company_id=source["company_id"],
            )
            cells = extract(context, raw)
            code = h.companies.get(source["company_id"]).security_code
            if code == "000651":
                assert cells == baseline(context, raw), (
                    "Gree extraction changed from frozen baseline"
                )
            elif code != "000333":
                continue
            samples.append((code, source["report_year"], cells, raw))
        assert sorted((c, y) for c, y, _, _ in samples) == [
            ("000333", 2025),
            ("000651", 2024),
            ("000651", 2025),
        ]
        midea = next(s for s in samples if s[:2] == ("000333", 2025))

        def chosen(cells):
            return {
                c["metric_key"]: c
                for c in cells
                if c["metric_key"] in CORE
                and c["extraction_status"] == "candidate"
                and (
                    c["time"].get("as_of_date") == "2025-12-31"
                    or (
                        c["time"].get("period_start") == "2025-01-01"
                        and c["time"].get("period_end") == "2025-12-31"
                    )
                )
            }

        selected = chosen(midea[2])
        assert set(selected) == CORE
        assert selected["revenue"]["raw_decimal"] == "456451731"
        assert selected["net_profit_parent"]["raw_decimal"] == "43945411"
        assert selected["operating_cash_flow"]["raw_decimal"] == "53345930"
        pdf = pymupdf.open(stream=midea[3], filetype="pdf")
        for c in selected.values():
            assert (
                c["scope"] == "consolidated"
                and c["raw_unit"] == "千元"
                and c["financial_review"] == "unconfirmed"
            )
            assert Decimal(c["normalized_decimal"]) == Decimal(c["raw_decimal"]) * 1000
            evidence = c["evidence_refs"][0]
            words = pdf[evidence["physical_page"] - 1].get_text("words")
            assert any(
                list(w[:4]) == evidence["bbox"] and w[4] == evidence["raw_value"] for w in words
            )
            assert evidence["column_index"] == 0
            assert [w[4] for w in evidence["header_words"] if w[4] in ("合并", "公司")] == [
                "合并",
                "合并",
                "公司",
                "公司",
            ]
        gree = chosen(next(s[2] for s in samples if s[:2] == ("000651", 2025)))
        assert CORE <= set(gree)
        comparisons = []
        for metric in sorted(CORE):
            a, b = gree[metric], selected[metric]
            assert all(
                a[k] == b[k] for k in ("time", "basis", "scope", "currency", "normalized_unit")
            )
            comparisons.append(
                dict(
                    metric_key=metric,
                    left_gree_decimal=a["normalized_decimal"],
                    right_midea_decimal=b["normalized_decimal"],
                    delta_midea_minus_gree_decimal=format(
                        Decimal(b["normalized_decimal"]) - Decimal(a["normalized_decimal"]), "f"
                    ),
                    state="candidate_observation",
                    left_page=a["evidence_refs"][0]["physical_page"],
                    right_page=b["evidence_refs"][0]["physical_page"],
                )
            )
        proof = dict(
            tier="REAL_PUBLIC_PDF_CANDIDATES_AND_DECIMAL",
            seed_manifest_sha256=digest,
            midea_cells=[
                {
                    k: c[k]
                    for k in ("metric_key", "time", "raw_decimal", "raw_unit", "normalized_decimal")
                }
                | {"page": c["evidence_refs"][0]["physical_page"]}
                for c in selected.values()
            ],
            gree_regression="exact_original_payload_equality_2024_2025",
            comparisons=comparisons,
            llm_calls=0,
            human_approvals=0,
            limitations=[
                "Candidate arithmetic only, no confirmed authority",
                "Existing peer service financial_review duplicate keyword blocks endpoint until root fix",
            ],
        )
        Path("/tmp/cplus-midea-extraction-proof.json").write_text(
            json.dumps(proof, ensure_ascii=False, indent=2)
        )
        verify_seed(seed, digest)

    asyncio.run(run())
