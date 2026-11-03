"""New opt-in routers; root owner registers runtime and gateway mutations."""
import inspect
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.showcase_research.models import HandoffRequest, IntentRequest, ResearchError, demo_identity


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

    router.showcase_identity_provider = identity
    return router
