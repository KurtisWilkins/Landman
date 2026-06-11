"""Storage-client config tests: gateway endpoints must use path-style addressing (ADR-0010)."""

from __future__ import annotations

from rjacq.core import storage
from rjacq.core.config import settings


def _fresh_client() -> object:
    storage.get_s3_client.cache_clear()
    return storage.get_s3_client()


def test_path_style_addressing_when_endpoint_set(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # An s3proxy/MinIO gateway only works with path-style URLs (endpoint/bucket/key).
    monkeypatch.setattr(settings, "s3_endpoint", "https://gw.example.com")
    client = _fresh_client()
    assert client.meta.config.s3["addressing_style"] == "path"


def test_default_addressing_when_no_endpoint(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # Plain AWS S3 (no custom endpoint) keeps boto3's default addressing.
    monkeypatch.setattr(settings, "s3_endpoint", None)
    client = _fresh_client()
    assert client.meta.config.s3 is None or "addressing_style" not in client.meta.config.s3
    storage.get_s3_client.cache_clear()
