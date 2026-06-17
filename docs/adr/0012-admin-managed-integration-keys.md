# 0012. Admin-managed integration keys (encrypted DB override)

Date: 2026-06-17
Status: Accepted

## Context

Integration API keys (Anthropic, Voyage, demographics, comp sources) were settable only as
Container Apps secrets via `az`, which requires Cloud Shell access and a revision restart, and
gives operators no in-app visibility into which keys are missing. A live incident — the OM
extractor 401'ing on an `invalid x-api-key` — showed the friction: fixing a key meant a CLI
round-trip and a restart.

CLAUDE.md §Security says "secrets only via env/secret store." We want an admin to set/rotate the
**integration** keys from the app without weakening that posture for infrastructure secrets.

## Decision

Add an **admin-only, in-app integration-key store**:

- A new `app_secrets` table (operational config — **not** part of the §8 data contract) holds
  Fernet-encrypted values, a `last4` hint, and `updated_by`/`updated_at` provenance.
- Encryption key is derived from `SECRET_KEY` (`core/app_config.py`). Rotating `SECRET_KEY`
  invalidates stored values (they must be re-entered) — an accepted trade-off.
- **Effective value = admin DB override if set, else the environment/Container-Apps secret**,
  resolved at request time — so a key can be fixed or rotated with **no restart**. The existing
  env/secret mechanism keeps working; the DB store only fills or overrides.
- Scope is the **integration/API keys** only (`ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`,
  population/Census, Google/Yelp/TripAdvisor). Infra secrets (`DATABASE_URL`, `SECRET_KEY`,
  `REDIS_URL`, `PROXY_AUTH_SECRET`, S3) are deliberately **out of scope** — editing those from a
  UI could take the app down.
- **Admin-only** (`Capability.SETTINGS_MANAGE`, held only by `Role.ADMIN`), enforced server-side.
- **Write-only**: the API never returns a stored secret — only `configured`/`source`/`last4`.
  Set actions are logged by key name + actor, never the value.

## Consequences

- Operators fix/rotate integration keys from **Settings** in the app; no Cloud Shell, no restart.
- The secret-exposure surface widens slightly (an admin session can set keys), mitigated by:
  admin-only RBAC, encryption at rest, write-only/masked reads, and no value logging.
- This is a deliberate, scoped relaxation of "secrets only via env" for *integration* keys; infra
  secrets remain env/secret-store only.
- `app_secrets` is operational config outside the §8 contract; its migration is additive.
