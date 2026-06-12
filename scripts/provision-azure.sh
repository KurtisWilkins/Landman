#!/usr/bin/env bash
# Provision the RJourney Acquisitions production stack on Azure Container Apps.
#
# Idempotent-friendly: re-running updates/no-ops existing resources. Mirrors docs/DEPLOYMENT.md
# §2 and wires object storage as Azure Blob behind an s3proxy gateway (ADR-0010). Secrets and
# overrides come from scripts/deploy.env (gitignored) — copy scripts/deploy.env.example first.
#
#   cp scripts/deploy.env.example scripts/deploy.env && $EDITOR scripts/deploy.env
#   make deploy-provision           # or: ./scripts/provision-azure.sh
#
# Requires: az CLI logged in (az login or Azure Cloud Shell). Images build server-side via
# `az acr build` — no local Docker needed, so this runs straight from Cloud Shell.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$here/.." && pwd)"
[[ -f "$here/deploy.env" ]] && source "$here/deploy.env"

# ── Config (override in scripts/deploy.env) ────────────────────────────────────────────────
: "${RG:=rjacq-prod}"
: "${LOC:?set LOC, e.g. eastus2 (per data-residency policy, ADR-0004)}"
: "${ACR:=rjacqprod}"                 # 5-50 alphanumerics, globally unique
: "${ENVNAME:=rjacq-env}"
: "${PGSERVER:=rjacq-pg}"
: "${PGADMIN:=rjadmin}"
: "${PGPASSWORD:?set PGPASSWORD in scripts/deploy.env (strong, not committed)}"
: "${PGDB:=rjacq}"
: "${REDISNAME:=rjacq-redis}"
: "${STORAGEACCT:?set STORAGEACCT (3-24 lowercase alphanumerics, globally unique)}"
: "${BLOBCONTAINER:=rjacq-files}"
: "${S3PROXY_IDENTITY:?set S3PROXY_IDENTITY (the S3 access key the app will use)}"
: "${S3PROXY_CREDENTIAL:?set S3PROXY_CREDENTIAL (the S3 secret key the app will use)}"
: "${SECRET_KEY:?set SECRET_KEY (app session signing, strong random)}"
: "${WEB_ORIGIN:=}"                   # public web URL once known (CORS / OIDC). Optional first pass.
: "${ADMIN_EMAILS:=}"                 # comma-separated allowlist → ADMIN role (you, Rory) — C-16
: "${ANALYST_EMAILS:=}"               # comma-separated allowlist → ANALYST role
: "${PROXY_AUTH_SECRET:=}"            # shared web↔API secret (strong random); defense-in-depth
: "${IMAGE_TAG:=bootstrap}"
: "${SKIP_IMAGE_BUILD:=0}"
: "${PLACEHOLDER_IMAGE:=mcr.microsoft.com/k8se/quickstart:latest}"

acr_login="${ACR}.azurecr.io"
api_img="${acr_login}/rjacq-api:${IMAGE_TAG}"
web_img="${acr_login}/rjacq-web:${IMAGE_TAG}"

say() { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }

# ── 0. Preflight ───────────────────────────────────────────────────────────────────────────
say "Preflight"
command -v az >/dev/null || { echo "az CLI not found"; exit 1; }
az extension add --upgrade -n containerapp -y >/dev/null 2>&1 || true
az extension add --upgrade -n rdbms-connect -y >/dev/null 2>&1 || true
az account show >/dev/null || { echo "Run 'az login' first"; exit 1; }

# ── 1. Resource group + registry ─────────────────────────────────────────────────────────────
say "Resource group + ACR"
az group create -n "$RG" -l "$LOC" -o none
az acr create -n "$ACR" -g "$RG" --sku Standard --admin-enabled false -o none

# ── 2. PostgreSQL Flexible Server (+ pgvector, + automated backups/PITR) ─────────────────────
say "PostgreSQL Flexible Server ($PGSERVER)"
if ! az postgres flexible-server show -n "$PGSERVER" -g "$RG" -o none 2>/dev/null; then
  az postgres flexible-server create \
    -n "$PGSERVER" -g "$RG" -l "$LOC" --version 16 \
    --tier GeneralPurpose --sku-name Standard_D2ds_v5 --storage-size 64 \
    --admin-user "$PGADMIN" --admin-password "$PGPASSWORD" \
    --backup-retention 21 \
    --public-access 0.0.0.0 -o none   # Container Apps egress reaches it; tighten to a VNet later
fi
# Create the application database if absent. NB: `db create` takes --name for the database
# (the old `-d` flag was silently rejected, so the db was never created); guard via `db list`
# which only needs the server, sidestepping per-version show/create flag differences.
if ! az postgres flexible-server db list -g "$RG" -s "$PGSERVER" \
      --query "[?name=='$PGDB'] | length(@)" -o tsv 2>/dev/null | grep -qx 1; then
  az postgres flexible-server db create -g "$RG" -s "$PGSERVER" --name "$PGDB" -o none
fi
az postgres flexible-server parameter set -g "$RG" -s "$PGSERVER" \
  --name azure.extensions --value vector -o none
# Enable the extension in the database (needs rdbms-connect; safe to re-run).
az postgres flexible-server execute \
  -n "$PGSERVER" -u "$PGADMIN" -p "$PGPASSWORD" -d "$PGDB" \
  -q "CREATE EXTENSION IF NOT EXISTS vector;" -o none 2>/dev/null \
  || echo "  (!) Could not auto-create the vector extension — run CREATE EXTENSION vector; manually."

pg_host="$(az postgres flexible-server show -n "$PGSERVER" -g "$RG" --query fullyQualifiedDomainName -o tsv)"
# URL-encode the password: a strong password may contain @ : / ? # % & = + or a space, any of
# which would otherwise corrupt the DSN (e.g. '#' truncates it). quote(safe="") encodes them all.
pg_pass_enc="$(PGPASSWORD="$PGPASSWORD" python3 -c 'import os,urllib.parse;print(urllib.parse.quote(os.environ["PGPASSWORD"], safe=""))')"
DATABASE_URL="postgresql+psycopg://${PGADMIN}:${pg_pass_enc}@${pg_host}:5432/${PGDB}?sslmode=require"

# ── 3. Redis (internal Container App; classic Azure Cache for Redis is retiring) ──────────────
# The Arq job queue holds no durable business data (all deal data is in Postgres), so a small
# always-on Redis container is sufficient and cheap. Swap REDIS_URL to a managed Redis later
# with no app change. Ensure the Container Apps env exists first (the §5 step is then a no-op).
say "Redis ($REDISNAME, internal Container App)"
az containerapp env show -n "$ENVNAME" -g "$RG" -o none 2>/dev/null \
  || az containerapp env create -n "$ENVNAME" -g "$RG" -l "$LOC" -o none
if ! az containerapp show -n "$REDISNAME" -g "$RG" -o none 2>/dev/null; then
  az containerapp create -n "$REDISNAME" -g "$RG" --environment "$ENVNAME" \
    --image redis:7-alpine --ingress internal --transport tcp \
    --target-port 6379 --exposed-port 6379 \
    --min-replicas 1 --max-replicas 1 --cpu 0.5 --memory 1.0Gi -o none
fi
redis_fqdn="$(az containerapp show -n "$REDISNAME" -g "$RG" \
  --query properties.configuration.ingress.fqdn -o tsv)"
REDIS_URL="redis://${redis_fqdn}:6379/0"

# ── 4. Object storage: Azure Blob + s3proxy gateway (ADR-0010) ───────────────────────────────
say "Storage account + blob container ($STORAGEACCT/$BLOBCONTAINER)"
az storage account create -n "$STORAGEACCT" -g "$RG" -l "$LOC" \
  --sku Standard_LRS --kind StorageV2 --min-tls-version TLS1_2 -o none
blob_key="$(az storage account keys list -n "$STORAGEACCT" -g "$RG" --query '[0].value' -o tsv)"
az storage container create --name "$BLOBCONTAINER" \
  --account-name "$STORAGEACCT" --account-key "$blob_key" --auth-mode key -o none

# ── 5. Container Apps environment ────────────────────────────────────────────────────────────
say "Container Apps environment ($ENVNAME)"
if ! az containerapp env show -n "$ENVNAME" -g "$RG" -o none 2>/dev/null; then
  az containerapp env create -n "$ENVNAME" -g "$RG" -l "$LOC" -o none
fi

# ── 6. First images, built server-side in ACR (no local Docker; placeholder if skipped) ──────
if [[ "$SKIP_IMAGE_BUILD" == "1" ]]; then
  say "Skipping image build — apps come up on the placeholder; run the deploy pipeline to roll real images"
  api_img="$PLACEHOLDER_IMAGE"; web_img="$PLACEHOLDER_IMAGE"
else
  say "Building first images in ACR (tag: $IMAGE_TAG) — server-side, no local Docker"
  # Skip an image that's already in the registry, so a re-run resumes without re-pulling base
  # images from Docker Hub (anonymous pulls can hit rate limits across repeated builds).
  az acr repository show -n "$ACR" --image "rjacq-api:$IMAGE_TAG" -o none 2>/dev/null \
    || ( cd "$repo_root" && az acr build --registry "$ACR" -f apps/api/Dockerfile -t "rjacq-api:$IMAGE_TAG" . )
  az acr repository show -n "$ACR" --image "rjacq-web:$IMAGE_TAG" -o none 2>/dev/null \
    || ( cd "$repo_root/apps/web" && az acr build --registry "$ACR" -f Dockerfile.prod -t "rjacq-web:$IMAGE_TAG" . )
fi
# Let the apps pull from ACR via the env's managed identity (assigned below for real images).
registry_args=(); [[ "$SKIP_IMAGE_BUILD" == "1" ]] || registry_args=(--registry-server "$acr_login" --registry-identity system)

# ── 7. s3proxy gateway (public ingress — presigned URLs are used straight from the browser) ──
say "s3proxy gateway over Azure Blob"
# Self-heal a Failed app: an early run created this with a now-fixed bad image tag, and a plain
# "exists?" guard would skip it forever, leaving it stuck on the failed revision. Recreate it.
s3_state="$(az containerapp show -n rjacq-s3proxy -g "$RG" --query properties.provisioningState -o tsv 2>/dev/null || true)"
if [[ "$s3_state" == "Failed" ]]; then
  echo "  rjacq-s3proxy is in a Failed state — deleting to recreate cleanly"
  az containerapp delete -n rjacq-s3proxy -g "$RG" --yes -o none
  s3_state=""
fi
if [[ -z "$s3_state" ]]; then
  az containerapp create -n rjacq-s3proxy -g "$RG" --environment "$ENVNAME" \
    --image andrewgaul/s3proxy:latest --ingress external --target-port 80 \
    --min-replicas 1 --max-replicas 2 \
    --secrets blob-key="$blob_key" s3-cred="$S3PROXY_CREDENTIAL" \
    --env-vars \
      S3PROXY_AUTHORIZATION=aws-v2-or-v4 \
      "S3PROXY_IDENTITY=$S3PROXY_IDENTITY" \
      S3PROXY_CREDENTIAL=secretref:s3-cred \
      "S3PROXY_ENDPOINT=http://0.0.0.0:80" \
      JCLOUDS_PROVIDER=azureblob \
      "JCLOUDS_IDENTITY=$STORAGEACCT" \
      JCLOUDS_CREDENTIAL=secretref:blob-key \
      "JCLOUDS_ENDPOINT=https://${STORAGEACCT}.blob.core.windows.net" -o none
fi
s3_fqdn="$(az containerapp show -n rjacq-s3proxy -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)"
S3_ENDPOINT="https://${s3_fqdn}"

# ── 8. API (internal), worker (no ingress), web (public) ─────────────────────────────────────
say "API / worker / web container apps"
common_secrets=(database-url="$DATABASE_URL" redis-url="$REDIS_URL" secret-key="$SECRET_KEY" s3-secret="$S3PROXY_CREDENTIAL")
[[ -n "$PROXY_AUTH_SECRET" ]] && common_secrets+=(proxy-secret="$PROXY_AUTH_SECRET")
common_env=(DATABASE_URL=secretref:database-url REDIS_URL=secretref:redis-url APP_ENV=production)
s3_env=("S3_ENDPOINT=$S3_ENDPOINT" "S3_BUCKET=$BLOBCONTAINER" "S3_ACCESS_KEY_ID=$S3PROXY_IDENTITY" S3_SECRET_ACCESS_KEY=secretref:s3-secret)
# Easy Auth identity → roles (C-16, ADR-0011). Emails are plain env; the proxy secret is a secret.
auth_env=("ADMIN_EMAILS=$ADMIN_EMAILS" "ANALYST_EMAILS=$ANALYST_EMAILS")
[[ -n "$PROXY_AUTH_SECRET" ]] && auth_env+=(PROXY_AUTH_SECRET=secretref:proxy-secret)
web_proxy_env=(); [[ -n "$PROXY_AUTH_SECRET" ]] && web_proxy_env=(PROXY_AUTH_SECRET=secretref:proxy-secret)
web_secret_args=(); [[ -n "$PROXY_AUTH_SECRET" ]] && web_secret_args=(--secrets proxy-secret="$PROXY_AUTH_SECRET")

az containerapp create -n rjacq-api -g "$RG" --environment "$ENVNAME" "${registry_args[@]}" \
  --image "$api_img" --ingress internal --target-port 8000 --min-replicas 2 --max-replicas 6 \
  --secrets "${common_secrets[@]}" \
  --env-vars "${common_env[@]}" SECRET_KEY=secretref:secret-key "${s3_env[@]}" "${auth_env[@]}" ${WEB_ORIGIN:+WEB_BASE_URL=$WEB_ORIGIN APP_BASE_URL=$WEB_ORIGIN} \
  -o none 2>/dev/null || echo "  (rjacq-api exists — update its image via the deploy pipeline)"

az containerapp create -n rjacq-worker -g "$RG" --environment "$ENVNAME" "${registry_args[@]}" \
  --image "$api_img" --min-replicas 1 --max-replicas 3 \
  --command arq rjacq.core.queue.WorkerSettings \
  --secrets "${common_secrets[@]}" \
  --env-vars "${common_env[@]}" "${s3_env[@]}" \
  -o none 2>/dev/null || echo "  (rjacq-worker exists — update via the pipeline)"

api_fqdn="$(az containerapp show -n rjacq-api -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)"
az containerapp create -n rjacq-web -g "$RG" --environment "$ENVNAME" "${registry_args[@]}" \
  --image "$web_img" --ingress external --target-port 8080 --min-replicas 2 --max-replicas 4 \
  "${web_secret_args[@]}" --env-vars "API_URL=https://${api_fqdn}" "${web_proxy_env[@]}" \
  -o none 2>/dev/null || echo "  (rjacq-web exists — update via the pipeline)"

# Reconcile secrets on the (possibly pre-existing) apps so a re-run repairs a stale DATABASE_URL
# or REDIS_URL — `create` no-ops when the app exists and would not pick up a corrected value.
for app in rjacq-api rjacq-worker; do
  az containerapp secret set -n "$app" -g "$RG" \
    --secrets "${common_secrets[@]}" -o none
done
# Apply auth identity (allowlist + proxy secret) to the existing api/web and roll the freshly
# built image — `create` no-ops on an existing app, so a first enablement needs these updates.
if [[ "$SKIP_IMAGE_BUILD" != "1" ]]; then
  [[ -n "$PROXY_AUTH_SECRET" ]] && az containerapp secret set -n rjacq-web -g "$RG" \
    --secrets proxy-secret="$PROXY_AUTH_SECRET" -o none
  az containerapp update -n rjacq-api -g "$RG" --image "$api_img" --set-env-vars "${auth_env[@]}" -o none
  if [[ ${#web_proxy_env[@]} -gt 0 ]]; then
    az containerapp update -n rjacq-web -g "$RG" --image "$web_img" --set-env-vars "${web_proxy_env[@]}" -o none
  else
    az containerapp update -n rjacq-web -g "$RG" --image "$web_img" -o none
  fi
fi

# ── 9. Migration + seed jobs (the deploy pipeline updates their image + runs migrate each release)
say "Migration + seed jobs"
# create_job NAME -- CMD...  : if the job exists, just reconcile its database-url secret (so a
# re-run repairs a stale DSN); otherwise create it. Splitting on existence keeps real create
# errors visible instead of masking them as a bogus "already exists".
create_job() {
  local name="$1"; shift; [[ "$1" == "--" ]] && shift
  if az containerapp job show -n "$name" -g "$RG" -o none 2>/dev/null; then
    echo "  $name exists — reconciling database-url secret"
    az containerapp job secret set -n "$name" -g "$RG" --secrets database-url="$DATABASE_URL" -o none
  else
    az containerapp job create -n "$name" -g "$RG" --environment "$ENVNAME" "${registry_args[@]}" \
      --image "$api_img" --trigger-type Manual --replica-timeout 600 --replica-retry-limit 1 \
      --secrets database-url="$DATABASE_URL" \
      --env-vars DATABASE_URL=secretref:database-url \
      --command "$@" -o none
  fi
}

# run_job NAME : start an execution, wait for it to finish, fail loudly (with logs) if it doesn't
# Succeed. Polling beats `--wait`, which is flaky for jobs and hides the failing replica's logs.
run_job() {
  local name="$1" exec_name status i
  exec_name="$(az containerapp job start -n "$name" -g "$RG" --query name -o tsv)"
  echo "  started $name execution: $exec_name"
  for ((i=0; i<60; i++)); do
    status="$(az containerapp job execution show -n "$name" -g "$RG" --job-execution-name "$exec_name" \
      --query properties.status -o tsv 2>/dev/null || true)"
    case "$status" in
      Succeeded) echo "  ✓ $name $exec_name Succeeded"; return 0 ;;
      Failed)    echo "  ✗ $name $exec_name FAILED — pulling logs from Log Analytics (waiting ~40s for ingestion)…"
                 sleep 40
                 local ws; ws="$(az monitor log-analytics workspace list -g "$RG" --query '[0].customerId' -o tsv 2>/dev/null)"
                 az monitor log-analytics query -w "$ws" --analytics-query \
                   "ContainerAppConsoleLogs_CL | where ContainerGroupName_s == '$exec_name' | project TimeGenerated, Log_s | order by TimeGenerated asc | take 200" \
                   --query "[].Log_s" -o tsv 2>/dev/null \
                   || echo "  (no console logs yet — re-query in a minute; ingestion lags)"
                 return 1 ;;
    esac
    sleep 10
  done
  echo "  ! $name $exec_name still '$status' after 10 min — check: az containerapp job execution show -n $name -g $RG --job-execution-name $exec_name"
  return 1
}

create_job rjacq-migrate -- alembic upgrade head
create_job rjacq-seed    -- rjacq-seed   # console entry point (no -m: Azure --command rejects dashes)

# ── 10. First migrate + one-time seed (only when running real images) ────────────────────────
if [[ "$SKIP_IMAGE_BUILD" != "1" ]]; then
  say "Applying migrations + seeding reference data"
  run_job rjacq-migrate
  run_job rjacq-seed
fi

web_fqdn="$(az containerapp show -n rjacq-web -g "$RG" --query properties.configuration.ingress.fqdn -o tsv 2>/dev/null || true)"
cat <<EOF

✅ Provisioned. Endpoints:
   Web (public)     https://${web_fqdn:-<pending>}
   API  (internal)  https://${api_fqdn}
   s3proxy (public) ${S3_ENDPOINT}

Next:
  • Set health probes on rjacq-api (/health) — see docs/DEPLOYMENT.md §2.4.
  • Bind your custom domain + cert to rjacq-web, then set APP_BASE_URL / WEB_BASE_URL to it
    (re-run with WEB_ORIGIN set) and configure the Entra OIDC redirect (DEPLOYMENT.md §2.6).
  • Add CORS on rjacq-web's origin to the s3proxy app so browser presigned PUT/GET succeed.
  • Wire the GitHub Actions deploy secrets/vars (DEPLOYMENT.md §3.1); pushes to main then
    build → migrate → roll automatically.
EOF
