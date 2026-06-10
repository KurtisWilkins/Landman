"""FastAPI application factory."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .api import api_router
from .core.config import settings
from .core.correlation import CorrelationIdMiddleware
from .core.logging import configure_logging, get_logger
from .core.sentry import init_sentry
from .schemas.common import ErrorResponse

log = get_logger("api")

# Generic HTTP status → error code (used when a handler raised a bare HTTPException).
_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    500: "internal_error",
    501: "not_implemented",
}

# The structured error envelope (CLAUDE.md) is documented on every operation so the
# frontend can rely on it; this also registers ErrorResponse in the OpenAPI components.
_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorResponse} for code in (400, 401, 403, 404, 422, 500, 501)
}


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http_exc(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail
        # Endpoints that already raised the structured envelope pass it through verbatim.
        if isinstance(detail, dict) and "error" in detail:
            payload = detail
        else:
            payload = {
                "error": {
                    "code": _STATUS_CODES.get(exc.status_code, "error"),
                    "message": str(detail),
                }
            }
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(RequestValidationError)
    async def _validation_exc(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed.",
                    "detail": {"errors": jsonable_encoder(exc.errors())},
                }
            },
        )


def create_app() -> FastAPI:
    configure_logging(level="INFO" if settings.is_production else "DEBUG")
    init_sentry()

    app = FastAPI(
        title="RJourney Acquisitions Platform API",
        version=__version__,
        description=(
            "API surface per design doc §9. Phase-0 endpoints are typed contract stubs; "
            "domain logic lands in Phases 1–4."
        ),
    )

    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_base_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__, "env": settings.app_env}

    _register_exception_handlers(app)
    app.include_router(api_router, responses=_ERROR_RESPONSES)
    log.info("api.startup", version=__version__, env=settings.app_env)
    return app


app = create_app()
