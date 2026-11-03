from typing import Literal
from pydantic import Field
from app.retrieval_v2.models import SourceRef, Strict

Topic = Literal["经营风险", "主要业务", "研发"]


class AnnualDiffRequest(Strict):
    operation_id: str
    left_source: SourceRef
    right_source: SourceRef
    topics: list[Topic] = Field(
        default_factory=lambda: ["经营风险", "主要业务", "研发"], min_length=1, max_length=3
    )
    generate_explanation: bool = False


class AnnualDiffError(Exception):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)
