"""New opt-in routers; root owner registers runtime and gateway mutations."""
import inspect
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute

from app.showcase_research.models import HandoffRequest, IntentRequest, JobRequest, PlanRequest, ResearchError, demo_identity


class ResearchRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def checked(request):
            try:
                response = await original(request)
            except Exception as exc:
                code = getattr(exc, "code", "research_operation_failed")
                status = getattr(exc, "status", 503)
                if isinstance(exc, RequestValidationError):
                    code, status = "invalid_research_request", 422
                response = JSONResponse({"detail": {"code": code, "message": code.replace("_", " ")}}, status)
            response.headers["Cache-Control"] = "no-store"
            return response
        return checked


def create_showcase_research_router(service, *, identity_provider=None):
    router = APIRouter(route_class=ResearchRoute, tags=["showcase-research"])

    async def identity(request):
        if identity_provider:
            result = identity_provider(request)
            result = await result if inspect.isawaitable(result) else result
        elif request.scope.get("findoc_private_identity") is not None:
            result = demo_identity(request, workspace_id=service.conversations.workspace)
        elif service.local_identity is not None:
            result = service.local_identity
        else:
            raise ResearchError("server_runtime_identity_required", 403)
        service.scopes.check_identity(result)
        return result

    @router.post("/research/intent")
    async def intent(payload: IntentRequest, request: Request):
        return await service.intent(payload, await identity(request))

    @router.get("/research/intents/{intent_id}")
    async def read_intent(intent_id: UUID, request: Request):
        return service.read(str(intent_id), "intent", await identity(request))

    @router.post("/research/handoffs")
    async def handoff(payload: HandoffRequest, request: Request):
        return await service.handoff(payload, await identity(request))

    @router.get("/research/operations/{operation_id}")
    async def operation(operation_id: UUID, request: Request):
        return service.operation(str(operation_id), await identity(request))

    @router.get("/research/conversations/{conversation_id}/links")
    async def links(conversation_id: UUID, request: Request):
        return service.links(str(conversation_id), await identity(request))

    @router.post("/synthesis/plans")
    async def plan(payload: PlanRequest, request: Request):
        return await service.plan(payload, await identity(request))

    @router.get("/synthesis/plans/{plan_id}")
    async def read_plan(plan_id: UUID, request: Request):
        return service.read(str(plan_id), "plan", await identity(request))

    @router.post("/synthesis/jobs", status_code=202)
    async def synthesis(payload: JobRequest, request: Request):
        return await service.create_job(payload, await identity(request), "synthesis")

    @router.post("/deep-research/jobs", status_code=202)
    async def deep(payload: JobRequest, request: Request):
        return await service.create_job(payload, await identity(request), "deep")

    @router.get("/synthesis/jobs")
    @router.get("/deep-research/jobs")
    async def history(request: Request, conversation_id: UUID | None = None):
        if set(request.query_params) - {"conversation_id"}:
            raise ResearchError("unknown_query_parameter", 422)
        return service.jobs(await identity(request), conversation_id=str(conversation_id) if conversation_id else None,
                            mode="deep" if request.url.path.startswith("/deep-") else "synthesis")

    @router.get("/synthesis/jobs/{job_id}")
    @router.get("/deep-research/jobs/{job_id}")
    async def job(job_id: UUID, request: Request):
        return service.job(str(job_id), await identity(request))

    @router.get("/deep-research/jobs/{job_id}/events")
    @router.get("/synthesis/jobs/{job_id}/events")
    async def events(job_id: UUID, request: Request, after_seq: int = Query(default=0, ge=0)):
        service.job(str(job_id), await identity(request))
        values = service.store.events(str(job_id), after_seq)
        if "text/event-stream" in request.headers.get("accept", ""):
            data = "".join(f"id: {event['event_seq']}\ndata: {__import__('json').dumps(event, ensure_ascii=False)}\n\n" for event in values)
            return Response(data, media_type="text/event-stream", headers={"Cache-Control": "no-store"})
        return {"schema_version": "execution-events-v1", "job_id": str(job_id), "events": values,
                "next_after_seq": values[-1]["event_seq"] if values else after_seq}

    router.on_shutdown.append(service.close)
    router.showcase_identity_provider = identity
    return router
