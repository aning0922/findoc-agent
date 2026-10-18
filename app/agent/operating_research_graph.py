"""D19 persistent extension of the same read-only LangGraph service scheduling.

The graph has no confirmation capability or model loop. D18 ToolSpec registry,
D11/D13 analysis and D16 selected evidence remain the only execution paths.
"""

from typing import Any, TypedDict
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command

from app.agent.execution_budget import ExecutionBudget
from app.documents.source_repository import SQLiteSourceRepository
from app.research.task_checkpointer import TaskCheckpointer
from app.research.task_contracts import StartTask, StartTaskV2, ResumeTask
from app.research.task_repository import TaskRepository
from app.research.template_contracts import TemplateRequest
from app.research.templates import TemplateService, TemplateSession, TemplateError, QUERIES
from app.research.repository import HistoryError


class OperatingState(TypedDict, total=False):
    task_id: str
    status: str
    resume: dict[str, Any]


class PersistentTemplateService:
    def __init__(self, templates: TemplateService, repository: TaskRepository):
        if templates.workspace_id != repository.workspace:
            raise ValueError("workspace_mismatch")
        self.templates, self.repository = templates, repository

    async def start(self, request: StartTask | StartTaskV2) -> dict[str, Any]:
        record, claim = self.repository.start(request)
        if claim is None:
            return record
        return await self.dispatch(record, claim, request.operation_id, None)

    async def resume(self, task_id: str, request: ResumeTask) -> dict[str, Any]:
        record, claim = self.repository.resume(task_id, request)
        if claim is None:
            return record
        return await self.dispatch(record, claim, request.operation_id, request)

    async def dispatch(
        self, record: dict[str, Any], claim: str, op: str, resume: ResumeTask | None
    ) -> dict[str, Any]:
        repo, task_id = self.repository, record["task_id"]
        budget = ExecutionBudget.restore(
            record["budget"], checkpoint=lambda value: repo.reserve(task_id, claim, value)
        )
        saver = TaskCheckpointer(repo, task_id, claim)
        session: TemplateSession | None = None

        def save() -> None:
            assert session is not None
            budget.checkpoint()
            repo.save_session(task_id, claim, session.payload(), budget.durable())

        async def prepare(state: OperatingState) -> dict[str, Any]:
            nonlocal session
            session = await self.templates.prepare(
                TemplateRequest.model_validate(record["input"]), budget=budget
            )
            session.task_id = task_id
            save()
            return {"status": session.state}

        def wait(state: OperatingState) -> dict[str, Any]:
            # On resume this node replays only interrupt(), never source/tool/model work.
            approved = interrupt(
                {"reason": "existing_d9_d10_confirmation_required", "task_id": task_id}
            )
            return {"resume": approved}

        async def readmit(state: OperatingState) -> dict[str, Any]:
            nonlocal session
            current = repo.get(task_id)
            request = TemplateRequest.model_validate(current["active_input"])
            session = TemplateSession(self.templates, request, budget=budget)
            session.state = "collecting_evidence"
            budget.phase = "resume:" + str(current["revision"])
            try:
                selected = ResumeTask.model_validate(state["resume"])
                if resume is None or selected != resume:
                    raise TemplateError("resume_authorization_invalid")
                raw = request.model_dump(mode="json")
                for item in selected.facts:
                    choice = next(
                        c for c in raw[item.side]["choices"] if c["metric_key"] == item.metric_key
                    )
                    if choice["fact_id"] is not None and (
                        choice["fact_id"],
                        choice["fact_set_id"],
                    ) != (item.fact_id, item.fact_set_id):
                        raise TemplateError("fact_replacement_forbidden")
                    choice.update(fact_id=item.fact_id, fact_set_id=item.fact_set_id)
                session.request = TemplateRequest.model_validate(raw)
                # Reserve source preparation before IO; six slot reads use the same tools/ledger.
                budget.consume("steps")
                budget.operation("read_approved_sources", "{}")
                session.selection = await self.templates.preparer.prepare_many(
                    document_ids=tuple(r.document_id for r in request.reports),
                    query=QUERIES[request.direction],
                )
                budget.check()
                session.validate_input_sources()
                previous_documents = current["snapshot"]["documents"]
                from dataclasses import asdict

                if [asdict(d) for d in session.selection.documents] != previous_documents:
                    raise TemplateError("source_changed")
                for side in ("first", "second"):
                    for choice in getattr(session.request, side).choices:
                        fact = await session.invoke(
                            "read_current_financial_fact", side=side, metric_key=choice.metric_key
                        )
                        if fact["readiness"] != "ready":
                            raise TemplateError("confirmation_required")
                        session.fact_states.append(fact)
                session.move("ready_for_analysis")
                await session.require_ready()
                for name in list(session.step_states)[:4]:
                    session.step_states[name] = "done"
            except Exception as exc:
                if isinstance(exc, HistoryError):
                    raise
                session.stop(exc)
            session.task_id = task_id
            save()
            return {"status": session.state}

        async def execute(state: OperatingState) -> dict[str, Any]:
            assert session is not None
            await session.execute_readonly()
            session.task_id = task_id
            save()
            return {"status": session.state}

        def admission(conn: Any, value: dict[str, Any]) -> None:
            snap = value["snapshot"]
            if snap is None or value["status"] in ("failed", "refused"):
                return
            SQLiteSourceRepository(repo.registry).verify_selection_in(
                conn, tuple(snap["documents"])
            )
            if value["status"] in ("collecting_explanation", "completed"):
                ids = tuple(sorted({f["receipt_id"] for f in snap["facts"]}))
                self.templates.facts.recheck_persisted_analysis_in(
                    conn,
                    workspace_id=repo.workspace,
                    receipt_ids=ids,
                    confirmation_kind="simulated_test"
                    if self.templates.simulated
                    else "local_operator",
                )

        graph = StateGraph(OperatingState)
        graph.add_node("prepare", prepare)
        graph.add_node("human_wait", wait)
        graph.add_node("readmit", readmit)
        graph.add_node("execute_readonly", execute)
        graph.add_edge(START, "prepare")
        graph.add_conditional_edges(
            "prepare",
            lambda s: (
                "human_wait"
                if s["status"] == "awaiting_human_confirmation"
                else "execute_readonly"
                if s["status"] == "ready_for_analysis"
                else END
            ),
        )
        graph.add_edge("human_wait", "readmit")
        graph.add_conditional_edges(
            "readmit", lambda s: "execute_readonly" if s["status"] == "ready_for_analysis" else END
        )
        graph.add_edge("execute_readonly", END)
        compiled = graph.compile(checkpointer=saver, name="persistent_operating_research")
        config: RunnableConfig = {"configurable": {"thread_id": task_id}}
        try:
            if resume is not None:
                snapshot = await compiled.aget_state(config)
                if snapshot.next != ("human_wait",) or not any(
                    t.interrupts for t in snapshot.tasks
                ):
                    raise HistoryError("waiting_checkpoint_invalid")
            result = await compiled.ainvoke(
                Command(resume=resume.model_dump(mode="json")) if resume else {"task_id": task_id},
                config=config,
                durability="sync",
            )
            waiting = bool(result.get("__interrupt__"))
            if budget.version == "template-budget-v2":
                try:
                    budget.check()
                except Exception as exc:
                    assert session is not None
                    # An overdue synchronous result cannot become completed at release.
                    session.state = "collecting_explanation" if session.state == "completed" else session.state
                    session.stop(exc)
                    waiting = False
                    save()
                budget.checkpoint()
            return repo.release(task_id, claim, op, waiting=waiting, admission=admission)
        except Exception:
            # Durable claim remains unknown. GET/replay only reads it; startup marks interrupted.
            raise HistoryError("task_save_or_execution_unknown") from None
