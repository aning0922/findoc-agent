"""Approved plans → finite native-function agents → verified durable results. GET never executes."""
import asyncio
import json
import time
from uuid import uuid4

from app.showcase_research.agents import AgentRunner, ROLE_TOOLS
from app.showcase_research.findings import interpretation, selected_financial_scope, unresolved
from app.showcase_research.models import AgentDraft, ResearchError, SupervisorProposal
from app.showcase_research.store import canonical, sha, timestamp


class ResearchJobs:
    async def plan(self, request, identity):
        intent = self.store.get(request.intent_id, "intent")
        scope = intent["scope"]
        self.scopes.identity(scope, identity)
        if intent["clarifying_question"]:
            raise ResearchError("intent_needs_clarification")
        if intent["mode"] == "quick":
            raise ResearchError("quick_mode_uses_existing_readonly_flow")
        old = self.store.reserve_operation(request.operation_id, "plan", request.model_dump())
        if old is not None:
            return old
        financial = intent["requires_confirmed_facts"] or bool(intent["metric_keys"]) and not any(t in intent["goal"] for t in ("只要原文", "不要计算"))
        roles = ["generalist"] if intent["mode"] == "synthesis" else ["evidence", "finance" if financial else "risk_operations"]
        origin, error = "program_condition_router", None
        if self.provider.configured:
            self.scopes.before_model(scope)
            prompt = "KIND=plan\n" + canonical({"goal": intent["goal"], "mode": intent["mode"],
                "safe_fallback": {"roles": roles, "goal": intent["goal"]},
                "contract": "Return JSON roles/goal only. Roles must match the server-selected route. No sub-delegation or permission changes."})
            try:
                proposed = SupervisorProposal.model_validate(await self.provider.json(intent["intent_id"], "supervisor", prompt))
                if proposed.goal != intent["goal"] or proposed.roles != roles:
                    raise ResearchError("supervisor_route_outside_approved_scope")
                origin = "supervisor_model_program_validated"
            except Exception as exc:
                error = getattr(exc, "code", "supervisor_unknown_or_invalid")
        else:
            error = "provider_unconfigured"
        value = {"schema_version": "research-plan-v2", "plan_id": str(uuid4()), "revision": 1, "intent_id": intent["intent_id"],
            "conversation_id": intent["conversation_id"], "goal": intent["goal"], "mode": intent["mode"],
            "company_ids": intent["company_ids"], "periods": intent["periods"], "metric_keys": intent["metric_keys"],
            "roles": roles, "allowed_tools": {role: list(ROLE_TOOLS[role]) for role in roles},
            "limits": {"model_attempts": {"synthesis": 5, "deep": 10}[intent["mode"]], "tool_calls": 12,
                       "parallel_agents": 2, "execution_seconds": 240, "per_call_output_tokens": 1024,
                       "reserved_input_tokens": 48000, "reserved_output_tokens": 12000},
            "plan_origin": origin, "provider_error": error, "scope": scope, "requires_explicit_confirmation": True}
        value["plan_sha256"] = sha(value)
        result = {**{k: v for k, v in value.items() if k != "scope"}, "scope": self.scopes.public(scope)}
        with self.scopes.publication(scope) as db:
            self.store.record(db, "plan", value["plan_id"], value)
            self.store.finish(db, request.operation_id, result, value["plan_id"])
        return result

    async def create_job(self, request, identity, mode):
        plan = self.store.get(request.approved_plan_id, "plan")
        scope = plan["scope"]
        self.scopes.identity(scope, identity)
        if (plan["revision"] != request.approved_plan_revision or plan["plan_sha256"] != request.approved_plan_sha256 or
                sha({k: v for k, v in plan.items() if k != "plan_sha256"}) != plan["plan_sha256"] or plan["mode"] != mode):
            raise ResearchError("approved_plan_mismatch")
        old = self.store.reserve_operation(request.operation_id, "job:" + mode, request.model_dump())
        if old is not None:
            return old
        intent = self.store.get(plan["intent_id"], "intent")
        await self.preparer.revalidate(self.conversations.selection(scope["conversation_id"], scope["query"]))
        job_id = str(uuid4())
        result = {"schema_version": "showcase-job-v2", "job_id": job_id, "mode": mode, "state": "queued",
                  "conversation_id": plan["conversation_id"], "plan_id": plan["plan_id"]}
        with self.scopes.publication(scope) as db:
            if db.execute("SELECT 1 FROM sr_jobs WHERE plan_id=?", (plan["plan_id"],)).fetchone():
                raise ResearchError("approved_plan_already_executed")
            db.execute("INSERT INTO sr_jobs VALUES (?,?,?,?,?,?,NULL,NULL,?,NULL)",
                       (job_id, plan["plan_id"], plan["conversation_id"], mode, "queued", canonical(scope), timestamp()))
            db.execute("UPDATE sr_budgets SET deadline=min(deadline,?) WHERE id=?", (min(time.time() + 240, scope["lease_expires_at"]), intent["intent_id"]))
            self.store.finish(db, request.operation_id, result, job_id)
        self.store.event(job_id, "controller", "批准计划已登记", "completed")
        task = asyncio.create_task(self._execute(job_id, plan, intent))
        self.pending_jobs.add(task)
        task.add_done_callback(self.pending_jobs.discard)
        return result

    async def _execute(self, job_id, plan, intent):
        scope = intent["scope"]
        try:
            with self.store.tx() as db:
                db.execute("UPDATE sr_jobs SET state='running' WHERE id=? AND state='queued'", (job_id,))
            self.store.event(job_id, "supervisor", "按计划分派只读子任务", "running")
            semaphore = asyncio.Semaphore(2)
            runner = AgentRunner(self)
            async def run(role):
                async with semaphore:
                    return await runner.run(job_id, intent, role)
            results = await asyncio.gather(*(run(role) for role in plan["roles"]))
            findings = [finding for result in results for finding in result["findings"]]
            partial = any(result["state"] != "completed" for result in results)
            self.store.event(job_id, "verifier", "复核引用与财务资格", "running")
            await self.findings.revalidate_quotes(scope, findings)
            if any(f["kind"] == "confirmed_financial" for f in findings):
                admitted, groups = await self.findings.confirmed(selected_financial_scope(intent))
                expected = [(f["text"], f["financial_refs"]) for f in admitted if f["kind"] == "confirmed_financial"]
                actual = [(f["text"], f["financial_refs"]) for f in findings if f["kind"] == "confirmed_financial"]
                if expected != actual:
                    raise ResearchError("financial_rendering_changed")
            else:
                groups = []
            if plan["mode"] == "deep" and not partial:
                self.scopes.before_model(scope)
                prompt = "KIND=merge\n" + canonical({"goal": intent["goal"], "verified_findings": [
                    {"reference_id": f["finding_id"], "kind": f["kind"], "text": f["text"][:500]} for f in findings],
                    "contract": "Return JSON {interpretations:[{text,evidence_ids:[reference_id]}]}; no thinking, no financial_refs, never approve numbers."})
                try:
                    merged = AgentDraft.model_validate(await self.provider.json(intent["intent_id"], "supervisor_merge", prompt))
                    known = {f["finding_id"]: f for f in findings}
                    for item in merged.interpretations:
                        if set(item.evidence_ids) - set(known):
                            raise ResearchError("merge_reference_unverified")
                        refs = [ref for key in item.evidence_ids for ref in known[key].get("evidence_refs", [])]
                        findings.append(interpretation(item.text, refs))
                except Exception as exc:
                    partial = True
                    findings.append(unresolved("汇合解释未完成，保留已经核验的工具结果。", getattr(exc, "code", "merge_provider_unknown")))
            await self.findings.revalidate_quotes(scope, findings)
            self.store.event(job_id, "verifier", "结果核验完成，准备保存", "completed")
            self.scopes.before_model(scope)
            if self.store.usage(intent["intent_id"])["deadline"] <= time.time():
                raise ResearchError("budget_deadline_exhausted")
            result = {"schema_version": "showcase-research-result-v2", "job_id": job_id, "goal": intent["goal"],
                      "mode": plan["mode"], "findings": findings, "scope_hash": scope["scope_hash"],
                      "agents": [{"agent_id": r["agent_id"], "state": r["state"]} for r in results],
                      "data_origin": self.execution_data_origin,
                      "limitations": ["AI interpretation is unreviewed; unresolved findings are not confirmed financial facts.",
                                      "Provider token usage is unknown unless separately supplied by the deployment cost guard."]}
            state = "partial" if partial else "completed"
            with self.scopes.publication(scope) as db:
                deadline = db.execute("SELECT deadline FROM sr_budgets WHERE id=?", (intent["intent_id"],)).fetchone()[0]
                if deadline <= time.time():
                    raise ResearchError("budget_deadline_exhausted")
                if groups:
                    checked = self.facts.recheck_persisted_analysis_in(db, workspace_id=scope["workspace_id"],
                        receipt_ids=tuple(g.fact_set_id for g in groups), confirmation_kind="local_operator")
                    if checked != tuple(groups):
                        raise ResearchError("financial_fact_changed")
                self.store.record(db, "job-result", job_id, result)
                # Publication transaction COMMIT is inside the memory.publication_guard context.
                db.execute("UPDATE sr_jobs SET state=?,result=?,ended_at=? WHERE id=? AND state='running'",
                           (state, canonical(result), timestamp(), job_id))
            self.store.event(job_id, "controller", "结果已保存", state)
        except asyncio.CancelledError:
            self._interrupt(job_id, "execution_cancelled")
            raise
        except Exception as exc:
            self._interrupt(job_id, getattr(exc, "code", "job_execution_failed"))

    def _interrupt(self, job_id, code):
        with self.store.tx() as db:
            db.execute("UPDATE sr_steps SET state='interrupted' WHERE run_id=? AND state='running'", (job_id,))
            changed = db.execute("UPDATE sr_jobs SET state='interrupted',result=NULL,error=?,ended_at=? WHERE id=? AND state IN ('queued','running')",
                       (code, timestamp(), job_id))
            if changed.rowcount != 1:
                return
        self.store.event(job_id, "controller", "执行中断，未发布新结果", "interrupted", public_summary=code)

    def job(self, job_id, identity):
        with self.store.tx() as db:
            row = db.execute("SELECT * FROM sr_jobs WHERE id=?", (job_id,)).fetchone()
            steps = db.execute("SELECT * FROM sr_steps WHERE run_id=? ORDER BY rowid", (job_id,)).fetchall()
        if row is None:
            raise ResearchError("job_not_found", 404)
        scope = json.loads(row["scope"])
        self.scopes.identity(scope, identity)
        plan = self.store.get(row["plan_id"], "plan")
        if row["result"] and self.store.get(job_id, "job-result") != json.loads(row["result"]):
            raise ResearchError("job_result_integrity_error", 503)
        return {"schema_version": "showcase-job-v2", "job_id": job_id, "plan_id": row["plan_id"],
                "conversation_id": row["conversation_id"], "mode": row["mode"], "state": row["state"],
                "created_at": row["created_at"], "ended_at": row["ended_at"], "error_code": row["error"],
                "scope": self.scopes.public(scope), "usage": self.store.usage(plan["intent_id"]),
                "steps": [{"step_id": s["id"], "agent_id": s["agent_id"], "state": s["state"],
                           "tools": [t["name"] for t in json.loads(s["payload"]).get("tools", [])]} for s in steps],
                "result": json.loads(row["result"]) if row["result"] else None}

    def jobs(self, identity, *, conversation_id=None, mode=None):
        self.scopes.check_identity(identity)
        if conversation_id:
            self.conversations.selection(conversation_id, "read job history")
        with self.store.tx() as db:
            rows = db.execute("SELECT id FROM sr_jobs WHERE (? IS NULL OR conversation_id=?) AND (? IS NULL OR mode=?) ORDER BY created_at DESC LIMIT 20",
                              (conversation_id, conversation_id, mode, mode)).fetchall()
        return {"schema_version": "showcase-job-list-v2", "items": [self.job(row["id"], identity) for row in rows]}

    async def verified_job(self, job_id, identity):
        """Zero-provider report adapter input; root projects financial_refs to verified ID strings."""
        value = self.job(job_id, identity)
        if value["state"] != "completed" or value["result"] is None:
            raise ResearchError("completed_job_required")
        with self.store.tx() as db:
            scope = json.loads(db.execute("SELECT scope FROM sr_jobs WHERE id=?", (job_id,)).fetchone()[0])
        self.scopes.before_model(scope)  # only checks generations, never invokes a provider.
        await self.preparer.revalidate(self.conversations.selection(scope["conversation_id"], scope["query"]))
        findings = value["result"]["findings"]
        await self.findings.revalidate_quotes(scope, findings)
        groups = []
        plan = self.store.get(value["plan_id"], "plan")
        intent = self.store.get(plan["intent_id"], "intent")
        if any(f["kind"] == "confirmed_financial" for f in findings):
            admitted, groups = await self.findings.confirmed(selected_financial_scope(intent))
            if [(f["text"], f["financial_refs"]) for f in admitted if f["kind"] == "confirmed_financial"] != [
                    (f["text"], f["financial_refs"]) for f in findings if f["kind"] == "confirmed_financial"]:
                raise ResearchError("financial_rendering_changed")
        with self.scopes.publication(scope) as db:
            if groups:
                checked = self.facts.recheck_persisted_analysis_in(db, workspace_id=scope["workspace_id"],
                    receipt_ids=tuple(g.fact_set_id for g in groups), confirmation_kind="local_operator")
                if checked != tuple(groups):
                    raise ResearchError("financial_fact_changed")
        plan = self.store.get(value["plan_id"], "plan")
        names = [c["name"] for c in scope["companies"] if c["company_id"] in plan["company_ids"]]
        return {"job_id": job_id, "workspace_id": scope["workspace_id"], "state": "completed", "company_name": "、".join(names),
                "period_label": "、".join(str(p) for p in plan["periods"]) or "披露原文范围", "data_origin": value["result"]["data_origin"],
                "findings": findings, "limitations": value["result"]["limitations"]}

    async def close(self):
        tasks = list(self.pending_jobs)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
