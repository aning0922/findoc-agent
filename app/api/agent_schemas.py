"""Agent HTTP 的严格输入与公开白名单；不承载内部运行对象。"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.agent.run_models import RunEventType
from app.agent.user_result import AgentRefusalReason, AgentResultError


NonEmptyText = Annotated[str, StringConstraints(strict=True, min_length=1, pattern=r"\S")]
"""拒绝非字符串、空串和纯空白；不在 HTTP 层限制业务查询句式。"""


class AgentRequest(BaseModel):
    """只收文档查找键与问题；额外控制字段或非法类型在执行前返回 422。"""

    model_config = ConfigDict(extra="forbid")

    document_id: NonEmptyText
    query: NonEmptyText


class _PublicModel(BaseModel):
    """拒绝多余输出字段，避免 API DTO 变成任意内部载荷的容器。"""

    model_config = ConfigDict(extra="forbid")


class AgentCitationResponse(_PublicModel):
    """只接收 to_public 已签发的引用字段，不从客户端或模型恢复来源。"""

    number: int = Field(strict=True, gt=0)
    source_file: NonEmptyText
    page: int = Field(strict=True, gt=0)
    chunk_id: NonEmptyText


class AgentAnswerResponse(_PublicModel):
    """已验证答案及非空引用；HTTP schema 不重新证明语义质量。"""

    status: Literal["answered"]
    content: NonEmptyText
    citations: list[AgentCitationResponse] = Field(min_length=1)


class AgentRefusalResponse(_PublicModel):
    """正常拒答的有限原因与服务端说明。"""

    status: Literal["refusal"]
    reason: AgentRefusalReason
    message: NonEmptyText


class AgentSystemErrorResponse(_PublicModel):
    """已提交的产品系统错误；没有候选正文或原始异常字段。"""

    status: Literal["system_error"]
    error_code: AgentResultError
    message: NonEmptyText


class AgentRunResponse(_PublicModel):
    """POST 与持久 GET 共用的 Run/文档身份及产品结果；不公开 workspace。"""

    run_id: NonEmptyText
    document_id: NonEmptyText
    user_result: Annotated[
        AgentAnswerResponse | AgentRefusalResponse | AgentSystemErrorResponse,
        Field(discriminator="status"),
    ]


class AgentEventResponse(_PublicModel):
    """执行后的历史投影；执行事件成功不表示产品 answered。"""

    sequence: int = Field(strict=True, gt=0)
    execution_event_type: RunEventType
    summary: str


class AgentEventsResponse(_PublicModel):
    """有序历史记录，不表示实时进度或精确工具耗时。"""

    run_id: NonEmptyText
    projection: Literal["history"] = "history"
    events: list[AgentEventResponse]
