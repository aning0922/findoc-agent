"""Root-wired readonly company membership from saved source refs, never report titles."""

from contextlib import contextmanager
import json
import sqlite3
from types import SimpleNamespace
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.cplus.exports import register_exports
from app.exports_v2.projection import digest
from app.retrieval_v2 import TrustedIdentity


def test_company_workflow_uses_owner_and_saved_source_identity_without_writes(tmp_path):
    def database(name, ddl):
        path = tmp_path / name
        with sqlite3.connect(path) as db:
            db.executescript(ddl)
        return path

    annual = database("annual.db", "CREATE TABLE results(id TEXT, owner TEXT, payload TEXT);")
    peer = database("peer.db", "CREATE TABLE snapshots(id TEXT, owner TEXT, payload TEXT);")
    hybrid = database(
        "hybrid.db", "CREATE TABLE objects(id TEXT, owner TEXT, kind TEXT,payload TEXT);"
    )
    statements = database("statements.db", "CREATE TABLE records(id TEXT,kind TEXT,payload TEXT);")
    reports = database(
        "reports.db",
        "CREATE TABLE reports(id TEXT,workspace TEXT);CREATE TABLE revisions(report_id TEXT,revision INTEGER,payload TEXT);",
    )
    payloads = []
    with sqlite3.connect(annual) as db:
        for cid, owner in [("a", "current"), ("b", "current"), ("a", "other")]:
            payload = dict(
                schema_version="annual-diff-v1",
                result_id=cid + owner,
                title="B公司报告" if cid == "a" else "A公司报告",
                left_source={"company_id": cid, "kind": "fast"},
                right_source={"company_id": cid, "kind": "fast"},
                topics=[],
                created_at="2026-11-03T11:00:00+00:00",
                financial_authority=False,
            )
            payloads.append(payload)
            db.execute(
                "INSERT INTO results VALUES(?,?,?)",
                (payload["result_id"], owner, json.dumps(payload)),
            )

    async def authorize(identity):
        return "current"

    @contextmanager
    def guard(*args):
        yield

    identity = TrustedIdentity(
        workspace_id="demo",
        instance_id="fixture",
        generation=1,
        principal_id="visitor",
        expires_at=time.time() + 300,
    )

    def company(cid):
        if cid not in ("a", "b"):
            raise ValueError("unknown_company")
        return SimpleNamespace(
            name="企业" + cid, security_code="001" if cid == "a" else "002", exchange="SZSE"
        )

    app = FastAPI()
    app.state.showcase_report_service = SimpleNamespace(path=reports)
    register_exports(
        app,
        tmp_path,
        hybrid=SimpleNamespace(path=hybrid, authorize=authorize),
        annual=SimpleNamespace(path=annual),
        peer=SimpleNamespace(store=SimpleNamespace(path=peer)),
        statements=SimpleNamespace(path=statements, companies=SimpleNamespace(get=company)),
        identity_provider=lambda request: identity,
        validate=lambda value: None,
        guard=guard,
        conversations=None,
    )
    before = [p.read_bytes() for p in (annual, peer, hybrid, statements, reports)]
    with TestClient(app) as client:
        for cid in ("a", "b"):
            response = client.get(f"/cplus/companies/{cid}/workflow")
            assert response.status_code == 200
            result = response.json()
            assert result["company_id"] == cid and len(result["items"]) == 1
            item = result["items"][0]
            assert item["report_ref"]["id"] == cid + "current"
            assert item["company_ids"] == [cid]
            payload = next(x for x in payloads if x["result_id"] == cid + "current")
            assert item["report_ref"]["payload_sha256"] == digest(payload)
            assert item["saved_at"] == payload["created_at"]
        assert client.get("/cplus/companies/missing/workflow").status_code >= 400
    assert [p.read_bytes() for p in (annual, peer, hybrid, statements, reports)] == before
