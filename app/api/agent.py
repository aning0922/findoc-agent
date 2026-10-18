"""同步完成的 Agent HTTP 薄适配；范围来自配置，错误与历史投影显式收窄。"""

import asyncio
from collections.abc import Callable, Coroutine
import sqlite3
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.agent.result_storage import (
    AgentResultIntegrityError,
    AgentResultNotReadyError,
    AgentResultNotStoredError,
)
from app.agent.run_models import AgentRunNotFoundError, RunEventType
from app.agent.runtime import AgentRuntimeService
from app.api.agent_schemas import (
    AgentEventResponse,
    AgentEventsResponse,
    AgentRequest,
    AgentRunResponse,
)
from app.documents.models import DocumentNotFoundError
from app.documents.preparation import DocumentNotReadyError


class _AgentUnavailableError(RuntimeError):
    """应用没有注入 Agent 依赖；只映射固定 503，不自动初始化服务。"""


_ERRORS: tuple[tuple[type[Exception], int, str, str], ...] = (
    (_AgentUnavailableError, 503, "agent_unavailable", "Agent 服务未启用"),
    (RequestValidationError, 422, "invalid_agent_request", "请求字段或类型不符合接口要求"),
    (DocumentNotFoundError, 404, "document_not_found", "文档不存在"),
    (DocumentNotReadyError, 409, "document_not_ready", "只有处理成功的文档可以执行任务"),
    (AgentRunNotFoundError, 404, "agent_run_not_found", "运行记录不存在"),
    (AgentResultNotReadyError, 409, "agent_result_not_ready", "运行结果尚未提交"),
    (AgentResultNotStoredError, 409, "agent_result_not_stored", "此运行未保存可展示的用户结果"),
    (AgentResultIntegrityError, 500, "agent_result_integrity_error", "运行结果暂时无法读取"),
    (sqlite3.Error, 500, "agent_storage_error", "运行数据读写失败，无法确认本次操作完成"),
)

_EVENT_SUMMARIES = {
    RunEventType.TOOL_REQUESTED: "记录到一次工具调用申请。",
    RunEventType.TOOL_SUCCEEDED: "一次工具调用完成；不代表用户答案已通过验证。",
    RunEventType.TOOL_FAILED: "一次工具调用失败。",
    RunEventType.RUN_SUCCEEDED: "执行循环正常结束；用户结果以结果接口为准。",
    RunEventType.RUN_FAILED: "执行循环以错误终态结束；用户结果以结果接口为准。",
}


class _AgentRoute(APIRoute):
    """只为 Agent 路由建立安全错误外壳，保留已有聊天与文档的 HTTP 行为。"""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        """包住请求解析、执行和响应投影；不回显校验输入、异常正文或数据库信息。"""
        original = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                return await original(request)
            except Exception as exc:
                for error_type, status_code, code, message in _ERRORS:
                    if isinstance(exc, error_type):
                        return JSONResponse(
                            status_code=status_code,
                            content={"detail": {"code": code, "message": message}},
                        )
                return JSONResponse(
                    status_code=500,
                    content={"detail": {
                        "code": "agent_internal_error", "message": "任务服务暂时无法完成本次请求",
                    }},
                )

        return handle


def create_agent_router(
    *, service: AgentRuntimeService | None, workspace_id: str | None,
) -> APIRouter:
    """构造三个端点；workspace 仅来自服务端注入，启用服务却缺失范围时启动失败。

    POST 等执行和提交后返回；GET 在线程中委托持久读取，不执行或修复性生成。
    此处仅提供本地 demo 资源绑定，不实现认证、后台队列或 POST 请求幂等。
    """
    if service is not None and (
        not isinstance(workspace_id, str) or not workspace_id.strip()
    ):
        raise ValueError("启用 Agent HTTP 必须注入服务端 workspace")
    router = APIRouter(prefix="/agent/runs", tags=["agent"], route_class=_AgentRoute)

    def enabled_service() -> AgentRuntimeService:
        """返回已注入服务；未启用时固定 503，不初始化任何重依赖。"""
        if service is None:
            raise _AgentUnavailableError
        return service

    @router.post("", response_model=AgentRunResponse, status_code=201)
    async def create_run(payload: AgentRequest) -> AgentRunResponse:
        """仅执行两个业务输入；三态已提交均为 201，保存异常由安全外壳处理。"""
        recorded = await enabled_service().run(
            document_id=payload.document_id, query=payload.query,
        )
        return AgentRunResponse.model_validate({
            "run_id": recorded.run.run_id,
            "document_id": recorded.run.document_id,
            "user_result": recorded.user_result.to_public(),
        })

    @router.get("/{run_id}", response_model=AgentRunResponse)
    async def get_result(run_id: str) -> AgentRunResponse:
        """以服务器固定范围读取已保存结果；不从 body/query/header 获取授权范围。"""
        active = enabled_service()
        assert workspace_id is not None  # 构造时已验证，仅用于类型收窄。
        stored = await asyncio.to_thread(
            active.get_user_result, workspace_id=workspace_id, run_id=run_id,
        )
        return AgentRunResponse.model_validate({
            "run_id": stored.run_id,
            "document_id": stored.document_id,
            "user_result": stored.user_result.to_public(),
        })

    @router.get("/{run_id}/events", response_model=AgentEventsResponse)
    async def get_events(run_id: str) -> AgentEventsResponse:
        """读取 sequence 有序的历史；只取事件类型生成固定摘要，绝不直通 payload。"""
        active = enabled_service()
        assert workspace_id is not None
        events = await asyncio.to_thread(
            active.list_events, workspace_id=workspace_id, run_id=run_id,
        )
        return AgentEventsResponse(
            run_id=run_id,
            events=[AgentEventResponse(
                sequence=event.sequence,
                execution_event_type=event.event_type,
                summary=_EVENT_SUMMARIES[event.event_type],
            ) for event in events],
        )

    return router
