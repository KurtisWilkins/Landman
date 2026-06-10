"""S3-compatible object storage client (source files, photos, feedback screenshots).

Feedback screenshots may contain deal financials — they are stored in access-scoped
buckets and their contents are never logged (CLAUDE.md; [DECISION] D-32 for redaction).
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, cast

import boto3

from .config import settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


@lru_cache
def get_s3_client() -> S3Client:
    """Return a configured boto3 S3 client. Works with AWS, R2, or MinIO via endpoint."""
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint or None,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
    )


def presign_put(key: str, content_type: str, expires_in: int = 900) -> str:
    """Presigned upload URL (size/type limits enforced at the API boundary)."""
    url = get_s3_client().generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.s3_bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=expires_in,
    )
    return cast(str, url)


def presign_get(key: str, expires_in: int = 900) -> str:
    """Presigned, time-limited download URL for access-scoped objects."""
    url = get_s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=expires_in,
    )
    return cast(str, url)
