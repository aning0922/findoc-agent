"""Strict memory-v1 transport and storage projection."""
from datetime import datetime
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from app.research.models import Strict, operation

MemoryKey = Literal["analysis_focus", "display_unit", "research_habit"]
VALUES = {
    "analysis_focus": frozenset({"cash_flow", "revenue", "profitability", "balanced"}),
    "display_unit": frozenset({"CNY_YUAN", "CNY_TEN_THOUSAND", "CNY_HUNDRED_MILLION"}),
    "research_habit": frozenset({"evidence_first", "compare_periods_first"}),
}


def allowed_value(key: str, value: str) -> str:
    if value not in VALUES[key]:
        raise ValueError("invalid_memory_value")
    return value


def instant(value: str) -> str:
    if datetime.fromisoformat(value).tzinfo is None:
        raise ValueError("timezone_required")
    return value


class Confirmed(Strict):
    confirmed: Literal[True]

    @field_validator("confirmed", mode="before")
    @classmethod
    def explicit_true(cls, value: object) -> object:
        if value is not True:
            raise ValueError("confirmation_required")
        return value


class CreateMemoryRequest(Confirmed):
    operation_id: str
    type: Literal["research_preference"]
    key: MemoryKey
    value: str = Field(min_length=1, max_length=200)
    source_turn_id: str | None = None

    _op = field_validator("operation_id")(operation)

    @field_validator("source_turn_id")
    @classmethod
    def source_id(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("source_turn_id_must_be_omitted_or_uuid")
        return operation(value)

    @model_validator(mode="after")
    def value_for_key(self) -> Self:
        allowed_value(self.key, self.value)
        return self


class PatchMemoryRequest(Confirmed):
    operation_id: str
    expected_revision: int = Field(ge=1)
    value: str = Field(min_length=1, max_length=200)

    _op = field_validator("operation_id")(operation)


class DeleteMemoryRequest(Strict):
    operation_id: str
    expected_revision: int = Field(ge=1)

    _op = field_validator("operation_id")(operation)


class MemoryItem(Strict):
    schema_version: Literal["memory-item-v1"] = "memory-item-v1"
    memory_id: str
    type: Literal["research_preference"]
    key: MemoryKey
    value: str = Field(min_length=1, max_length=200)
    source_turn_id: str | None
    revision: int = Field(ge=1)
    confirmed_at: str
    created_at: str
    updated_at: str

    _id = field_validator("memory_id")(operation)
    @field_validator("source_turn_id")
    @classmethod
    def nullable_source_id(cls, value: str | None) -> str | None:
        return operation(value) if value is not None else None

    _time = field_validator("confirmed_at", "created_at", "updated_at")(instant)

    @model_validator(mode="after")
    def value_for_key(self) -> Self:
        allowed_value(self.key, self.value)
        return self


class MemoryList(Strict):
    schema_version: Literal["memory-list-v1"] = "memory-list-v1"
    items: list[MemoryItem] = Field(max_length=10)
    generation: int = Field(ge=0)


class MemoryOperation(Strict):
    schema_version: Literal["memory-operation-v1"] = "memory-operation-v1"
    operation_id: str
    memory_id: str
    kind: Literal["create_memory", "update_memory", "delete_memory"]
    status: Literal["completed"] = "completed"
    revision: int = Field(ge=1)
    resource_deleted: bool
    created_at: str

    _ids = field_validator("operation_id", "memory_id")(operation)
    _time = field_validator("created_at")(instant)


class MemoryCandidate(Strict):
    type: Literal["research_preference"] = "research_preference"
    key: MemoryKey
    value: str
    source_turn_id: str
    confirmation_required: Literal[True] = True

    _source = field_validator("source_turn_id")(operation)

    @model_validator(mode="after")
    def value_for_key(self) -> Self:
        allowed_value(self.key, self.value)
        return self


class MemoryError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)
