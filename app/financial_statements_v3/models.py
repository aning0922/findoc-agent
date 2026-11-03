from datetime import date
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Instant(Strict):
    kind: Literal["instant"]
    as_of_date: str

    @model_validator(mode="after")
    def valid(self):
        if date.fromisoformat(self.as_of_date).isoformat() != self.as_of_date:
            raise ValueError("noncanonical date")
        return self


class Duration(Strict):
    kind: Literal["duration"]
    period_start: str
    period_end: str
    period_type: Literal["annual", "quarter", "ytd", "other"]

    @model_validator(mode="after")
    def valid(self):
        start, end = date.fromisoformat(self.period_start), date.fromisoformat(self.period_end)
        if (
            start > end
            or start.isoformat() != self.period_start
            or end.isoformat() != self.period_end
        ):
            raise ValueError("invalid period")
        return self


Time = Annotated[Instant | Duration, Field(discriminator="kind")]
time_adapter = TypeAdapter(Time)
