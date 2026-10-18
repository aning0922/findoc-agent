"""D5 real services/HTTP/isolated SQLite; no real-PDF semantic verification."""

from dataclasses import replace
from pathlib import Path
import hashlib
import sqlite3
from uuid import UUID

from fastapi.testclient import TestClient
import pytest

from app.api.app import create_app
from app.companies.models import CompanyCreate
from app.companies.service import CompanyService
from app.companies.sqlite_repository import SQLiteCompanyRepository
from tests.test_revenue_confirmation import Harness


@pytest.fixture
def registry(tmp_path: Path):
    h = Harness(tmp_path)
    repository = SQLiteCompanyRepository(h.database)
    service = CompanyService(repository, workspace_id="demo")
    with TestClient(create_app(h.documents, company_service=service)) as client:
        yield h, repository, service, client


def company_payload(index=0):
    return {
        "name": ["企业甲", "企业乙", "企业丙"][index],
        "security_code": ["000001", "000002", "600003"][index],
        "exchange": "szse",
    }


def create_company(client, index=0):
    response = client.post("/companies", json=company_payload(index))
    assert response.status_code == 201, response.text
    return response.json()


def metadata_payload(company_id, year=2023, **changes):
    return {
        "company_id": company_id,
        "report_year": year,
        "report_type": "annual",
        "basis": "PRC_GAAP",
        "period_start": f"{year:04d}-01-01",
        "period_end": f"{year:04d}-12-31",
        **changes,
    }


def add_document(h, workspace, content):
    record = h.documents_repository.get(h.document_id)
    assert record
    sha = hashlib.sha256(content).hexdigest()
    document_id = hashlib.sha256(f"{workspace}\0{sha}".encode()).hexdigest()
    stored, _ = h.documents_repository.create_or_get(
        replace(
            record,
            workspace_id=workspace,
            content_sha256=sha,
            document_id=document_id,
            object_key=f"documents/{document_id}.pdf",
        )
    )
    return stored.document_id


def test_three_companies_crud_restart_and_nonbaseline_reports(registry):
    h, repository, service, client = registry
    companies = [create_company(client, i) for i in range(3)]
    assert len({c["company_id"] for c in companies}) == 3
    for c in companies:
        assert str(UUID(c["company_id"])) == c["company_id"]
        assert c["company_id"] != c["security_code"]
        assert "workspace_id" not in c
        assert client.get(f"/companies/{c['company_id']}").json() == c
    assert client.get("/companies").json() == companies
    changed = client.patch(
        f"/companies/{companies[0]['company_id']}",
        json={
            "name": "企业甲股份有限公司",
            "security_code": "600001",
            "exchange": "sse",
            "country": "CN",
        },
    )
    assert changed.status_code == 200
    assert changed.json()["exchange"] == "SSE"
    reports = []
    for index, year in enumerate([2023, 2026, 2022]):
        document_id = add_document(h, "demo", f"%PDF-test-{index}".encode())
        payload = metadata_payload(companies[index]["company_id"], year)
        result = client.put(f"/documents/{document_id}/metadata", json=payload)
        assert result.status_code == 200, result.text
        assert result.json()["status"] == "pending_verification"
        assert "workspace_id" not in result.json()
        reports.append((document_id, result.json()))
    reopened = CompanyService(SQLiteCompanyRepository(h.database), workspace_id="demo")
    with TestClient(create_app(h.documents, company_service=reopened)) as restarted:
        assert restarted.get("/companies").json() == client.get("/companies").json()
        for document_id, data in reports:
            assert restarted.get(f"/documents/{document_id}/metadata").json() == data
    assert service.get(companies[0]["company_id"]).name == "企业甲股份有限公司"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": "x"},
        {**company_payload(), "name": " "},
        {**company_payload(), "name": 1},
        {**company_payload(), "name": "x" * 201},
        {**company_payload(), "name": "bad\nname"},
        {**company_payload(), "security_code": 1},
        {**company_payload(), "security_code": ""},
        {**company_payload(), "security_code": "bad/code"},
        {**company_payload(), "exchange": " "},
        {**company_payload(), "country": "CHN"},
        {**company_payload(), "country": None},
        {**company_payload(), "company_id": "mine"},
        {**company_payload(), "workspace_id": "other"},
        {**company_payload(), "extra": "x"},
    ],
)
def test_create_illegal_inputs_are_rejected_without_writes(registry, payload):
    client = registry[3]
    assert client.post("/companies", json=payload).status_code == 422
    assert client.get("/companies").json() == []


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": None},
        {"name": " "},
        {"name": False},
        {"name": "x\x00y"},
        {"security_code": None},
        {"exchange": "bad space"},
        {"country": "cn"},
        {"workspace_id": "other"},
        {"company_id": "mine"},
    ],
)
def test_patch_illegal_inputs_preserve_record(registry, payload):
    client = registry[3]
    company = create_company(client)
    url = f"/companies/{company['company_id']}"
    assert client.patch(url, json=payload).status_code == 422
    assert client.get(url).json() == company


def test_security_identity_conflicts_normalize_and_are_workspace_local(registry):
    h, repo, _, client = registry
    first, second = create_company(client), create_company(client, 1)
    duplicate = client.post("/companies", json={**company_payload(), "exchange": "SZSE"})
    assert duplicate.status_code == 409
    before = client.get("/companies").json()
    assert (
        client.patch(
            f"/companies/{second['company_id']}",
            json={
                "security_code": first["security_code"],
                "name": "should roll back",
            },
        ).status_code
        == 409
    )
    assert client.get("/companies").json() == before
    other = CompanyService(repo, workspace_id="other")
    assert other.create(CompanyCreate.model_validate(company_payload())).workspace_id == "other"
    # Same code on another exchange is a distinct business identity.
    assert (
        client.post("/companies", json={**company_payload(), "exchange": "SSE"}).status_code == 201
    )


def test_unknown_and_cross_workspace_reads_and_updates_are_indistinguishable(registry):
    h, repo, _, client = registry
    other = CompanyService(repo, workspace_id="other").create(
        CompanyCreate.model_validate(company_payload())
    )
    for method, payload in [("get", None), ("patch", {"name": "forbidden"})]:
        unknown = client.request(method, "/companies/unknown", json=payload)
        outside = client.request(method, f"/companies/{other.company_id}", json=payload)
        assert outside.status_code == unknown.status_code == 404
        assert outside.json() == unknown.json() == {"detail": "资源不存在"}
    assert repo.get("other", other.company_id) == other
    assert client.get("/companies?workspace_id=other").json() == []
    assert client.get("/companies", headers={"X-Workspace-Id": "other"}).json() == []


@pytest.mark.parametrize(
    "changes",
    [
        {"report_year": 0},
        {"report_year": 10000},
        {"report_year": "2023"},
        {"report_year": True},
        {"report_year": 2023.0},
        {"report_type": "monthly"},
        {"basis": "guess"},
        {"period_start": "20230101"},
        {"period_end": "2023-02-29"},
        {"period_start": "2022-01-01"},
        {"period_end": "2024-12-31"},
        {"period_start": "2023-12-31", "period_end": "2023-01-01"},
        {"period_end": "2023-06-30"},
        {"company_id": " "},
        {"workspace_id": "other"},
        {"status": "verified"},
        {"content_sha256": "override"},
        {"period_start": 123},
        {"basis": None},
    ],
)
def test_invalid_metadata_has_no_binding(registry, changes):
    h, _, _, client = registry
    c = create_company(client)
    url = f"/documents/{h.document_id}/metadata"
    assert client.put(url, json={**metadata_payload(c["company_id"]), **changes}).status_code == 422
    assert client.get(url).status_code == 404


@pytest.mark.parametrize("year", [1, 1999, 2023, 2026, 2099, 9999])
def test_report_year_is_dynamic(registry, year):
    h, _, _, client = registry
    company = create_company(client)
    response = client.put(
        f"/documents/{h.document_id}/metadata", json=metadata_payload(company["company_id"], year)
    )
    assert response.status_code == 200, response.text
    assert response.json()["report_year"] == year


@pytest.mark.parametrize(
    "report_type,start,end",
    [
        ("semiannual", "2026-01-01", "2026-06-30"),
        ("quarterly", "2026-04-01", "2026-06-30"),
    ],
)
def test_explicit_nonannual_periods(registry, report_type, start, end):
    h, _, _, client = registry
    c = create_company(client)
    assert (
        client.put(
            f"/documents/{h.document_id}/metadata",
            json=metadata_payload(
                c["company_id"],
                2026,
                report_type=report_type,
                period_start=start,
                period_end=end,
            ),
        ).status_code
        == 200
    )


@pytest.mark.parametrize("changed", ["company", "year", "type", "basis"])
def test_duplicate_bytes_reuse_identity_and_conflicting_binding_never_rebinds(registry, changed):
    h, _, _, client = registry
    c, other = create_company(client), create_company(client, 1)
    url = f"/documents/{h.document_id}/metadata"
    payload = metadata_payload(c["company_id"])
    bound = client.put(url, json=payload)
    assert bound.status_code == 200
    assert client.put(url, json=payload).json() == bound.json()
    duplicate = client.post(
        "/documents",
        files={
            "file": ("renamed.pdf", b"%PDF-explicit-test-double", "application/pdf"),
        },
    )
    assert duplicate.status_code == 202 and duplicate.json()["duplicate"] is True
    assert duplicate.json()["document_id"] == h.document_id
    conflicting = {
        "company": metadata_payload(other["company_id"]),
        "year": metadata_payload(c["company_id"], 2026),
        "type": metadata_payload(
            c["company_id"], report_type="semiannual", period_end="2023-06-30"
        ),
        "basis": metadata_payload(c["company_id"], basis="IFRS"),
    }[changed]
    assert client.put(url, json=conflicting).status_code == 409
    assert client.get(url).json() == bound.json()
    assert len(h.documents_repository.list_by_workspace("demo")) == 1


def test_metadata_scope_checks_both_document_and_company(registry):
    h, repo, _, client = registry
    own = create_company(client)
    other = CompanyService(repo, workspace_id="other").create(
        CompanyCreate.model_validate(company_payload())
    )
    outside_doc = add_document(h, "other", b"%PDF-explicit-test-double")
    for doc in [h.document_id, outside_doc, "unknown"]:
        denied = client.put(f"/documents/{doc}/metadata", json=metadata_payload(other.company_id))
        assert denied.status_code == 404 and denied.json() == {"detail": "资源不存在"}
    for doc in [outside_doc, "unknown"]:
        assert client.get(f"/documents/{doc}/metadata").json() == {"detail": "资源不存在"}
        assert (
            client.put(
                f"/documents/{doc}/metadata", json=metadata_payload(own["company_id"])
            ).status_code
            == 404
        )
    assert client.get(f"/documents/{h.document_id}/metadata").status_code == 404
    # Equal bytes in different workspaces remain independent under legacy dedup rules.
    other_service = CompanyService(repo, workspace_id="other")
    from app.companies.models import ReportMetadataInput

    other_service.bind(
        outside_doc, ReportMetadataInput.model_validate(metadata_payload(other.company_id))
    )
    assert client.get(f"/documents/{outside_doc}/metadata?workspace_id=other").status_code == 404


def test_disabled_routes_and_safe_storage_errors(registry, monkeypatch):
    h, repo, _, client = registry
    with TestClient(create_app(h.documents)) as disabled:
        assert disabled.get("/companies").status_code == 503
    monkeypatch.setattr(
        repo,
        "list",
        lambda workspace: (_ for _ in ()).throw(sqlite3.OperationalError("/secret/database.db")),
    )
    response = client.get("/companies")
    assert response.status_code == 500 and response.json() == {"detail": "企业服务暂时不可用"}
