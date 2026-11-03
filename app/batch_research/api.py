from typing import Literal
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import Field
from app.retrieval_v2.models import Strict, SourceRef, RetrievalError
from app.retrieval_v2.service import resolve


class Cell(Strict):
    cell_key: str
    company_id: str
    template: Literal["risk_excerpt", "annual_changes"]
    sources: list[SourceRef] = Field(min_length=1, max_length=2)


class Plan(Strict):
    operation_id: str
    cells: list[Cell] = Field(min_length=1, max_length=12)
    preparation_confirmed: bool


class Start(Strict):
    operation_id: str
    batch_plan_id: str
    batch_plan_revision: int = Field(ge=1)
    batch_plan_sha256: str
    confirmed: bool


class Cancel(Strict):
    operation_id: str
    expected_revision: int = Field(ge=1)


def create_batch_router(service, identity_provider):
    router = APIRouter(prefix="/cplus")

    async def invoke(action, p, request, batch=None):
        try:
            i = await resolve(identity_provider(request))
            if action == "cancel":
                return await service.cancel(batch, p.model_dump(), i)
            return await getattr(service, action)(p.model_dump(), i)
        except Exception as e:
            return JSONResponse(
                {
                    "detail": {
                        "code": e.code if isinstance(e, RetrievalError) else "batch_unavailable"
                    }
                },
                status_code=e.status if isinstance(e, RetrievalError) else 503,
            )

    @router.post("/batch-plans")
    async def plan(p: Plan, request: Request):
        return await invoke("plan", p, request)

    @router.post("/batches")
    async def start(p: Start, request: Request):
        return await invoke("start", p, request)

    @router.post("/batches/{batch}/cancel")
    async def cancel(batch: str, p: Cancel, request: Request):
        return await invoke("cancel", p, request, batch)

    @router.get("/batch-plans/{plan_id}")
    async def read_plan(plan_id: str, request: Request):
        identity = await resolve(identity_provider(request))
        return service.store.read(plan_id, await service.owner(identity))

    @router.get("/batches/{batch}")
    async def read(batch: str, request: Request):
        return await service.read(batch, await resolve(identity_provider(request)))

    @router.get("/batch-operations/{op}")
    async def operation(op: str, request: Request):
        return service.store.operation(
            op, await service.owner(await resolve(identity_provider(request)))
        )

    return router
