"""Three representative checks: adversarial geometry, API trust boundary, real PDF candidates.

Real-PDF test is opt-in via FINDOC_FINANCE_V2_PDF_ROOT. Embedding/index are always
fake and all test confirmations simulated_test. Real human approvals and LLM=0.
"""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from uuid import uuid4

from fastapi.testclient import TestClient
import pymupdf
import pytest

from app.companies.models import CompanyCreate
from app.documents.models import DocumentStatus
from app.finance_v2.api import create_finance_v2_router
from app.finance_v2.contracts import FinanceError
from app.finance_v2.extraction import DEFINITION, debt_ratio, extract
from app.finance_v2.service import ExtendedFinanceService, OwnerAuthorization
from app.rag.parse.models import PDFCell, PDFLayout
from tests.test_document_sources import Harness, metadata


def operation(**fields):
    return {"operation_id": str(uuid4()), **fields}


def geometry():
    def cell(text, x, y, width=80):
        return PDFCell(text=text, bbox=(x, y, x + width, y + 10))
    rows = [[cell("合并资产负债表", 40, 20, 160)], [cell("单位：人民币万元", 40, 40, 160)],
            [cell("项目", 40, 60), cell("2031年12月31日", 250, 60, 90), cell("2030年12月31日", 420, 60, 90)],
            [cell("资产总计", 40, 80), cell("1,234.50", 280, 80), cell("1,000.00", 450, 80)],
            [cell("负债合计", 40, 100), cell("600.00", 280, 100), cell("500.00", 450, 100)]]
    record = {"evidence_id": "table", "source_revision": "a" * 64, "physical_page": 2, "kind": "paragraph",
              "text": "合并资产负债表", "layout": PDFLayout(strategy="text_geometry", rows=rows).model_dump(mode="json")}
    basis = {"evidence_id": "basis", "source_revision": "a" * 64, "physical_page": 3, "kind": "paragraph",
             "text": "遵循企业会计准则：财务报表符合企业会计准则的要求", "layout": None}
    source = {"company_id": "company", "document_id": "document", "source_revision": "a" * 64,
              "content_sha256": "b" * 64, "parser_version": "fast-pdf-fixture", "report_year": 2031,
              "report_type": "annual", "period_start": "2031-01-01", "period_end": "2031-12-31", "basis": "PRC_GAAP",
              "assessment": {k: "matches_cover" for k in ("company", "report_year", "report_type")},
              "evidence_ids": ["table", "basis"]}
    return source, [record, basis]


def test_geometry_dates_units_conflicts_and_decimal_fail_closed():
    source, records = geometry()
    metrics = extract(source, records)
    assert len(metrics) == 4 and all(m["status"] == "candidate" for m in metrics)
    current = [m for m in metrics if m["as_of_date"] == "2031-12-31"]
    assert next(m for m in current if m["metric_key"] == "total_assets")["value_decimal"] == "12345000.00"
    comparative = [m for m in metrics if m["as_of_date"] == "2030-12-31"]
    assert all(m["report_year"] == 2031 and m["period"] == 2030 for m in comparative)
    assert debt_ratio(current) == "48.602673"
    for change, expected in [("zero", "zero_or_negative_balance"), ("negative", "zero_or_negative_balance"),
                             ("date", "incomparable_as_of_date"), ("version", "incomparable_source_revision")]:
        changed = deepcopy(current)
        asset = next(m for m in changed if m["metric_key"] == "total_assets")
        if change == "zero":
            asset["value_decimal"] = "0"
        if change == "negative":
            asset["value_decimal"] = "-1"
        if change == "date":
            asset["as_of_date"] = "2030-12-31"
        if change == "version":
            asset["source_revision"] = "c" * 64
        with pytest.raises(FinanceError, match=expected):
            debt_ratio(changed)
    for mutation in ("parent", "no_unit", "no_date", "wrong_label", "conflicting"):
        changed = deepcopy(records)
        rows = changed[0]["layout"]["rows"]
        if mutation == "parent":
            rows[0][0]["text"] = "母公司资产负债表"
        if mutation == "no_unit":
            rows[1][0]["text"] = "单位：美元"
        if mutation == "no_date":
            rows[2][1]["text"] = "期末"
        if mutation == "wrong_label":
            rows[4][0]["text"] = "流动负债合计"
        if mutation == "conflicting":
            conflict = deepcopy(changed[0])
            conflict["evidence_id"] = "conflict"
            conflict["layout"]["rows"][3][1]["text"] = "999.00"
            changed.append(conflict)
        context = {**source, "evidence_ids": [r["evidence_id"] for r in changed]}
        result = extract(context, changed)
        assert any(m["status"] == "unsupported" for m in result), mutation
        assert all(m["value_decimal"] is None for m in result if m["status"] == "unsupported")


def synthetic_pdf():
    with pymupdf.open() as pdf:
        cover = pdf.new_page()
        cover.insert_text((40, 60), "测试股份有限公司", fontname="china-s", fontsize=12)
        cover.insert_text((40, 90), "2031年年度报告", fontname="china-s", fontsize=12)
        page = pdf.new_page()
        for x, y, text in [(40, 45, "合并资产负债表"), (40, 65, "单位：人民币元"),
                           (40, 85, "项目"), (250, 85, "2031年12月31日"), (420, 85, "2030年12月31日"),
                           (40, 110, "资产总计"), (280, 110, "1,000.00"), (450, 110, "900.00"),
                           (40, 135, "负债合计"), (280, 135, "500.00"), (450, 135, "450.00"),
                           (40, 190, "遵循企业会计准则：本公司财务报表符合企业会计准则的要求")]:
            page.insert_text((x, y), text, fontname="china-s", fontsize=9)
        return pdf.tobytes()


def assembled(root, raw, *, name="测试股份有限公司", year=2031, code="FINANCEV2", exchange="DEMO"):
    root.mkdir(parents=True, exist_ok=True)
    h = Harness(root)
    company = h.companies.create(CompanyCreate(name=name, security_code=code, exchange=exchange))
    uploaded = h.upload(raw, metadata(company.company_id, year), filename="source.pdf")
    assert uploaded.status_code == 202, uploaded.text
    document = uploaded.json()["document_id"]
    assert h.processor.process(document).status == DocumentStatus.READY
    source = h.client.get(f"/documents/{document}/source").json()
    return h, company.company_id, document, source


def test_api_receipts_simulated_never_admitted_immutable_and_source_changes(tmp_path):
    root = tmp_path / "findoc-finance-v2-test-api"
    h, company, document, source = assembled(root, synthetic_pdf())
    service = ExtendedFinanceService(root, h.service, confirmation_kind="simulated_test")
    with pytest.raises(ValueError, match="isolated test root"):
        ExtendedFinanceService(tmp_path / "ordinary-root", h.service, confirmation_kind="simulated_test")
    # Default/missing owner adapter fails closed; simulated test path uses a server-only fake capability.
    h.client.app.include_router(create_finance_v2_router(service))
    collect = operation(company_id=company, document_id=document, expected_source_revision=source["source_revision"])
    first = h.client.post("/financial/extended-metrics/collect", json=collect)
    assert first.status_code == 200, first.text
    metrics = first.json()["metrics"]
    assert len(metrics) == 4 and all(m["status"] == "candidate" for m in metrics), first.text
    assert h.client.post("/financial/extended-metrics/collect", json=collect).json() == first.json()
    assert h.client.post("/financial/extended-metrics/collect", json={**collect, "company_id": "different"}).status_code == 409
    selected = [m["metric_id"] for m in metrics if m["as_of_date"] == "2031-12-31"]
    review = h.client.post("/financial/extended-reviews", json=operation(metric_refs=selected))
    assert review.status_code == 200 and review.json()["acceptable"], review.text
    confirm = operation(review_id=review.json()["review_id"], review_sha256=review.json()["review_sha256"], confirmed=True)
    assert h.client.post("/financial/extended-confirmations", json=confirm).status_code == 503
    # New standalone app keeps the same isolated DB, with explicitly simulated authorization.
    from fastapi import FastAPI
    app = FastAPI()
    authorization = OwnerAuthorization(root, "simulated-test-actor", time.time() + 60)
    app.include_router(create_finance_v2_router(service, owner_authorizer=lambda request: authorization))
    client = TestClient(app)
    receipt = client.post("/financial/extended-confirmations", json=confirm)
    assert receipt.status_code == 200 and receipt.json()["confirmation_kind"] == "simulated_test", receipt.text
    assert all(m["status"] == "candidate" for m in client.get("/financial/extended-metrics", params={"company_id": company}).json()["metrics"])
    rejected = client.post("/financial/extended-analyses", json=operation(metric_refs=selected))
    assert rejected.status_code == 403 and rejected.json()["detail"]["code"] == "current_local_operator_confirmation_required"
    assert client.post("/financial/extended-analyses", json=operation(metric_refs=selected, value_decimal="1")).status_code == 422
    assert client.post("/financial/extended-confirmations", json={**confirm, "confirmation_kind": "local_operator"}).status_code == 422
    assert client.post("/financial/extended-confirmations", json=confirm).json() == receipt.json()
    authorization = OwnerAuthorization(root, "simulated-test-actor", time.time() - 1)
    assert client.post("/financial/extended-confirmations", json=confirm).status_code == 403
    authorization = OwnerAuthorization(root, "simulated-test-actor", time.time() + 60)
    revocation = operation(reason="Explicit simulated test revocation")
    revoked = client.post("/financial/extended-confirmations/" + receipt.json()["receipt_id"] + "/revoke", json=revocation)
    assert revoked.status_code == 200, revoked.text
    with service.store.tx() as db:
        with pytest.raises(Exception, match="immutable"):
            db.execute("UPDATE fv2_receipts SET payload='{}'")
    doc_record = h.docs.get(document)
    h.objects._resolve_object_path(doc_record.object_key).write_bytes(b"%PDF-corrupted-test-object")
    unavailable = client.get("/financial/extended-metrics", params={"company_id": company})
    assert all(m["status"] == "unsupported" and m["value_decimal"] is None for m in unavailable.json()["metrics"])
    assert client.post("/financial/extended-analyses", json=operation(metric_refs=selected)).status_code == 409
    assert client.get("/financial/extended-operations/" + confirm["operation_id"]).json()["historical_snapshot"] is True


@pytest.mark.local_data
def test_real_pdf_candidates_only_with_immutable_source_layout():
    root_value = os.environ.get("FINDOC_FINANCE_V2_PDF_ROOT")
    if not root_value:
        pytest.skip("Set FINDOC_FINANCE_V2_PDF_ROOT to authorized preflight PDF directory")
    path = Path(root_value) / "gree-2025.pdf"
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "7cc972f2d199e2ec3797cc5da479e8268afa59b77875770de3bcd3648242fb8c"
    root = Path(tempfile.mkdtemp(prefix="findoc-finance-v2-real-proof-")).resolve()
    h, company, document, source = assembled(root, raw, name="珠海格力电器股份有限公司", year=2025, code="000651", exchange="SZSE")
    service = ExtendedFinanceService(root, h.service)
    h.client.app.include_router(create_finance_v2_router(service))
    response = h.client.post("/financial/extended-metrics/collect", json=operation(
        company_id=company, document_id=document, expected_source_revision=source["source_revision"]))
    assert response.status_code == 200, response.text
    metrics = response.json()["metrics"]
    assert len(metrics) == 4 and all(m["status"] == "candidate" for m in metrics), response.text[:2000]
    expected = {("total_assets", "2025-12-31"): ("391371999819.49", 86),
                ("total_assets", "2025-01-01"): ("368031704522.86", 86),
                ("total_liabilities", "2025-12-31"): ("241580719144.79", 87),
                ("total_liabilities", "2025-01-01"): ("226518009574.89", 87)}
    for metric in metrics:
        value, page = expected[metric["metric_key"], metric["as_of_date"]]
        assert Decimal(metric["value_decimal"]) == Decimal(value)
        assert metric["unit"] == "CNY_YUAN" and metric["period_kind"] == "instant" and metric["period"] == 2025
        assert metric["metric_definition_version"] == DEFINITION and metric["confirmation_ref"] is None
        assert any(ref["physical_page"] == page and ref["raw_unit"] == "元" for ref in metric["evidence_refs"])
        assert all(ref["period_header_cells"] and ref["scope_cells"] and ref["raw_cells"] for ref in metric["evidence_refs"])
    refs = [m["metric_id"] for m in metrics if m["as_of_date"] == "2025-12-31"]
    assert h.client.post("/financial/extended-analyses", json=operation(metric_refs=refs)).status_code == 403
    (root / "finance-v2-evidence.json").write_text(json.dumps({"pdf_sha256": source["content_sha256"],
        "source": source, "metrics": metrics, "real": ["PDF", "fast parser", "immutable SQLite layout", "source checks"],
        "fake": ["embedding", "vector index", "chunk IDs"], "llm_requests": 0, "human_approvals": 0}, ensure_ascii=False, indent=2))
    assert hashlib.sha256(path.read_bytes()).hexdigest() == source["content_sha256"]
    print("REAL_PDF_CANDIDATE_EVIDENCE=" + str(root / "finance-v2-evidence.json"))
