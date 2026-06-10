"""Inbound webhooks (§9): deal email intake and GitHub issue/PR sync."""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from ._stub import not_implemented

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/email-intake", status_code=status.HTTP_202_ACCEPTED)
async def email_intake(_request: Request) -> dict[str, str]:
    """Inbound deal mail → create a deal in initial_uw + queue parse (§5.1).

    TODO(decision: §14 C-18): Graph mailbox vs. inbound-parse provider; verify signature.
    """
    not_implemented("POST /webhooks/email-intake", phase="Phase 1 (intake)")


@router.post("/webhooks/github", status_code=status.HTTP_202_ACCEPTED)
async def github_webhook(_request: Request) -> dict[str, str]:
    """Sync issue/PR state back to feedback_dispatch (§5.12.4). Verify HMAC signature."""
    not_implemented("POST /webhooks/github", phase="Phase 4 (feedback)")
