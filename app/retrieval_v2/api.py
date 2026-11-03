from typing import Literal
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import Field, field_validator
from .models import Strict, SourceRef, RetrievalError, FinancialFocus
from .service import resolve


class Operation(Strict):
    operation_id: str


class Build(Operation):
    sources: list[SourceRef] = Field(min_length=1, max_length=4)


class Search(Build):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=5)


class Enrollment(Operation):
    document_id: str
    artifact_id: str
    expected_source_revision: str
    expected_artifact_sha256: str
    selected_pages: list[int] = Field(min_length=1, max_length=50)
    confirmed: Literal[True]

    @field_validator("confirmed", mode="before")
    @classmethod
    def explicit(cls, value):
        if value is not True:
            raise ValueError("explicit_confirmation_required")
        return value


class Context(Operation):
    title: str = Field(min_length=1, max_length=200)
    selected_sources: list[SourceRef] = Field(min_length=1, max_length=4)
    parent_conversation_id: str | None = None
    financial_focus: FinancialFocus | None = None


class Answer(Operation):
    context_id: str
    context_revision: int = Field(ge=1)
    context_sha256: str
    question: str = Field(min_length=1, max_length=2000)


def create_retrieval_router(service, identity_provider):
    router = APIRouter(prefix="/cplus")

    def error(exc):
        return JSONResponse(
            {
                "detail": {
                    "code": exc.code if isinstance(exc, RetrievalError) else "retrieval_unavailable"
                }
            },
            status_code=exc.status if isinstance(exc, RetrievalError) else 503,
            headers={"Cache-Control": "no-store"},
        )

    async def write(kind, payload, request):
        try:
            return await service.mutate(
                kind, payload.model_dump(), await resolve(identity_provider(request))
            )
        except Exception as exc:
            return error(exc)

    @router.post("/retrieval/builds")
    async def build(payload: Build, request: Request):
        return await write("build", payload, request)

    @router.post("/retrieval/searches")
    async def search(payload: Search, request: Request):
        return await write("search", payload, request)

    @router.post("/research/enrollments")
    async def enroll(payload: Enrollment, request: Request):
        return await write("enrollment", payload, request)

    @router.post("/research/contexts")
    async def context(payload: Context, request: Request):
        return await write("context", payload, request)

    @router.post("/research/answers")
    async def answer(payload: Answer, request: Request):
        return await write("answer", payload, request)

    async def read(kind, identifier, request):
        try:
            identity = await resolve(identity_provider(request))
            owner = await service.authorize(identity)
            if kind == 'operation':
                return service.operation(identifier,owner)
            value=service.read(kind,identifier,owner)
            context=value if kind=='context' else service.read('context',value['context_id'],owner)
            try:
                await service.validate_context(context,owner)
                with service.guard(identity,context):
                    pass
                status='current'
            except Exception:
                status='stale_or_unavailable'
            return {**value,'current_source_status':status,'historical_snapshot':True}
        except Exception as exc:
            return error(exc)

    @router.get("/research/contexts/{identifier}")
    async def read_context(identifier: str, request: Request):
        return await read("context", identifier, request)

    @router.get("/research/answers/{identifier}")
    async def read_answer(identifier: str, request: Request):
        return await read("answer", identifier, request)

    @router.get("/research/operations/{identifier}")
    async def read_operation(identifier: str, request: Request):
        return await read("operation", identifier, request)

    return router
