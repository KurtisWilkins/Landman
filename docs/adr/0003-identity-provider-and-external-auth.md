# 0003. Identity provider + external auth method (C-16)

Date: 2026-06-10
Status: Accepted (resolved 2026-06-11)

## Context

§14 **C-16** (Phase-0 blocker): confirm Microsoft Entra ID for internal SSO (OIDC) and the
secondary method for external PE partners (email magic-link vs. password). §2/§10 require
RBAC enforced server-side.

## Decision

**Resolved 2026-06-11.** Internal SSO is **Microsoft Entra ID (OIDC)**; external PE partners
authenticate via **email magic-link** (no partner passwords to manage). RBAC stays server-side.

**Implementation update (2026-06-12, ADR-0011):** the internal Entra path is delivered via
**Azure Container Apps Easy Auth** (the platform verifies the token; the app authorizes the
injected identity against an email allowlist) rather than hand-rolled OIDC discovery/JWKS in the
app. The external magic-link flow remains to be built. `OIDC_*`/`EXTERNAL_AUTH_SECRET` stay as
seams for that external flow.

_Original Phase-0 analysis:_ Phase 0 builds the auth *skeleton* without committing to
provider specifics: a `Principal` model, an RBAC capability matrix for the four §2 roles,
and a `decode_token` seam that refuses to mint a trusted identity in production until
configured. OIDC issuer/JWKS and the external method are env placeholders
(`OIDC_*`, `EXTERNAL_AUTH_SECRET`) with `TODO(decision: §14 C-16)`.

## Consequences

- The full surface is RBAC-gated today (dev shim only for local testing).
- Real OIDC discovery/JWKS verification and the external flow are wired once C-16 lands.
- External-partner scoped-deal access depends on D-24 and is left as a `Principal` field.
