"""Read-only selected-source profile; no latest-version authority selection."""


class ProfileService:
    def __init__(self, statements):
        self.statements = statements

    async def profile(self, company_id):
        company = self.statements.companies.get(company_id)
        collections = await self.statements.list_collections(company_id)
        return {
            "schema_version": "company360-v1",
            "company": company.model_dump(mode="json"),
            "collections": collections["collections"],
            "selected_financial_kpis": [],
            "limitations": [
                "Choose explicit statement collections to project financial trends; no latest filing selected."
            ],
        }


def create_profile_router(service):
    from fastapi import APIRouter
    from app.finance_v2.api import FinanceRoute

    router = APIRouter(prefix="/cplus", route_class=FinanceRoute)

    @router.get("/companies/{company_id}/profile")
    async def profile(company_id: str):
        return await service.profile(company_id)

    return router
