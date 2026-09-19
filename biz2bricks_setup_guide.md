# Biz2Bricks — GCP Setup Guide

End-to-end instructions for deploying a Biz2Bricks service to Google Cloud,
from a clean machine to a running Cloud Run service.

Written against `doc_intelligence_backend_api_v2.0`, but Part 8 covers adapting
it to any other service in the platform.

Every gotcha in Part 7 is one we actually hit, not a hypothetical.

---

## Contents

1. [Prerequisites](#1-prerequisites)
2. [One-time machine setup](#2-one-time-machine-setup)
3. [Choose a project and verify billing](#3-choose-a-project-and-verify-billing)
4. [Enable APIs](#4-enable-apis)
5. [Provision infrastructure](#5-provision-infrastructure)
6. [Deploy](#6-deploy)
7. [Troubleshooting](#7-troubleshooting)
8. [Adapting this for another app](#8-adapting-this-for-another-app)
9. [Cost management](#9-cost-management)
10. [Before real users](#10-before-real-users)
11. [Deployed services](#11-deployed-services-biz2bricks-dev-v1)
12. [CORS between the services](#12-cors-between-the-services)

---

## 1. Prerequisites

| Tool | Why | Install |
|---|---|---|
| `gcloud` | All GCP operations | See §2.1 — **read it, do not just brew install** |
| `gh` | Repo access, CI triggers | `brew install gh` |
| `docker` | Builds the container image | Docker Desktop; the daemon must be running |
| `uv` | Python dependency management | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| `biz2bricks` | Infra provisioning CLI | `uv pip install -e ../biz2bricks_infra` |

You also need a GCP account with **Owner** or equivalent on the target project,
and a billing account linked to it.

---

## 2. One-time machine setup

### 2.1 Install the gcloud SDK — NOT in a synced folder

> **Do not install the SDK under `~/Documents`, `~/Desktop`, iCloud Drive,
> Google Drive, Dropbox, or OneDrive.**

File-sync services resolve conflicts by creating numbered copies —
`__init__ 2.py`, `gcloud 3.py`. The gcloud module loader picks these up and
crashes with:

```
ERROR: gcloud crashed (LayoutException): You cannot define groups [Gcloud] in a
command file: [.../lib/surface/__init__ 2.py]
```

We hit this with **13,622 duplicate files**. It fails *intermittently* — some
commands work, others crash — which makes it maddening to diagnose.

Install somewhere unsynced:

```bash
cd ~ && curl -O https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-darwin-arm64.tar.gz
tar -xf google-cloud-cli-darwin-arm64.tar.gz     # creates ~/google-cloud-sdk
./google-cloud-sdk/install.sh
exec -l $SHELL                                    # reload PATH
gcloud version                                    # must print cleanly
```

**Already corrupted?** See §7.1.

### 2.2 Authenticate

```bash
gcloud auth login                        # user credentials, for CLI commands
gcloud auth application-default login    # ADC, for local app code
gh auth login                            # GitHub, for repo + CI triggers
```

Verify:

```bash
gcloud auth list          # your account should be ACTIVE (*)
gh auth status
```

> Tokens expire. A `Reauthentication failed. cannot prompt during
> non-interactive execution` error means re-run `gcloud auth login`.

### 2.3 Clone and install

```bash
git clone https://github.com/<org>/doc_intelligence_backend_api_v2.0.git
cd doc_intelligence_backend_api_v2.0
uv sync
uv pip install -e ../biz2bricks_infra    # provides the `biz2bricks` CLI
```

---

## 3. Choose a project and verify billing

### 3.1 Pick the project — and set it as the default

```bash
gcloud projects list
gcloud config set project <PROJECT_ID>
gcloud config get-value project          # MUST echo back what you just set
```

> **Verify the read-back.** The provisioner's confirmation banner prints the
> *gcloud default* project, while its actual operations use `GCP_PROJECT_ID`
> from your env file. If those disagree, the banner shows one project while
> work happens in another. See §7.2.

### 3.2 Confirm billing is linked and open

```bash
gcloud billing projects describe <PROJECT_ID>
```

Look for `billingEnabled: true`. A project with no billing account silently
fails to create paid resources.

```bash
gcloud billing accounts list             # confirm the account is OPEN
```

> If a project is linked to a billing account that does **not** appear in this
> list, you lack permission to view that account — you will not be able to see
> its costs. Resolve that before provisioning.

---

## 4. Enable APIs

```bash
PROJECT_ID=<PROJECT_ID>

gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  iamcredentials.googleapis.com \
  --project=$PROJECT_ID
```

Verify:

```bash
gcloud services list --enabled --project=$PROJECT_ID
```

> **Enabled APIs are free.** They cost nothing until you create a resource.
> Disabling unused ones is good hygiene — it prevents an accidental
> `gcloud container clusters create` costing ~$73/month — but it is **not** a
> cost saving. Do not expect your bill to change.

Only enable `servicenetworking.googleapis.com` if you intend to use a **private
IP** Cloud SQL instance. This setup uses a public IP; see §9.3 for why.

---

## 5. Provision infrastructure

Order matters. Steps 5.1 and 5.2 must precede the first deploy or it fails.

### 5.1 Secrets

`cloudbuild.yaml` and `deploy.sh` mount these from Secret Manager. **They must
exist first** — a missing secret fails the deploy with an unhelpful error.

```bash
PROJECT_ID=<PROJECT_ID>

printf '%s' "$(openssl rand -hex 32)" \
  | gcloud secrets create JWT_SECRET_KEY \
      --project=$PROJECT_ID --replication-policy=automatic --data-file=-

printf '%s' '<YOUR_DB_PASSWORD>' \
  | gcloud secrets create DATABASE_PASSWORD \
      --project=$PROJECT_ID --replication-policy=automatic --data-file=-
```

**Secret naming by environment.** `deploy.sh` appends `-prod` for production:

| Deploy command | Secret names | Cloud Run service |
|---|---|---|
| `./deploy.sh --deploy` | `JWT_SECRET_KEY`, `DATABASE_PASSWORD` | `document-intelligence-api-dev` |
| `./deploy.sh --deploy --env production` | `JWT_SECRET_KEY-prod`, `DATABASE_PASSWORD-prod` | `document-intelligence-api` |

> **The DB password must match in three places**: the Secret Manager secret, the
> env file the provisioner reads (it sets the Cloud SQL user password from it),
> and the env file the deploy reads. A mismatch produces a confusing
> authentication failure at runtime, not at deploy time. Verify:
>
> ```bash
> gcloud secrets versions access latest --secret=DATABASE_PASSWORD \
>   --project=$PROJECT_ID | shasum
> ```
> Compare against the env file value's hash.

### 5.2 Artifact Registry — not covered by the provisioner

> **`biz2bricks provision full-setup` does NOT create this.** It provisions
> Cloud SQL, GCS, the service account and secrets only. `cloudbuild.yaml`
> pushes to a repository that will not exist, and the build fails.

```bash
gcloud artifacts repositories create document-intelligence \
  --project=$PROJECT_ID \
  --repository-format=docker \
  --location=us-central1 \
  --description="Backend API container images"
```

Then apply the retention policy — **images are kept forever by default**, at
$0.10/GB/month beyond the 0.5GB free tier:

```bash
./scripts/gcp/setup_cleanup_policy.sh            # dry run (default)
./scripts/gcp/setup_cleanup_policy.sh --apply    # enforce
```

The policy keeps the 3 most recent versions and deletes anything older than 30
days. It uses `"tagState": "ANY"` deliberately: every image carries a unique
`$BUILD_ID` or timestamp tag, so an untagged-only policy would match nothing.

### 5.3 Cloud SQL, bucket, service account

```bash
biz2bricks provision full-setup --env-file .env.production
```

This creates, idempotently:

| Resource | Configuration |
|---|---|
| Cloud SQL | PostgreSQL 15, `db-f1-micro`, 10GB SSD, ZONAL, **no backups** |
| Database | `doc_intelligence` |
| GCS bucket | From `GCS_BUCKET_NAME` |
| Service account | `document-intelligence-api-sa@<project>.iam.gserviceaccount.com` |
| IAM roles | `cloudsql.client`, `storage.objectAdmin`, `secretmanager.secretAccessor` |

> **One role is missing and you must add it.** `roles/storage.objectAdmin`
> grants object access but **not** `storage.buckets.get`, which the app calls
> when initialising its GCS client. Without it the service starts, reports
> `/health` as 200, and `/status` as `degraded` with GCS `unavailable`.
> Grant the minimal extra role, scoped to the bucket:
>
> ```bash
> gcloud storage buckets add-iam-policy-binding gs://<BUCKET> \
>   --member="serviceAccount:document-intelligence-api-sa@$PROJECT_ID.iam.gserviceaccount.com" \
>   --role="roles/storage.legacyBucketReader"
> ```

**Takes ~10 minutes** — Cloud SQL instance creation dominates. The CLI prompts
for confirmation; read the project name in the banner before answering (§7.2).

Monitor progress from another shell:

```bash
gcloud sql instances list --project=$PROJECT_ID
# wait for STATUS: RUNNABLE
```

> **Backups are OFF.** The provisioner passes `--no-backup`. Acceptable
> pre-launch; see §10.

---

## 6. Deploy

### 6.1 Manual deploy

```bash
./deploy.sh --deploy --project-id <PROJECT_ID>                    # dev
./deploy.sh --deploy --project-id <PROJECT_ID> --env production   # production
./deploy.sh --fast --project-id <PROJECT_ID> --skip-tests         # quick redeploy
```

> **`--project-id` is required.** Without it the script exits immediately with
> `--project-id is required for deployment`. It does not fall back to the
> gcloud default project. You can instead export `GCP_PROJECT_ID`, which the
> script reads as the default.

Requires the Docker daemon to be running.

### 6.2 Continuous deployment

```bash
./scripts/gcp/setup_triggers.sh
```

Creates GitHub-connected Cloud Build triggers: `develop` → dev, `master` →
prod. Requires the repo to be connected to Cloud Build first (one-time, done in
the console).

### 6.3 Verify

```bash
SERVICE_URL=$(gcloud run services describe document-intelligence-api-dev \
  --region=us-central1 --format="value(status.url)")

curl -s "$SERVICE_URL/health"    # 200
curl -s "$SERVICE_URL/status"    # PostgreSQL + GCS both reachable
```

Database tables are created automatically on first boot by
`DatabaseManager._ensure_tables`, so there is no separate migration step for a
fresh install.

Then confirm nothing unexpected is running:

```bash
./scripts/gcp/audit_costs.sh
```

Expect exactly one Cloud SQL instance (`db-f1-micro`/ZONAL), one Cloud Run
service at min-instances 0, and no VPC connectors.

### 6.4 Rollback

```bash
./scripts/gcp/rollback.sh --env=dev --list
./scripts/gcp/rollback.sh --env=dev --revision=<REVISION_NAME>
```

Rollback targets Cloud Run **revisions**, not image tags, so it works
regardless of how the image was built.

---

## 7. Troubleshooting

### 7.1 gcloud crashes with `LayoutException`

Sync-duplicated SDK files (§2.1). Check the scale:

```bash
find <SDK_PATH> -name "* [0-9].*" | wc -l
```

The durable fix is reinstalling outside the synced folder. To unblock now,
**check for orphans before deleting** — if sync lost an original and kept only
`foo 2.py`, blanket-deleting removes the only copy and makes things worse:

```bash
python3 - <<'PY'
import os, re, pathlib
SDK = pathlib.Path("<SDK_PATH>")
pat = re.compile(r"^(.*) (\d+)(\.[^.]*)$")
for root, dirs, files in os.walk(SDK):
    for f in files:
        m = pat.match(f)
        if m and not (pathlib.Path(root) / (m.group(1) + m.group(3))).exists():
            print("ORPHAN (rename, do not delete):", pathlib.Path(root) / f)
PY
```

Rename orphans back to their proper names, then delete the rest.

### 7.2 Provisioner shows the wrong project

The confirmation banner prints `get_project_id()` — the **gcloud default** —
while all actual operations use `config.project_id` from your env file. If your
gcloud default is stale, the banner shows a project that is not the target.

Targeting is still correct, but never rely on that. Keep them aligned:

```bash
gcloud config set project <PROJECT_ID>
grep GCP_PROJECT_ID .env.production        # must match
```

### 7.3 `docker push` fails with an auth error

`gcloud auth configure-docker` with no argument only configures `gcr.io`.
Artifact Registry needs its host named:

```bash
gcloud auth configure-docker us-central1-docker.pkg.dev
```

`deploy.sh` does this automatically as of the registry consolidation change.

### 7.4 Cloud Run runs as the wrong identity

`deploy.sh` previously selected a service account with
`gcloud iam service-accounts list | head -n 1` — whichever email sorted first.
In a project containing `github-actions-deployer@`, the service ran as the CI
identity: wrong, and over-privileged.

Fixed via the `RUNTIME_SA_NAME` constant. Verify what is actually deployed:

```bash
gcloud run services describe <SERVICE> --region=us-central1 \
  --format="value(spec.template.spec.serviceAccountName)"
```

### 7.5 `/status` reports `degraded`, GCS `unavailable` (403)

```
does not have storage.buckets.get access to the Google Cloud Storage bucket
```

`roles/storage.objectAdmin` does not include `storage.buckets.get`. Add
`roles/storage.legacyBucketReader` on the bucket (see §5.3).

**After granting it, force a new revision.** The app builds its GCS client once
at startup, so a warm container keeps serving the cached failure:

```bash
gcloud run services update <SERVICE> --region=us-central1 \
  --update-env-vars="IAM_FIX_AT=$(date +%s)"
```

### 7.6 Deploy succeeds but exits 1

Two separate causes, both fixed in `deploy.sh`:

- **`tmp_env_file: unbound variable`** — the `EXIT` trap referenced a
  function-local variable. By the time the trap fires the function has returned,
  so under `set -u` the cleanup aborted the script *after* a fully successful
  deploy. The variable must be script-scoped for the trap to see it.
- **"Some smoke tests failed"** — `pytest -m smoke` exits 5 when it collects
  nothing, and no test in this repo carries a `smoke` marker (the registered
  ones are `unit`, `integration`, `auth`, `slow`). Exit 5 is now reported
  distinctly from a real failure.

### 7.7 Cloud Build costs more than expected

`cloudbuild.yaml` must **not** set `machineType`. The 2,500 free
build-minutes/month apply only to the default pool's default machine type;
naming any custom type (e.g. `E2_HIGHCPU_8`) opts the build out of the free tier
entirely and bills every minute.

### 7.8 Cannot read files in `~/Downloads` (macOS)

macOS TCC protects `~/Downloads`, `~/Documents` and `~/Desktop` per-application.
Symptom: `stat` works but `cat`/`unzip` return `Operation not permitted`.

Either move the files elsewhere, or grant Full Disk Access to your terminal in
System Settings → Privacy & Security, then restart it.

### 7.9 `gcloud ... --format="value(...)"` returns blank fields

Some fields are not populated in list output. `artifacts repositories list`
shortens `name` to the basename and leaves `location` empty. Use
`--format=json` and parse the fully-qualified resource name instead.

---

## 8. Adapting this for another app

1. **Copy** `deploy.sh`, `cloudbuild.yaml`, and `scripts/gcp/` into the new repo.
2. **Change** in `deploy.sh`: `RUNTIME_SA_NAME`, the service names in
   `run_deploy_mode()`, and the Artifact Registry repo in the image path.
3. **Change** in `cloudbuild.yaml`: `_SERVICE_NAME`, `_GCS_BUCKET_NAME`,
   `_CLOUD_SQL_INSTANCE`, `_DATABASE_NAME`.
4. **Create** `development-env.yaml` / `production-env.yaml` with that app's
   config. Keep `CLOUD_SQL_INSTANCE` consistent with `.env.production`.
5. **Decide on the database.** Services sharing one database can share one
   Cloud SQL instance with separate databases — far cheaper than an instance
   each. Add a database rather than an instance where you can.
6. **Reuse** the Artifact Registry repo. One repo with several image names keeps
   a single cleanup policy covering everything.
7. Work through Parts 4–6.

Do **not** copy `.env.production` between apps — it contains secrets and is
gitignored for that reason.

### 8.1 Deploying a service that has no `deploy.sh`

Some services (e.g. `doc_intelligence_ai_v3.0`) ship only a `cloudbuild.yaml`.
Deploy those with:

```bash
gcloud builds submit --config cloudbuild.yaml --project=<PROJECT_ID>
```

**Check what gets uploaded first.** `gcloud builds submit` uploads the source
directory to a GCS bucket. Without a `.gcloudignore`, gcloud falls back to
`.gitignore` semantics — but only while the directory is a git repo, which makes
the protection conditional on something unrelated. Write an explicit
`.gcloudignore` and verify it:

```bash
gcloud meta list-files-for-upload | grep -E "\.env|\.key|credential"
```

> **Use `.env*`, not `.env` and `.env.*`.** Neither of those matches
> underscore variants. In `doc_intelligence_ai_v3.0` a file named `.env_dev`
> holds live OpenAI, Google and LlamaCloud keys and was missed by both patterns
> — it would have been uploaded despite being correctly gitignored.

### 8.2 Always set `--service-account` on Cloud Run

If `gcloud run deploy` omits `--service-account`, the service runs as the
**default compute service account**, which in a typical project holds
`roles/run.admin` and `roles/storage.admin`. A running service that can delete
Cloud Run services and wipe buckets is far more privileged than it needs to be.

Name the runtime identity explicitly:

```yaml
--service-account=document-intelligence-api-sa@<PROJECT_ID>.iam.gserviceaccount.com
```

Audit what is actually deployed:

```bash
gcloud run services list --format="table(
  metadata.name,
  spec.template.spec.serviceAccountName:label=RUNS_AS)"
```

### 8.3 Share one Artifact Registry repo

The backend, AI service and frontend all push to the single
`document-intelligence` repo under different image names (`backend-api`,
`ai-api`, `frontend`). One repo means one cleanup policy covering every service
— add a new repo per service and each needs its own, which is how image storage
quietly grows.

---

## 9. Cost management

### 9.1 What this setup costs

| Item | Monthly |
|---|---|
| Cloud SQL `db-f1-micro`, ZONAL, 10GB SSD | ~$9.40 |
| Cloud Run — backend API (1 CPU/1Gi, scale-to-zero) | $0 idle |
| Cloud Run — AI API (2 CPU/2Gi, scale-to-zero) | $0 idle |
| Cloud Build (within free tier — see §7.7) | $0 |
| Artifact Registry (one repo, cleanup policy) | ~$0.25 |
| GCS + Secret Manager | ~$0.25 |
| **Total idle** | **~$10** |

Both Cloud Run services have `min-instances: 0`, so they cost nothing while
idle. The AI service is provisioned at 2 CPU / 2Gi and `max-instances: 5`, so
it is the one that grows fastest under load — it is the first place to look if
the bill moves.

**Adding a service does not add a database.** The AI service shares the
backend's Cloud SQL instance, GCS bucket and Artifact Registry repo. That is
the difference between ~$10/month total and ~$10/month *per service*.

### 9.2 What actually costs money

Things that bill **per hour regardless of traffic** — these are what to look for
when a bill surprises you:

- Cloud SQL instances (any tier, always-on)
- GKE clusters (~$73/month for the control plane alone)
- Memorystore / Redis (~$35+/month)
- Serverless VPC Access connectors (~$9–15/month, 2+ always-on instances)
- Load balancers / forwarding rules (~$18/month each)
- Reserved static IPs not attached to anything
- Vertex AI endpoints with a deployed model
- Cloud Run with `min-instances > 0`

Things that **cost nothing**: enabled APIs, empty projects, service accounts,
IAM bindings, Artifact Registry repos with no images.

Run `./scripts/gcp/audit_costs.sh` to sweep for all of the above.

### 9.3 Public vs private IP

This setup uses a **public IP** with no authorized networks. The Cloud SQL
connector authenticates via IAM over TLS, so the database is not reachable by
password alone.

There is **no cost argument for private IP**: a public IPv4 is free while the
instance is running and only bills (~$0.010/hr) once it is *stopped*. Private IP
would additionally require enabling `servicenetworking` and configuring Direct
VPC egress on Cloud Run, for no saving.

A corollary: **stopping an idle instance saves less than it appears** — you stop
paying for CPU and memory but start paying for the IP, and storage bills either
way.

### 9.4 Finding an unexplained charge

Resource sweeps cannot see subscriptions. If `audit_costs.sh` comes back clean
but the bill is high, it is probably a **subscription** (e.g. Gemini Code
Assist), a support plan, or charges from since-deleted resources.

A charge that is **flat month to month** with ~1–2% drift is a USD-priced
subscription converted to your currency — usage-based charges vary far more.

The only authoritative view is the console:

```
https://console.cloud.google.com/billing/<BILLING_ACCOUNT_ID>/reports
```

Group by **SKU**, set the range to a full month.

**Enable BigQuery billing export** so costs are queryable in future — without it
no CLI or API can tell you what you spent.

> Disabling an API does **not** cancel a subscription. Licences bill at the
> billing-account level, independent of which projects enable the API.

---

## 10. Before real users

The default configuration trades safety for cost. These are conscious
pre-launch trade-offs, not oversights — revisit **all** of them before any real
customer data lands:

- [ ] **Enable automated backups and PITR.** The provisioner passes
      `--no-backup` (`biz2bricks_infra/provision/provisioner.py`). There is
      currently no recovery path from a bad deploy or a dropped table.
- [ ] **Rotate the database password.** Development configs carry weak
      placeholder passwords. Generate a strong one, update Secret Manager, and
      update the Cloud SQL user.
- [ ] **Move off shared-core.** `db-f1-micro` carries **no SLA** and is
      ineligible for committed-use discounts. `db-g1-small` or larger for a
      production commitment.
- [ ] **Separate dev and production.** A single environment is fine pre-launch;
      it is not fine once customers depend on it.
- [ ] **Review CORS.** `PRODUCTION_CORS_ORIGINS` should list real frontend
      origins only — no `localhost`.
- [ ] **Set a billing budget alert** so the next surprise arrives by email
      rather than on the invoice.
- [ ] **Confirm the runtime service account** holds only the roles it needs
      (§7.4).

---

## 11. Deployed services (biz2bricks-dev-v1)

| Service | URL | Health |
|---|---|---|
| `document-intelligence-api-dev` | `https://document-intelligence-api-dev-tfibpeg5zq-uc.a.run.app` | `/health`, `/status` |
| `document-intelligence-ai-api-dev` | `https://document-intelligence-ai-api-dev-tfibpeg5zq-uc.a.run.app` | `/health` only |
| `document-intelligence-ui-dev` | `https://document-intelligence-ui-dev-tfibpeg5zq-uc.a.run.app` | `/` redirects to `/register` |

All three run as `document-intelligence-api-sa@biz2bricks-dev-v1.iam.gserviceaccount.com`.

> The AI service exposes **no `/status`** — it returns 404 there. Use `/health`,
> which reports the database, document agent, sheets agent and LlamaParse
> individually. The two services do not share a health-endpoint contract.

Shared infrastructure:

- Cloud SQL `doc-intelligence-db`, database `doc_intelligence`
- GCS bucket `biz2bricks-dev-v1-document-store`
- Artifact Registry `document-intelligence`, image names `backend-api` /
  `document-intelligence-api-dev` / `ai-api`
- Secrets: `JWT_SECRET_KEY`, `REFRESH_SECRET_KEY`, `DATABASE_PASSWORD`,
  `openai-api-key`, `google-api-key`, `llamaparse-api-key`

---

## 12. CORS between the services

Two separate mechanisms, and neither is obvious.

### Backend API

`PRODUCTION_CORS_ORIGINS` is **only read when `ENVIRONMENT=production`**. A
development deploy ignores it entirely, even when the variable is set on the
service — the app silently runs on its localhost-only defaults, and the frontend
gets blocked with no clue why.

For any non-production deploy use `ADDITIONAL_CORS_ORIGINS`, which applies in
both environments:

```bash
gcloud run services update document-intelligence-api-dev --region=us-central1 \
  --update-env-vars='^@^ADDITIONAL_CORS_ORIGINS=["https://<FRONTEND_URL>"]'
```

### AI service

Reads `CORS_ORIGINS`, and **defaults to `["*"]` with `allow_credentials=True`**
when unset. Starlette echoes the requesting origin back in that combination, so
an unset value means any website can make credentialed calls — to a service
deployed `--allow-unauthenticated` with OpenAI, Google and LlamaCloud keys
mounted. Always set it:

```bash
gcloud run services update document-intelligence-ai-api-dev --region=us-central1 \
  --update-env-vars='^@^CORS_ORIGINS=["https://<FRONTEND_URL>","http://localhost:3000"]'
```

### `--update-env-vars` and commas

gcloud splits `--update-env-vars` on commas, so a JSON array value is parsed as
several variables and the command fails. Prefix with `^@^` to change the
delimiter to `@`, as above. A failed update leaves the variable **unset** rather
than erroring loudly, so always verify:

```bash
gcloud run services describe <SERVICE> --region=us-central1 \
  --format="value(spec.template.spec.containers[0].env)"
```

### Verifying CORS

Anchor the grep to the header **name**. `access-control-allow-headers` lists
`Access-Control-Allow-Origin` among its allowed header names, so an unanchored
grep reports a leak that is not there:

```bash
curl -s -X OPTIONS "$BACKEND/api/v1/auth/login" \
  -H "Origin: https://evil.example.com" \
  -H "Access-Control-Request-Method: POST" -D - -o /dev/null \
  | grep -iE "^access-control-allow-origin:"      # anchored; no output = refused
```

---

## Quick reference

```bash
# Auth
gcloud auth login && gcloud auth application-default login && gh auth login
gcloud config set project <PROJECT_ID>

# Provision
gcloud artifacts repositories create document-intelligence \
  --repository-format=docker --location=us-central1
./scripts/gcp/setup_cleanup_policy.sh --apply
biz2bricks provision full-setup --env-file .env.production

# Deploy + verify
./deploy.sh --deploy --project-id <PROJECT_ID>
curl -s "$(gcloud run services describe document-intelligence-api-dev \
  --region=us-central1 --format='value(status.url)')/status"

# Operate
./scripts/gcp/audit_costs.sh
./scripts/gcp/rollback.sh --env=dev --list
biz2bricks status --env-file .env.production
```
