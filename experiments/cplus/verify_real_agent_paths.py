"""Operator-run real HTTP agent paths; worker validation uses controlled fixtures only.

Default order: E01-06 deep (two server roles), then E01-01 synthesis. Existing
5-CNY ledger is read-only here; only the deployed guarded SDK may write it.
No POST retries, no resume, no legacy financial accept/save or handoff route.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time
from urllib.parse import quote, urlsplit
from uuid import uuid4

import httpx

PROJECT = Path(__file__).resolve().parents[2]
IDENTITY_KEYS = (
    "workspace_id",
    "document_id",
    "company_id",
    "report_year",
    "report_type",
    "period_start",
    "period_end",
    "basis",
    "source_revision",
    "content_sha256",
    "attempt",
    "parser_version",
)
CASE_MODES = (("E01-06", "deep", 10), ("E01-01", "synthesis", 5))
ALLOWED_POSTS = {
    "/demo/login",
    "/demo/claim",
    "/conversations",
    "/research/intent",
    "/synthesis/plans",
    "/synthesis/jobs",
    "/deep-research/jobs",
    "/showcase-reports/drafts",
    "/showcase-reports",
}
TERMINAL = {"completed", "partial", "interrupted", "failed"}


class StopRun(RuntimeError):
    pass


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    tmp.replace(path)


class SQLiteLedger:
    """No initialization, migrations, chmod, copying, reserve or refund methods."""

    def __init__(self, path):
        self.path = path

    def snapshot(self):
        with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as db:
            cap = db.execute("SELECT cap FROM config WHERE id=1").fetchone()[0]
            rows = db.execute(
                "SELECT id,reserved,state,input_tokens,output_tokens FROM calls"
            ).fetchall()
        if Decimal(cap) != Decimal("5"):
            raise StopRun("existing_cap_is_not_5_no_budget_replacement")
        return {
            "cap_cny": cap,
            "rows": {
                r[0]: {
                    "reserved_cny": r[1],
                    "state": r[2],
                    "input_tokens": r[3],
                    "output_tokens": r[4],
                }
                for r in rows
            },
        }


def public_budget(snapshot):
    values = list(snapshot["rows"].values())
    return {
        "cap_cny": snapshot["cap_cny"],
        "physical_guard_rows": len(values),
        "reserved_cny": str(sum((Decimal(r["reserved_cny"]) for r in values), Decimal(0))),
        "unknown_rows": sum(r["state"] == "unknown" for r in values),
        "actual_billed_cny": "not_observed",
    }


class Window:
    def __init__(self, ledger, maximum):
        if not 1 <= maximum <= 12:
            raise ValueError("explicit_max_new_calls_must_be_1_to_12")
        self.ledger, self.maximum, self.baseline = ledger, maximum, ledger.snapshot()

    def current(self):
        current = self.ledger.snapshot()
        if not set(self.baseline["rows"]).issubset(current["rows"]):
            raise StopRun("ledger_rows_disappeared_no_reset_or_replacement_allowed")
        return current

    def delta(self, current=None):
        current = current or self.current()
        return {k: v for k, v in current["rows"].items() if k not in self.baseline["rows"]}

    def admit(self, upper):
        current = self.current()
        added = self.delta(current)
        if len(added) + upper > self.maximum:
            raise StopRun("insufficient_physical_call_headroom_no_further_task_started")
        if any(r["state"] != "returned" for r in added.values()):
            raise StopRun("new_guard_row_unknown_or_unsettled_no_further_write")
        if Decimal(public_budget(current)["reserved_cny"]) >= Decimal(current["cap_cny"]):
            raise StopRun("existing_cny_allowance_exhausted")
        return current


class Runner:
    def __init__(
        self,
        client,
        window,
        output,
        *,
        sleep=time.sleep,
        monotonic=time.monotonic,
        tier="INJECTED_PROTOCOL_CALLER",
        api_prefix="",
        private_session_file=None,
    ):
        if api_prefix not in ("", "/api"):
            raise ValueError("unsupported_api_prefix")
        self.api_prefix=api_prefix
        self.private_session_file=private_session_file
        self.client, self.window, self.output = client, window, output
        self.sleep, self.monotonic = sleep, monotonic
        self.proof = {
            "schema_version": "cplus-real-agent-paths-v1",
            "tier": tier,
            "execution": "STARTED",
            "max_new_calls": window.maximum,
            "budget_before": public_budget(window.baseline),
            "physical_denominator": "new existing guarded SDK reservation/attempt rows; not billed cost or accepted-answer count",
            "logical_denominator": "sr_budgets.attempts from each final job.usage; tool reservations are separate",
            "operations": [],
            "reads": [],
            "cases": [],
            "financial_approvals": 0,
            "full_human_answer_acceptance": False,
            "paired_same_question_comparison": False,
            "original_unknown_policy": "baseline unknown rows retained; never retried/refunded",
            "readonly_recoveries": [],
        }
        self.save()

    def save(self):
        current = self.window.current()
        self.proof["budget_after"] = public_budget(current)
        self.proof["new_guard_rows"] = self.window.delta(current)
        self.proof["new_guard_rows_count"] = len(self.proof["new_guard_rows"])
        self.proof["old_unknown_state_changes"] = {
            k: {"before": v["state"], "after": current["rows"][k]["state"]}
            for k, v in self.window.baseline["rows"].items()
            if v["state"] == "unknown" and current["rows"][k]["state"] != v["state"]
        }
        write_json(self.output / "result.json", self.proof)

    def get(self, path, *, params=None, raw=False):
        response = self.client.get(self.api_prefix+path, params=params)
        self.proof["reads"].append({"path": path, "params": params, "status": response.status_code})
        self.save()
        if response.status_code != 200:
            raise StopRun(f"read_failed:{path}:{response.status_code}")
        return response.content if raw else response.json()

    def post(self, path, payload, *, upper=0, recovery=None, auth=False, expected=(200, 201, 202)):
        if path not in ALLOWED_POSTS:
            raise StopRun("mutation_not_in_explicit_demo_allowlist")
        self.window.admit(upper)
        body = {"operation_id": str(uuid4()), **payload}
        record = {
            "path": path,
            "operation_id": body["operation_id"],
            "state": "INTENT_DURABLY_SAVED",
            "maximum_remaining_model_calls_admitted": upper,
        }
        if not auth:
            record.update(request_body=body, request_sha256=digest(body))
        self.proof["operations"].append(record)
        self.save()
        try:
            response = self.client.post(self.api_prefix+path, json=body)
            record["http_status"] = response.status_code
            if response.status_code not in expected:
                record.update(state="REJECTED_OR_UNKNOWN_NO_REPLAY", safe_error=response.json())
                raise StopRun(f"post_not_accepted:{path}:{response.status_code}")
            value = response.json()
            record.update(state="RESPONSE_RECEIVED", result=value)
            self.save()
            return value
        except (httpx.HTTPError, StopRun, ValueError) as exc:
            record["state"] = "UNKNOWN_OR_REJECTED_NO_REPLAY"
            record["error_type"] = type(exc).__name__
            self.save()
            if recovery:
                # One read only; even recovered completion does not resume writes.
                target = recovery(body["operation_id"])
                try:
                    recovered = self.get(target)
                    self.proof["readonly_recoveries"].append({"path": target, "result": recovered})
                except Exception as read_error:
                    self.proof["readonly_recoveries"].append(
                        {"path": target, "error_type": type(read_error).__name__}
                    )
                self.save()
            raise StopRun("mutation_result_uncertain_or_rejected_stop_no_automatic_replay") from exc

    def login(self, username, password):
        status = self.get("/demo/status")
        if status["service_state"] != "ready":
            raise StopRun("controller_not_ready_do_not_takeover_or_reset")
        attempt = self.post(
            "/demo/login",
            {"username": username, "password": password},
            auth=True,
            recovery=lambda oid: "/demo/operations/" + oid,
        )
        deadline = self.monotonic() + 180
        while True:
            value = self.get("/demo/operations/" + attempt["operation_id"])
            if value.get("claimable"):
                break
            if value.get("state") in ("failed", "interrupted") or self.monotonic() >= deadline:
                raise StopRun("login_attempt_not_claimable_no_repeat")
            self.sleep(0.5)
        self.post(
            "/demo/claim",
            {"attempt_operation_id": attempt["operation_id"]},
            auth=True,
            recovery=lambda oid: "/demo/operations/" + oid,
        )
        self.proof["session"] = self.get("/demo/session")
        if self.private_session_file is not None:
            cookies=[dict(name=c.name,value=c.value,domain=c.domain,path=c.path,
                          expires=c.expires if c.expires is not None else -1,httpOnly=True,
                          secure=c.secure,sameSite="Lax") for c in self.client.cookies.jar]
            descriptor=os.open(self.private_session_file,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
            with os.fdopen(descriptor,"w") as stream:
                json.dump({'cookies':cookies,'origins':[]},stream)
            self.proof['private_session_saved_for_owned_browser']=True
        self.save()

    def frozen_source(self):
        companies = self.get("/companies")
        selected = [c for c in companies if c["security_code"] == "000651"]
        if len(selected) != 1:
            raise StopRun("explicit_gree_company_not_unique")
        candidates = []
        for doc in self.get("/documents"):
            if doc["status"] != "ready":
                continue
            metadata = self.get(f"/documents/{quote(doc['document_id'], safe='')}/metadata")
            if (
                metadata["company_id"] == selected[0]["company_id"]
                and metadata["report_year"] == 2025
            ):
                candidates.append(doc["document_id"])
        if len(candidates) != 1:
            raise StopRun("explicit_gree_2025_source_not_unique_no_latest_fallback")
        source = self.get(f"/cplus/documents/{quote(candidates[0], safe='')}/research-source")
        if (
            source["kind"] != "fast"
            or source["company_id"] != selected[0]["company_id"]
            or source["report_year"] != 2025
        ):
            raise StopRun("frozen_source_identity_mismatch")
        raw = self.get(
            f"/documents/{quote(source['document_id'], safe='')}/file",
            params={
                "source_revision": source["source_revision"],
                "company_id": source["company_id"],
            },
            raw=True,
        )
        if hashlib.sha256(raw).hexdigest() != source["content_sha256"]:
            raise StopRun("http_pdf_sha_mismatch")
        import pymupdf

        with pymupdf.open(stream=raw, filetype="pdf") as pdf:
            pages = len(pdf)
        self.proof["source"] = source
        self.proof["http_pdf"] = {"sha256": source["content_sha256"], "physical_pages": pages}
        self.save()
        return source, pages

    def frozen_two_years(self):
        current,current_pages=self.frozen_source()
        older=[]
        for doc in self.get('/documents'):
            if doc['status']!='ready':
                continue
            metadata=self.get('/documents/'+quote(doc['document_id'],safe='')+'/metadata')
            if metadata['company_id']==current['company_id'] and metadata['report_year']==2024:
                older.append(doc['document_id'])
        if len(older)!=1:
            raise StopRun('explicit_gree_2024_not_unique')
        previous=self.get('/cplus/documents/'+older[0]+'/research-source')
        raw=self.get('/documents/'+older[0]+'/file',params={'source_revision':previous['source_revision'],'company_id':previous['company_id']},raw=True)
        if hashlib.sha256(raw).hexdigest()!=previous['content_sha256']:
            raise StopRun('older_http_pdf_sha_mismatch')
        import pymupdf
        with pymupdf.open(stream=raw,filetype='pdf') as pdf:
            previous_pages=len(pdf)
        sources=sorted([previous,current],key=lambda r:r['document_id'])
        pages={current['document_id']:current_pages,previous['document_id']:previous_pages}
        self.proof.update(interview_scope_variant='two_explicit_report_years_not_the_single_2025_fixed_fixture',sources=sources,http_pdfs=pages)
        self.save()
        return sources,pages

    def events(self, base, job_id):
        after, events = 0, []
        for _ in range(10):
            value = self.get(f"{base}/{job_id}/events", params={"after_seq": after})
            batch = value["events"]
            if not batch:
                return events
            if any(e["job_id"] != job_id for e in batch) or any(
                e["event_seq"] <= after for e in batch
            ):
                raise StopRun("events_cursor_or_identity_invalid")
            events.extend(batch)
            after = value["next_after_seq"]
        raise StopRun("events_page_bound_exceeded")

    def verify_findings(self, job, source, pages):
        selected=source if isinstance(source,list) else [source]
        findings = job["result"]["findings"]
        if any(f["kind"] == "confirmed_financial" for f in findings):
            raise StopRun("unexpected_financial_authority_with_no_selected_facts")
        verified, seen = [], set()
        for finding in findings:
            for ref in finding.get("evidence_refs", []):
                matched=[s for s in selected if s['document_id']==ref['document_id']]
                if len(matched)!=1:
                    raise StopRun('quote_outside_explicit_sources')
                frozen=matched[0]
                for key in (
                    "company_id",
                    "document_id",
                    "source_revision",
                    "content_sha256",
                    "parser_version",
                ):
                    if ref[key] != frozen[key]:
                        raise StopRun("quote_outside_exact_frozen_source")
                if not 1 <= ref["physical_page"] <= (pages[ref["document_id"]] if isinstance(pages,dict) else pages):
                    raise StopRun("quote_page_outside_http_pdf")
                signature = digest(ref)
                if signature in seen:
                    continue
                record = self.get(
                    f"/documents/{quote(ref['document_id'], safe='')}/evidence/{quote(ref['evidence_id'], safe='')}",
                    params={
                        "source_revision": ref["source_revision"],
                        "company_id": ref["company_id"],
                    },
                )
                if any(
                    record[k] != ref[k]
                    for k in ("document_id", "company_id", "source_revision", "evidence_id")
                ):
                    raise StopRun("evidence_endpoint_identity_changed")
                if (
                    record["physical_page"] != ref["physical_page"]
                    or not ref["text"]
                    or ref["text"] not in record["text"]
                ):
                    raise StopRun("complete_exact_quote_not_in_current_server_record")
                seen.add(signature)
                verified.append({"evidence_ref": ref, "exact_record_verified": True})
        return verified

    def run_case(self, case, mode, upper, source, pages, *, prepared=None):
        self.window.admit(
            upper - (2 if prepared else 0)
        )  # Require the complete mode's worst-case headroom before its first paid phase.
        first = self.window.current()
        entry = {
            "case_id": case["id"],
            "exact_question": case["question"],
            "mode": mode,
            "state": "STARTING",
            "case_upper_model_attempts": upper,
            "budget_before": public_budget(first),
        }
        self.proof["cases"].append(entry)
        self.save()
        selected=source if isinstance(source,list) else [source]
        prepaid=2 if prepared else 0
        if prepared:
            if prepared['case_id']!=case['id'] or prepared['exact_question']!=case['question'] or prepared['mode']!=mode or prepared.get('job_ack'):
                raise StopRun('prepared_case_mismatch_or_job_already_dispatched')
            conversation,intent,plan=(prepared[k] for k in ('conversation','intent','plan'))
            entry.update(conversation=conversation,intent=intent,plan=plan,prepaid_successful_calls=2)
            after_intent=None
        else:
            conversation = self.post(
                "/conversations",
                {
                    "document_ids": [s["document_id"] for s in selected],
                    "title": f"C+ {case['id']} {mode} bounded source study",
                },
                recovery=lambda oid: "/conversations/by-operation/" + oid,
            )
            expected = [{k: s[k] for k in IDENTITY_KEYS} for s in selected]
            if sorted(conversation["sources"],key=lambda r:r["document_id"]) != sorted(expected,key=lambda r:r["document_id"]) or conversation.get("active_turn_id"):
                raise StopRun("conversation_scope_not_exact_or_has_active_turn")
            entry["conversation"] = conversation
            self.save()
            cid = conversation["conversation_id"]
            intent = self.post(
                "/research/intent",
                {"conversation_id": cid, "text": case["question"], "requested_mode": mode},
                upper=1,
                recovery=lambda oid: "/research/operations/" + oid,
            )
            entry["intent"] = intent
            self.save()
            if (
                intent["provider_error"] is not None
                or intent["proposal_origin"] != "model_proposal_program_validated"
                or intent["clarifying_question"]
            ):
                raise StopRun("intent_fallback_unknown_or_clarification_retained_no_next_model_phase")
            if (
                intent["mode"] != mode
                or intent["goal"] != case["question"]
                or intent["scope"]["source_scope_sha"] != conversation["source_scope_sha"]
            ):
                raise StopRun("intent_scope_or_goal_changed")
            after_intent = self.window.current()
            if len(after_intent["rows"]) - len(first["rows"]) != 1:
                raise StopRun("intent_physical_denominator_not_one_check_shared_window_or_guard")
            plan = self.post(
                "/synthesis/plans",
                {"intent_id": intent["intent_id"]},
                upper=1,
                recovery=lambda oid: "/research/operations/" + oid,
            )
            entry["plan"] = plan
            self.save()
        roles = plan["roles"]
        valid_roles=(len(roles)==2 and len(set(roles))==2 and "evidence" in roles and set(roles)<={"evidence","finance","risk_operations"}) if mode=="deep" else roles==["generalist"]
        if (
            plan["provider_error"] is not None
            or plan["plan_origin"] != "supervisor_model_program_validated"
            or plan["mode"] != mode
            or not valid_roles
            or plan["scope"] != intent["scope"]
            or not plan["requires_explicit_confirmation"]
        ):
            raise StopRun("plan_not_model_validated_or_role_scope_changed")
        expected_cap = 10 if mode == "deep" else 5
        if (
            plan["limits"]["model_attempts"] != expected_cap
            or plan["limits"]["parallel_agents"] != 2
        ):
            raise StopRun("server_execution_bounds_changed_do_not_guess_new_denominator")
        after_plan = self.window.current()
        if not prepared and len(after_plan["rows"]) - len(after_intent["rows"]) != 1:
            raise StopRun("plan_physical_denominator_not_one")
        approval = {
            "approved_plan_id": plan["plan_id"],
            "approved_plan_revision": plan["revision"],
            "approved_plan_sha256": plan["plan_sha256"],
            "confirmed": True,
        }
        entry["explicit_approval"] = approval
        entry["approval_basis"] = (
            "operator explicitly runs this fixed-case bounded harness; exact stored plan identity/roles checked and persisted before POST"
        )
        self.save()
        base = "/deep-research/jobs" if mode == "deep" else "/synthesis/jobs"
        queued = self.post(
            base,
            approval,
            upper=expected_cap - 2,
            recovery=lambda oid: "/research/operations/" + oid,
        )
        entry["job_ack"] = queued
        self.save()
        deadline = self.monotonic() + 300
        while True:
            job = self.get(base + "/" + queued["job_id"])
            entry["job"] = job
            self.save()
            if job["state"] in TERMINAL:
                break
            if job["state"] not in ("queued", "running") or self.monotonic() >= deadline:
                raise StopRun("job_poll_bound_reached_original_job_retained_no_new_start")
            self.sleep(1)
        stable_before = self.window.current()
        entry["events"] = self.events(base, job["job_id"])
        self.save()
        if job["state"] != "completed":
            raise StopRun("job_partial_failed_or_interrupted_retained_no_report_or_next_job")
        if (
            job["mode"] != mode
            or job["plan_id"] != plan["plan_id"]
            or job["scope"] != intent["scope"]
            or sorted(a["agent_id"] for a in job["result"]["agents"]) != sorted(roles)
            or any(a["state"] != "completed" for a in job["result"]["agents"])
        ):
            raise StopRun("job_roles_or_frozen_scope_not_completed")
        phases = {e["agent_id"] for e in entry["events"]}
        if not {"controller", "supervisor", "verifier", *roles}.issubset(phases):
            raise StopRun("native_handoff_phase_events_missing")
        for role in roles:
            steps = [s for s in job["steps"] if s["agent_id"] == role and s["state"] == "completed"]
            required_tool="read_confirmed_facts" if role=="finance" else "search_evidence"
            if not steps or not any(required_tool in step["tools"] for step in steps):
                raise StopRun("required_native_evidence_tool_trace_missing")
        entry["exact_quotes"] = self.verify_findings(job, source, pages)
        entry["model_interpretations"] = sum(
            f["kind"] == "model_interpretation" for f in job["result"]["findings"]
        )
        entry["logical_model_attempts"] = job["usage"]["attempts"]
        entry["physical_guard_rows_for_case"] = len(self.window.current()["rows"]) - len(
            first["rows"]
        ) + prepaid
        entry["logical_minus_physical"] = (
            entry["logical_model_attempts"] - entry["physical_guard_rows_for_case"]
        )
        if (
            entry["logical_minus_physical"] != 0
            or job["usage"]["unknown_attempts"]
            or not entry["exact_quotes"]
        ):
            raise StopRun("usage_denominator_or_exact_evidence_not_reconciled")
        # Read job/events/source evidence again without model activity before report writes.
        self.get(base + "/" + job["job_id"])
        if self.window.current() != stable_before:
            raise StopRun("read_only_phase_changed_provider_ledger_shared_activity_or_late_usage")
        self.window.admit(0)
        draft = self.post(
            "/showcase-reports/drafts",
            {"job_id": job["job_id"]},
            recovery=lambda oid: "/showcase-reports/operations/" + oid,
        )
        saved = self.post(
            "/showcase-reports",
            {
                "draft_id": draft["draft_id"],
                "title": f"{case['id']} {mode} · AI待审研究",
                "notes": "原文与解释分开；没有人工财务签核。",
            },
            recovery=lambda oid: "/showcase-reports/operations/" + oid,
        )
        entry["saved_report"] = saved
        self.save()
        report = self.get(f"/showcase-reports/{saved['report_id']}/revisions/{saved['revision']}")
        if report["current_source_status"] != "current":
            raise StopRun("saved_report_current_source_unavailable")

        def project(findings):
            return [
                {
                    k: f.get(k)
                    for k in ("finding_id", "kind", "text", "evidence_refs", "financial_refs")
                }
                for f in findings
            ]

        if project(report["snapshot"]["findings"]) != project(job["result"]["findings"]):
            raise StopRun("report_snapshot_content_changed")
        entry["report_revision"] = report
        entry["reads_and_report_writes_zero_new_model_rows"] = (
            self.window.current() == stable_before
        )
        if not entry["reads_and_report_writes_zero_new_model_rows"]:
            raise StopRun("report_or_read_appended_model_call")
        entry["state"] = "COMPLETED_HTTP_AGENT_TOOL_REPORT_PATH_HUMAN_REVIEW_PENDING"
        entry["budget_after"] = public_budget(self.window.current())
        self.save()

    def execute(self, cases, username, password, *, only_mode=None, paired_case=False, two_years=False):
        try:
            self.login(username, password)
            source, pages = self.frozen_two_years() if two_years else self.frozen_source()
            modes=(("E01-15","deep",10),("E01-15","synthesis",5)) if paired_case else CASE_MODES
            for case_id, mode, upper in modes:
                if only_mode and mode != only_mode:
                    continue
                self.run_case(cases[case_id], mode, upper, source, pages)
            if paired_case and not only_mode:
                a,b=self.proof["cases"]
                self.proof["paired_same_question_comparison"]=(a["exact_question"]==b["exact_question"] and a["conversation"]["sources"]==b["conversation"]["sources"])
            self.proof["execution"] = "COMPLETED_REQUESTED_HTTP_PATHS_NOT_HUMAN_ANSWER_ACCEPTANCE"
        except Exception as exc:
            self.proof["execution"] = "STOPPED_WITH_RECEIPTS_NO_REPLAY"
            self.proof["stop"] = {"type": type(exc).__name__, "reason": str(exc)[:500]}
        finally:
            self.save()
        return self.proof


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--origin", required=True)
    p.add_argument(
        "--login-config",
        required=True,
        type=Path,
        help="Dedicated DEMO_USERNAME/DEMO_PASSWORD file, not LLM/root .env",
    )
    p.add_argument("--existing-budget-db", required=True, type=Path)
    p.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Fresh empty output directory; existing runs are never resumed",
    )
    p.add_argument("--max-new-calls", required=True, type=int, choices=range(1, 13))
    p.add_argument("--only-mode", choices=("deep", "synthesis"))
    p.add_argument("--api-prefix",choices=("", "/api"),default="",help="Use /api through the local React gateway; empty for direct controller")
    p.add_argument("--two-report-years",action="store_true",help="Additional interview scenario with both explicit Gree2024/25 PDFs; not the single-year fixed-case fixture")
    p.add_argument("--paired-case",action="store_true",help="Execute the exact E01-15 question independently in both modes")
    p.add_argument("--private-session-file",type=Path,help="New ignored data/600 storage state for the root-owned browser only; never written into evidence")
    args = p.parse_args()
    u = urlsplit(args.origin)
    if (
        u.scheme != "http"
        or u.hostname not in ("127.0.0.1", "localhost")
        or u.username
        or u.password
        or u.path
        or u.query
        or u.fragment
    ):
        p.error("--origin must be an exact loopback HTTP origin without credentials/path")
    if args.output.exists() and any(args.output.iterdir()):
        p.error("existing output refused; inspect/reconcile the original run, do not auto-resume")
    args.output.mkdir(parents=True, exist_ok=True)
    if args.private_session_file is not None:
        args.private_session_file=args.private_session_file.resolve()
        if not args.private_session_file.is_relative_to((PROJECT/"data").resolve()) or args.private_session_file.exists():
            p.error("private session must be a new file in ignored project data")
        args.private_session_file.parent.mkdir(parents=True,exist_ok=True)
    # This branch is for the authorized root operator only. Worker fixture tests
    # inject a fake reader/MockTransport and never call main with real paths.
    from app.demo.shared_budget import existing_shared_budget
    from dotenv import dotenv_values

    budget_path = existing_shared_budget(args.existing_budget_db, PROJECT)
    config = dotenv_values(args.login_config, interpolate=False)
    if set(config) != {"DEMO_USERNAME", "DEMO_PASSWORD"} or not all(config.values()):
        p.error(
            "login config must contain only nonempty DEMO_USERNAME and DEMO_PASSWORD; no owner/LLM secrets"
        )
    fixed_path = PROJECT / "docs/cplus/eval/fixed-cases.json"
    cases = {c["id"]: c for c in json.loads(fixed_path.read_text())["cases"]}
    with httpx.Client(
        base_url=args.origin,
        headers={"Origin": args.origin},
        trust_env=False,
        follow_redirects=False,
        timeout=httpx.Timeout(100, connect=3),
    ) as client:
        runner = Runner(
            client,
            Window(SQLiteLedger(budget_path), args.max_new_calls),
            args.output,
            tier="OPERATOR_REAL_HTTP_GUARDED_SDK",
            api_prefix=args.api_prefix,
            private_session_file=args.private_session_file,
        )
        runner.proof.update(
            script_sha256=file_sha(Path(__file__)),
            fixed_cases_sha256=file_sha(fixed_path),
            source_contract_baseline="e510876",
            runner_checkout_head=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True
            ).strip(),
            audited_contract_sha256={
                name: file_sha(PROJECT / name)
                for name in (
                    "app/showcase_research/api.py",
                    "app/showcase_research/models.py",
                    "app/showcase_research/jobs.py",
                    "app/showcase_research/agents.py",
                    "app/showcase_research/provider.py",
                    "app/conversations/models.py",
                    "app/showcase_reports/api.py",
                    "app/showcase_reports/research_adapter.py",
                )
            },
            origin=args.origin,
        )
        result = runner.execute(
            cases, config["DEMO_USERNAME"], config["DEMO_PASSWORD"], only_mode=args.only_mode, paired_case=args.paired_case, two_years=args.two_report_years
        )
    print(
        json.dumps(
            {
                "execution": result["execution"],
                "new_guard_rows": result["new_guard_rows_count"],
                "output": str(args.output / "result.json"),
            },
            ensure_ascii=False,
        )
    )
    raise SystemExit(0 if result["execution"].startswith("COMPLETED_") else 2)


if __name__ == "__main__":
    main()
