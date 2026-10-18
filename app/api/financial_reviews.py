"""D9 adapters over the existing confirmation service; clients cannot supply money."""

from collections.abc import Callable, Coroutine
from datetime import date
import sqlite3
import logging
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.agent.metric_extraction import METRICS
from app.agent.revenue_confirmation import (
    ConfirmationKind,
    RevenueConfirmationError,
    RevenueConfirmationService,
)
from app.companies.models import RegistryNotFoundError
from app.documents.models import DocumentNotFoundError
from app.documents.preparation import DocumentReader
from app.documents.source_models import SourceError

Id = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=100, pattern=r"^[^\s\x00-\x1f\x7f]+$"),
]
Hash = Annotated[str, StringConstraints(strict=True, pattern=r"^[a-f0-9]{64}$")]
Snapshot = Annotated[
    str, StringConstraints(strict=True, pattern=r"^financial-review-v1:[a-f0-9]{64}$")
]
Year = Annotated[int, Field(strict=True, ge=1, le=9999)]


class FinancialSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    review_schema: Literal["financial-review-v1"]
    company_id: Id
    document_id: Id
    source_revision: Hash
    metric_keys: Annotated[list[Id], Field(min_length=1, max_length=20)]
    periods: Annotated[list[Year], Field(min_length=1, max_length=100)]

    @model_validator(mode="after")
    def unique_selection(self) -> "FinancialSelection":
        if len(set(self.metric_keys)) != len(self.metric_keys) or any(
            k not in METRICS for k in self.metric_keys
        ):
            raise ValueError("invalid metric selection")
        if len(set(self.periods)) != len(self.periods):
            raise ValueError("duplicate periods")
        return self


class FinancialAcceptRequest(FinancialSelection):
    snapshot_id: Snapshot
    accepted: bool
    request_id: Id


class FinancialPersistRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    receipt_id: Id


class FinancialRevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    reason: Annotated[str, StringConstraints(min_length=1, max_length=500)]


class FinancialRoute(APIRoute):
    failure_message = "本次审阅或接受未取得有效凭证，请核对状态后继续。"
    failure_code = "financial_review_failed"
    failure_payload: dict[str, str] = {}

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                response = await original(request)
                response.headers["Cache-Control"] = "no-store"
                return response
            except Exception as exc:
                status, code = 500, self.failure_code
                if isinstance(exc, RequestValidationError):
                    status, code = 422, "invalid_financial_request"
                elif isinstance(exc, SourceError):
                    status, code = exc.status, exc.code
                elif isinstance(exc, (DocumentNotFoundError, RegistryNotFoundError)):
                    status, code = 404, "resource_not_found"
                elif isinstance(exc, RevenueConfirmationError):
                    code = exc.code
                    status = (
                        503
                        if code == "financial_service_unavailable"
                        else 422
                        if code == "invalid_financial_selection"
                        else 404
                        if code in ("acceptance_not_found", "facts_not_found")
                        else 500
                        if code == "confirmation_integrity_error"
                        else 409
                    )
                elif isinstance(exc, sqlite3.Error):
                    code = "financial_storage_error"
                if status >= 500:
                    logging.getLogger(__name__).exception(
                        "Financial persistence/read failed: %s", code
                    )
                return JSONResponse(
                    status_code=status,
                    headers={"Cache-Control": "no-store"},
                    content={
                        **self.failure_payload,
                        "detail": {
                            "code": code,
                            "message": self.failure_message,
                        }
                    },
                )

        return handle


def create_financial_review_router(
    *,
    service: RevenueConfirmationService | None,
    documents: DocumentReader,
    workspace_id: str | None,
    confirmation_kind: ConfirmationKind = "local_operator",
) -> APIRouter:
    router = APIRouter(
        prefix="/financial-facts", tags=["financial-review"], route_class=FinancialRoute
    )

    async def enabled(document_id: str) -> RevenueConfirmationService:
        if service is None:
            raise RevenueConfirmationError("financial_service_unavailable")
        document = await documents.get_document(document_id)
        if document.workspace_id != workspace_id:
            raise DocumentNotFoundError(document_id)
        return service

    @router.post("/reviews")
    async def preview(payload: FinancialSelection) -> object:
        active = await enabled(payload.document_id)
        review = await active.preview_financial(**payload.model_dump(exclude={"review_schema"}))
        return dict(
            **review.to_payload(),
            snapshot_id=review.snapshot_id,
            review_status="ready_for_acceptance" if review.acceptable else "blocked",
            facts_status="unconfirmed",
        )

    @router.post("/confirmations")
    async def accept(payload: FinancialAcceptRequest) -> object:
        active = await enabled(payload.document_id)
        args = payload.model_dump(exclude={"review_schema", "snapshot_id"})
        receipt = await active.confirm_financial(
            **args, reviewed_snapshot_id=payload.snapshot_id, confirmation_kind=confirmation_kind
        )
        return receipt.to_payload()

    @router.get("/confirmations/{request_id}")
    async def recover(
        request_id: Id,
        document_id: Id,
        company_id: Id,
        source_revision: Hash,
        snapshot_id: Snapshot,
        metric_keys: Annotated[list[str], Query(min_length=1, max_length=20)],
        periods: Annotated[list[int], Query(min_length=1, max_length=100)],
        review_schema: Literal["financial-review-v1"],
    ) -> object:
        # Query ints are decoded by HTTP; the same DTO applies all remaining selection checks.
        try:
            selection = FinancialSelection(
                review_schema=review_schema,
                document_id=document_id,
                company_id=company_id,
                source_revision=source_revision,
                metric_keys=metric_keys,
                periods=periods,
            )
        except ValueError as exc:
            raise RevenueConfirmationError("invalid_financial_selection") from exc
        active = await enabled(document_id)
        receipt = await active.recover_financial(
            **selection.model_dump(exclude={"review_schema"}),
            reviewed_snapshot_id=snapshot_id,
            request_id=request_id,
            confirmation_kind=confirmation_kind,
        )
        return receipt.to_payload()

    @router.get("/acceptances")
    async def discover_acceptances(
        document_id: Id, company_id: Id, source_revision: Hash,
        metric_keys: Annotated[list[str], Query(min_length=1, max_length=20)],
        periods: Annotated[list[int], Query(min_length=1, max_length=100)],
        review_schema: Literal["financial-review-v1"],
    ) -> object:
        try:
            selection = FinancialSelection(
                review_schema=review_schema, document_id=document_id, company_id=company_id,
                source_revision=source_revision, metric_keys=metric_keys, periods=periods,
            )
        except ValueError as exc:
            raise RevenueConfirmationError("invalid_financial_selection") from exc
        active = await enabled(document_id)
        return await active.discover_financial_acceptances(
            workspace_id=workspace_id,
            confirmation_kind=confirmation_kind,
            **selection.model_dump(exclude={"review_schema"}),
        )

    @router.get("/acceptances/{receipt_id}")
    async def read_acceptance(receipt_id: Id) -> object:
        if service is None or workspace_id is None:
            raise RevenueConfirmationError("financial_service_unavailable")
        receipt = await service.read_financial_acceptance(
            workspace_id=workspace_id,
            receipt_id=receipt_id,
            confirmation_kind=confirmation_kind,
        )
        return receipt.to_payload()

    @router.post("/acceptances/{receipt_id}/revoke")
    async def revoke(receipt_id: Id, payload: FinancialRevokeRequest) -> object:
        if service is None or workspace_id is None:
            raise RevenueConfirmationError("financial_service_unavailable")
        return await service.revoke_financial_acceptance(workspace_id=workspace_id,
            receipt_id=receipt_id,confirmation_kind=confirmation_kind,reason=payload.reason)

    @router.post("/persisted")
    async def persist(payload: FinancialPersistRequest) -> object:
        if service is None or workspace_id is None:
            raise RevenueConfirmationError("financial_service_unavailable")
        result = await service.persist_financial(
            workspace_id=workspace_id,
            receipt_id=payload.receipt_id,
            confirmation_kind=confirmation_kind,
        )
        return result.to_payload()

    @router.get("/persisted/{receipt_id}")
    async def read_facts(receipt_id: Id, include_invalid: bool = False) -> object:
        if service is None or workspace_id is None:
            raise RevenueConfirmationError("financial_service_unavailable")
        result = await service.read_financial_facts(
            workspace_id=workspace_id,
            receipt_id=receipt_id,
            confirmation_kind=confirmation_kind,
            include_invalid=include_invalid,
        )
        return result.to_payload()

    @router.get("")
    async def query_facts(
        company_id: Id,
        period: Annotated[int | None, Query(ge=1, le=9999)] = None,
        period_start: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
        period_end: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
        metric_key: Literal["revenue", "net_profit_parent", "operating_cash_flow"] | None = None,
        scope: Literal["consolidated"] = "consolidated",
        document_id: Id | None = None,
        disclosure_version: Id | None = None,
        source_revision: Hash | None = None,
        include_invalid: bool = False,
    ) -> object:
        if service is None or workspace_id is None:
            raise RevenueConfirmationError("financial_service_unavailable")
        try:
            for value in (period_start, period_end):
                if value is not None and date.fromisoformat(value).isoformat() != value:
                    raise ValueError("noncanonical date")
            if period_start and period_end and period_start > period_end:
                raise ValueError("reversed period")
        except ValueError as exc:
            raise RevenueConfirmationError("invalid_financial_selection") from exc
        return await service.query_financial_facts(
            workspace_id=workspace_id,
            confirmation_kind=confirmation_kind,
            company_id=company_id,
            period=period,
            period_start=period_start,
            period_end=period_end,
            metric_key=metric_key,
            scope=scope,
            document_id=document_id,
            disclosure_version=disclosure_version,
            source_revision=source_revision,
            include_invalid=include_invalid,
        )

    return router
