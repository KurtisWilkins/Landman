# 0010. Object storage: Azure Blob behind an s3proxy gateway

Date: 2026-06-11
Status: Accepted

## Context

The app's storage client is **S3-API** (boto3 + `S3_ENDPOINT`): it stores source files, gallery
photos, and feedback screenshots, and hands the browser **presigned PUT/GET URLs** for direct
upload/download. ADR-0004 puts production on Azure. Azure Blob, however, does **not** speak the
S3 API natively, so an S3-native bucket (Cloudflare R2 / AWS S3) or an S3-gateway in front of
Blob is required.

The decision (2026-06-11): keep object storage **inside Azure** for single-vendor /
data-residency reasons.

## Decision

**Azure Blob Storage fronted by an `s3proxy` gateway.** s3proxy (`andrewgaul/s3proxy`,
actively maintained) exposes an S3 API and translates to Azure Blob via Apache jclouds. The app
points `S3_ENDPOINT` at the gateway; the gateway holds the Blob account key.

- **Not MinIO.** MinIO **removed its Azure gateway mode in 2022**, so it is not an option for a
  new deployment; s3proxy is the current, maintained equivalent.
- The gateway runs as a **public-ingress** Container App. Presigned URLs are used straight from
  the browser, so the endpoint must be reachable by clients; the presigned **signature** (the
  s3proxy identity/credential) is what authorizes each request — the Blob key never leaves the
  gateway.
- The boto3 client uses **path-style addressing** whenever `S3_ENDPOINT` is set
  (`endpoint/bucket/key`); virtual-host style does not resolve against a gateway and breaks
  presigned URLs (`core/storage.py`).

## Consequences

- Single-vendor (Azure) storage; the app stays S3-API and portable — swapping to R2/S3 later is
  just `S3_ENDPOINT` + credentials, no code change.
- Operational cost: one more container (the gateway) to run, patch, and scale.
- **CORS:** the gateway must allow the web origin so browser presigned PUT/GET succeed.
- Feedback screenshots may contain deal financials — Blob container stays access-scoped and its
  contents are never logged (CLAUDE.md; redaction `[DECISION]` D-32 still open).
- Provisioned by `scripts/provision-azure.sh`; see docs/DEPLOYMENT.md §2.2.
