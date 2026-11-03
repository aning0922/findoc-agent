"""Public demo HTTP boundary. Legacy app is never mounted in this process."""
from contextlib import asynccontextmanager
from collections import defaultdict, deque
import time
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.demo.config import DemoConfig
from app.demo.controller import DemoController
from app.demo.gateway import proxy

COOKIE = "findoc_demo"
PENDING_COOKIE = "findoc_demo_pending"


class Operation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    @field_validator("*", mode="before", check_fields=False)
    @classmethod
    def strict_confirmation(cls, value, info):
        if info.field_name == "confirm" and value is not True:
            raise ValueError("Explicit true required")
        return value

    operation_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class Login(Operation):
    username: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=1024)


class Claim(Operation):
    attempt_operation_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class Takeover(Login):
    owner_password: str = Field(min_length=1, max_length=1024)
    confirm: Literal[True]
    expected_generation: int = Field(ge=1)


class OwnerAuthorize(Operation):
    owner_password: str = Field(min_length=1, max_length=1024)
    confirm: Literal[True]


def create_demo_app(config: DemoConfig, manager, *, cookie_name=COOKIE) -> FastAPI:
    if cookie_name not in (COOKIE, "findoc_demo_cplus"):
        raise ValueError("unsupported_demo_cookie_namespace")
    controller = DemoController(config, manager)
    controller.cookie_name = cookie_name
    active_cookie, pending_cookie = cookie_name, cookie_name + "_pending"

    @asynccontextmanager
    async def lifespan(app):
        await controller.start()
        try:
            yield
        finally:
            await controller.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.demo_controller = controller
    attempts = defaultdict(deque)

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        # Pydantic's default errors echo inputs, including passwords.
        return JSONResponse({"detail": {"code": "invalid_request", "message": "Invalid request fields"}}, 422)

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        if request.method not in ("GET", "HEAD"):
            if request.headers.get("origin") not in config.origins:
                return JSONResponse({"detail": {"code": "origin_forbidden", "message": "Origin forbidden"}}, 403,
                                    headers={"Cache-Control": "no-store"})
            content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
            if content_type not in ("application/json", "multipart/form-data") or (
                request.url.path.startswith("/demo/") and content_type != "application/json"
            ):
                return JSONResponse({"detail": {"code": "content_type_required", "message": "Invalid content type"}}, 415,
                                    headers={"Cache-Control": "no-store"})
        if request.url.path in ("/demo/login", "/demo/takeover", "/demo/owner-authorize"):
            now = time.monotonic()
            key = request.client.host if request.client else "unknown"
            # Never trust browser X-Forwarded-For as a rate-limit identity.
            if len(attempts) > 2048:
                for old_key in list(attempts):
                    if not attempts[old_key] or attempts[old_key][-1] < now - 60:
                        del attempts[old_key]
                if len(attempts) > 2048:
                    return JSONResponse({"detail": {"code": "rate_limited", "message": "Try later"}}, 429,
                                        headers={"Cache-Control": "no-store"})
            bucket = attempts[key]
            while bucket and bucket[0] <= now - 60:
                bucket.popleft()
            if len(bucket) >= 20:
                return JSONResponse({"detail": {"code": "rate_limited", "message": "Try later"}}, 429,
                                    headers={"Cache-Control": "no-store"})
            bucket.append(now)
        if request.method == "POST" and request.url.path.startswith("/demo/"):
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 16384:
                    return JSONResponse({"detail": {"code": "request_too_large", "message": "Request too large"}}, 413,
                                        headers={"Cache-Control": "no-store"})
            # Starlette's cached Request replays this bounded body to the endpoint parser.
            request._body = bytes(body)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    def response(body, status=200, *, active=None, pending=None):
        result = JSONResponse(body, status)
        if active:
            result.set_cookie(active_cookie, active, httponly=True, secure=config.secure_cookie,
                              samesite="strict", max_age=config.ttl_minutes * 60, path="/")
        if pending:
            result.set_cookie(pending_cookie, pending, httponly=True, secure=config.secure_cookie,
                              samesite="strict", max_age=config.pending_seconds, path="/")
        return result

    def cookies(request):
        return request.cookies.get(active_cookie), request.cookies.get(pending_cookie)

    @app.get("/demo/status")
    async def status():
        return controller.status()

    @app.post("/demo/login")
    async def login(payload: Login, request: Request):
        code, body, pending = controller.login(payload.model_dump(), *cookies(request))
        return response(body, code, pending=pending)

    @app.post("/demo/takeover")
    async def takeover(payload: Takeover, request: Request):
        code, body, pending = controller.takeover(payload.model_dump(), *cookies(request))
        return response(body, code, pending=pending)

    @app.post("/demo/owner-authorize")
    async def owner_authorize(payload: OwnerAuthorize, request: Request):
        return controller.owner_authorize(payload.model_dump(), request.cookies.get(active_cookie))

    @app.get("/demo/session")
    async def session(request: Request):
        return controller.session(request.cookies.get(active_cookie))

    @app.post("/demo/claim")
    async def claim(payload: Claim, request: Request):
        body, active = controller.claim(payload.operation_id, payload.attempt_operation_id, *cookies(request))
        return response(body, active=active)

    @app.post("/demo/logout")
    async def logout(payload: Operation, request: Request):
        result = response(controller.logout(payload.operation_id, request.cookies.get(active_cookie)))
        result.delete_cookie(active_cookie, path="/", secure=config.secure_cookie, httponly=True, samesite="strict")
        result.delete_cookie(pending_cookie, path="/", secure=config.secure_cookie, httponly=True, samesite="strict")
        return result

    @app.get("/demo/operations/{operation_id}")
    async def operation(operation_id: UUID, request: Request):
        return controller.operation(str(operation_id), *cookies(request))

    @app.get("/demo/resets/{reset_id}")
    async def reset(reset_id: UUID, request: Request):
        return controller.reset_status(str(reset_id), *cookies(request))

    @app.api_route("/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    async def business(request: Request, path: str):
        return await proxy(request, controller)

    return app
