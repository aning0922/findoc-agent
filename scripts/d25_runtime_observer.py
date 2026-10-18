"""Transparent execution metadata for the D25 production runtime.

Calls the original implementations once, preserving results and exceptions.
Never records credentials, prompts, response content, or accepts any fact.
"""

from datetime import datetime, timezone
from functools import wraps
import json
import os
from pathlib import Path
import threading
import time
from uuid import uuid4

_lock = threading.Lock()


def record(event, **fields):
    path = Path(os.environ["FINDOC_D25_EXECUTION_LOG"])
    with _lock, path.open("a") as stream:
        stream.write(json.dumps(dict(at=datetime.now(timezone.utc).isoformat(),
                                     pid=os.getpid(), event=event, **fields)) + "\n")


def observe(owner, name, label, summarize):
    original = getattr(owner, name)

    @wraps(original)
    def call(*args, **kwargs):
        identity = str(uuid4())
        start = time.monotonic()
        record(label + ".started", call_id=identity)
        try:
            result = original(*args, **kwargs)
        except Exception as exc:
            record(label + ".failed", call_id=identity, error_type=type(exc).__name__,
                   seconds=time.monotonic() - start)
            raise
        record(label + ".completed", call_id=identity,
               seconds=time.monotonic() - start, **summarize(result))
        return result

    setattr(owner, name, call)


def create_app():
    from openai.resources.chat.completions import Completions
    from app.api import runtime_factory
    from app.rag.retriever import Retriever

    def completion_summary(response):
        return dict(provider_request_id=response.id, model=response.model,
                    usage=response.usage.model_dump() if response.usage else None,
                    tool_names=[t.function.name for c in response.choices
                                for t in (c.message.tool_calls or [])
                                if t.type == "function"])

    observe(Completions, "create", "provider", completion_summary)
    observe(runtime_factory, "_runtime_bge_embed", "bge",
            lambda value: dict(model="BAAI/bge-m3", vectors=len(value),
                               dimensions=len(value[0]) if value else 0))
    observe(Retriever, "retrieve", "retrieval",
            lambda hits: dict(hits=[dict(document_id=h.document_id,
                                         source_revision=h.source_revision,
                                         page=h.page, chunk_id=h.chunk_id, score=h.score)
                                   for h in hits]))
    app = runtime_factory.create_isolated_runtime_app_from_env()

    @app.get("/_d25/runtime-health", include_in_schema=False)
    def runtime_health():
        resources = app.state.runtime_rag_resources
        stats = resources.milvus_client.get_collection_stats(
            runtime_factory.RUNTIME_COLLECTION_NAME
        )
        record("milvus.metadata_read", row_count=stats.get("row_count"))
        return dict(production_gates=True, collection=runtime_factory.RUNTIME_COLLECTION_NAME,
                    stats=stats, model=resources.rag_service._llm_client.model)

    @app.middleware("http")
    async def requests(request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        record("http", method=request.method, path=request.url.path,
               status=response.status_code, seconds=time.monotonic() - start)
        return response

    record("runtime.ready", factory="create_isolated_runtime_app_from_env",
           production_gates=True, confirmation_kind="local_operator")
    return app
