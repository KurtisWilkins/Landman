# 0011. Authentication delivery via Container Apps EasyAuth (refines C-16)

Date: 2026-06-17
Status: Accepted

## Context

ADR-0003 resolved **C-16**: Microsoft Entra ID for internal SSO. It assumed the app would
implement OIDC discovery/JWKS verification in-process (`OIDC_*`). Deploying on Azure Container
Apps (ADR-0004) offers a simpler, lower-risk path: the platform's built-in authentication
("EasyAuth") terminates the Entra OIDC flow at the edge, in front of the container, so the
application never handles tokens, JWKS, or callbacks itself.

The web app is the only public ingress; the API is internal and reached via the web app's nginx
`/api` proxy. We need the API to know the authenticated user without trusting a spoofable header.

## Decision

Authenticate at the **edge with Container Apps EasyAuth** (Entra, single-tenant; external
partners may be invited as Entra guests). This **refines the C-16 implementation** in ADR-0003
(provider is still Entra) — in-process `OIDC_*` is not used for internal users.

- EasyAuth on the **web** app requires authentication and injects `X-MS-CLIENT-PRINCIPAL-NAME`
  (the user's email/UPN); it strips any client-supplied `X-MS-CLIENT-PRINCIPAL-*` headers.
- **nginx** (`/api`) forwards that email to the API and stamps `X-Proxy-Auth: <PROXY_AUTH_SECRET>`,
  overwriting any client value so it cannot be forged.
- The **API** trusts `X-MS-CLIENT-PRINCIPAL-NAME` **only** when `X-Proxy-Auth` matches the shared
  secret (constant-time compare). It maps the email to a role from config
  (`ADMIN_EMAILS`/`EXECUTIVE_EMAILS`/`EQUITY_PARTNER_EMAILS`/`ANALYST_EMAILS`); RBAC stays
  server-side. Unconfigured secret ⇒ `501 auth_not_configured` (never mint an identity);
  bad/missing secret ⇒ `401`; authenticated-but-unprovisioned email ⇒ `403`.

The shared secret is the trust boundary because the API has its own ingress: an identity header
alone is never trusted. The model depends on EasyAuth running in **require-authentication** mode
so unauthenticated requests can't reach nginx carrying a forged principal.

## Consequences

- No OIDC/JWKS code to maintain; token lifecycle, refresh, and login UI are the platform's.
- `PROXY_AUTH_SECRET` must be set identically on the web and api apps; rotating it is a two-app
  update. Role membership is config-driven (no redeploy to add a user).
- The local **dev shim** (`Bearer dev <role>`) is unchanged and is refused in production.
- The external PE-partner path (magic-link, ADR-0003) is still future work; guests on the tenant
  can use the same edge login in the interim.
- The in-process `OIDC_*` settings remain for a possible future non-EasyAuth deployment but are
  inert here.
