# 0004. Cloud provider / region and deal-data constraints (C-17)

Date: 2026-06-10
Status: Proposed

## Context

§14 **C-17** (Phase-0 blocker): cloud provider/region and any environment constraint on
deal data. §13 notes Azure aligns with Entra; AWS is also acceptable. Object storage is
S3-compatible either way.

## Decision

**Unresolved — pending CTO.** Phase 0 targets a provider-agnostic local stack
(docker-compose: Postgres+pgvector, Redis, MinIO) and an S3-compatible storage client that
works against AWS S3, Cloudflare R2, or MinIO via an endpoint setting. No
provider-specific service is baked in. Hosting choice is recorded here once made.

## Consequences

- Local development is unblocked and portable.
- Production hosting, region/data-residency, and managed-service choices (Postgres, Redis,
  object storage, secrets) are deferred to C-17 and related items (C-21, C-30).
