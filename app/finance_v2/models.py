"""Frozen first-slice extended-metric-v2 output: consolidated instant balances only."""
from datetime import date
from typing import Annotated, Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.finance_v2.contracts import Hash, Id, UUIDText

DecimalText = Annotated[str, Field(pattern=r"^-?\d+(?:\.\d+)?$")]


class ExtendedMetricV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    schema_version: Literal["extended-metric-v2"]
    metric_id: UUIDText
    company_id: Id
    document_id: Id
    source_revision: Hash
    content_sha256: Hash
    report_year: Annotated[int, Field(ge=1, le=9999)]
    period: Annotated[int, Field(ge=1, le=9999)] | None
    period_kind: Literal["instant"]
    as_of_date: str | None
    period_start: None = None
    period_end: None = None
    metric_definition_version: Literal["consolidated-balance-sheet-instant-v1"]
    metric_key: Literal["total_assets", "total_liabilities", "debt_asset_ratio"]
    value_decimal: DecimalText | None
    unit: Literal["CNY_YUAN", "PERCENT"]
    scope: Literal["consolidated"]
    basis: str | None
    status: Literal["candidate", "confirmed", "unsupported"]
    evidence_refs: list[dict[str, Any]]
    basis_refs: list[dict[str, Any]]
    unsupported_reasons: list[str]
    confirmation_ref: dict[str, Any] | None = None
    formula: str | None = None
    input_refs: list[UUIDText] = Field(default_factory=list)
    confirmation_refs: list[dict[str, Any]] = Field(default_factory=list)
    calculation_version: str | None = None
    source_status: Literal["current_valid", "unavailable"] | None = None
    historical_value_decimal: DecimalText | None = None

    @model_validator(mode="after")
    def temporal_and_authority_axes(self):
        if self.as_of_date is not None:
            instant = date.fromisoformat(self.as_of_date)
            if instant.isoformat() != self.as_of_date or self.period != instant.year:
                raise ValueError("Period must match the explicit as_of_date, not report_year")
        elif self.period is not None or self.status != "unsupported":
            raise ValueError("Unknown instant cannot produce a usable balance")
        if self.status == "unsupported":
            if self.value_decimal is not None or not self.unsupported_reasons:
                raise ValueError("Unsupported balances have no usable value and need a reason")
        elif self.value_decimal is None or not self.evidence_refs or self.unsupported_reasons:
            raise ValueError("Usable balances need evidence and a Decimal string")
        if self.metric_key == "debt_asset_ratio":
            if self.unit != "PERCENT" or len(self.input_refs) != 2 or not self.formula:
                raise ValueError("Derived ratio requires two explicit inputs and formula")
        elif self.unit != "CNY_YUAN" or self.formula or self.input_refs:
            raise ValueError("Raw balances are CNY amounts, not client formulas")
        if self.status == "confirmed":
            receipts = self.confirmation_refs if self.metric_key == "debt_asset_ratio" else [self.confirmation_ref]
            if not receipts or any(not r or r.get("confirmation_kind") != "local_operator" for r in receipts):
                raise ValueError("Confirmed output requires local_operator receipts")
        return self
