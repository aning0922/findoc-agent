from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, computed_field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class SourceRef(Strict):
    kind: Literal["fast", "ocr"]
    workspace_id: str
    company_id: str
    document_id: str
    source_revision: str
    content_sha256: str
    parser_version: str
    report_year: int
    attempt: int | None = None
    report_type: str | None = None
    basis: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    enrollment_id: str | None = None
    artifact_id: str | None = None
    artifact_sha256: str | None = None
    config_hash: str | None = None
    metadata_sha256: str | None = None
    selected_pages: list[int] = Field(default_factory=list, max_length=50)
    identity_status: Literal["fast_source_verified", "file_transcription_only"]


class EvidenceRef(Strict):
    source_ref: SourceRef
    evidence_id: str
    physical_page: int
    text: str
    line_index: int | None = None
    bbox: list[float] | None = None


class FinancialFocus(Strict):
    schema_version: Literal['financial-point-focus-v1']
    collection_id: str
    cell_id: str
    cell_revision: int
    payload_sha256: str
    metric_key: str
    time: dict[str,str]
    normalized_decimal: str
    normalized_unit: str
    source_ref: SourceRef
    financial_authority: Literal[False] = False


class Candidate(Strict):
    evidence_ref: EvidenceRef
    text: str
    document_type: str
    section: str | None = None
    lexical_rank: int | None = None
    dense_rank: int | None = None
    dense_cosine: float | None = None
    fusion_score: float
    rerank_score: float
    retrieval_version: str = "hybrid-trigram-rrf60-topic-v1"

    @computed_field
    @property
    def source_ref(self) -> SourceRef:
        return self.evidence_ref.source_ref


class TrustedIdentity(Strict):
    workspace_id: str
    instance_id: str
    generation: int
    principal_id: str
    expires_at: float


class RetrievalError(Exception):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)
