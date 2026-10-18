"""D28 observation only: delegates unchanged to the formal runtime and real dependencies."""

from contextvars import ContextVar
from functools import wraps
import json
import os
from pathlib import Path
import threading
import time
from urllib.parse import urlparse


def create_app():
    import httpx
    from openai.resources.chat.completions import Completions
    from app.api import runtime_factory
    from app.documents.processor import DocumentProcessor
    from app.rag.retriever import Retriever
    from app.rag.publications import IndexPublications

    log = Path(os.environ["FINDOC_D28_EVENT_LOG"])
    lock = threading.Lock()
    label = ContextVar("d28_request", default="startup")

    def record(event):
        event.update(time_unix=time.time(), request=label.get())
        with lock, log.open("a") as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")

    def observe(owner, name, kind, summary=lambda result: {}):
        original = getattr(owner, name)

        @wraps(original)
        def call(*args, **kwargs):
            start = time.monotonic()
            event = dict(kind=kind)
            try:
                result = original(*args, **kwargs)
                event.update(summary(result))
                return result
            except Exception as exc:
                event["error_type"] = type(exc).__name__
                raise
            finally:
                event["seconds"] = time.monotonic() - start
                record(event)

        setattr(owner, name, call)

    provider_host = urlparse(os.environ["LLM_BASE_URL"]).hostname
    original_send = httpx.Client.send

    @wraps(original_send)
    def send(client, request, *args, **kwargs):
        if request.url.host != provider_host:
            return original_send(client, request, *args, **kwargs)
        start = time.monotonic()
        event = dict(kind="provider_http")
        record(dict(kind="provider_http.started"))
        try:
            response = original_send(client, request, *args, **kwargs)
            event["status"] = response.status_code
            return response
        except Exception as exc:
            event["error_type"] = type(exc).__name__
            raise
        finally:
            event["seconds"] = time.monotonic() - start
            record(event)

    httpx.Client.send = send
    observe(Completions, "create", "provider", lambda r: dict(
        response_id=r.id, model=r.model, usage=r.usage.model_dump() if r.usage else None,
    ))
    observe(runtime_factory, "_runtime_bge_embed", "bge", lambda r: dict(
        vectors=len(r), dimensions=len(r[0]) if r else None,
    ))
    observe(Retriever, "retrieve", "retrieve", lambda r: dict(hits=[dict(
        document_id=h.document_id, source_revision=h.source_revision,
        physical_page=h.page, chunk_id=h.chunk_id, score=h.score,
    ) for h in r]))
    observe(IndexPublications, "search", "milvus_search")
    observe(DocumentProcessor, "process", "document_process", lambda r: dict(
        document_id=r.document_id, status=r.status.value,
    ))
    start = time.monotonic()
    app = runtime_factory.create_isolated_runtime_app_from_env()
    record(dict(kind="ready", seconds=time.monotonic() - start, production_gates=True))

    @app.middleware("http")
    async def audit(request, call_next):
        token = label.set(request.headers.get("X-D28-Evidence", request.url.path)[:100])
        start = time.monotonic()
        try:
            response = await call_next(request)
            record(dict(kind="http", method=request.method, path=request.url.path,
                        status=response.status_code, seconds=time.monotonic() - start))
            return response
        finally:
            label.reset(token)

    return app
