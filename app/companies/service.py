"""Server-owned workspace; public callers cannot supply authorization scope."""

from app.companies.models import (
    Company,
    CompanyCreate,
    CompanyPatch,
    ReportMetadataInput,
    ReportMetadata,
)
from app.companies.sqlite_repository import SQLiteCompanyRepository


class CompanyService:
    def __init__(self, repository: SQLiteCompanyRepository, *, workspace_id: str) -> None:
        if not isinstance(workspace_id, str) or not workspace_id.strip():
            raise ValueError("server workspace must be non-empty")
        self._repository = repository
        self._workspace_id = workspace_id

    def create(self, payload: CompanyCreate) -> Company:
        payload = CompanyCreate.model_validate(payload.model_dump())
        return self._repository.create(self._workspace_id, payload)

    def list(self) -> list[Company]:
        return self._repository.list(self._workspace_id)

    def get(self, company_id: str) -> Company:
        return self._repository.get(self._workspace_id, company_id)

    def update(self, company_id: str, payload: CompanyPatch) -> Company:
        payload = CompanyPatch.model_validate(payload.model_dump(exclude_unset=True))
        return self._repository.update(self._workspace_id, company_id, payload)

    def bind(self, document_id: str, payload: ReportMetadataInput) -> ReportMetadata:
        payload = ReportMetadataInput.model_validate(payload.model_dump())
        return self._repository.bind(self._workspace_id, document_id, payload)

    def metadata(self, document_id: str) -> ReportMetadata:
        return self._repository.metadata(self._workspace_id, document_id)
