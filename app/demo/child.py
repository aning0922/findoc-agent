"""Private, loopback-only per-generation runtime entrypoint (not the public gateway)."""
import asyncio
from contextlib import closing
import hmac
import inspect
import json
import os
from pathlib import Path
import sqlite3

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.demo.seed import sha256, verify_materialized


class InternalBoundary:
    """ASGI guard also covers docs, unknown/legacy routes, PDF and SSE."""
    def __init__(self, app, secret, generation, instance_id):
        self.app, self.secret = app, secret
        self.generation, self.instance_id = str(generation), instance_id

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        valid = scope["type"] == "http" and scope.get("client", ("",))[0] in ("127.0.0.1", "::1")
        for name, expected in ((b"x-findoc-internal-secret", self.secret),
                               (b"x-findoc-generation", self.generation),
                               (b"x-findoc-instance", self.instance_id)):
            valid = valid and hmac.compare_digest(headers.get(name, b""), expected.encode())
        if not valid:
            if scope["type"] == "websocket":
                return await send({"type": "websocket.close", "code": 1008})
            return await JSONResponse({"detail": {"code": "internal_auth_required", "message": "Forbidden"}}, 403)(scope, receive, send)
        return await self.app(scope, receive, send)


def fake_runtime(root: Path, generation: int) -> FastAPI:
    """Explicit FAKE child for HTTP/OS-process mechanism tests; no LLM/embedding claims."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    async def health():
        return {"status": "ok", "engine": "FAKE"}

    @app.get("/companies")
    async def companies():
        with closing(sqlite3.connect(root / "documents.db")) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute("SELECT * FROM companies ORDER BY company_id")]

    @app.post("/companies")
    async def create_company(request: Request):
        payload = await request.json()
        from app.companies.models import CompanyCreate
        from app.companies.sqlite_repository import SQLiteCompanyRepository
        company = SQLiteCompanyRepository(root / "documents.db").create("demo", CompanyCreate.model_validate(payload))
        return company.model_dump(mode="json")

    @app.get("/documents/{document_id}/file")
    async def fake_pdf(document_id: str, delay: float = 0):
        await asyncio.sleep(min(10, max(0, delay)))
        # Transport fixture only, deliberately not a financial PDF or PDF export acceptance.
        return Response(f"%PDF-FAKE-generation-{generation}".encode(), media_type="application/pdf")

    @app.post("/chat")
    async def chat(request: Request):
        payload = await request.json()
        delay = min(10, max(0, float(payload.get("delay", 0.2))))
        async def events():
            yield f"data: FAKE-start-generation-{generation}\n\n"
            await asyncio.sleep(delay)
            # Slow work belongs exclusively to this process/root, including after cancellation.
            (root / "fake-late-result.txt").write_text("FAKE late result")
            yield f"data: FAKE-late-generation-{generation}\n\n"
        return StreamingResponse(events(), media_type="text/event-stream")

    return app


def create_child_app():
    root = Path(os.environ["FINDOC_RUNTIME_ROOT"])
    if not root.is_absolute() or root.is_symlink():
        raise ValueError("Private child requires absolute isolated runtime root")
    generation = int(os.environ["DEMO_INTERNAL_GENERATION"])
    secret, instance = os.environ["DEMO_INTERNAL_SECRET"], os.environ["DEMO_INTERNAL_INSTANCE"]
    if generation < 1 or len(secret) < 32 or not instance:
        raise ValueError("Private child identity required")
    manifest_sha = os.environ["DEMO_INTERNAL_MANIFEST_SHA"]
    manifest_path = root / ".demo-manifest.json"
    if sha256(manifest_path) != manifest_sha:
        raise ValueError("Private child manifest identity mismatch")
    manifest = json.loads(manifest_path.read_text())
    mode = os.environ.get("DEMO_CHILD_MODE", "real")
    metadata_bound = False
    if mode == "fake":
        app = fake_runtime(root, generation)
    elif mode == "real":
        from app.api.runtime_factory import create_runtime_app
        requested = {"showcase_generation": generation, "showcase_seed_version": manifest["seed_version"],
                     "showcase_preset_task_ids": frozenset(manifest["preset_task_ids"])}
        signature = inspect.signature(create_runtime_app)
        supported = {k: v for k, v in requested.items() if k in signature.parameters}
        metadata_bound = len(supported) == len(requested)
        app = create_runtime_app(root, **supported)
    else:
        raise ValueError("DEMO_CHILD_MODE must be real or fake")
    # Probe after true runtime construction/migrations/index warmup; no provider generation call.
    probe = verify_materialized(root, manifest)
    vectors = []
    if mode == "real":
        from app.api.runtime_factory import RUNTIME_COLLECTION_NAME
        client = app.state.runtime_rag_resources.milvus_client
        requirements = manifest.get("vector_indexes", []) or [{"collection": RUNTIME_COLLECTION_NAME, "rows": 0}]
        for spec in requirements:
            if not client.has_collection(collection_name=spec["collection"]):
                raise ValueError("Runtime vector collection missing")
            actual = int(client.get_collection_stats(collection_name=spec["collection"])["row_count"])
            if actual != spec["rows"]:
                raise ValueError("Runtime vector collection count mismatch")
            vectors.append({"collection": spec["collection"], "rows": actual})

    @app.get("/internal/demo-readiness")
    async def readiness():
        return {"schema_version": "demo-child-readiness-v1", "ready": True,
                "instance_id": instance, "generation": generation, "manifest_sha256": manifest_sha,
                "seed_version": manifest["seed_version"], "engine": mode,
                "showcase_metadata_bound": metadata_bound, **probe, "vector_indexes": vectors}

    # Wrapper rather than app.middleware: all framework errors and route aliases remain guarded.
    return InternalBoundary(app, secret, generation, instance)
