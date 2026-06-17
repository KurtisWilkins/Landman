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
: "${IMAGE_TAG:=bootstrap}"
: "${SKIP_IMAGE_BUILD:=0}"
: "${PLACEHOLDER_IMAGE:=mcr.microsoft.com/k8se/quickstart:latest}"

acr_login="${ACR}.azurecr.io"
api_img="${acr_login}/rjacq-api:${IMAGE_TAG}"
web_img="${acr_login}/rjacq-web:${IMAGE_TAG}"

say() { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }

# Poll a Container Apps job execution to completion (mirrors the deploy.yml gate).
wait_job() { # wait_job <job-name> <execution-name>
  local job="$1" exec_name="$2" stat
  for _ in $(seq 1 60); do
    stat="$(az containerapp job execution show -n "$job" -g "$RG" \
      --job-execution-name "$exec_name" --query properties.status -o tsv)"
    echo "  $job: $stat"
    case "$stat" in
      Succeeded) return 0 ;;
      Failed|Degraded) echo "  (!) $job execution $exec_name failed — check its logs"; return 1 ;;
    esac
    sleep 10
  done
  echo "  (!) $job timed out after 10 minutes"; return 1
}

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
az postgres flexible-server db create -g "$RG" -s "$PGSERVER" -d "$PGDB" -o none 2>/dev/null || true
az postgres flexible-server parameter set -g "$RG" -s "$PGSERVER" \
  --name azure.extensions --value vector -o none
# Enable the extension in the database (needs rdbms-connect; safe to re-run).
az postgres flexible-server execute \
  -n "$PGSERVER" -u "$PGADMIN" -p "$PGPASSWORD" -d "$PGDB" \
  -q "CREATE EXTENSION IF NOT EXISTS vector;" -o none 2>/dev/null \
  || echo "  (!) Could not auto-create the vector extension — run CREATE EXTENSION vector; manually."

pg_host="$(az postgres flexible-server show -n "$PGSERVER" -g "$RG" --query fullyQualifiedDomainName -o tsv)"
DATABASE_URL="postgresql+psycopg://${PGADMIN}:${PGPASSWORD}@${pg_host}:5432/${PGDB}?sslmode=require"

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
  # Pull base images from Google's public Docker Hub mirror (no auth, no anonymous rate limit
  # — Docker Hub throttles the shared ACR build pool's anonymous pulls).
  ( cd "$repo_root" && az acr build --registry "$ACR" --build-arg "BASE_REGISTRY=mirror.gcr.io/library/" \
    -f apps/api/Dockerfile -t "rjacq-api:$IMAGE_TAG" . )
  ( cd "$repo_root/apps/web" && az acr build --registry "$ACR" --build-arg "BASE_REGISTRY=mirror.gcr.io/library/" \
    -f Dockerfile.prod -t "rjacq-web:$IMAGE_TAG" . )
fi
# Let the apps pull from ACR via the env's managed identity (assigned below for real images).
registry_args=(); [[ "$SKIP_IMAGE_BUILD" == "1" ]] || registry_args=(--registry-server "$acr_login" --registry-identity system)

# ── 7. s3proxy gateway (public ingress — presigned URLs are used straight from the browser) ──
say "s3proxy gateway over Azure Blob"
if ! az containerapp show -n rjacq-s3proxy -g "$RG" -o none 2>/dev/null; then
  az containerapp create -n rjacq-s3proxy -g "$RG" --environment "$ENVNAME" \
    --image andrewgaul/s3proxy:sha-ba0d4eb --ingress external --target-port 80 \
    --min-replicas 1 --max-replicas 2 \
    --secrets blob-key="$blob_key" s3-cred="$S3PROXY_CREDENTIAL" \
    --env-vars \
      S3PROXY_AUTHORIZATION=aws-v2-or-v4 \
      "S3PROXY_IDENTITY=$S3PROXY_IDENTITY" \
      S3PROXY_CREDENTIAL=secretref:s3-cred \
      JCLOUDS_PROVIDER=azureblob \
      "JCLOUDS_IDENTITY=$STORAGEACCT" \
      JCLOUDS_CREDENTIAL=secretref:blob-key \
      "JCLOUDS_ENDPOINT=https://${STORAGEACCT}.blob.core.windows.net" -o none
fi
s3_fqdn="$(az containerapp show -n rjacq-s3proxy -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)"
S3_ENDPOINT="https://${s3_fqdn}"

# Enable CORS on the gateway so the browser can run presigned PUT/GET (uploads/downloads).
# Idempotent, so it also finalizes an already-provisioned gateway on a re-run. We allow all
# origins rather than enumerate them because the Azure CLI cannot set env-var values containing
# spaces (azure-cli#30396) and S3PROXY_CORS_ALLOW_ORIGINS/_METHODS are space-separated lists.
# This is safe for a presigned-only gateway: every request still carries an AWS signature, which
# is the actual access control — CORS only governs which browser origins may *attempt* a request.
az containerapp update -n rjacq-s3proxy -g "$RG" \
  --set-env-vars S3PROXY_CORS_ALLOW_ALL=true -o none

# ── 8. API (internal), worker (no ingress), web (public) ─────────────────────────────────────
say "API / worker / web container apps"
common_secrets=(database-url="$DATABASE_URL" redis-url="$REDIS_URL" secret-key="$SECRET_KEY" s3-secret="$S3PROXY_CREDENTIAL")
common_env=(DATABASE_URL=secretref:database-url REDIS_URL=secretref:redis-url APP_ENV=production)
s3_env=("S3_ENDPOINT=$S3_ENDPOINT" "S3_BUCKET=$BLOBCONTAINER" "S3_ACCESS_KEY_ID=$S3PROXY_IDENTITY" S3_SECRET_ACCESS_KEY=secretref:s3-secret)

if ! az containerapp show -n rjacq-api -g "$RG" -o none 2>/dev/null; then
  az containerapp create -n rjacq-api -g "$RG" --environment "$ENVNAME" "${registry_args[@]}" \
    --image "$api_img" --ingress internal --target-port 8000 --min-replicas 2 --max-replicas 6 \
    --secrets "${common_secrets[@]}" \
    --env-vars "${common_env[@]}" SECRET_KEY=secretref:secret-key "${s3_env[@]}" ${WEB_ORIGIN:+WEB_BASE_URL=$WEB_ORIGIN APP_BASE_URL=$WEB_ORIGIN} \
    -o none
else
  echo "  (rjacq-api exists — update its image via the deploy pipeline)"
fi

if ! az containerapp show -n rjacq-worker -g "$RG" -o none 2>/dev/null; then
  az containerapp create -n rjacq-worker -g "$RG" --environment "$ENVNAME" "${registry_args[@]}" \
    --image "$api_img" --min-replicas 1 --max-replicas 3 \
    --command arq rjacq.core.queue.WorkerSettings \
    --secrets "${common_secrets[@]}" \
    --env-vars "${common_env[@]}" "${s3_env[@]}" \
    -o none
else
  echo "  (rjacq-worker exists — update via the pipeline)"
fi

api_fqdn="$(az containerapp show -n rjacq-api -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)"
if ! az containerapp show -n rjacq-web -g "$RG" -o none 2>/dev/null; then
  az containerapp create -n rjacq-web -g "$RG" --environment "$ENVNAME" "${registry_args[@]}" \
    --image "$web_img" --ingress external --target-port 8080 --min-replicas 2 --max-replicas 4 \
    --env-vars "API_URL=https://${api_fqdn}" \
    -o none
else
  echo "  (rjacq-web exists — update via the pipeline)"
fi

# Finalize the public web origin on the API once it is known (drives CORS + the OIDC redirect).
# Idempotent update so it also applies to an already-provisioned API on a re-run; both values are
# single tokens (no spaces), so --set-env-vars handles them.
if [[ -n "$WEB_ORIGIN" ]]; then
  say "Setting APP_BASE_URL / WEB_BASE_URL on the API ($WEB_ORIGIN)"
  az containerapp update -n rjacq-api -g "$RG" \
    --set-env-vars "APP_BASE_URL=$WEB_ORIGIN" "WEB_BASE_URL=$WEB_ORIGIN" -o none
fi

# ── 9. Migration job (the deploy pipeline updates its image + runs it each release) ──────────
say "Migration job"
if ! az containerapp job show -n rjacq-migrate -g "$RG" -o none 2>/dev/null; then
  az containerapp job create -n rjacq-migrate -g "$RG" --environment "$ENVNAME" "${registry_args[@]}" \
    --image "$api_img" --trigger-type Manual --replica-timeout 600 --replica-retry-limit 1 \
    --command alembic upgrade head \
    --secrets database-url="$DATABASE_URL" \
    --env-vars DATABASE_URL=secretref:database-url \
    -o none
else
  echo "  (rjacq-migrate exists)"
fi

# ── 10. First migrate + one-time seed (only when running real images) ────────────────────────
# Seeding waits for the migration execution to SUCCEED first — the seed job writes to tables
# the migration creates, and job start is async.
if [[ "$SKIP_IMAGE_BUILD" != "1" ]]; then
  say "Applying migrations (waiting for completion)"
  exec_name="$(az containerapp job start -n rjacq-migrate -g "$RG" --query name -o tsv)"
  wait_job rjacq-migrate "$exec_name"

  say "Seeding reference data"
  if ! az containerapp job show -n rjacq-seed -g "$RG" -o none 2>/dev/null; then
    az containerapp job create -n rjacq-seed -g "$RG" --environment "$ENVNAME" "${registry_args[@]}" \
      --image "$api_img" --trigger-type Manual --replica-timeout 600 --replica-retry-limit 0 \
      --command python -m rjacq.seeds.load \
      --secrets database-url="$DATABASE_URL" \
      --env-vars DATABASE_URL=secretref:database-url -o none
  fi
  exec_name="$(az containerapp job start -n rjacq-seed -g "$RG" --query name -o tsv)"
  wait_job rjacq-seed "$exec_name" \
    || echo "  (!) seed failed — safe to re-run: az containerapp job start -n rjacq-seed -g $RG"
fi

web_fqdn="$(az containerapp show -n rjacq-web -g "$RG" --query properties.configuration.ingress.fqdn -o tsv 2>/dev/null || true)"
cat <<EOF

✅ Provisioned. Endpoints:
   Web (public)     https://${web_fqdn:-<pending>}
   API  (internal)  https://${api_fqdn}
   s3proxy (public) ${S3_ENDPOINT}

Done automatically by this script:
  • s3proxy CORS enabled (browser presigned PUT/GET work).
  • APP_BASE_URL / WEB_BASE_URL set on the API${WEB_ORIGIN:+ ($WEB_ORIGIN)}.

Still your move (needs your domain / Entra tenant / repo admin — see docs/DEPLOYMENT.md §2.7):
  • Bind a custom domain + managed cert to rjacq-web, then re-run with WEB_ORIGIN set so the
    API's base URLs and the OIDC redirect point at it.
  • Register the app in Entra ID and set the OIDC redirect to <web-origin>/api/auth/callback.
  • (Optional) Switch the API to HTTP /health probes — default TCP probes already gate traffic.
  • Wire the GitHub Actions deploy secrets/vars (DEPLOYMENT.md §3.1); pushes to main then
    build → migrate → roll automatically.
EOF
