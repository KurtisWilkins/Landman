# 0011. Authentication: Container Apps Easy Auth + email allowlist (C-16 internal path)

Date: 2026-06-12
Status: Accepted

## Context

Design-doc §2/§10 calls for two sign-in paths, both left open under `[DECISION] C-16`:
internal RJourney users via **Microsoft Entra ID (OIDC)**, and external PE partners via a
secondary method (magic-link or password). `core/auth.py` shipped as a guarded skeleton:
`decode_token` returns `501 auth_not_configured` in production and refuses to mint an identity.

The platform is on Azure Container Apps (ADR-0004). To **start using the product** we need
internal sign-in now, without building (and owning the security of) a full OIDC code exchange,
JWKS verification, and session layer — and without resolving the still-open external-partner
method.

## Decision

**Resolve the internal half of C-16: Microsoft sign-in via Azure Container Apps Easy Auth, with
app-side authorization by an email allowlist.** The external PE-partner method stays open under
C-16.

- **Easy Auth on the public web app.** The platform's built-in AuthN/AuthZ middleware verifies
  the Entra token and, with `RequireAuthentication`, redirects unauthenticated browsers to the
  Microsoft login. The app handles **no** passwords, code exchange, or token validation.
- **Identity flows to the API as a header.** Easy Auth injects `X-MS-CLIENT-PRINCIPAL-NAME`;
  nginx forwards it (and a shared `X-Proxy-Auth` secret) to the internal API. The API trusts the
  identity **only** with the correct proxy secret, so the internal-ingress API cannot be handed a
  spoofed user from inside the Container Apps environment.
- **Authorization by allowlist (`role_for_email`).** `ADMIN_EMAILS` → `ADMIN`, `ANALYST_EMAILS`
  → `ANALYST`. An authenticated user on **no** list is denied (`403`) — never a default role
  (CLAUDE.md: never loosen RBAC). RBAC capability checks are unchanged and stay server-side.
- **Single-tenant** Entra app registration (`AzureADMyOrg`), provisioned by
  `scripts/enable-easy-auth.sh`.

## Consequences

- Fast, secure internal sign-in with minimal app code; token verification is the platform's job.
- The bearer `decode_token` path remains a **local-dev shim only** and still refuses to mint an
  identity in production.
- The external PE-partner path (C-16) is still unresolved; equity-partner deal-scoping (D-24)
  is unaffected and remains open.
- Trust of the injected header depends on the proxy secret + internal ingress; if the API is ever
  exposed or reached by another in-env component, the secret is the backstop. A later move to
  full app-level OIDC or mTLS would replace the header-trust model without changing `role_for_email`.
- Adds `scripts/enable-easy-auth.sh` and `ADMIN_EMAILS`/`ANALYST_EMAILS`/`PROXY_AUTH_SECRET`
  settings; see docs/DEPLOYMENT.md §2.6.
