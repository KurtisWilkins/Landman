# Deployment runbook — RJourney Acquisitions Platform

Production target: **Azure Container Apps** + fresh managed data services (ADR-0004). This
runbook covers one-time provisioning, the automated update pipeline, and — most importantly —
the **data-safety discipline** that lets you push updates frequently with no downtime and no
loss of data once real acquisition targets have been underwritten.

> **The short version of the safety story.** Your data lives in **managed PostgreSQL**, which
> is completely independent of the app containers. Redeploying the app spins up new container
> revisions and drains the old ones — it never touches the database. The *only* thing that
> touches the database is an Alembic migration, and migrations are run as a gated step that
> must be **backward-compatible** (expand-contract). With ≥2 replicas and health probes, users
> see no interruption, and Rory's entered data is safe across every deploy.

---

## 1. Architecture

```
                         ┌────────────────────────────────────────────┐
   users ── HTTPS ──▶ Web Container App (nginx + SPA)                  │
                     │   • serves built React assets                   │
                     │   • reverse-proxies /api → API (internal)       │
                     └───────────────┬────────────────────────────────┘
                                     │ internal ingress
                     ┌───────────────▼───────────────┐   ┌──────────────────────┐
                     │ API Container App (FastAPI)    │   │ Worker Container App  │
                     │   • /health liveness+readiness │   │   (Arq queue worker)  │
                     │   • min replicas ≥ 2           │   └───────────┬──────────┘
                     └───────┬───────────────┬────────┘               │
                             │               │                        │
          ┌──────────────────▼──┐   ┌────────▼─────────┐   ┌──────────▼──────────┐
          │ Postgres Flexible    │   │ Azure Cache for  │   │ Object storage      │
          │ Server 16 (pgvector) │   │ Redis            │   │ (S3-compatible)     │
          │ automated backups+PITR│  └──────────────────┘   └─────────────────────┘
          └──────────────────────┘
   Images: Azure Container Registry (ACR).  Identity: Microsoft Entra ID (ADR-0003).
```

Why this shape:
- **Single ingress through the web app** (nginx proxies `/api`) → same-origin, no CORS, auth
  cookies "just work", and the API can stay **internal** (not exposed publicly).
- **Container Apps revisions** give automatic rolling, zero-downtime releases with health gating.
- **Worker** shares the API image; it just runs a different command (`arq …`).

> **Object storage (ADR-0010).** The storage client is **S3-API** (boto3 + `S3_ENDPOINT`) and
> hands the browser presigned URLs. Azure Blob is *not* S3-native, so production runs
> **Azure Blob fronted by an `s3proxy` gateway** (single-vendor on Azure). Note MinIO's Azure
> gateway was removed in 2022 — `s3proxy` is the maintained equivalent. (Swapping to S3-native
> **Cloudflare R2 / AWS S3** later is just `S3_ENDPOINT` + creds, no code change.)

---

## 2. One-time provisioning

> **Fastest path — one command.** `make deploy-provision` runs `scripts/provision-azure.sh`,
> which performs everything in this section (RG, ACR, Postgres+pgvector, Redis, storage + s3proxy
> gateway, Container Apps env, the three apps + migration job, first migrate + seed). Copy
> `scripts/deploy.env.example → scripts/deploy.env` (gitignored) and fill in the secrets first.
> The steps below document what the script does and how to run them by hand.
>
> **No local tooling needed — run it from [Azure Cloud Shell](https://shell.azure.com)** (the
> `>_` icon in the portal, Bash). Cloud Shell is pre-authenticated; images build server-side via
> `az acr build`, so Docker isn't required. From Cloud Shell:
> ```bash
> git clone https://github.com/KurtisWilkins/Landman.git && cd Landman
> cp scripts/deploy.env.example scripts/deploy.env && code scripts/deploy.env   # fill it in
> make deploy-provision
> ```

Prereqs: `az` CLI logged in to the target subscription, plus the `containerapp` and
`rdbms-connect` extensions. Set shared variables once:

```bash
RG=rjacq-prod
LOC=<REGION>                  # e.g. eastus2 — choose per data-residency policy (ADR-0004)
ACR=rjacqprod                 # ACR name (login server becomes ${ACR}.azurecr.io)
ENVNAME=rjacq-env
PGSERVER=rjacq-pg
PGADMIN=rjadmin

az group create -n $RG -l $LOC
az acr create -n $ACR -g $RG --sku Standard
az containerapp env create -n $ENVNAME -g $RG -l $LOC   # add --logs-destination log-analytics
```

### 2.1 PostgreSQL (with pgvector + backups)

```bash
az postgres flexible-server create \
  -n $PGSERVER -g $RG -l $LOC --version 16 \
  --tier GeneralPurpose --sku-name Standard_D2ds_v5 --storage-size 64 \
  --admin-user $PGADMIN --admin-password '<STRONG_PASSWORD>' \
  --backup-retention 21 --high-availability ZoneRedundant     # PITR + HA for prod

az postgres flexible-server db create -g $RG -s $PGSERVER -d rjacq

# Allow + enable pgvector (used for GL-mapping embeddings).
az postgres flexible-server parameter set -g $RG -s $PGSERVER \
  --name azure.extensions --value vector
# then, connected to the rjacq database:  CREATE EXTENSION IF NOT EXISTS vector;
```

`--backup-retention 21` gives 21 days of automated backups **and point-in-time restore** —
this is the primary safety net for underwritten-acquisition data.

### 2.2 Redis (job queue) and object storage (Azure Blob + s3proxy, ADR-0010)

```bash
az redis create -n rjacq-redis -g $RG -l $LOC --sku Standard --vm-size c1

# Object storage: Azure Blob + an s3proxy S3 gateway.
STORAGEACCT=rjacqprodfiles      # 3-24 lowercase alphanumerics, globally unique
az storage account create -n $STORAGEACCT -g $RG -l $LOC --sku Standard_LRS --kind StorageV2
BLOB_KEY=$(az storage account keys list -n $STORAGEACCT -g $RG --query '[0].value' -o tsv)
az storage container create --name rjacq-files --account-name $STORAGEACCT \
  --account-key "$BLOB_KEY" --auth-mode key

# s3proxy gateway — PUBLIC ingress (the browser uses presigned URLs directly; the presigned
# signature authorizes each request, the Blob key stays on the gateway). S3PROXY_IDENTITY /
# S3PROXY_CREDENTIAL are the S3 keys the app signs with — you choose them.
az containerapp create -n rjacq-s3proxy -g $RG --environment $ENVNAME \
  --image andrewgaul/s3proxy:sha-ba0d4eb --ingress external --target-port 80 \
  --secrets blob-key="$BLOB_KEY" s3-cred="$S3PROXY_CREDENTIAL" \
  --env-vars S3PROXY_AUTHORIZATION=aws-v2-or-v4 S3PROXY_IDENTITY=$S3PROXY_IDENTITY \
    S3PROXY_CREDENTIAL=secretref:s3-cred JCLOUDS_PROVIDER=azureblob \
    JCLOUDS_IDENTITY=$STORAGEACCT JCLOUDS_CREDENTIAL=secretref:blob-key \
    JCLOUDS_ENDPOINT=https://$STORAGEACCT.blob.core.windows.net
```

Then enable **CORS** on the gateway so browser presigned PUT/GET succeed. `provision-azure.sh`
does this for you (idempotently, so a re-run finalizes an existing gateway):

```bash
az containerapp update -n rjacq-s3proxy -g $RG --set-env-vars S3PROXY_CORS_ALLOW_ALL=true
```

We allow all origins rather than enumerate them because the Azure CLI cannot set env-var values
containing spaces ([azure-cli#30396](https://github.com/Azure/azure-cli/issues/30396)) and
`S3PROXY_CORS_ALLOW_ORIGINS`/`_METHODS` are space-separated lists. This is safe for a
presigned-only gateway: every request still carries an AWS signature (the real access control);
CORS only governs which browser origins may *attempt* a request.

The API's `S3_ENDPOINT` is the gateway's public FQDN; `S3_ACCESS_KEY_ID` /
`S3_SECRET_ACCESS_KEY` are `S3PROXY_IDENTITY` / `S3PROXY_CREDENTIAL`. The boto3 client switches
to path-style addressing automatically whenever `S3_ENDPOINT` is set (`core/storage.py`).

### 2.3 Secrets and config

Store everything sensitive as **Container Apps secrets** (or reference Key Vault). The app
reads these env vars (`apps/api/rjacq/core/config.py`):

| Env var | Notes |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg://rjadmin:<pwd>@rjacq-pg.postgres.database.azure.com:5432/rjacq?sslmode=require` — **`sslmode=require` is mandatory** |
| `REDIS_URL` | from the Redis instance (use the SSL port / `rediss://`) |
| `SECRET_KEY` | session signing — strong random value |
| `APP_ENV` | `production` (flips logging to INFO, `is_production`) |
| `APP_BASE_URL` / `WEB_BASE_URL` | public web URL (drives CORS + OIDC redirect) |
| `S3_ENDPOINT` / `S3_BUCKET` / `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` | object storage — `S3_ENDPOINT` = s3proxy public FQDN, keys = the s3proxy identity/credential (ADR-0010) |
| `ANTHROPIC_API_KEY` / `VOYAGE_API_KEY` | AI + embeddings (ADR-0005/0008) |
| `OIDC_*` / `EXTERNAL_AUTH_SECRET` | Entra ID OIDC + magic-link (ADR-0003) |
| `SHIELD_*` | **read-only** SHIELD creds (ADR-0002) — never a writable login |
| `POPULATION_PROVIDER` / `POPULATION_PROVIDER_API_KEY` / `CENSUS_ACS_YEAR` | population rings (ADR-0009) |
| `SENTRY_DSN` / `RELEASE` | observability; set `RELEASE` to the deployed commit SHA |
| `GITHUB_APP_ID` / `GITHUB_APP_PRIVATE_KEY` / `GITHUB_WEBHOOK_SECRET` | feedback dispatch |

Never commit any of these; keep `.env.example` current when a new var is added.

### 2.4 Container Apps + migration job

Build the first images **server-side in ACR** (no local Docker — works in Azure Cloud Shell):

```bash
SHA=$(git rev-parse --short=12 HEAD)
az acr build --registry $ACR -f apps/api/Dockerfile     -t rjacq-api:$SHA .
( cd apps/web && az acr build --registry $ACR -f Dockerfile.prod -t rjacq-web:$SHA . )
```

Create the apps. The **API is internal**; the **web is the only public ingress**:

```bash
# API (internal ingress, ≥2 replicas). Attach secrets/env-vars from §2.3.
az containerapp create -n rjacq-api -g $RG --environment $ENVNAME \
  --image $ACR.azurecr.io/rjacq-api:$SHA \
  --ingress internal --target-port 8000 --min-replicas 2 --max-replicas 6 \
  --secrets database-url=... redis-url=... secret-key=... \
  --env-vars DATABASE_URL=secretref:database-url REDIS_URL=secretref:redis-url \
             SECRET_KEY=secretref:secret-key APP_ENV=production

# Worker — same image, different command, no ingress.
az containerapp create -n rjacq-worker -g $RG --environment $ENVNAME \
  --image $ACR.azurecr.io/rjacq-api:$SHA --min-replicas 1 \
  --command "arq" "rjacq.core.queue.WorkerSettings" \
  --secrets database-url=... redis-url=... \
  --env-vars DATABASE_URL=secretref:database-url REDIS_URL=secretref:redis-url

# Web — public ingress; API_URL points at the API's internal FQDN.
API_FQDN=$(az containerapp show -n rjacq-api -g $RG \
  --query properties.configuration.ingress.fqdn -o tsv)
az containerapp create -n rjacq-web -g $RG --environment $ENVNAME \
  --image $ACR.azurecr.io/rjacq-web:$SHA \
  --ingress external --target-port 8080 --min-replicas 2 --max-replicas 4 \
  --env-vars API_URL=https://$API_FQDN
```

**Health probes (optional upgrade).** When ingress is enabled, Container Apps already adds
**default TCP probes** on the target port, so revisions are health-gated out of the box — this
is why the apps come up healthy from `provision-azure.sh` without extra steps. Upgrading the API
to **HTTP `/health`** probes additionally confirms the app *responds*, not just that the port is
open. `az containerapp update --yaml` **replaces** the container template, so fetch the current
spec, add the `probes` block to the API container, and re-apply — don't hand-write a partial
file (you'd drop the image/secrets/env):

```bash
az containerapp show -n rjacq-api -g $RG -o yaml > api.yaml
# Add under properties.template.containers[0]:
#   probes:
#     - type: Liveness
#       httpGet: { path: /health, port: 8000 }
#       periodSeconds: 10
#     - type: Readiness
#       httpGet: { path: /health, port: 8000 }
#       initialDelaySeconds: 5
#       periodSeconds: 5
az containerapp update -n rjacq-api -g $RG --yaml api.yaml
```

Create the **migration job** (the pipeline updates its image and runs it each deploy):

```bash
az containerapp job create -n rjacq-migrate -g $RG --environment $ENVNAME \
  --image $ACR.azurecr.io/rjacq-api:$SHA \
  --trigger-type Manual --replica-timeout 600 --replica-retry-limit 1 \
  --command "alembic" "upgrade" "head" \
  --secrets database-url=... --env-vars DATABASE_URL=secretref:database-url
```

### 2.5 First migration + one-time seed

Job starts are **async** — wait for the migrate execution to report `Succeeded` before
seeding (the seed writes to tables the migration creates). `provision-azure.sh` does this
polling for you; manually it looks like:

```bash
exec_name=$(az containerapp job start -n rjacq-migrate -g $RG --query name -o tsv)
az containerapp job execution show -n rjacq-migrate -g $RG \
  --job-execution-name $exec_name --query properties.status -o tsv   # repeat until Succeeded
# Seed reference data ONCE (GL chart §8.5 + gate questions; idempotent upsert-by-PK):
az containerapp job create -n rjacq-seed -g $RG --environment $ENVNAME \
  --image $ACR.azurecr.io/rjacq-api:$SHA --trigger-type Manual --replica-timeout 600 \
  --command "python" "-m" "rjacq.seeds.load" \
  --secrets database-url=... --env-vars DATABASE_URL=secretref:database-url
az containerapp job start -n rjacq-seed -g $RG
```

### 2.6 Custom domain, TLS, and Entra

These need resources only you control (DNS, the Entra tenant), so they stay manual:

- Bind your domain + managed certificate to the **web** app
  (`az containerapp hostname add` / `... bind`).
- Re-run `make deploy-provision` with `WEB_ORIGIN=https://<your-domain>` set in
  `scripts/deploy.env`. The script then sets `APP_BASE_URL` / `WEB_BASE_URL` on the API (drives
  CORS + the OIDC redirect) — idempotently, so it just updates the running API.
- Register the app in **Entra ID** (ADR-0003); set the OIDC redirect URI to
  `https://<your-domain>/api/auth/callback` (nginx proxies `/api` → API `/auth/callback`).
- Confirm SHIELD creds are the **read-only** login (ADR-0002) — the app must never write there.

---

## 3. The automated update pipeline (the fast path)

`.github/workflows/deploy.yml` runs on every merge to `main` (and on manual dispatch):

```
build API + web images (SHA-tagged, registry-cached)
        │
   run migration job on the NEW image  ──fails──▶ stop (apps NOT rolled)
        │ success
   roll API → worker → web revisions (rolling, health-gated)
```

### 3.1 Wire it up once

**Azure OIDC** (no stored cloud passwords) — create a federated credential for the repo's
`production` environment and grant it push/deploy rights:

```bash
APP_ID=$(az ad app create --display-name rjacq-github-deploy --query appId -o tsv)
az ad sp create --id $APP_ID
az ad app federated-credential create --id $APP_ID --parameters '{
  "name":"github-prod",
  "issuer":"https://token.actions.githubusercontent.com",
  "subject":"repo:KurtisWilkins/landman:environment:production",
  "audiences":["api://AzureADTokenExchange"]
}'
SUB=$(az account show --query id -o tsv)
az role assignment create --assignee $APP_ID --role Contributor \
  --scope /subscriptions/$SUB/resourceGroups/$RG
az role assignment create --assignee $APP_ID --role AcrPush \
  --scope $(az acr show -n $ACR --query id -o tsv)
```

**GitHub → Settings → Secrets and variables → Actions:**

- Secrets: `AZURE_CLIENT_ID` (= `$APP_ID`), `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`.
- Variables: `ACR_LOGIN_SERVER` (`rjacqprod.azurecr.io`), `AZURE_RESOURCE_GROUP` (`rjacq-prod`),
  `API_CONTAINER_APP` (`rjacq-api`), `WORKER_CONTAINER_APP` (`rjacq-worker`),
  `WEB_CONTAINER_APP` (`rjacq-web`), `MIGRATE_JOB` (`rjacq-migrate`).
- **Environment `production`**: **current posture is auto-deploy on merge** — leave the
  environment with **no required reviewers**, so a merge to `main` rolls straight to production
  (CI + branch protection are the guards). To add a manual approval gate later, add a required
  reviewer to the `production` environment — no workflow change needed.

### 3.2 Day-to-day: shipping an update

1. Open a PR; CI (`ci.yml`) must be green (branch protection — ADR-0007).
2. Merge to `main`. `deploy.yml` builds, migrates (if any), and rolls — typically a few
   minutes, zero downtime.
3. Or trigger manually: **Actions → Deploy → Run workflow** (with `skip_migrations` for a
   code-only release).

That's the "push quickly" loop: **merge → live**, gated only by CI and (optionally) one
approval click.

---

## 4. Zero-downtime mechanics

- **Single-revision mode** (default): each deploy creates a new revision; traffic shifts to it
  only after readiness probes pass, then the old revision drains in-flight requests.
- **`--min-replicas 2`** on API and web so a rolling replacement never drops to zero capacity.
- **`/health`** backs both probes (returns version + env).
- The SPA shell is served `no-store` while hashed `/assets/*` are immutable, so a deploy is
  picked up immediately without stale-cache breakage.

---

## 5. Data safety & migrations (read before any schema change)

This is what protects underwritten-acquisition data across frequent deploys.

1. **App redeploys never touch data.** Containers are stateless; all state is in managed
   Postgres / Redis / object storage. Rolling revisions = no data impact.
2. **Migrations are the only DB step, and they run *before* the new revision is live.** During
   the rollover both old and new code briefly run against the just-migrated schema, so every
   migration must be **backward-compatible with the currently-running release**.
3. **Expand-contract (parallel change) — never a destructive change in the same deploy as the
   code that needs it:**
   - **Expand:** additive only — new *nullable* column, new table, new index
     (`CREATE INDEX CONCURRENTLY`), new enum value. Deploy. Old + new code both work.
   - **Backfill:** populate/transform data in a follow-up step or migration.
   - **Contract:** only in a *later* release, once no running code references the old shape,
     drop/rename/tighten. 
   A column rename = add new + backfill + switch code + (later) drop old — across ≥2 deploys.
4. **Never edit a shipped migration; always add a new one** (CLAUDE.md). Never run Alembic
   *downgrades* against production.
5. **Back up before contracting/irreversible migrations.** Automated PITR covers you, but for
   a risky change take an explicit logical snapshot first:
   `pg_dump "$DATABASE_URL" -Fc -f pre_<rev>.dump`.
6. **Idempotent re-runnable work:** seeds upsert by PK (safe to re-run); Arq jobs are
   at-least-once, so handlers must tolerate retries.

Following this, a deploy that lands while Rory is entering data is safe: her in-progress and
saved targets persist in Postgres, the schema only grew, and the app rolled without dropping
requests.

---

## 6. Rollback

- **Bad code revision** (fast, no data risk because migrations were backward-compatible):
  ```bash
  az containerapp revision list -n rjacq-api -g $RG -o table
  az containerapp ingress traffic set -n rjacq-api -g $RG \
    --revision-weight <previous-revision>=100
  ```
  Repeat for `rjacq-web` / `rjacq-worker`, or `az containerapp update --image …:<previous-sha>`.
- **Bad migration:** because changes are expand-only, the previous code still runs against the
  new schema — usually just roll the code back. If data was corrupted, **restore via PITR**:
  ```bash
  az postgres flexible-server restore -g $RG -n rjacq-pg-restore \
    --source-server rjacq-pg --restore-time <ISO8601-before-incident>
  ```
  then repoint `DATABASE_URL`. This is why expand-contract + backups matter.

---

## 7. Operations

- Logs: `az containerapp logs show -n rjacq-api -g $RG --follow` (structured JSON; correlation
  IDs threaded per request).
- Health: `GET https://<your-domain>/api/health`.
- Errors: Sentry (front + back), tagged with `RELEASE` = deployed SHA.
- Scaling: tune `--min/max-replicas` and add KEDA rules (e.g. scale the worker on Redis queue
  depth) as load grows.
