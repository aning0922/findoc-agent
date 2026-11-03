"""CONTROLLED_HTTP_MOCK_PROTOCOL_ONLY: no real config, provider, ledger or ports."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

import httpx
import pymupdf
import pytest

from app.conversations.models import CreateConversationRequest
from app.showcase_research.models import IntentRequest, PlanRequest, JobRequest
from app.showcase_reports.api import Draft, Create
from experiments.cplus.verify_real_agent_paths import (
    Runner,
    Window,
    SQLiteLedger,
    IDENTITY_KEYS,
    StopRun,
)


class FakeLedger:
    def __init__(self):
        self.rows = {
            "fixture-old-unknown": {
                "reserved_cny": "0.01",
                "state": "unknown",
                "input_tokens": None,
                "output_tokens": None,
            }
        }

    def snapshot(self):
        return {"cap_cny": "5", "rows": deepcopy(self.rows)}

    def sdk(self, count=1, unknown=False):
        for _ in range(count):
            key = "fixture-new-" + str(len(self.rows))
            self.rows[key] = {
                "reserved_cny": "0.001",
                "state": "unknown" if unknown else "returned",
                "input_tokens": None if unknown else 2,
                "output_tokens": None if unknown else 1,
            }


class FakeHTTP:
    def __init__(self, ledger, *, fault=None, recovery_status=200):
        self.ledger, self.fault, self.recovery_status = ledger, fault, recovery_status
        self.requests, self.intents, self.plans, self.jobs, self.reports = [], {}, {}, {}, {}
        self.last_mode, self.last_job = None, None
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text(
                (50, 70), "经营风险原文。现金流变化原文。", fontname="china-s"
            )
            self.raw = pdf.tobytes()
        self.source = dict(
            kind="fast",
            workspace_id="demo",
            document_id="fixture-doc",
            company_id="fixture-company",
            report_year=2025,
            report_type="annual",
            period_start="2025-01-01",
            period_end="2025-12-31",
            basis="PRC_GAAP",
            source_revision="a" * 64,
            content_sha256=hashlib.sha256(self.raw).hexdigest(),
            attempt=1,
            parser_version="fixture-only",
            identity_status="fast_source_verified",
        )
        self.identity = {k: self.source[k] for k in IDENTITY_KEYS}
        self.scope = dict(
            scope_hash="b" * 64,
            runtime_instance_id="fixture-instance",
            lease_generation=1,
            source_scope_sha="c" * 64,
            fact_selection_sha="d" * 64,
            memory_generation=0,
            allowed_tools=["search_evidence", "read_confirmed_facts", "recall_notes"],
        )
        self.ref = {
            k: self.source[k]
            for k in (
                "document_id",
                "company_id",
                "source_revision",
                "content_sha256",
                "parser_version",
            )
        }
        self.ref.update(
            physical_page=1,
            chunk_id="fixture-chunk",
            evidence_id="fixture-evidence",
            text="经营风险原文。",
        )

    def __call__(self, request):
        path = request.url.path
        body = json.loads(request.content) if request.method == "POST" else None
        self.requests.append({"method": request.method, "path": path, "body": body})

        def reply(value, status=200):
            return httpx.Response(status, json=value)

        if path == "/demo/status":
            return reply({"service_state": "ready"})
        if path == "/demo/login":
            return reply({"operation_id": body["operation_id"]}, 202)
        if path.startswith("/demo/operations/"):
            return reply({"claimable": True})
        if path == "/demo/claim":
            return reply({"state": "active"})
        if path == "/demo/session":
            return reply({"lease_generation": 1, "state": "active"})
        if path == "/companies":
            return reply([{"company_id": "fixture-company", "security_code": "000651"}])
        if path == "/documents":
            return reply([{"document_id": "fixture-doc", "status": "ready"}])
        if path.endswith("/metadata"):
            return reply({"company_id": "fixture-company", "report_year": 2025})
        if path.endswith("/research-source"):
            return reply(self.source)
        if path.endswith("/file"):
            return httpx.Response(
                200, content=self.raw, headers={"content-type": "application/pdf"}
            )
        if "/evidence/" in path:
            return reply({**self.ref, "text": "经营风险原文。现金流变化原文。"})
        if path == "/conversations":
            CreateConversationRequest.model_validate(body)
            return reply(
                dict(
                    conversation_id=str(uuid4()),
                    sources=[self.identity],
                    source_scope_sha=self.scope["source_scope_sha"],
                    active_turn_id=None,
                ),
                201,
            )
        if path == "/research/intent":
            request_model = IntentRequest.model_validate(body)
            self.last_mode = request_model.requested_mode
            self.ledger.sdk(unknown=self.fault == "intent-timeout")
            if self.fault == "intent-timeout":
                raise httpx.ReadTimeout("fixture transport only", request=request)
            identifier = str(uuid4())
            value = dict(
                intent_id=identifier,
                conversation_id=body["conversation_id"],
                mode=body["requested_mode"],
                goal=body["text"],
                provider_error=None,
                proposal_origin="model_proposal_program_validated",
                clarifying_question=None,
                scope=self.scope,
            )
            self.intents[identifier] = value
            return reply(value)
        if path == "/synthesis/plans":
            PlanRequest.model_validate(body)
            self.ledger.sdk()
            intent = self.intents[body["intent_id"]]
            mode = intent["mode"]
            identifier = str(uuid4())
            value = dict(
                plan_id=identifier,
                revision=1,
                plan_sha256="e" * 64,
                intent_id=body["intent_id"],
                mode=mode,
                provider_error=None,
                plan_origin="supervisor_model_program_validated",
                scope=self.scope,
                roles=["evidence", "risk_operations"] if mode == "deep" else ["generalist"],
                requires_explicit_confirmation=True,
                limits={"model_attempts": 10 if mode == "deep" else 5, "parallel_agents": 2},
            )
            self.plans[identifier] = value
            return reply(value)
        if path in ("/synthesis/jobs", "/deep-research/jobs") and request.method == "POST":
            JobRequest.model_validate(body)
            plan = self.plans[body["approved_plan_id"]]
            mode = plan["mode"]
            self.ledger.sdk(5 if mode == "deep" else 2)
            identifier = str(uuid4())
            self.last_job = identifier
            findings = [
                {
                    "finding_id": "quote-" + identifier,
                    "kind": "sourced_excerpt",
                    "text": self.ref["text"],
                    "evidence_refs": [self.ref],
                    "financial_refs": [],
                },
                {
                    "finding_id": "interpretation-" + identifier,
                    "kind": "model_interpretation",
                    "text": "模型待审解释。",
                    "evidence_refs": [self.ref],
                    "financial_refs": [],
                },
            ]
            self.jobs[identifier] = dict(
                job_id=identifier,
                mode=mode,
                plan_id=plan["plan_id"],
                scope=self.scope,
                state="partial" if self.fault == "partial" else "completed",
                usage={"attempts": 7 if mode == "deep" else 4, "unknown_attempts": 0},
                result={
                    "agents": [{"agent_id": r, "state": "completed"} for r in plan["roles"]],
                    "findings": findings,
                },
                steps=[
                    {"agent_id": r, "state": "completed", "tools": ["search_evidence"]}
                    for r in plan["roles"]
                ],
            )
            if self.fault == "job-ack-timeout":
                raise httpx.ReadTimeout("fixture ACK loss", request=request)
            return reply({"job_id": identifier, "state": "queued"}, 202)
        if path.startswith("/research/operations/"):
            return reply(
                {"state": "completed", "result": {"job_id": self.last_job}}
                if self.last_job
                else {"state": "unknown"},
                self.recovery_status,
            )
        if path.endswith("/events"):
            job_id = path.split("/")[-2]
            job = self.jobs[job_id]
            names = [
                "controller",
                "supervisor",
                *[a["agent_id"] for a in job["result"]["agents"]],
                "verifier",
            ]
            events = [
                dict(
                    job_id=job_id,
                    event_seq=i + 1,
                    agent_id=name,
                    event_type="phase",
                    state="completed",
                )
                for i, name in enumerate(names)
            ]
            after = int(request.url.params["after_seq"])
            batch = [e for e in events if e["event_seq"] > after]
            return reply(
                {"events": batch, "next_after_seq": batch[-1]["event_seq"] if batch else after}
            )
        if path.startswith(("/synthesis/jobs/", "/deep-research/jobs/")):
            return reply(self.jobs[path.split("/")[-1]])
        if path == "/showcase-reports/drafts":
            Draft.model_validate(body)
            self.report_job = self.jobs[body["job_id"]]
            return reply({"draft_id": str(uuid4())})
        if path == "/showcase-reports" and request.method == "POST":
            Create.model_validate(body)
            identifier = str(uuid4())
            value = {
                "report_id": identifier,
                "revision": 1,
                "snapshot": {"findings": self.report_job["result"]["findings"]},
            }
            self.reports[identifier] = value
            return reply(value)
        if path.startswith("/showcase-reports/"):
            return reply({**self.reports[path.split("/")[2]], "current_source_status": "current"})
        raise AssertionError("unexpected fixture route " + request.method + " " + path)


def run_fixture(tmp_path, *, maximum=12, fault=None, recovery_status=200):
    ledger = FakeLedger()
    server = FakeHTTP(ledger, fault=fault, recovery_status=recovery_status)
    output = tmp_path / "receipt"
    output.mkdir()
    cases = {
        c["id"]: c
        for c in json.loads(
            (Path(__file__).resolve().parents[1] / "docs/cplus/eval/fixed-cases.json").read_text()
        )["cases"]
    }
    with httpx.Client(
        base_url="http://fixture-only", transport=httpx.MockTransport(server)
    ) as client:
        runner = Runner(
            client,
            Window(ledger, maximum),
            output,
            sleep=lambda _: None,
            tier="CONTROLLED_HTTP_MOCK_PROTOCOL_ONLY",
        )
        result = runner.execute(cases, "fixture-username", "fixture-password")
    result["actual_provider_calls"] = 0
    return result, server, ledger


def test_both_paths_schema_fields_approval_quotes_reports_and_call_denominators(tmp_path):
    result, server, ledger = run_fixture(tmp_path)
    assert result["execution"].startswith("COMPLETED_")
    assert [(c["case_id"], c["mode"]) for c in result["cases"]] == [
        ("E01-06", "deep"),
        ("E01-01", "synthesis"),
    ]
    assert [c["physical_guard_rows_for_case"] for c in result["cases"]] == [7, 4]
    assert all(
        c["logical_minus_physical"] == 0
        and c["exact_quotes"]
        and c["reads_and_report_writes_zero_new_model_rows"]
        for c in result["cases"]
    )
    assert (
        result["new_guard_rows_count"] == 11
        and ledger.rows["fixture-old-unknown"]["state"] == "unknown"
    )
    assert (
        len(
            [
                r
                for r in server.requests
                if r["path"] == "/showcase-reports" and r["method"] == "POST"
            ]
        )
        == 2
    )
    serialized = json.dumps(result)
    assert "fixture-password" not in serialized and "fixture-username" not in serialized
    assert result["financial_approvals"] == 0 and result["full_human_answer_acceptance"] is False


@pytest.mark.parametrize("recovery_status", [200, 404])
def test_intent_transport_unknown_never_reposts_or_starts_plan_even_after_get(
    tmp_path, recovery_status
):
    result, server, ledger = run_fixture(
        tmp_path, fault="intent-timeout", recovery_status=recovery_status
    )
    assert result["execution"] == "STOPPED_WITH_RECEIPTS_NO_REPLAY"
    assert len([r for r in server.requests if r["path"] == "/research/intent"]) == 1
    assert not any(r["path"] == "/synthesis/plans" for r in server.requests)
    assert result["new_guard_rows_count"] == 1 and any(
        r["state"] == "unknown" for r in result["new_guard_rows"].values()
    )
    assert result["readonly_recoveries"]


def test_job_ack_unknown_keeps_original_operation_does_not_resume_after_completed_get(tmp_path):
    result, server, _ = run_fixture(tmp_path, fault="job-ack-timeout")
    assert result["execution"] == "STOPPED_WITH_RECEIPTS_NO_REPLAY"
    assert (
        len([r for r in server.requests if r["method"] == "POST" and r["path"].endswith("/jobs")])
        == 1
    )
    assert result["readonly_recoveries"][0]["result"]["state"] == "completed"
    assert not any(r["path"] == "/showcase-reports/drafts" for r in server.requests)
    assert len(result["cases"]) == 1


def test_low_remaining_headroom_stops_before_second_mode_intent(tmp_path):
    result, server, _ = run_fixture(tmp_path, maximum=10)
    assert result["execution"] == "STOPPED_WITH_RECEIPTS_NO_REPLAY"
    assert result["new_guard_rows_count"] == 7 and len(result["cases"]) == 1
    assert len([r for r in server.requests if r["path"] == "/research/intent"]) == 1
    assert "headroom" in result["stop"]["reason"]


def test_partial_job_retains_events_without_report_or_next_mode(tmp_path):
    result, server, _ = run_fixture(tmp_path, fault="partial")
    assert result["cases"][0]["job"]["state"] == "partial" and result["cases"][0]["events"]
    assert result["execution"] == "STOPPED_WITH_RECEIPTS_NO_REPLAY"
    assert not any(r["path"] == "/showcase-reports/drafts" for r in server.requests)
    assert len(result["cases"]) == 1


def test_ledger_reader_is_read_only_and_never_creates_allowance(tmp_path):
    path = tmp_path / "controlled-fixture-budget.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE config(id INTEGER,cap TEXT)")
        db.execute("INSERT INTO config VALUES(1,'5')")
        db.execute(
            "CREATE TABLE calls(id TEXT,reserved TEXT,state TEXT,input_tokens INTEGER,output_tokens INTEGER)"
        )
        db.execute("INSERT INTO calls VALUES('old-fixture','0.01','unknown',NULL,NULL)")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    snapshot = SQLiteLedger(path).snapshot()
    assert snapshot["rows"]["old-fixture"]["state"] == "unknown"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    missing = tmp_path / "must-not-be-created.db"
    with pytest.raises(sqlite3.OperationalError):
        SQLiteLedger(missing).snapshot()
    assert not missing.exists()


@pytest.mark.parametrize(
    "path",
    [
        "/research/handoffs",
        "/financial-facts/confirmations",
        "/research/tasks/x/resume",
        "/financial/save",
    ],
)
def test_financial_and_legacy_handoff_mutations_never_dispatched(tmp_path, path):
    ledger = FakeLedger()
    seen = []
    with httpx.Client(
        base_url="http://fixture-only", transport=httpx.MockTransport(lambda r: seen.append(r))
    ) as client:
        runner = Runner(
            client, Window(ledger, 12), tmp_path, tier="CONTROLLED_HTTP_MOCK_PROTOCOL_ONLY"
        )
        with pytest.raises(StopRun, match="allowlist"):
            runner.post(path, {})
    assert seen == []
