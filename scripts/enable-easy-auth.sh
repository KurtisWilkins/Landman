#!/usr/bin/env bash
# One-time: turn on Microsoft (Entra) sign-in for the public web app via Azure Container Apps
# Easy Auth (ADR-0011, design-doc C-16 internal path). Azure verifies the login and injects the
# user's identity; the app then authorizes that identity against ADMIN_EMAILS/ANALYST_EMAILS
# (provision-azure.sh) — anyone not on a list is denied. Re-runnable.
#
#   ./scripts/enable-easy-auth.sh
#
# Requires: az logged in, and rights to create an Entra app registration (Application Developer
# or higher). Run AFTER provision-azure.sh (the web app must exist).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ -f "$here/deploy.env" ]] && source "$here/deploy.env"
: "${RG:=rjacq-prod}"
: "${WEBAPP:=rjacq-web}"
: "${ENTRA_APP_NAME:=RJourney Acquisitions}"

say() { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }

web_fqdn="$(az containerapp show -n "$WEBAPP" -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)"
[[ -n "$web_fqdn" ]] || { echo "Could not resolve $WEBAPP ingress FQDN — run provision-azure.sh first"; exit 1; }
redirect="https://${web_fqdn}/.auth/login/aad/callback"
tenant_id="$(az account show --query tenantId -o tsv)"
issuer="https://login.microsoftonline.com/${tenant_id}/v2.0"

# ── 1. Entra app registration (single-tenant; idempotent by display name) ────────────────────
say "Entra app registration ($ENTRA_APP_NAME)"
app_id="$(az ad app list --display-name "$ENTRA_APP_NAME" --query '[0].appId' -o tsv 2>/dev/null || true)"
if [[ -z "$app_id" ]]; then
  app_id="$(az ad app create --display-name "$ENTRA_APP_NAME" \
    --sign-in-audience AzureADMyOrg --web-redirect-uris "$redirect" --query appId -o tsv)"
  echo "  created app $app_id"
else
  az ad app update --id "$app_id" --web-redirect-uris "$redirect" -o none
  echo "  reused app $app_id (redirect refreshed)"
fi

# ── 2. Client secret for the confidential (server-side) Easy Auth client ─────────────────────
say "Client secret"
client_secret="$(az ad app credential reset --id "$app_id" --display-name easyauth \
  --years 2 --query password -o tsv)"

# ── 3. Configure Easy Auth on the web app: Microsoft provider + require authentication ───────
say "Container Apps Easy Auth on $WEBAPP"
az containerapp auth microsoft update -n "$WEBAPP" -g "$RG" \
  --client-id "$app_id" --client-secret "$client_secret" \
  --issuer "$issuer" --yes -o none
# Allow-anonymous mode: ACA's RedirectToLoginPage returns a bare 401 instead of redirecting
# (observed on this environment), so nginx performs the login redirect itself (web image).
# Easy Auth still verifies every session and injects/strips the identity headers, and the API
# still requires an allowlisted identity + the proxy secret — anonymity ends at the SPA shell.
az containerapp auth update -n "$WEBAPP" -g "$RG" \
  --unauthenticated-client-action AllowAnonymous \
  --redirect-provider azureactivedirectory -o none

cat <<EOF

✅ Microsoft sign-in enabled.
   Web:      https://${web_fqdn}        (visiting it now prompts a Microsoft login)
   Tenant:   ${tenant_id}
   App reg:  ${ENTRA_APP_NAME} (${app_id})
   Redirect: ${redirect}
   Sign out: https://${web_fqdn}/.auth/logout

Authorization is by allowlist (set ADMIN_EMAILS / ANALYST_EMAILS in scripts/deploy.env and
re-run provision-azure.sh): a signed-in user not on a list gets 403 from the API.
EOF
