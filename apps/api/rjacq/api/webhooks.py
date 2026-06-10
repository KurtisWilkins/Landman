"""Inbound webhooks (§9): deal email intake and GitHub issue/PR sync."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.db import get_session
from ..feedback import service as feedback_service
from ..feedback.github import verify_signature
from ._stub import not_implemented

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/email-intake", status_code=status.HTTP_202_ACCEPTED)
async def email_intake(_request: Request) -> dict[str, str]:
    """Inbound deal mail → create a deal in initial_uw + queue parse (§5.1).

    TODO(decision: §14 C-18): Graph mailbox vs. inbound-parse provider; verify signature.
    """
    not_implemented("POST /webhooks/email-intake", phase="Phase 1 (intake)")


@router.post("/webhooks/github", status_code=status.HTTP_202_ACCEPTED)
async def github_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Sync issue/PR state back to feedback_dispatch (§5.12.4). Verify HMAC signature."""
    # Headers are read off the request (not declared as typed params) so the §9 contract
    # signature for this inbound webhook stays unchanged.
    body = await request.body()
    x_github_event = request.headers.get("X-GitHub-Event")
    x_hub_signature_256 = request.headers.get("X-Hub-Signature-256")
    if not settings.github_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "webhook_not_configured",
                    "message": "GITHUB_WEBHOOK_SECRET is not set (decision C-28).",
                }
            },
        )
    if not verify_signature(body, x_hub_signature_256):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "bad_signature", "message": "Invalid signature."}},
        )

    payload = json.loads(body or b"{}")
    dispatch = await feedback_service.apply_webhook(
        session, event=x_github_event or "", payload=payload
    )
    await session.commit()
    return {"status": "synced" if dispatch is not None else "ignored"}
