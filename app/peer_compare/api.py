from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import Field
from app.retrieval_v2.models import Strict, RetrievalError
from app.retrieval_v2.service import resolve


class Selection(Strict):
    collection_id: str
    cell_ids: list[str] = Field(min_length=1, max_length=128)


class Compare(Strict):
    operation_id: str
    company_ids: list[str] = Field(min_length=2, max_length=3)
    collection_refs: list[Selection] = Field(min_length=2, max_length=6)
    candidate_view: bool = False


def create_peer_comparison_router(service, identity_provider):
    router = APIRouter(prefix="/cplus/peer-comparisons")

    def fail(e):
        from app.cplus.diagnostics import safe_failure
        safe_failure('peer',e)
        return JSONResponse(
            {"detail": {"code": e.code if isinstance(e, RetrievalError) else "peer_unavailable"}},
            status_code=e.status if isinstance(e, RetrievalError) else 503,
        )

    @router.post("")
    async def compare(p: Compare, request: Request):
        try:
            return await service.compare(p.model_dump(), await resolve(identity_provider(request)))
        except Exception as e:
            return fail(e)

    @router.get("/operations/{op}")
    async def operation(op: str, request: Request):
        try:
            owner = await service.owner(await resolve(identity_provider(request)))
            return service.store.operation(op, owner)
        except Exception as e:
            return fail(e)

    @router.get("/{key}")
    async def read(key: str, request: Request):
        try:
            return await service.read(key, await resolve(identity_provider(request)))
        except Exception as e:
            return fail(e)

    return router
