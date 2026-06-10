"""ASGI middleware that assigns/propagates a correlation ID per request."""

from __future__ import annotations

import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .logging import correlation_id_var

HEADER = b"x-correlation-id"


class CorrelationIdMiddleware:
    """Read an inbound ``X-Correlation-ID`` or mint one; echo it on the response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        incoming = headers.get(HEADER)
        cid = incoming.decode() if incoming else uuid.uuid4().hex
        token = correlation_id_var.set(cid)

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                message["headers"].append((HEADER, cid.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            correlation_id_var.reset(token)
