"""Finite real-service LangGraph. No saver, replay, retries, or write tools."""

from dataclasses import replace
import time
from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.conversations.context import ConversationContext, load_context, resolve
from app.conversations.models import MemoryCandidate, ResolvedQuery, TurnResult, error_result
from app.conversations.repository import ConversationError
from app.conversations.service import ExecutionResult, TurnExecution
from app.conversations.tools import ConversationTools
from app.memory.candidates import extract_user_memory_candidates
from app.memory.service import MemoryService


class State(TypedDict, total=False):
    execution: TurnExecution
    context: ConversationContext
    resolved: ResolvedQuery
    reason: str | None
    deadline: float
    output: ExecutionResult


class ConversationGraph:
    def prepare_context(self, execution: TurnExecution) -> None:
        from app.conversations.summaries import SummaryRepository
        SummaryRepository(execution.repository).refresh(execution, self.memory)

    def __init__(self, tools: ConversationTools, memory: MemoryService):
        self.tools, self.memory = tools, memory
        builder = StateGraph(State)
        builder.add_node("load_context", self.load_context)
        builder.add_node("resolve_reference", self.resolve_reference)
        builder.add_node("guard_scope", self.guard_scope)
        builder.add_node("intent_router", lambda state: {})
        builder.add_node("read_tools", self.read_tools)
        builder.add_node("clarify", self.clarify)
        builder.add_node("guard_result", self.guard_result)
        builder.set_entry_point("load_context")
        builder.add_edge("load_context", "resolve_reference")
        builder.add_edge("resolve_reference", "guard_scope")
        builder.add_edge("guard_scope", "intent_router")
        builder.add_conditional_edges("intent_router", lambda state: "clarify"
            if state["reason"] else "read_tools", {"clarify": "clarify", "read_tools": "read_tools"})
        builder.add_edge("read_tools", "guard_result")
        builder.add_edge("clarify", "guard_result")
        builder.add_edge("guard_result", END)
        self.graph = builder.compile(checkpointer=None)

    async def __call__(self, execution: TurnExecution) -> ExecutionResult:
        try:
            state = await self.graph.ainvoke({"execution": execution,
                "deadline": time.monotonic() + 240}, config={"recursion_limit": 16,
                "configurable": {"thread_id": execution.turn.conversation_id}})
            return state["output"]
        except ConversationError as exc:
            return ExecutionResult(error_result(exc.code), status="interrupted"
                                   if exc.code == "context_changed" else "failed")

    def load_context(self, state: State) -> dict:
        return {"context": load_context(state["execution"], self.memory)}

    def resolve_reference(self, state: State) -> dict:
        resolved, reason = resolve(state["execution"], state["context"])
        return {"resolved": resolved, "reason": reason}

    async def guard_scope(self, state: State) -> dict:
        self.tools.check_time(state["deadline"])
        await self.tools.preparer.revalidate(state["execution"].selection)
        return {}

    async def read_tools(self, state: State) -> dict:
        resolved = state["resolved"]
        ex, ctx = state["execution"], state["context"]
        if resolved.intent == "source_quote":
            output = await self.tools.source_quote(ex, ctx, resolved, state["deadline"])
        else:
            output = await self.tools.financial(ex, ctx, resolved, state["deadline"])
        return {"output": output}

    def clarify(self, state: State) -> dict:
        reason = state["reason"]
        result = TurnResult(kind="unsupported" if reason == "unsupported_request" else "clarification",
            answer_text="请明确所选企业、财务年度和指标；更换企业或来源请创建新会话。"
                if reason != "preference_confirmation_required" else "请点击保存偏好，明确确认后才会用于后续会话。",
            reason_code=reason)
        return {"output": ExecutionResult(result,
            status="refused" if result.kind == "unsupported" else "completed", resolved=state["resolved"])}

    def guard_result(self, state: State) -> dict:
        output = state["output"]
        self.tools.check_time(state["deadline"])
        ex, ctx = state["execution"], state["context"]
        prior = output.admit

        def admit(conn, turn):
            ex.repository.check_generation_in(conn, ctx.memory_generation)
            if prior:
                prior(conn, turn)

        candidates = extract_user_memory_candidates(ex.turn.user_text, ex.turn.turn_id)
        # Convert only the current persisted user's exact grammar, never a tool/PDF/model output.
        checked = TurnResult.model_validate({**output.result.model_dump(), "memory_candidates": [
            MemoryCandidate.model_validate(c.model_dump()).model_dump() for c in candidates]})
        return {"output": replace(output, result=checked, admit=admit)}
