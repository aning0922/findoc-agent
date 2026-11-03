from typing import Literal
from pydantic import Field
from app.retrieval_v2.models import Strict, SourceRef


class TemplateRunRequest(Strict):
    operation_id: str
    template_id: Literal["overview", "cash", "peer", "changes"]
    template_version: Literal["cplus-template-v1"]
    question: str = Field(min_length=1, max_length=2000)
    selected_sources: list[SourceRef] = Field(min_length=1, max_length=3)
    generate_explanation: bool = False
