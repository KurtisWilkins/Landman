# Backend image (API + workers). Build context is the repo root so migrations/ and
# alembic.ini are available alongside the package.
# BASE_REGISTRY lets ACR builds pull the base image from our own registry (avoiding Docker Hub's
# anonymous pull-rate limit); empty default keeps local/CI builds on Docker Hub. Pass e.g.
# --build-arg BASE_REGISTRY=rjacqprod.azurecr.io/ once the base image is imported there.
ARG BASE_REGISTRY=
FROM ${BASE_REGISTRY}python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

# uv for fast, reproducible installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install dependencies first for layer caching.
COPY apps/api/pyproject.toml apps/api/README.md /app/apps/api/
COPY apps/api/rjacq /app/apps/api/rjacq
RUN uv pip install --system -e "/app/apps/api"

# Migrations live at the repo root.
COPY migrations /app/migrations
COPY alembic.ini /app/alembic.ini

EXPOSE 8000
# Behind nginx + Container Apps ingress: trust forwarded headers so request URLs/scheme are
# correct (HTTPS redirects, correlation IDs). Scaling is by replica, so one worker per replica.
CMD ["uvicorn", "rjacq.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
