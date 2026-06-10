"""GitHub seam for agentic dispatch (§5.12).

A small ``GitHubClient`` protocol keeps the dispatch logic testable (the service takes a
client; tests inject a fake). The concrete HTTP client targets the GitHub REST API.

Auth/repo ownership is an unresolved decision (§14 C-28/C-29): we never guess credentials.
``build_github_client`` returns a configured client only when creds are present, else None,
so the dispatch endpoint reports "not configured" rather than silently failing.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import httpx

from ..core.config import settings


def verify_signature(body: bytes, signature_header: str | None) -> bool:
    """Verify a GitHub ``X-Hub-Signature-256`` header against the configured secret.

    Returns False when the secret is unset (we cannot verify, so we must not trust) or the
    signature is missing/incorrect. Uses a constant-time comparison.
    """
    secret = settings.github_webhook_secret
    if not secret or not signature_header:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


@dataclass(frozen=True)
class CreatedIssue:
    number: int
    url: str  # html_url


@runtime_checkable
class GitHubClient(Protocol):
    async def create_issue(self, *, title: str, body: str, labels: list[str]) -> CreatedIssue: ...


class HttpGitHubClient:
    """Creates issues via the GitHub REST API using a bearer token."""

    def __init__(self, repo: str, token: str, base_url: str = "https://api.github.com") -> None:
        self._repo = repo
        self._token = token
        self._base_url = base_url.rstrip("/")

    async def create_issue(self, *, title: str, body: str, labels: list[str]) -> CreatedIssue:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._base_url}/repos/{self._repo}/issues",
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                json={"title": title, "body": body, "labels": labels},
            )
        resp.raise_for_status()
        data = resp.json()
        return CreatedIssue(number=int(data["number"]), url=str(data["html_url"]))


def build_github_client() -> GitHubClient | None:
    """Return a configured client, or None when GitHub creds are unresolved (C-28/C-29).

    TODO(decision: §14 C-28/C-29): finalize repo + token/app auth ownership. We read a
    token from ``github_app_private_key`` as the bearer placeholder; swap for the App
    installation-token flow once the decision lands.
    """
    token = settings.github_app_private_key
    if not settings.github_repo or not token:
        return None
    return HttpGitHubClient(repo=settings.github_repo, token=token)
