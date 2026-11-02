"""Conversation application boundary: register once, run once, commit/read back.

The A1 fake is explicit opt-in. Production graph construction belongs to A2.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import sqlite3

from app.conversations.models import (
    ConversationDetail, CreateConversationRequest, CreateTurnRequest, ResolvedQuery,
    Turn, TurnData, TurnResult, TurnStatus, error_result,
)
from app.conversations.repository import CandidateValidationError, ConversationError, ConversationRepository
from app.documents.preparation import DocumentTaskPreparer, PreparedDocumentSelection
from app.documents.source_models import SourceError


@dataclass(frozen=True)
class TurnExecution:
    repository: ConversationRepository
    turn: TurnData
    selection: PreparedDocumentSelection
    claim: str


@dataclass(frozen=True)
class ExecutionResult:
    result: TurnResult
    status: TurnStatus = "completed"
    resolved: ResolvedQuery | None = None
    provider_outcome: str | None = None
    admit: Callable[[sqlite3.Connection, TurnData], None] | None = None


Handler = Callable[[TurnExecution], Awaitable[ExecutionResult]]


async def fake_handler(execution: TurnExecution) -> ExecutionResult:
    """Explicit deterministic test substitute; no evidence, model or numeric claims."""
    docs = execution.selection.documents
    company_ids = {d.company_id for d in docs}
    return ExecutionResult(
        TurnResult(kind="clarification", answer_text="测试替身：会话已保存，请继续明确研究问题。"),
        resolved=ResolvedQuery(text=execution.turn.user_text, intent="clarify",
            company_id=next(iter(company_ids)) if len(company_ids) == 1 else None,
            metric_key=None, periods=[], resolution="ambiguous", context_turn_ids=[]),
    )


class ConversationService:
    def __init__(self, repository: ConversationRepository, preparer: DocumentTaskPreparer,
                 *, handler: Handler):
        self.repository, self.preparer, self.handler = repository, preparer, handler

    async def create(self, request: CreateConversationRequest) -> tuple[ConversationDetail, bool]:
        old = self.repository.existing("create_conversation", None, request)
        if old is not None:
            return self.repository.detail(old.conversation_id), False
        selection = await self.preparer.prepare_many(document_ids=request.document_ids,
                                                      query="会话来源核验")
        cid, created = self.repository.create(request, selection)
        # Only committed/read-back state can become a response.
        return self.repository.detail(cid), created

    async def send(self, cid: str, request: CreateTurnRequest) -> Turn:
        old = self.repository.existing("send_turn", cid, request)
        if old is not None:
            return self.repository.turn_by_operation(cid, request.operation_id)
        pinned = self.repository.selection(cid, request.text)
        fresh = await self.preparer.prepare_many(document_ids=list(pinned.document_ids),
                                                 query=request.text)
        if fresh != pinned:
            raise ConversationError("source_changed", 409)
        turn, claim, created = self.repository.register(cid, request, fresh)
        if not created:
            return self.repository.get_turn(cid, turn.turn_id)
        assert claim is not None
        try:
            output = await self.handler(TurnExecution(self.repository, turn, pinned, claim))
            # Bytes first, then scope/fact qualification inside the commit transaction.
            await self.preparer.revalidate(pinned)
        except asyncio.CancelledError:
            try:
                self.repository.finish(cid, turn.turn_id, claim, error_result("interrupted"),
                                       status="interrupted")
            except Exception:
                # Keep the durable running reservation; startup recovery closes it.
                # No late provider thread has permission to publish its return value.
                pass
            raise
        except SourceError:
            output = ExecutionResult(error_result("source_changed"), status="failed")
        except Exception:
            output = ExecutionResult(error_result("execution_error"), status="failed")
        try:
            self.repository.finish(cid, turn.turn_id, claim, output.result,
                                   status=output.status, resolved=output.resolved,
                                   provider_outcome=output.provider_outcome, admit=output.admit)
        except CandidateValidationError:
            self.repository.finish(cid, turn.turn_id, claim, error_result("result_validation_error"),
                                   status="failed")
        return self.repository.get_turn(cid, turn.turn_id)
