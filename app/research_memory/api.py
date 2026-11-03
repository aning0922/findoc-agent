from typing import Literal
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.research_memory.service import MemoryError


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Create(Strict):
    operation_id: str
    type: Literal["research_question", "note", "saved_evidence"]
    text: str | None = None
    confirmed: Literal[True]
    company_id: str | None = None
    source_conversation_id: str | None = None
    source_turn_ids: list[str] = Field(default_factory=list, max_length=8)
    document_id: str | None = None
    source_revision: str | None = None
    evidence_id: str | None = None
    artifact_id: str | None = None
    physical_page: int | None = Field(default=None, ge=1)
    source_line_index: int | None = Field(default=None, ge=0)

    @field_validator("confirmed", mode="before")
    @classmethod
    def true_only(cls, value):
        if value is not True:
            raise ValueError("confirmation_required")
        return value


class Patch(Strict):
    operation_id: str
    expected_revision: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=2000)
    confirmed: Literal[True]

    @field_validator("confirmed", mode="before")
    @classmethod
    def true_only(cls, value):
        if value is not True:
            raise ValueError("confirmation_required")
        return value


class Delete(Strict):
    operation_id: str
    expected_revision: int = Field(ge=1)


def create_research_memory_router(service):
    router = APIRouter(prefix="/research-memories", tags=["research-memory"])

    def fail(exc):
        return JSONResponse(
            {
                "detail": {
                    "code": exc.code if isinstance(exc, MemoryError) else "memory_unavailable",
                    "message": "研究记忆暂不可用，请查看操作状态。",
                }
            },
            exc.status if isinstance(exc, MemoryError) else 503,
            headers={"Cache-Control": "no-store"},
        )

    @router.post("")
    async def create(payload: Create):
        try:
            p = payload.model_dump()
            refs = {
                k: p[k]
                for k in (
                    "company_id",
                    "source_conversation_id",
                    "source_turn_ids",
                    "document_id",
                    "source_revision",
                    "evidence_id",
                    "artifact_id",
                    "physical_page",
                    "source_line_index",
                )
            }
            return await service.mutate(
                kind="create",
                operation_id=p["operation_id"],
                memory_type=p["type"],
                text=p["text"],
                refs=refs,
                confirmed=p["confirmed"],
            )
        except Exception as exc:
            return fail(exc)

    @router.get("")
    async def listing(q: str | None = None, company_id: str | None = None):
        try:
            return await service.list(q=q, company_id=company_id)
        except Exception as exc:
            return fail(exc)

    @router.get("/operations/{operation_id}")
    async def operation(operation_id: str):
        try:
            return service.operation(operation_id)
        except Exception as exc:
            return fail(exc)

    @router.patch("/{memory_id}")
    async def patch(memory_id: str, payload: Patch):
        try:
            return await service.mutate(kind="patch", memory_id=memory_id, **payload.model_dump())
        except Exception as exc:
            return fail(exc)

    @router.delete("/{memory_id}")
    async def delete(memory_id: str, payload: Delete):
        try:
            return await service.mutate(kind="delete", memory_id=memory_id, **payload.model_dump())
        except Exception as exc:
            return fail(exc)

    return router
