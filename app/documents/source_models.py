"""Strict report-upload/correction inputs and public source errors."""

from typing import Annotated
from urllib.parse import urlsplit

from pydantic import Field, field_validator

from app.companies.models import ReportMetadataInput, StrictInput


class ReportUploadInput(ReportMetadataInput):
    source_url: Annotated[str, Field(max_length=2000)] | None = None

    @field_validator("source_url")
    @classmethod
    def public_url(cls, value: str | None) -> str | None:
        if value is not None:
            parts = urlsplit(value)
            if parts.scheme not in ("https", "http") or not parts.hostname or parts.username:
                raise ValueError("use a public HTTP(S) source URL without credentials")
        return value


class BindingCorrectionInput(StrictInput):
    expected_attempt: Annotated[int, Field(ge=1)]
    metadata: ReportMetadataInput
    reason: Annotated[str, Field(min_length=1, max_length=1000)]


class ReindexInput(StrictInput):
    expected_attempt: Annotated[int, Field(ge=1)]


class SourceError(Exception):
    def __init__(self, code: str, status: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
