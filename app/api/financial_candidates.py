"""Read-only dynamic candidate adapter. Confirmation stays in the existing service."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.agent.revenue_extraction import RevenueCandidateService
from app.companies.models import RegistryNotFoundError
from app.documents.models import DocumentNotFoundError
from app.documents.source_models import SourceError


def create_financial_candidate_router(service: RevenueCandidateService | None) -> APIRouter:
    router = APIRouter()

    @router.get("/documents/{document_id}/financial-candidates")
    async def candidates(
        document_id: str,
        company_id: str,
        source_revision: Annotated[str, Query(pattern=r"^[0-9a-f]{64}$")],
        metric_keys: Annotated[list[str], Query(min_length=1, max_length=20)],
        periods: Annotated[list[int], Query(min_length=1, max_length=100)],
    ) -> object:
        if service is None:
            raise HTTPException(503, "financial_candidates_unavailable")
        try:
            return await service.collect_metrics(
                document_id=document_id,
                company_id=company_id,
                source_revision=source_revision,
                metric_keys=tuple(metric_keys),
                periods=tuple(periods),
            )
        except SourceError as exc:
            raise HTTPException(exc.status, exc.code) from exc
        except (DocumentNotFoundError, RegistryNotFoundError) as exc:
            raise HTTPException(404, "resource_not_found") from exc
        except ValueError as exc:
            raise HTTPException(422, "invalid_financial_selection") from exc
        except Exception as exc:
            raise HTTPException(500, "financial_candidates_unavailable") from exc

    return router
