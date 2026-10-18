"""Strict inputs shared by the HTTP and application service boundaries."""

from datetime import date, datetime
from typing import Annotated, Literal
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Name = Annotated[str, Field(min_length=1, max_length=200)]
Identity = Annotated[str, Field(min_length=1, max_length=32)]
ReportType = Literal["annual", "semiannual", "quarterly"]
Basis = Literal["PRC_GAAP", "IFRS", "US_GAAP", "unknown"]


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    @field_validator("*", mode="before")
    @classmethod
    def clean_text(cls, value: object) -> object:
        if isinstance(value, str):
            if any(ord(c) < 32 or ord(c) == 127 for c in value):
                raise ValueError("control characters are not allowed")
            return value.strip()
        return value


class CompanyIdentityInput(StrictInput):
    @field_validator("security_code", "exchange", check_fields=False)
    @classmethod
    def normalize_identity(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("security identity cannot be null")
        value = value.upper()
        if re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,31}", value) is None:
            raise ValueError("invalid security identity")
        return value


class CompanyCreate(CompanyIdentityInput):
    name: Name
    security_code: Identity
    exchange: Identity
    country: Annotated[str, Field(pattern=r"^[A-Z]{2}$")] = "CN"


class CompanyPatch(CompanyIdentityInput):
    name: Name | None = None
    security_code: Identity | None = None
    exchange: Identity | None = None
    country: Annotated[str, Field(pattern=r"^[A-Z]{2}$")] | None = None

    @model_validator(mode="after")
    def require_changes(self) -> "CompanyPatch":
        if not self.model_fields_set or any(
            getattr(self, field) is None for field in self.model_fields_set
        ):
            raise ValueError("provide at least one non-null change")
        return self


class Company(BaseModel):
    model_config = ConfigDict(frozen=True)
    company_id: str
    workspace_id: str
    name: str
    security_code: str
    exchange: str
    country: str
    created_at: datetime
    updated_at: datetime


class ReportMetadataInput(StrictInput):
    company_id: Annotated[str, Field(min_length=1, max_length=100)]
    report_year: Annotated[int, Field(ge=1, le=9999)]
    report_type: ReportType
    basis: Basis
    period_start: date
    period_end: date

    @field_validator("period_start", "period_end", mode="before")
    @classmethod
    def iso_date(cls, value: object) -> object:
        # JSON has no date primitive; accept only canonical ISO calendar dates.
        if isinstance(value, str):
            parsed = date.fromisoformat(value)
            if parsed.isoformat() != value:
                raise ValueError("use YYYY-MM-DD")
            return parsed
        return value

    @model_validator(mode="after")
    def validate_period(self) -> "ReportMetadataInput":
        start, end = self.period_start, self.period_end
        if start.year != self.report_year or end.year != self.report_year or start > end:
            raise ValueError("period must belong to report_year")
        if self.report_type == "annual" and (start.month, start.day, end.month, end.day) != (
            1,
            1,
            12,
            31,
        ):
            raise ValueError("annual period must cover the full calendar year")
        if self.report_type == "semiannual" and (start.month, start.day, end.month, end.day) != (
            1,
            1,
            6,
            30,
        ):
            raise ValueError("semiannual period must cover January through June")
        if self.report_type == "quarterly" and (start.month, start.day, end.month, end.day) not in (
            (1, 1, 3, 31),
            (4, 1, 6, 30),
            (7, 1, 9, 30),
            (10, 1, 12, 31),
        ):
            raise ValueError("quarterly period must cover one calendar quarter")
        return self


class ReportMetadata(ReportMetadataInput):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=False)
    workspace_id: str
    document_id: str
    status: Literal["pending_verification"]
    created_at: datetime


class RegistryNotFoundError(Exception):
    """Unknown and inaccessible identities have the same public error."""


class RegistryConflictError(Exception):
    """Security identity or existing immutable report binding conflicts."""
