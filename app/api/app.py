from typing import Annotated

from fastapi import (
    FastAPI,
    File,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse

from app.agent.runtime import AgentRuntimeService
from app.agent.revenue_confirmation import ConfirmationKind, RevenueConfirmationService
from app.agent.revenue_extraction import RevenueCandidateService
from app.api.research_sources import create_research_source_router
from app.api.agent import create_agent_router
from app.api.companies import create_company_router
from app.api.document_sources import create_source_router
from app.api.financial_candidates import create_financial_candidate_router
from app.api.financial_reviews import create_financial_review_router
from app.api.financial_analyses import create_financial_analysis_router
from app.documents.source_service import DocumentSourceService
from app.companies.service import CompanyService
from app.api.revenue_research import create_revenue_research_router
from app.api.schemas import (
    ChatRequest,
    DocumentResponse,
    DocumentUploadResponse,
    HealthResponse,
)
from app.api.sse import stream_chat_sse
from app.chat.service import ChatService, DocumentNotReadyError
from app.documents.models import (
    DocumentNotFoundError,
    DocumentStateConflictError,
    DocumentUploadResult,
    DocumentTooLargeError,
    InvalidDocumentError,
)
from app.documents.service import (
    DEFAULT_MAX_UPLOAD_BYTES,
    DocumentService,
)


def _to_upload_response(
    result: DocumentUploadResult,
) -> DocumentUploadResponse:
    """把内部上传结果转换为不暴露存储字段的API响应。"""
    document_payload = DocumentResponse.model_validate(
        result.record,
    ).model_dump()

    return DocumentUploadResponse.model_validate(
        {
            **document_payload,
            "duplicate": result.duplicate,
        }
    )


def create_app(
    document_service: DocumentService,
    *,
    company_service: CompanyService | None = None,
    source_service: DocumentSourceService | None = None,
    candidate_service: RevenueCandidateService | None = None,
    chat_service: ChatService | None = None,
    agent_service: AgentRuntimeService | None = None,
    agent_workspace_id: str | None = None,
    revenue_service: RevenueConfirmationService | None = None,
    revenue_workspace_id: str | None = None,
    financial_confirmation_kind: ConfirmationKind = "local_operator",
    max_selected_documents: int = 4,
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
) -> FastAPI:
    """创建文档、聊天、Agent 及可选收入审阅/确认接口的 FastAPI 应用。

    Args:
        document_service: 已注入基础设施依赖的文档应用服务。
        company_service: 服务端固定空间的企业/元数据服务；缺省时安全返回503。
        agent_service: 已装配的 Agent 服务；缺省时 Agent 端点返回安全 503。
        agent_workspace_id: 服务器配置的查询范围；启用 Agent 时必须显式提供。
        revenue_service: 已装配的收入确认服务；缺省时收入端点安全返回 503。
        revenue_workspace_id: 服务端收入范围；启用收入时必须显式提供。
        max_upload_bytes: 路由读取上传内容时使用的字节上限。

    Returns:
        可供测试或uvicorn运行的FastAPI应用。

    Raises:
        ValueError: max_upload_bytes不是正整数。
        ValueError: 启用 Agent 却未提供非空服务端 workspace。
        ValueError: 启用收入却未提供非空服务端 workspace。
    """
    if max_upload_bytes <= 0:
        raise ValueError("max_upload_bytes 必须是正整数")

    app = FastAPI(title="FinDoc RAG API")
    app.include_router(create_research_source_router(
        document_service, source_service, max_selected_documents=max_selected_documents,
    ))
    app.include_router(create_company_router(company_service))
    app.include_router(create_source_router(source_service, max_upload_bytes))
    app.include_router(create_financial_candidate_router(candidate_service))
    app.include_router(create_financial_review_router(
        service=revenue_service, documents=document_service, workspace_id=revenue_workspace_id,
        confirmation_kind=financial_confirmation_kind,
    ))
    app.include_router(create_financial_analysis_router(
        service=revenue_service, workspace_id=revenue_workspace_id,
    ))
    app.include_router(
        create_agent_router(
            service=agent_service,
            workspace_id=agent_workspace_id,
        )
    )
    app.include_router(
        create_revenue_research_router(
            service=revenue_service,
            documents=document_service,
            workspace_id=revenue_workspace_id,
        )
    )

    @app.get(
        "/health",
        response_model=HealthResponse,
    )
    async def health() -> HealthResponse:
        """返回进程存活状态，不等待后台文档任务。"""
        return HealthResponse(status="ok")

    @app.post(
        "/documents",
        response_model=DocumentUploadResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def upload_document(
        file: Annotated[
            UploadFile,
            File(description="带文本层的PDF文件"),
        ],
    ) -> DocumentUploadResponse:
        """读取受限大小的PDF内容并提交给文档应用服务。"""
        try:
            # 多读一个字节，才能区分“刚好达到上限”和“超过上限”。
            content = await file.read(max_upload_bytes + 1)
        finally:
            await file.close()

        try:
            result = await document_service.upload_document(
                source_file=file.filename or "",
                content=content,
            )
        except DocumentTooLargeError as exc:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=str(exc),
            ) from exc
        except InvalidDocumentError as exc:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=str(exc),
            ) from exc

        except Exception as exc:
            raise HTTPException(500, "文档服务暂时不可用") from exc

        return _to_upload_response(result)

    @app.get(
        "/documents",
        response_model=list[DocumentResponse],
    )
    async def list_documents() -> list[DocumentResponse]:
        """列出服务端固定workspace中的文档状态。"""
        records = await document_service.list_documents()
        return [DocumentResponse.model_validate(record) for record in records]

    @app.get(
        "/documents/{document_id}",
        response_model=DocumentResponse,
    )
    async def get_document(
        document_id: str,
    ) -> DocumentResponse:
        """查询一个文档的当前处理状态。"""
        try:
            record = await document_service.get_document(document_id)
        except DocumentNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文档不存在",
            ) from exc

        return DocumentResponse.model_validate(record)

    @app.post(
        "/documents/{document_id}/retry",
        response_model=DocumentResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def retry_document(
        document_id: str,
    ) -> DocumentResponse:
        """仅把failed文档重新排队并尝试派发。"""
        try:
            record = await document_service.retry_document(document_id)
        except DocumentNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文档不存在",
            ) from exc
        except DocumentStateConflictError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="只有处理失败的文档可以重试",
            ) from exc

        return DocumentResponse.model_validate(record)

    @app.post("/chat")
    async def chat(
        payload: ChatRequest,
        request: Request,
    ) -> StreamingResponse:
        """对通过HTTP前置检查的聊天请求返回SSE响应。

        输入：只包含document_id和query的浏览器请求。
        输出：通过前置检查后返回text/event-stream。
        失败：文档不存在返回404，未ready返回409，未注入聊天服务返回503。
        边界：不执行检索或引用验证，只连接ChatService和SSE传输层。
        """
        if chat_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="聊天服务未启用",
            )
        try:
            prepared = await chat_service.prepare(
                document_id=payload.document_id, query=payload.query
            )
        except DocumentNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文档不存在",
            ) from exc
        except DocumentNotReadyError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="只有处理成功的文档可以聊天",
            ) from exc
        return StreamingResponse(
            stream_chat_sse(chat_service, prepared, request.is_disconnected),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app
