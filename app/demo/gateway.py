"""Fixed-handle HTTP gateway with durable attempt reservation and response fences."""
import asyncio
from contextlib import closing
import hashlib
import json
import re
import sqlite3
from uuid import UUID

from fastapi import HTTPException, Request
import httpx
from starlette.responses import Response, StreamingResponse

from app.demo.controller import reject, token_hash
from app.demo.policy import mutation_for

MAX_BYTES = 24 * 1024 * 1024
RESPONSE_HEADERS = {"content-type", "content-disposition", "content-range", "accept-ranges", "etag",
                    "x-report-id", "x-report-revision", "x-report-payload-sha256", "x-markdown-sha256",
                    "x-report-eligibility", "x-markdown-renderer"}
REQUEST_HEADERS = {"content-type", "accept", "range", "if-range", "if-none-match", "last-event-id"}


class GatewayLedger:
    """Business response cache stays in its generation, never in the control DB."""
    def __init__(self, root):
        self.path = root / ".demo-gateway.db"
        with closing(self.connect()) as db:
            db.execute("CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, owner TEXT NOT NULL, "
                       "digest TEXT NOT NULL,state TEXT NOT NULL,status INTEGER,headers TEXT,body BLOB)")
            db.commit()
        self.path.chmod(0o600)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def reserve(self, operation_id, owner, digest):
        with closing(self.connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
            if row:
                if row["owner"] != owner or row["digest"] != digest:
                    reject(409, "operation_conflict")
                if row["state"] != "completed":
                    reject(409, "operation_unknown", operation_id=operation_id)
                return dict(row)
            db.execute("INSERT INTO operations VALUES (?,?,?,'unknown',NULL,NULL,NULL)",
                       (operation_id, owner, digest))
            db.commit()
        return None

    def complete(self, operation_id, status, headers, body):
        with closing(self.connect()) as db:
            db.execute("UPDATE operations SET state='completed',status=?,headers=?,body=? WHERE id=?",
                       (status, json.dumps(headers), body, operation_id))
            db.commit()

    def state(self, operation_id, owner):
        with closing(self.connect()) as db:
            row = db.execute("SELECT state FROM operations WHERE id=? AND owner=?", (operation_id, owner)).fetchone()
        if not row:
            reject(404, "operation_not_found")
        return {"operation_id": operation_id, "state": row["state"]}


class FencedResponse:
    """Last check at ASGI emission; already-started revoked responses terminate empty."""
    def __init__(self, response, controller, token, generation):
        self.response, self.controller, self.token, self.generation = response, controller, token, generation
        self.background = None

    async def __call__(self, scope, receive, send):
        started, blocked = False, False

        async def fenced_send(message):
            nonlocal started, blocked
            if blocked:
                return
            try:
                self.controller.fence(self.token, self.generation)
            except HTTPException as exc:
                blocked = True
                if not started:
                    from starlette.responses import JSONResponse
                    await JSONResponse({"detail": exc.detail}, exc.status_code,
                                       headers={"Cache-Control": "no-store"})(scope, receive, send)
                else:
                    await send({"type": "http.response.body", "body": b"", "more_body": False})
                return
            if message["type"] == "http.response.start":
                started = True
            await send(message)
        await self.response(scope, receive, fenced_send)


async def bounded_body(request):
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BYTES:
            reject(413, "request_too_large")
        chunks.append(chunk)
    return b"".join(chunks)


def operation_key(request, body, rule):
    header = request.headers.get("x-operation-id")
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    value = None
    if content_type == "application/json":
        try:
            payload = json.loads(body)
            value = payload.get("operation_id") if isinstance(payload, dict) else None
        except (ValueError, UnicodeError):
            reject(422, "invalid_json")
    if header and value and header != value:
        reject(409, "operation_conflict")
    operation_id = value or header
    try:
        if not isinstance(operation_id, str) or str(UUID(operation_id)) != operation_id:
            raise ValueError()
    except ValueError:
        reject(422, "operation_id_required")
    if value and not rule.native_operation:
        # Only the gateway envelope field is consumed; legacy strict body remains intact.
        payload.pop("operation_id")
        body = json.dumps(payload, separators=(",", ":")).encode()
    return operation_id, body


async def proxy(request: Request, controller):
    path = request.url.path
    if path.startswith(("/demo/", "/internal/")) or path in ("/demo", "/internal"):
        reject(404, "route_not_found")
    # Reject ambiguous paths before a downstream router can normalize into another route.
    if "//" in path or "\\" in path or re.search(r"%|[\x00-\x1f\x7f]", path) or any(
            segment in (".", "..") for segment in path.split("/")):
        reject(400, "invalid_path")
    mutating = request.method not in ("GET", "HEAD")
    rule = mutation_for(request.method, path) if mutating else None
    # Authenticate before revealing route registration or owner requirements.
    handle = controller.capture(request.cookies.get("findoc_demo"), owner=bool(rule and rule.owner))
    token, generation = request.cookies.get("findoc_demo"), handle.generation
    if mutating and rule is None:
        reject(403, "mutation_not_allowed")
    body = await bounded_body(request)
    controller.fence(token, generation)
    controller.capture(token, owner=bool(rule and rule.owner))
    ledger, operation_id = None, None
    if mutating:
        operation_id, upstream_body = operation_key(request, body, rule)
        digest = hashlib.sha256(request.method.encode() + b"\0" + path.encode() + b"\0" +
                                request.url.query.encode() + b"\0" + body).hexdigest()
        controller.reserve_gateway(operation_id, token, generation, digest)
        ledger = GatewayLedger(handle.root)
        cached = ledger.reserve(operation_id, token_hash(token), digest)
        if cached:
            return fenced(Response(cached["body"], cached["status"], headers=json.loads(cached["headers"])),
                          controller, token, generation)
        body = upstream_body
    headers = {key: value for key, value in request.headers.items() if key.lower() in REQUEST_HEADERS}
    # Neither browser Authorization/Cookie/Host nor browser internal headers reach runtime.
    headers.update({"X-Findoc-Internal-Secret": handle.secret,
                    "X-Findoc-Generation": str(generation), "X-Findoc-Instance": handle.instance_id})
    # handle.client is created once for the captured loopback endpoint, with redirects disabled.
    upstream = None
    try:
        url = handle.client.base_url.copy_with(path=path, query=request.url.query.encode())
        upstream_request = handle.client.build_request(request.method, url, headers=headers, content=body)
        controller.fence(token, generation)
        controller.capture(token, owner=bool(rule and rule.owner))
        upstream = await handle.client.send(upstream_request, stream=True, follow_redirects=False)
        controller.fence(token, generation)
        if 300 <= upstream.status_code < 400:
            reject(502, "upstream_redirect_forbidden")
        public_headers = {k: v for k, v in upstream.headers.items() if k in RESPONSE_HEADERS}
        public_headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
        is_sse = upstream.headers.get("content-type", "").startswith("text/event-stream")
        if is_sse:
            response = StreamingResponse(stream_events(upstream, controller, token, generation,
                                                       ledger, operation_id, public_headers),
                                         status_code=upstream.status_code, headers=public_headers)
            upstream = None  # generator owns closing, including downstream disconnect.
            return fenced(response, controller, token, generation)
        content = bytearray()
        async for chunk in guarded_chunks(upstream, controller, token, generation):
            content.extend(chunk)
            if len(content) > MAX_BYTES:
                reject(502, "response_too_large")
        controller.fence(token, generation)
        if ledger:
            ledger.complete(operation_id, upstream.status_code, public_headers, bytes(content))
            controller.complete_gateway(operation_id)
        return fenced(Response(bytes(content), upstream.status_code, headers=public_headers), controller, token, generation)
    except httpx.HTTPError:
        controller.runtime_failed(generation)
        reject(503, "runtime_unavailable")
    finally:
        if upstream:
            await upstream.aclose()


def fenced(response, controller, token, generation):
    # A Response subclass keeps FastAPI from attempting to JSON-encode this wrapper.
    return GuardedResponse(response, controller, token, generation)


class GuardedResponse(Response):
    def __init__(self, response, controller, token, generation):
        super().__init__(b"", status_code=response.status_code)
        self.raw_headers = response.raw_headers
        self.guard = FencedResponse(response, controller, token, generation)

    async def __call__(self, scope, receive, send):
        await self.guard(scope, receive, send)


async def guarded_chunks(upstream, controller, token, generation):
    iterator = upstream.aiter_bytes().__aiter__()
    next_chunk = asyncio.create_task(anext(iterator))
    try:
        while True:
            controller.fence(token, generation)
            done, _ = await asyncio.wait({next_chunk}, timeout=0.2)
            if not done:
                continue
            try:
                chunk = next_chunk.result()
            except StopAsyncIteration:
                break
            controller.fence(token, generation)
            yield chunk
            next_chunk = asyncio.create_task(anext(iterator))
    finally:
        if not next_chunk.done():
            next_chunk.cancel()
        await asyncio.gather(next_chunk, return_exceptions=True)


async def stream_events(upstream, controller, token, generation, ledger, operation_id, headers):
    pending, transcript = b"", bytearray()
    try:
        async for chunk in guarded_chunks(upstream, controller, token, generation):
            pending = (pending + chunk).replace(b"\r\n", b"\n")
            if len(pending) > MAX_BYTES:
                return
            while b"\n\n" in pending:
                event, pending = pending.split(b"\n\n", 1)
                controller.fence(token, generation)
                frame = event + b"\n\n"
                transcript.extend(frame)
                if len(transcript) > MAX_BYTES:
                    return
                yield frame
        controller.fence(token, generation)
        if pending:
            return  # Incomplete SSE frame: retain UNKNOWN rather than certify a truncated stream.
        if ledger:
            ledger.complete(operation_id, upstream.status_code, headers, bytes(transcript))
            controller.complete_gateway(operation_id)
    except httpx.HTTPError:
        controller.runtime_failed(generation)
        return
    except HTTPException:
        # Revocation discards data; never emit a final late result or retry provider work.
        return
    finally:
        await upstream.aclose()
