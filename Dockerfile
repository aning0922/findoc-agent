FROM ghcr.io/astral-sh/uv:0.11.25 AS uv-tool

FROM python:3.12-slim-bookworm AS api
COPY --from=uv-tool /uv /usr/local/bin/uv
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-default-groups --no-install-project

RUN groupadd --gid 10001 findoc \
    && useradd --uid 10001 --gid findoc --create-home findoc \
    && mkdir -p /var/lib/findoc /var/cache/findoc \
    && chown findoc:findoc /var/lib/findoc /var/cache/findoc
COPY app/ ./app/
USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["/app/.venv/bin/uvicorn"]
CMD ["app.api.runtime_factory:create_isolated_runtime_app_from_env", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

FROM node:24-bookworm-slim AS web-build
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.28-alpine AS web
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=web-build /web/dist/ /usr/share/nginx/html/
EXPOSE 8080
