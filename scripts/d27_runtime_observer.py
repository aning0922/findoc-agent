"""Bounded production-gate D27 server; transparent real provider instrumentation."""

import json
import os
from pathlib import Path
import threading
import time
from urllib.parse import urlparse


def create_app():
    from openai.resources.chat.completions import Completions
    from app.api import runtime_factory
    from app.rag.retriever import Retriever
    from app.rag.publications import IndexPublications
    from app.documents.processor import DocumentProcessor

    log = Path(os.environ["D27_SERVER_LOG"])
    lock = threading.Lock()
    used = 0
    physical_used = 0

    def record(value):
        with lock, log.open("a") as f:
            f.write(json.dumps(value, ensure_ascii=False) + "\n")

    def observe(owner, name, kind, summary=lambda r: {}):
        original = getattr(owner, name)

        def call(*a, **kw):
            t = time.perf_counter()
            event = dict(kind=kind, started_monotonic=t)
            if kind == "provider":
                record(dict(kind="provider.started", started_monotonic=t))
            try:
                result = original(*a, **kw)
                event.update(summary(result))
                return result
            except Exception as exc:
                event["error_type"] = type(exc).__name__
                raise
            finally:
                event["seconds"] = time.perf_counter() - t
                record(event)

        setattr(owner, name, call)

    original = Completions.create

    def bounded(self, *a, **kw):
        nonlocal used
        with lock:
            if used >= 4:
                raise RuntimeError("D27 server physical-call budget exhausted")
            used += 1
        kw["max_tokens"] = 4096
        return original(self, *a, **kw)

    Completions.create = bounded
    import httpx

    original_send = httpx.Client.send
    provider_host = urlparse(os.environ["LLM_BASE_URL"]).hostname

    def physical_send(self, request, *a, **kw):
        nonlocal physical_used
        if request.url.host != provider_host:
            return original_send(self, request, *a, **kw)
        with lock:
            if physical_used >= 4:
                raise RuntimeError("D27 physical network budget exhausted")
            physical_used += 1
        t = time.perf_counter()
        record(dict(kind="provider_http.started", started_monotonic=t))
        event = dict(kind="provider_http", started_monotonic=t)
        try:
            response = original_send(self, request, *a, **kw)
            event["status"] = response.status_code
            return response
        except Exception as exc:
            event["error_type"] = type(exc).__name__
            raise
        finally:
            event["seconds"] = time.perf_counter() - t
            record(event)

    httpx.Client.send = physical_send
    observe(
        Completions,
        "create",
        "provider",
        lambda r: dict(
            request_id=r.id, model=r.model, usage=r.usage.model_dump() if r.usage else None
        ),
    )
    observe(runtime_factory, "_runtime_bge_embed", "bge", lambda r: dict(vectors=len(r)))
    observe(
        Retriever,
        "retrieve",
        "retrieve",
        lambda r: dict(
            hits=[
                dict(
                    document_id=h.document_id,
                    source_revision=h.source_revision,
                    page=h.page,
                    chunk_id=h.chunk_id,
                    score=h.score,
                )
                for h in r
            ]
        ),
    )
    observe(IndexPublications, "search", "milvus_search")
    observe(
        DocumentProcessor,
        "process",
        "document_process",
        lambda r: dict(document_id=r.document_id, status=r.status.value),
    )
    t = time.perf_counter()
    app = runtime_factory.create_isolated_runtime_app_from_env()
    record(
        dict(
            kind="ready",
            seconds=time.perf_counter() - t,
            production_gates=True,
            model=app.state.runtime_rag_resources.rag_service._llm_client.model,
        )
    )

    @app.middleware("http")
    async def http(request, call_next):
        t = time.perf_counter()
        response = await call_next(request)
        record(
            dict(
                kind="http",
                method=request.method,
                path=request.url.path,
                seconds=time.perf_counter() - t,
                status=response.status_code,
            )
        )
        return response

    return app
