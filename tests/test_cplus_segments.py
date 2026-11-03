"""Read-only public proof is opt-in; no financial confirmation or model calls."""

import hashlib
import os
from pathlib import Path
import pytest
from app.financial_statements_v3.segments import extract_segments
from tests.test_finance_v2 import synthetic_pdf


def source(raw):
    return dict(
        workspace_id="SYNTHETIC_PUBLIC_EXTRACTOR_PROOF",
        company_id="SYNTHETIC_ADAPTER_NOT_RUNTIME",
        document_id="6086c34fb2c61f64e9d57a572fb560232dc71ad642a3359e3085fc438ef193ec",
        source_revision="SYNTHETIC_NOT_RUNTIME_ADMISSION",
        content_sha256=hashlib.sha256(raw).hexdigest(),
        parser_version="direct-public-pdf-proof",
        report_year=2025,
        basis="unknown",
    )


def test_segments_missing_is_honest_and_changed_bytes_rejected():
    raw = synthetic_pdf()
    s = source(raw)
    result = extract_segments(s, raw)
    assert result["groups"] == [] and result["limitations"] == [
        "supported_revenue_composition_table_not_found"
    ]
    with pytest.raises(ValueError, match="pdf_hash_changed"):
        extract_segments(s, raw + b"changed")


def test_readonly_gree_2025_composition():
    path = os.environ.get("CPLUS_SEGMENT_PUBLIC_PDF")
    if not path:
        pytest.skip("explicit readonly public PDF required")
    raw = Path(path).read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "7cc972f2d199e2ec3797cc5da479e8268afa59b77875770de3bcd3648242fb8c"
    )
    result = extract_segments(source(raw), raw)
    assert len(result["groups"]) == 4
    product = next(
        g
        for g in result["groups"]
        if g["dimension"] == "product" and g["time"]["period_end"] == "2025-12-31"
    )
    region = next(
        g
        for g in result["groups"]
        if g["dimension"] == "region" and g["time"]["period_end"] == "2025-12-31"
    )
    assert len(product["items"]) == 5 and len(region["items"]) == 3
    assert product["raw_disclosed_total_decimal"] == "170447058533.57"
    assert product["items"][0]["normalized_decimal"] == "133055208627.13"
    assert region["items"][0]["normalized_decimal"] == "126407077425.42"
    assert all(g["sum_matches_disclosed_total"] for g in result["groups"])
    assert all(i["evidence"]["physical_page"] == 24 for g in result["groups"] for i in g["items"])
    assert all(
        g["financial_review"] == "unconfirmed" and g["currency"] == "unknown"
        for g in result["groups"]
    )
    print(
        "REAL_PUBLIC_PDF_SEGMENT_CANDIDATES: physical24; 2years x product/region; product5/region3; approvals0; source_revision synthetic adapter proof, NOT runtime admission"
    )
