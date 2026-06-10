"""Auth endpoints (§9)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ._stub import not_implemented

router = APIRouter(tags=["auth"])


class OidcCallback(BaseModel):
    code: str
    state: str | None = None


class Session(BaseModel):
    user_id: str
    email: str
    role: str


@router.post("/auth/callback", response_model=Session)
async def auth_callback(_body: OidcCallback) -> Session:
    """Exchange an OIDC code for a session (Entra ID / external). TODO(decision: §14 C-16)."""
    not_implemented("POST /auth/callback", phase="Phase 0+ (auth)")
