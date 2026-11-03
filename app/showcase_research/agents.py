"""Finite native-function agents: separate role prompts, tools and structured handoffs."""
import asyncio
import json
import time
from uuid import uuid4

from app.showcase_research.findings import interpretation, selected_financial_scope, unresolved
from app.showcase_research.models import AgentDraft, ResearchError
from app.showcase_research.store import canonical

TOOL_SCHEMAS = {
    "search_evidence": {"type": "function", "function": {"name": "search_evidence", "description": "Search only server-frozen annual-report sources; no writes or web requests.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string", "maxLength": 1000}}, "required": ["query"], "additionalProperties": False}}},
    "read_confirmed_facts": {"type": "function", "function": {"name": "read_confirmed_facts", "description": "Read only the user's frozen selected local_operator facts; missing facts remain unresolved.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
    "recall_notes": {"type": "function", "function": {"name": "recall_notes", "description": "Read the frozen semantic-memory snapshot; user notes never grant financial truth.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
}
ROLE_TOOLS = {"evidence": ("search_evidence", "recall_notes"), "finance": ("read_confirmed_facts",),
              "risk_operations": ("search_evidence", "recall_notes"), "generalist": tuple(TOOL_SCHEMAS)}
PURPOSES = {"evidence": "Locate exact original report passages. Do not calculate or approve finance.",
            "finance": "Read admitted selected finance or explain missing confirmation. Never select latest facts or write receipts.",
            "risk_operations": "Inspect disclosed operating risks and conditions; separate quoted evidence from interpretation.",
            "generalist": "Read evidence and, if required, selected confirmed finance; no signing or write capabilities."}


class AgentRunner:
    def __init__(self, service):
        self.service = service

    async def tool(self, job_id, intent_id, role, name, arguments, scope, intent):
        service = self.service
        if name not in ROLE_TOOLS[role] or type(arguments) is not dict:
            raise ResearchError("agent_tool_not_allowed")
        if name == "search_evidence":
            if set(arguments) != {"query"} or not isinstance(arguments["query"], str) or not 1 <= len(arguments["query"]) <= 1000:
                raise ResearchError("invalid_agent_tool_arguments")
        elif arguments:
            raise ResearchError("invalid_agent_tool_arguments")
        service.scopes.before_model(scope)
        attempt = service.store.reserve_call(intent_id, role, kind="tool", output_limit=0)
        service.store.event(job_id, role, name, "running", event_type="tool")
        async def execute():
            if name == "search_evidence":
                selection = service.conversations.selection(scope["conversation_id"], arguments["query"])
                hits = await service.search.search(selection, top_k=6)
                # Business-risk questions should not publish covers or unrelated
                # table chunks as useful evidence. This ranks only actual hits
                # within the frozen scope; it invents no pages, text or amounts.
                if "风险" in arguments["query"]:
                    hits = tuple(sorted(
                        (hit for hit in hits if "风险" in hit.text and len(hit.text) >= 60),
                        key=lambda hit: sum(hit.text.count(term) for term in (
                            "市场竞争", "宏观经济", "原材料", "海外市场", "汇率", "风险")),
                        reverse=True,
                    ))[:3]
                findings = []
                for hit in hits:
                    try:
                        findings.append(await service.findings.quote(scope, hit))
                    except ResearchError:
                        continue
                return findings or [unresolved("检索结果没有通过固定来源和逐页精确引用核验。")]
            if name == "read_confirmed_facts":
                try:
                    findings, _ = await service.findings.confirmed(selected_financial_scope(intent))
                    return findings
                except Exception as exc:
                    return [unresolved("所选财务事实当前不可准入，请人工核对。", getattr(exc, "code", "financial_admission_failed"))]
            return [{"memory_id": note["memory_id"], "revision": note["revision"], "text": note["text"], "authority": "untrusted_research_lead"}
                    for note in scope["memory_items"]]
        remaining = min(20, service.store.usage(intent_id)["deadline"] - time.time())
        result = await asyncio.wait_for(execute(), timeout=max(0.001, remaining))
        service.store.returned(attempt)
        service.scopes.before_model(scope)
        service.store.event(job_id, role, name, "completed", event_type="tool")
        return result

    async def run(self, job_id, intent, role):
        service, scope = self.service, intent["scope"]
        step_id, findings, trace = str(uuid4()), [], []
        with service.store.tx() as db:
            db.execute("INSERT INTO sr_steps VALUES (?,?,?,'running',?)", (step_id, job_id, role, canonical({"tools": []})))
        service.store.event(job_id, role, "子任务开始", "running")
        try:
            known, draft = {}, None
            for iteration in range(3):
                service.scopes.before_model(scope)
                compact_results = [{"name": t["name"], "result": [{"reference_id": item.get("finding_id", item.get("memory_id")),
                    "kind": item.get("kind", "research_note"), "text": item.get("text", "")[:400],
                    "numeric_authority": item.get("kind") == "confirmed_financial"} for item in t["result"]]} for t in trace]
                prompt = "ROLE=" + role + "\n" + canonical({"purpose": PURPOSES[role], "goal": intent["goal"],
                    "sources": scope["sources"], "selected_companies": intent["company_ids"],
                    "requested_fact_periods": intent["periods"], "requested_metric_keys": intent["metric_keys"], "tools_used": compact_results,
                    "contract": "Use permitted local function tools first. Then return ONLY one JSON object {interpretations:[{text,evidence_ids:[reference_id]}]}, no markdown or prose outside JSON. At most 2 interpretations, each at most 180 Chinese characters and 2 reference IDs. Summarize briefly, do not reproduce full excerpts: the program publishes exact excerpts separately. Explain evidence gaps; do not invent missing risks. No thinking, no financial_refs, no raw authority. Numeric interpretation stays unverified."})
                used = {t["name"] for t in trace}
                mandatory = "read_confirmed_facts" if role == "finance" else "search_evidence"
                required = mandatory if mandatory not in used else "read_confirmed_facts" if (
                    role == "generalist" and intent["requires_confirmed_facts"] and "read_confirmed_facts" not in used) else None
                choice = {"type": "function", "function": {"name": required}} if required else None
                response = await service.provider.json(intent["intent_id"], role, prompt,
                    tools=[TOOL_SCHEMAS[name] for name in ROLE_TOOLS[role]], tool_choice=choice)
                if not isinstance(response, dict) or response.get("role") != "assistant":
                    raise ResearchError("agent_protocol_error")
                calls = response.get("tool_calls") or []
                if calls:
                    # Some compatible providers return multiple calls even with
                    # parallel_tool_calls=False. Bound and validate the batch,
                    # then execute it sequentially through the same tool gate.
                    # Accompanying prose is discarded, never published.
                    if not isinstance(calls, list) or len(calls) > 3:
                        raise ResearchError("agent_tool_batch_limit_exceeded")
                    checked_calls = []
                    for call in calls:
                        function = call.get("function", {})
                        if call.get("type") != "function" or not isinstance(function.get("arguments"), str):
                            raise ResearchError("agent_tool_call_protocol_error")
                        arguments = json.loads(function["arguments"])
                        if function.get("name") not in ROLE_TOOLS[role]:
                            raise ResearchError("agent_tool_not_allowed")
                        checked_calls.append((function["name"], arguments))
                    for name, arguments in checked_calls:
                        result = await self.tool(job_id, intent["intent_id"], role, name, arguments, scope, intent)
                        trace.append({"name": name, "arguments": arguments, "state": "completed", "result": result})
                        for item in result:
                            if "finding_id" in item:
                                known[item["finding_id"]] = item
                                findings.append(item)
                        with service.store.tx() as db:
                            db.execute("UPDATE sr_steps SET payload=? WHERE id=?", (canonical({"tools": trace}), step_id))
                    continue
                content = response.get("content")
                if not isinstance(content, str) or len(content) > 12000:
                    raise ResearchError("agent_draft_invalid")
                draft = AgentDraft.model_validate(json.loads(content))
                break
            mandatory = "read_confirmed_facts" if role == "finance" else "search_evidence"
            if mandatory not in {t["name"] for t in trace}:
                raise ResearchError("agent_required_tool_missing")
            if role == "generalist" and intent["requires_confirmed_facts"] and "read_confirmed_facts" not in {t["name"] for t in trace}:
                findings.append(unresolved("单Agent未取得已选择的财务事实；未发布金融数值解释。"))
            if draft is None:
                raise ResearchError("agent_round_limit_reached")
            for item in draft.interpretations:
                if set(item.evidence_ids) - set(known):
                    raise ResearchError("agent_reference_not_from_tools")
                refs = [ref for key in item.evidence_ids for ref in known[key].get("evidence_refs", [])]
                findings.append(interpretation(item.text, refs))
            with service.store.tx() as db:
                db.execute("UPDATE sr_steps SET state='completed',payload=? WHERE id=?", (canonical({"tools": trace, "findings": findings}), step_id))
            service.store.event(job_id, role, "子任务已交接", "completed")
            return {"agent_id": role, "findings": findings, "state": "completed"}
        except Exception as exc:
            code = getattr(exc, "code", "agent_draft_invalid_json" if isinstance(exc, json.JSONDecodeError) else "agent_draft_schema_invalid" if type(exc).__name__ == "ValidationError" else "agent_provider_unknown_or_failed")
            with service.store.tx() as db:
                db.execute("UPDATE sr_steps SET state='failed',payload=? WHERE id=?", (canonical({"tools": trace, "error_code": code}), step_id))
            service.store.event(job_id, role, "子任务未完成", "failed", public_summary=code)
            return {"agent_id": role, "findings": [unresolved("研究子任务未完成。", code)], "state": "failed"}
