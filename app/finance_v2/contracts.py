"""Strict v2 input contracts. Client amounts and client authority are forbidden."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

UUIDText = Annotated[str, Field(pattern=r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")]
Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Id = Annotated[str, Field(min_length=1, max_length=128)]


class Operation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    operation_id: UUIDText


class Collect(Operation):
    company_id: Id
    document_id: Id
    expected_source_revision: Hash


class Select(Operation):
    metric_refs: Annotated[list[UUIDText], Field(min_length=1, max_length=8)]

    @field_validator("metric_refs")
    @classmethod
    def unique(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Duplicate metric refs")
        return value


class Confirm(Operation):
    review_id: UUIDText
    review_sha256: Hash
    confirmed: Literal[True]

    @field_validator("confirmed", mode="before")
    @classmethod
    def explicit_true(cls, value):
        if value is not True:
            raise ValueError("Explicit human confirmation required")
        return value


class Revoke(Operation):
    reason: Annotated[str, Field(min_length=1, max_length=500)]


class FinanceError(Exception):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)
