"""Opt-in v2 router. Integration owns runtime registration and gateway route policy."""
import inspect
import sqlite3
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.companies.models import RegistryNotFoundError
from app.documents.models import DocumentNotFoundError
from app.documents.source_models import SourceError
from app.finance_v2.contracts import Collect, Confirm, FinanceError, Revoke, Select


class FinanceRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def checked(request):
            try:
                response = await original(request)
            except Exception as exc:
                if isinstance(exc, (FinanceError, SourceError)):
                    code, status = exc.code, exc.status
                elif isinstance(exc, (RegistryNotFoundError, DocumentNotFoundError)):
                    code, status = "resource_not_found", 404
                elif isinstance(exc, RequestValidationError):
                    code, status = "invalid_finance_v2_request", 422
                elif isinstance(exc, sqlite3.Error):
                    code, status = "finance_storage_unavailable", 503
                else:
                    # Preserve explicit integration authorization failures without echoing input.
                    from fastapi import HTTPException
                    code, status = ("owner_authorization_required", exc.status_code) if isinstance(exc, HTTPException) else ("finance_operation_failed", 503)
                response = JSONResponse({"detail": {"code": code, "message": code.replace("_", " ")}}, status)
            response.headers["Cache-Control"] = "no-store"
            return response
        return checked


def create_finance_v2_router(service, *, owner_authorizer=None):
    """owner_authorizer(Request) -> OwnerAuthorization | Awaitable[OwnerAuthorization].

    Must be injected only behind secret+generation+instance guarded child and an
    owner-only gateway policy. Missing authorizer keeps confirmation/revocation off.
    """
    router = APIRouter(prefix="/financial", route_class=FinanceRoute, tags=["finance-v2"])

    async def owner(request):
        if owner_authorizer is None:
            raise FinanceError("finance_v2_owner_gate_not_connected", 503)
        value = owner_authorizer(request)
        return await value if inspect.isawaitable(value) else value

    @router.post("/extended-metrics/collect")
    async def collect(payload: Collect):
        return await service.collect(payload)

    @router.get("/extended-metrics")
    async def metrics(request: Request, company_id: Annotated[str, Query(min_length=1, max_length=128)]):
        if set(request.query_params) != {"company_id"} or len(request.query_params.getlist("company_id")) != 1:
            raise FinanceError("unknown_query_parameter", 422)
        return await service.list_metrics(company_id)

    @router.get("/extended-signals")
    async def signals(request: Request,
                      company_id: Annotated[str, Query(min_length=1, max_length=128)],
                      document_id: Annotated[str, Query(min_length=1, max_length=128)],
                      source_revision: Annotated[str, Query(pattern=r"^[a-f0-9]{64}$")]):
        keys = {"company_id", "document_id", "source_revision"}
        if set(request.query_params) != keys or any(len(request.query_params.getlist(key)) != 1 for key in keys):
            raise FinanceError("unknown_query_parameter", 422)
        return await service.signals(company_id, document_id, source_revision)

    @router.post("/extended-reviews")
    async def review(payload: Select):
        return await service.review(payload)

    @router.post("/extended-confirmations")
    async def confirm(payload: Confirm, request: Request):
        return await service.confirm(payload, await owner(request))

    @router.post("/extended-confirmations/{receipt_id}/revoke")
    async def revoke(receipt_id: UUID, payload: Revoke, request: Request):
        return await service.revoke(str(receipt_id), payload, await owner(request))

    @router.post("/extended-analyses")
    async def analyse(payload: Select):
        return await service.analyse(payload)

    @router.get("/extended-operations/{operation_id}")
    async def operation(operation_id: UUID):
        return service.operation(str(operation_id))

    return router
