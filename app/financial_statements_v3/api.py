import inspect
from typing import Literal
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.finance_v2.api import FinanceRoute
from app.finance_v2.contracts import FinanceError, UUIDText, Hash


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Operation(Strict):
    operation_id: UUIDText


class Collect(Operation):
    document_id: str
    expected_source_revision: Hash


class CellRef(Strict):
    cell_id: UUIDText
    cell_revision: int = Field(ge=1)
    payload_sha256: Hash


class Review(Operation):
    cell_refs: list[CellRef] = Field(min_length=1, max_length=64)


class Confirm(Operation):
    review_id: UUIDText
    review_sha256: Hash
    confirmed: Literal[True]

    @field_validator("confirmed", mode="before")
    @classmethod
    def explicit(cls, value):
        if value is not True:
            raise ValueError("explicit boolean required")
        return value


class Revoke(Operation):
    reason: str = Field(min_length=1, max_length=500)


class CollectionSelection(Strict):
    collection_id: UUIDText
    cell_ids: list[UUIDText] = Field(min_length=1, max_length=128)


class Trend(Operation):
    collection_refs: list[UUIDText | CollectionSelection] = Field(min_length=1, max_length=5)
    metric_keys: list[str] = Field(min_length=1, max_length=30)
    candidate_view: bool = False


def create_statement_router(service, *, owner_authorizer=None):
    router = APIRouter(prefix="/cplus", route_class=FinanceRoute)

    async def owner(request):
        if owner_authorizer is None:
            raise FinanceError("owner_authorization_required", 403)
        value = owner_authorizer(request)
        return await value if inspect.isawaitable(value) else value

    @router.post("/financial/collections")
    async def collect(p: Collect):
        return await service.collect(**p.model_dump())

    @router.get("/financial/collections/{collection_id}")
    async def collection(collection_id: str):
        return await service.collection(collection_id)

    @router.get("/companies/{company_id}/statements")
    async def statements(company_id: str):
        return await service.list_collections(company_id)

    @router.post("/financial/reviews")
    async def review(p: Review):
        return await service.review(**p.model_dump())

    @router.post("/financial/confirmations")
    async def confirm(p: Confirm, request: Request):
        return await service.confirm(**p.model_dump(), authorization=await owner(request))

    @router.post("/financial/confirmations/{receipt_id}/revoke")
    async def revoke(receipt_id: str, p: Revoke, request: Request):
        return await service.revoke(
            receipt_id, **p.model_dump(), authorization=await owner(request)
        )

    @router.get("/financial/operations/{operation_id}")
    async def operation(operation_id: str):
        return service.operation(operation_id)

    @router.post("/financial/trend-projections")
    async def trends(p: Trend):
        return await service.trends(**p.model_dump())

    return router
