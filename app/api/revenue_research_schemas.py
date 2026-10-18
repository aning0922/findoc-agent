"""收入审阅/确认的严格 HTTP DTO；公开投影不改变内部快照或业务事实。"""

from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StringConstraints,
)

from app.agent.research_workflow import RevenueCandidate
from app.agent.revenue_confirmation import RevenueConfirmation, RevenueReview
from app.documents.models import DocumentRecord


NonEmptyId = Annotated[str, StringConstraints(strict=True, min_length=1, pattern=r"\S")]
SnapshotId = Annotated[
    str, StringConstraints(strict=True, min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
]
DecimalText = Annotated[
    str, StringConstraints(strict=True, pattern=r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
]


class _RevenueDTO(BaseModel):
    """输入和嵌套输出均拒绝额外字段及隐式类型转换。"""

    model_config = ConfigDict(extra="forbid", strict=True)


class RevenueReviewRequest(_RevenueDTO):
    """只接收文档查找键；不接受客户端提供候选或范围。"""

    document_id: NonEmptyId


class RevenueConfirmationRequest(_RevenueDTO):
    """只接收所见快照和明确动作；false 合法但不能创建确认。"""

    document_id: NonEmptyId
    snapshot_id: SnapshotId
    accepted: StrictBool


class RevenueRevisionResponse(_RevenueDTO):
    """公开来源版本；内部 workspace/document 范围由外层服务核验。"""

    content_sha256: SnapshotId
    attempt: StrictInt = Field(ge=1)
    extraction_method: NonEmptyId
    extraction_version: NonEmptyId


class RevenueEvidenceResponse(_RevenueDTO):
    """一处完整证据：保留原文、原始金额/单位及字符位置。"""

    chunk_id: NonEmptyId
    source_file: NonEmptyId
    page: StrictInt = Field(ge=1)
    text: NonEmptyId
    start: StrictInt = Field(ge=0)
    end: StrictInt = Field(ge=1)
    raw_value: NonEmptyId
    raw_unit: NonEmptyId | None


class RevenueCandidateResponse(_RevenueDTO):
    """未确认候选的公开内容；金额为 Decimal 格式化后的字符串。"""

    source_ref: NonEmptyId
    chunk_id: NonEmptyId
    source_file: NonEmptyId
    page: StrictInt = Field(ge=1)
    period: StrictInt
    value: DecimalText
    unit: Literal["CNY_YUAN"]
    extraction_method: NonEmptyId
    extraction_version: NonEmptyId
    evidence: list[RevenueEvidenceResponse] = Field(min_length=1)


class RevenueReviewResponse(_RevenueDTO):
    """完整审阅响应；snapshot_id 直接来自内部 RevenueReview。"""

    schema_version: Literal["revenue-research-review-v1"] = Field(
        default="revenue-research-review-v1", alias="schema"
    )
    document_id: NonEmptyId
    source_file: NonEmptyId
    snapshot_id: SnapshotId
    revision: RevenueRevisionResponse
    candidates: list[RevenueCandidateResponse] = Field(min_length=2, max_length=2)


class RevenueConfirmationResponse(_RevenueDTO):
    """已提交确认回执；只公开本入口的固定操作者类型与原确认时间。"""

    schema_version: Literal["revenue-research-confirmation-v1"] = Field(
        default="revenue-research-confirmation-v1", alias="schema"
    )
    document_id: NonEmptyId
    confirmation_id: NonEmptyId
    confirmed_at: AwareDatetime
    snapshot_id: SnapshotId
    confirmation_kind: Literal["local_operator"]


def _candidate_response(candidate: RevenueCandidate) -> RevenueCandidateResponse:
    """逐字段投影服务候选，遍历全部证据；不复制算法或经 float 转换金额。"""
    return RevenueCandidateResponse.model_validate(
        {
            "source_ref": candidate.source_ref,
            "chunk_id": candidate.chunk_id,
            "source_file": candidate.source_file,
            "page": candidate.page,
            "period": candidate.period,
            "value": format(candidate.value, "f"),
            "unit": candidate.unit.value if candidate.unit is not None else None,
            "extraction_method": candidate.extraction_method,
            "extraction_version": candidate.extraction_version,
            "evidence": [
                {
                    "chunk_id": item.chunk_id,
                    "source_file": item.source_file,
                    "page": item.page,
                    "text": item.text,
                    "start": item.start,
                    "end": item.end,
                    "raw_value": item.raw_value,
                    "raw_unit": item.raw_unit,
                }
                for item in candidate.evidence
            ],
        }
    )


def _check_review_identity(review: RevenueReview, document: DocumentRecord) -> None:
    """输出必须属于前置核准的文档/范围/逻辑文件，异常对象不部分公开。"""
    if (review.revision.workspace_id, review.revision.document_id) != (
        document.workspace_id,
        document.document_id,
    ) or any(item.source_file != document.source_file for item in review.candidates):
        raise ValueError("审阅对象与核准文档身份不一致")


def to_review_response(review: RevenueReview, *, document: DocumentRecord) -> RevenueReviewResponse:
    """将完整领域审阅转为公开 DTO；只省去 scope，不重新计算公开摘要。"""
    _check_review_identity(review, document)
    revision = review.revision
    return RevenueReviewResponse(
        document_id=revision.document_id,
        source_file=document.source_file,
        snapshot_id=review.snapshot_id,
        revision=RevenueRevisionResponse(
            content_sha256=revision.content_sha256,
            attempt=revision.attempt,
            extraction_method=revision.extraction_method,
            extraction_version=revision.extraction_version,
        ),
        candidates=[
            _candidate_response(item) for item in sorted(review.candidates, key=lambda c: c.period)
        ],
    )


def to_confirmation_response(
    confirmation: RevenueConfirmation, *, document: DocumentRecord, reviewed_snapshot_id: str
) -> RevenueConfirmationResponse:
    """只从保存成功的服务回执投影；相同有效确认保留原 ID/时间。"""
    _check_review_identity(confirmation.review, document)
    if confirmation.review.snapshot_id != reviewed_snapshot_id:
        raise ValueError("确认回执与所见快照不一致")
    return RevenueConfirmationResponse.model_validate(
        {
            "document_id": confirmation.review.revision.document_id,
            "confirmation_id": confirmation.confirmation_id,
            "confirmed_at": confirmation.confirmed_at,
            "snapshot_id": confirmation.review.snapshot_id,
            "confirmation_kind": confirmation.confirmation_kind,
        }
    )
