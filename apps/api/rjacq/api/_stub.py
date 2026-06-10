"""Helper for Phase-0 stub endpoints."""

from __future__ import annotations

from typing import NoReturn

from fastapi import HTTPException, status


def not_implemented(endpoint: str, phase: str) -> NoReturn:
    """Raise a structured 501 so callers see a clear, contract-shaped error.

    The endpoint's typed ``response_model`` still populates the OpenAPI schema, which is
    what the frontend builds against; only the runtime body is deferred to ``phase``.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "error": {
                "code": "not_implemented",
                "message": f"{endpoint} is a Phase-0 contract stub.",
                "detail": {"implemented_in": phase},
            }
        },
    )
