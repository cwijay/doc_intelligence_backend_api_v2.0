# Local Docker Stack Implementation Plan (Phase 1 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the whole Biz2Bricks platform up on a Mac mini with one `docker compose up`, reachable over public HTTPS, with Postgres and Redis self-hosted and object storage still pointed at the existing GCS bucket.

**Architecture:** A new `biz2bricks_stack` repo holds `docker-compose.yml`, a `Caddyfile`, env templates and `stack.sh`, building images from sibling repo checkouts. Postgres (pgvector) and Redis replace Cloud SQL and Memorystore via flags that already exist in the codebase. Caddy routes four hostnames to the three app containers; `cloudflared` dials out to the Cloudflare edge so no inbound ports are opened. GCS access from inside containers uses a mounted service-account key.

**Tech Stack:** Docker Compose, Colima, `pgvector/pgvector:pg16`, `redis:7-alpine`, `caddy:2-alpine`, `cloudflare/cloudflared`, existing `python:3.12-slim` and `node:20-alpine` app Dockerfiles.

**Spec:** `docs/superpowers/specs/2026-09-13-local-docker-deployment-design.md`

## Global Constraints

- **No application logic changes.** The only permitted edits to the three app repos in this phase are Dockerfile dependency fixes. All behaviour changes come from environment variables that already exist.
- **GCP deployment must be unaffected.** No change to `cloudbuild.yaml`, `deploy.sh`, `production-env.yaml`, or any default value in `app/core/config.py`.
- **`STORAGE_BACKEND` and `DEPLOYMENT_MODE` are NOT introduced in this phase.** They arrive in phase 2 with the storage abstraction. This phase sets the already-existing flags (`USE_CLOUD_SQL_CONNECTOR=false`, `CACHE_BACKEND=redis`) explicitly.
- **Repo paths.** All five repos are siblings under `/Users/chamindawijayasundara/Documents/biz_to_bricks/biz_2_bricks_v2/`. The stack repo is created as a sixth sibling named `biz2bricks_stack`.
- **Architecture is arm64.** Do not pass `--platform linux/amd64` anywhere; every image used has a native arm64 build.
- **Secrets never get committed.** `secrets/` and `.env` are gitignored in the stack repo from the first commit.
- **Domain placeholder.** This plan writes `example.com`. Substitute the real domain when running; `stack.sh` threads it through as build args.

---

### Task 1: Stack repo skeleton

**Files:**
- Create: `../biz2bricks_stack/.gitignore`
- Create: `../biz2bricks_stack/README.md`
- Create: `../biz2bricks_stack/.env.example`
- Create: `../biz2bricks_stack/secrets/.gitkeep`

**Interfaces:**
- Consumes: nothing
- Produces: `.env` variable names used by every later task — `POSTGRES_PASSWORD`, `DATABASE_NAME`, `JWT_SECRET_KEY`, `REFRESH_SECRET_KEY`, `GCP_PROJECT_ID`, `GCS_BUCKET_NAME`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `LLAMA_CLOUD_API_KEY`, `PUBLIC_DOMAIN`, `CLOUDFLARE_TUNNEL_TOKEN`

- [ ] **Step 1: Install and start Colima with enough memory**

Colima's default VM is 2 GB of RAM, which will not run this stack — the AI
service alone can exceed that during a bulk job. Size it explicitly.

```bash
brew install colima docker docker-compose
colima start --cpu 6 --memory 16 --disk 100 --vm-type vz --mount-type virtiofs
```

On a 32 GB machine use `--memory 20`. On 16 GB use `--memory 10` and expect
swapping under bulk load.

- [ ] **Step 2: Verify the runtime is up and correctly sized**

```bash
colima status
docker info --format '{{.MemTotal}} {{.NCPU}}'
```

Expected: Colima running, and `MemTotal` reporting roughly the requested memory
in bytes (16 GB ≈ `17179869184`). A value near `2147483648` means the VM was
already running at the old default — `colima stop && colima start ...` to resize.

- [ ] **Step 3: Make Colima start at boot**

Without this, a power cut leaves the machine up with the stack down.

```bash
brew services start colima
brew services list | grep colima
```

Expected: `colima` listed as `started`.

- [ ] **Step 4: Create the repo directory and initialise git**

```bash
cd /Users/chamindawijayasundara/Documents/biz_to_bricks/biz_2_bricks_v2
mkdir -p biz2bricks_stack/secrets
cd biz2bricks_stack
git init
touch secrets/.gitkeep
```

- [ ] **Step 5: Write `.gitignore`**

```gitignore
.env
.env.local
secrets/*
!secrets/.gitkeep
*.log
```

- [ ] **Step 6: Write `.env.example`**

```bash
# ---- Public hostnames ----
# Four subdomains are required. See README for why MinIO/files needs its own.
PUBLIC_DOMAIN=example.com

# ---- Database (self-hosted Postgres) ----
POSTGRES_PASSWORD=change-me-to-a-long-random-string
DATABASE_NAME=doc_intelligence
DATABASE_USER=postgres

# ---- Auth secrets ----
# Generate each with: python3 -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET_KEY=
REFRESH_SECRET_KEY=

# ---- GCS (still used for object storage in phase 1) ----
GCP_PROJECT_ID=biz2bricks-dev-v1
GCS_BUCKET_NAME=biz2bricks-dev-v1-document-store
GCS_PREFIX=

# ---- Remote model APIs ----
OPENAI_API_KEY=
GOOGLE_API_KEY=
LLAMA_CLOUD_API_KEY=

# ---- Cloudflare Tunnel ----
# From Cloudflare Zero Trust > Networks > Tunnels > create tunnel > copy token
CLOUDFLARE_TUNNEL_TOKEN=
```

- [ ] **Step 7: Write `README.md`**

````markdown
# biz2bricks_stack

Self-hosted Docker deployment of the Biz2Bricks platform.

## Prerequisites

- Colima (not Docker Desktop — see below)
- The five sibling repos checked out beside this one
- A GCP service-account key at `secrets/gcp-sa-key.json`
- A Cloudflare tunnel token

## Quick start

```bash
cp .env.example .env    # then fill it in
./stack.sh up
```

## Why Colima and not Docker Desktop

Docker Desktop needs a logged-in GUI session, which forces auto-login and
conflicts with FileVault. Colima runs headless and is scriptable, which is
what a machine acting as a server needs.

## Why four hostnames

The frontend bakes `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_AI_API_URL` at image
build time and the browser calls both APIs directly, so each needs a real
origin with CORS. From phase 3, `files.` additionally needs its own origin
because an S3 presigned URL's signature covers the `Host` header.

Changing `PUBLIC_DOMAIN` requires rebuilding the frontend image, not just
restarting it. `stack.sh` handles this.
````

- [ ] **Step 8: Verify nothing secret is trackable**

```bash
cd ../biz2bricks_stack
cp .env.example .env
echo '{"fake":"key"}' > secrets/gcp-sa-key.json
git add -A --dry-run 2>&1 | grep -E '\.env$|gcp-sa-key' && echo "LEAK" || echo "clean"
```

Expected: `clean`

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "chore: scaffold biz2bricks_stack repo"
```

---

### Task 2: Postgres and Redis with schema bootstrap

**Files:**
- Create: `../biz2bricks_stack/docker-compose.yml`
- Create: `../biz2bricks_stack/postgres-init/01-extensions.sql`

**Interfaces:**
- Consumes: `.env` from Task 1
- Produces: services `postgres` (5432) and `redis` (6379) on the default compose network; `DATABASE_URL=postgresql+asyncpg://postgres:${POSTGRES_PASSWORD}@postgres:5432/${DATABASE_NAME}` for later tasks

- [ ] **Step 1: Write the pgvector extension init script**

`postgres-init/01-extensions.sql` — Postgres runs any `.sql` in `/docker-entrypoint-initdb.d` on first boot of an empty data volume.

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

- [ ] **Step 2: Write the first half of `docker-compose.yml`**

```yaml
name: biz2bricks

services:
  postgres:
    image: pgvector/pgvector:pg16
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${DATABASE_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${DATABASE_NAME}
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./postgres-init:/docker-entrypoint-initdb.d:ro
    ports:
      - "127.0.0.1:5432:5432"   # localhost only, for psql and biz2bricks CLI
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DATABASE_USER} -d ${DATABASE_NAME}"]
      interval: 5s
      timeout: 5s
      retries: 12

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: ["redis-server", "--save", "60", "1", "--loglevel", "warning"]
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 12

networks:
  default:
    # Docker's default address pools can be exhausted on a machine already running
    # several compose projects; without this the network create fails with
    # "all predefined address pools have been fully subnetted". Pick a range
    # outside the exhausted 172.16-172.31 and 192.168.x defaults rather than
    # reclaiming another project's network.
    ipam:
      config:
        - subnet: 10.55.0.0/24

volumes:
  pgdata:
  redisdata:
```

Note the `127.0.0.1:` prefix on the Postgres port binding. Without it Docker
publishes on all interfaces, which on a machine that is about to be internet-facing
would expose Postgres directly.

- [ ] **Step 3: Bring both up and verify health**

```bash
cd ../biz2bricks_stack
docker compose up -d postgres redis
sleep 15
docker compose ps --format '{{.Service}} {{.Health}}'
```

Expected: `postgres healthy` and `redis healthy`

- [ ] **Step 4: Verify the pgvector extension actually installed**

```bash
docker compose exec -T postgres psql -U postgres -d doc_intelligence \
  -c "SELECT extname FROM pg_extension WHERE extname='vector';"
```

Expected: one row, `vector`. If empty, the data volume pre-existed the init
script — `docker compose down -v` and repeat Step 3.

- [ ] **Step 5: Create the schema using the existing infra CLI**

The `biz2bricks` CLI reads `DATABASE_URL` and works against any Postgres, not
just Cloud SQL. Run it from the backend repo where it is installed.

```bash
cd ../doc_intelligence_backend_api_v2.0
cat > /tmp/stack-db.env <<'EOF'
USE_CLOUD_SQL_CONNECTOR=false
DATABASE_URL=postgresql+asyncpg://postgres:CHANGE_ME@localhost:5432/doc_intelligence
DATABASE_NAME=doc_intelligence
DATABASE_USER=postgres
# `db init` reads DATABASE_URL alone, but `seed tiers` builds its own connection
# from the individual fields and fails with "password authentication failed"
# without this line. Both are required.
DATABASE_PASSWORD=CHANGE_ME
EOF
# substitute the real POSTGRES_PASSWORD into /tmp/stack-db.env first
uv run biz2bricks db init --env-file /tmp/stack-db.env
uv run biz2bricks seed tiers --env-file /tmp/stack-db.env
```

- [ ] **Step 6: Verify the expected tables exist**

```bash
cd ../biz2bricks_stack
docker compose exec -T postgres psql -U postgres -d doc_intelligence -c "\dt" | tail -25
docker compose exec -T postgres psql -U postgres -d doc_intelligence \
  -c "SELECT count(*) FROM subscription_tiers;"
```

Expected: 21 tables. `organizations`, `users`, `folders`, `documents` and
`audit_logs` must all be present, alongside the usage, AI and session tables. The
tier count must be greater than zero (currently 3). Older docs cite 18 tables —
the schema has grown; trust the named tables, not the count.

- [ ] **Step 7: Commit**

```bash
git add docker-compose.yml postgres-init/
git commit -m "feat: add postgres (pgvector) and redis services"
```

---

### Task 3a: litellm gateway (own instance)

**Files:**
- Create: `../biz2bricks_stack/litellm/config.yaml`
- Modify: `../biz2bricks_stack/docker-compose.yml`
- Modify: `../biz2bricks_stack/.env.example`

**Interfaces:**
- Consumes: nothing from earlier tasks
- Produces: service `litellm` reachable in-network at `http://litellm:4000`; Task 4 sets
  `OPENAI_API_BASE=http://litellm:4000/v1` and `OPENAI_API_KEY=${LITELLM_MASTER_KEY}`

**Why this exists:** the platform owns its gateway rather than borrowing another
project's container, so that project's compose lifecycle cannot take biz2bricks' model
access down.

**What this does NOT cover:** document parsing (`src/rag/gemini_parse_util.py`) and RAG
(`src/rag/gemini_file_store.py`) call `google.genai.Client()` directly with file-upload
semantics. These are not chat completions and cannot be proxied by litellm.
`GOOGLE_API_KEY` therefore stays a direct dependency of the AI service.

- [ ] **Step 1: Add gateway variables to `.env.example`**

Append:

```bash
# ---- litellm gateway ----
# The AI service authenticates to litellm with this value; litellm then uses the
# provider keys below. Generate with: python3 -c "import secrets; print('sk-'+secrets.token_hex(24))"
LITELLM_MASTER_KEY=
# Upstream provider key litellm uses on your behalf. Leave empty until you have one —
# the container still starts, and model calls fail with a clear auth error.
LITELLM_OPENAI_API_KEY=
```

- [ ] **Step 2: Write `litellm/config.yaml`**

Two models are served: `gpt-5.6-terra` and `gpt-5.6-luna`. The AI service's own
defaults (`gpt-5.1-codex-mini`, `gpt-4o-mini`, `gpt-5-mini`) are NOT used — Task 4
overrides every model env var explicitly, so the gateway serves only what is
actually requested.

```yaml
model_list:
  - model_name: gpt-5.6-terra
    litellm_params:
      model: openai/gpt-5.6-terra
      api_key: os.environ/LITELLM_OPENAI_API_KEY
  - model_name: gpt-5.6-luna
    litellm_params:
      model: openai/gpt-5.6-luna
      api_key: os.environ/LITELLM_OPENAI_API_KEY

router_settings:
  num_retries: 2
  timeout: 120
  fallbacks:
    - gpt-5.6-terra: [gpt-5.6-luna]

litellm_settings:
  drop_params: true

general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
```

No `database_url` is set, so litellm runs keyless-mode with the master key only —
no extra Postgres, no virtual-key management to maintain. No `success_callback` is
set either; this instance deliberately has no Langfuse dependency.

- [ ] **Step 3: Add the `litellm` service to `docker-compose.yml`**

```yaml
  litellm:
    image: ghcr.io/berriai/litellm:main-stable
    restart: unless-stopped
    command: ["--config", "/app/config.yaml", "--port", "4000"]
    environment:
      LITELLM_MASTER_KEY: ${LITELLM_MASTER_KEY}
      LITELLM_OPENAI_API_KEY: ${LITELLM_OPENAI_API_KEY}
    volumes:
      - ./litellm/config.yaml:/app/config.yaml:ro
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:4000/health/liveliness"]
      interval: 15s
      timeout: 5s
      start_period: 30s
      retries: 5
```

No host port is published — port 4000 is already taken on this machine by another
project's gateway, and nothing outside the compose network needs to reach this one.

- [ ] **Step 4: Start it and verify liveness**

```bash
cd ../biz2bricks_stack
docker compose up -d litellm
sleep 30
docker compose ps --format '{{.Service}} {{.Health}}' | grep litellm
```

Expected: `litellm healthy`

- [ ] **Step 5: Verify the model list is served and matches the AI service's names**

```bash
docker compose exec -T litellm \
  curl -s -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" http://localhost:4000/v1/models
```

Expected: a JSON list containing exactly `gpt-5.6-terra` and `gpt-5.6-luna`. A 401
means `LITELLM_MASTER_KEY` is not set in `.env`. If litellm logs an unknown-model
error at startup, correct the IDs in `config.yaml` — they are passed through to
OpenAI verbatim and have not been validated against a live account.

This verifies routing and naming only. It does not verify that upstream calls
succeed — that needs a real `LITELLM_OPENAI_API_KEY` and is covered by Task 10.

- [ ] **Step 6: Confirm the borrowed gateway is untouched**

```bash
docker ps --format '{{.Names}}' | grep -c '^infra-litellm-1$'
```

Expected: `1` — the other project's gateway is still running and was not modified.

- [ ] **Step 7: Commit**

```bash
git add litellm/config.yaml docker-compose.yml .env.example
git commit -m "feat: add own litellm gateway instance"
```

---

### Task 3: Backend API container

**Files:**
- Modify: `../doc_intelligence_backend_api_v2.0/Dockerfile` (the `uv sync` line)
- Modify: `../biz2bricks_stack/docker-compose.yml`

**Interfaces:**
- Consumes: `postgres`, `redis` from Task 2
- Produces: service `api` on port 8000, reachable in-network at `http://api:8000`

- [ ] **Step 1: Write the failing check — confirm the redis extra is missing**

`CACHE_BACKEND=redis` fails at import because `app/core/cache.py` imports
`redis.asyncio` lazily and the Dockerfile installs no extras.

```bash
cd ../doc_intelligence_backend_api_v2.0
grep -n 'uv sync' Dockerfile
```

Expected: `RUN uv sync --frozen --no-cache --no-dev` — note the absence of `--extra redis`.

- [ ] **Step 2: Add the redis extra to the Dockerfile**

Change that line to:

```dockerfile
RUN uv sync --frozen --no-cache --no-dev --extra redis
```

This is additive: Cloud Run builds gain the `redis` package but keep
`CACHE_BACKEND=memory`, so behaviour there is unchanged.

- [ ] **Step 3: Add the `api` service to `docker-compose.yml`**

Insert under `services:`, after `redis`:

```yaml
  api:
    build:
      context: ../doc_intelligence_backend_api_v2.0
      dockerfile: Dockerfile
    restart: unless-stopped
    depends_on:
      postgres: {condition: service_healthy}
      redis: {condition: service_healthy}
    environment:
      PORT: 8000
      ENVIRONMENT: production
      DEBUG: "false"
      LOG_LEVEL: INFO

      # Database — self-hosted, connector off
      USE_CLOUD_SQL_CONNECTOR: "false"
      DATABASE_URL: postgresql+asyncpg://${DATABASE_USER}:${POSTGRES_PASSWORD}@postgres:5432/${DATABASE_NAME}
      DATABASE_NAME: ${DATABASE_NAME}
      DATABASE_USER: ${DATABASE_USER}
      DATABASE_PASSWORD: ${POSTGRES_PASSWORD}

      # Cache — self-hosted redis
      CACHE_ENABLED: "true"
      CACHE_BACKEND: redis
      REDIS_HOST: redis
      REDIS_PORT: 6379

      # Object storage — still GCS in phase 1
      GCP_PROJECT_ID: ${GCP_PROJECT_ID}
      GCS_BUCKET_NAME: ${GCS_BUCKET_NAME}
      GOOGLE_APPLICATION_CREDENTIALS: /secrets/gcp-sa-key.json

      # Auth
      JWT_SECRET_KEY: ${JWT_SECRET_KEY}
      REFRESH_SECRET_KEY: ${REFRESH_SECRET_KEY}

      # Public surface
      ALLOWED_HOST_PATTERNS: '["*.${PUBLIC_DOMAIN}","api","localhost","127.0.0.1"]'
      PRODUCTION_CORS_ORIGINS: 'https://app.${PUBLIC_DOMAIN}'
    volumes:
      - ./secrets/gcp-sa-key.json:/secrets/gcp-sa-key.json:ro
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 15s
      timeout: 5s
      start_period: 40s
      retries: 5
```

Mounting a real service-account key also fixes signed URLs. `generate_signed_url()`
takes the `isinstance(credentials, service_account.Credentials)` branch and signs
directly, skipping the IAM `signBlob` fallback that cannot work off-GCP.

- [ ] **Step 4: Generate the service-account key**

```bash
cd ../doc_intelligence_backend_api_v2.0
uv run biz2bricks sa create-key -o ../biz2bricks_stack/secrets/gcp-sa-key.json \
  --env-file .env.production
chmod 600 ../biz2bricks_stack/secrets/gcp-sa-key.json
```

- [ ] **Step 5: Build and start, then verify health**

The `api` service publishes no host port — it is reached through Caddy from
Task 6 — so check it from inside the container.

```bash
cd ../biz2bricks_stack
docker compose up -d --build api
sleep 45
docker compose exec -T api curl -sf http://localhost:8000/health \
  || docker compose logs --tail=50 api
```

Expected: a JSON health payload, HTTP 200.

- [ ] **Step 6: Verify Postgres, GCS and Redis are all wired**

```bash
docker compose exec -T api curl -s http://localhost:8000/status
```

Expected: the payload reports PostgreSQL reachable and GCS initialised. A GCS
failure here means the key mount or `GCP_PROJECT_ID` is wrong — check
`docker compose logs api | grep -i gcs`.

- [ ] **Step 7: Commit**

```bash
cd ../doc_intelligence_backend_api_v2.0
git add Dockerfile
git commit -m "build: install redis extra so CACHE_BACKEND=redis works in-container"
cd ../biz2bricks_stack
git add docker-compose.yml
git commit -m "feat: add backend api service"
```

---

### Task 4: AI service container

**Files:**
- Modify: `../biz2bricks_stack/docker-compose.yml`

**Interfaces:**
- Consumes: `postgres`, `redis` from Task 2
- Produces: service `ai` on port 8001, reachable in-network at `http://ai:8001`

- [ ] **Step 1: Add the `ai` service to `docker-compose.yml`**

The AI service's Dockerfile already installs everything from `requirements.txt`,
including WeasyPrint's native dependencies, so no Dockerfile change is needed.

```yaml
  ai:
    build:
      context: ../doc_intelligence_ai_v3.0
      dockerfile: Dockerfile
    restart: unless-stopped
    depends_on:
      postgres: {condition: service_healthy}
      litellm: {condition: service_healthy}
    environment:
      PORT: 8001
      LOG_LEVEL: INFO
      DEBUG: "false"

      # Database
      DATABASE_ENABLED: "true"
      USE_CLOUD_SQL_CONNECTOR: "false"
      DATABASE_URL: postgresql+asyncpg://${DATABASE_USER}:${POSTGRES_PASSWORD}@postgres:5432/${DATABASE_NAME}
      DATABASE_NAME: ${DATABASE_NAME}
      DATABASE_USER: ${DATABASE_USER}
      DATABASE_PASSWORD: ${POSTGRES_PASSWORD}

      # Object storage — still GCS in phase 1.
      # Note the variable is GCS_BUCKET here, not GCS_BUCKET_NAME as in the API.
      GCS_BUCKET: ${GCS_BUCKET_NAME}
      GCS_PREFIX: ${GCS_PREFIX}
      PARSED_DIRECTORY: parsed
      GENERATED_DIRECTORY: generated
      GOOGLE_APPLICATION_CREDENTIALS: /secrets/gcp-sa-key.json

      # Chat models route through the stack's own litellm gateway.
      # langchain-openai reads OPENAI_API_BASE, so no code change is needed.
      OPENAI_API_BASE: http://litellm:4000/v1
      OPENAI_API_KEY: ${LITELLM_MASTER_KEY}

      # Pinned explicitly so the gateway only serves models it actually has.
      # terra takes the reasoning-heavy paths, luna the summarisation path.
      OPENAI_SHEET_MODEL: gpt-5.6-terra
      EXTRACTOR_AGENT_MODEL: gpt-5.6-terra
      DOCUMENT_AGENT_MODEL: gpt-5.6-luna
      EXTRACTOR_FALLBACK_MODEL: gpt-5.6-luna

      # Document parsing and RAG bypass litellm — they use the native google-genai
      # SDK with file-upload semantics, which is not a chat-completions call.
      GOOGLE_API_KEY: ${GOOGLE_API_KEY}
      LLAMA_CLOUD_API_KEY: ${LLAMA_CLOUD_API_KEY}
      DOCUMENT_PARSER: gemini
    volumes:
      - ./secrets/gcp-sa-key.json:/secrets/gcp-sa-key.json:ro
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
      interval: 15s
      timeout: 5s
      start_period: 90s
      retries: 5
```

The 90-second `start_period` is deliberate — importing LangGraph, LangChain,
pandas and DuckDB is slow, and a shorter window marks the container unhealthy
before it has finished booting.

- [ ] **Step 2: Build and start**

```bash
docker compose up -d --build ai
sleep 90
docker compose ps --format '{{.Service}} {{.Health}}' | grep ai
```

Expected: `ai healthy`

- [ ] **Step 3: Verify it answers and reached the database**

```bash
docker compose exec -T ai curl -sf http://localhost:8001/health
docker compose logs ai 2>&1 | grep -iE 'error|traceback' | head -20
```

Expected: HTTP 200 from `/health`; no tracebacks in the logs.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add ai service"
```

---

### Task 5: Frontend container

**Files:**
- Modify: `../biz2bricks_stack/docker-compose.yml`

**Interfaces:**
- Consumes: `api`, `ai`
- Produces: service `frontend` on port 3000

- [ ] **Step 1: Add the `frontend` service to `docker-compose.yml`**

`next.config.ts` already sets `output: 'standalone'`, so the existing multi-stage
Dockerfile works unchanged. The `NEXT_PUBLIC_*` values are build args, not runtime
env — they are compiled into the client bundle.

```yaml
  frontend:
    build:
      context: ../document_intelligence_fe_v2
      dockerfile: Dockerfile
      args:
        NEXT_PUBLIC_API_URL: https://api.${PUBLIC_DOMAIN}
        NEXT_PUBLIC_AI_API_URL: https://ai.${PUBLIC_DOMAIN}
        NEXT_PUBLIC_APP_NAME: Biz2Bricks
        NEXT_PUBLIC_APP_VERSION: 1.0.0
        NEXT_PUBLIC_AUTH_ENABLED: "true"
        NEXT_PUBLIC_GCS_BUCKET_NAME: ${GCS_BUCKET_NAME}
    restart: unless-stopped
    depends_on:
      api: {condition: service_healthy}
    environment:
      PORT: 3000
      HOSTNAME: 0.0.0.0
```

- [ ] **Step 2: Build and start**

```bash
docker compose up -d --build frontend
sleep 20
docker compose exec -T frontend wget -qO- http://localhost:3000 | head -5
```

Expected: HTML output beginning with a doctype.

- [ ] **Step 3: Verify the API URL was baked in, not left blank**

An empty build arg silently produces a bundle that calls `undefined/api/v1/...`,
which only surfaces as a broken page much later.

```bash
docker compose exec -T frontend sh -c \
  "grep -ro 'api\.${PUBLIC_DOMAIN}' .next/static | head -3"
```

Expected: at least one match. No matches means the build arg did not reach the
build — check that `PUBLIC_DOMAIN` is set in `.env`.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add frontend service"
```

---

### Task 6: Caddy reverse proxy

**Files:**
- Create: `../biz2bricks_stack/Caddyfile`
- Modify: `../biz2bricks_stack/docker-compose.yml`

**Interfaces:**
- Consumes: `frontend`, `api`, `ai`
- Produces: service `caddy` listening on `:80` in-network, routing three hostnames; `files.` is added in phase 3

- [ ] **Step 1: Write the `Caddyfile`**

TLS is terminated at the Cloudflare edge, so Caddy serves plain HTTP on :80 and
must not try to provision certificates itself — hence `auto_https off`.

```caddy
{
    auto_https off
    admin off
}

:80 {
    @app host app.{$PUBLIC_DOMAIN}
    handle @app {
        reverse_proxy frontend:3000
    }

    @api host api.{$PUBLIC_DOMAIN}
    handle @api {
        reverse_proxy api:8000
    }

    @ai host ai.{$PUBLIC_DOMAIN}
    handle @ai {
        reverse_proxy ai:8001
    }

    handle {
        respond "unknown host" 404
    }
}
```

Caddy's `reverse_proxy` preserves the inbound `Host` header by default. Do not
add a `header_up Host` override — phase 3's MinIO presigned URLs depend on this
default behaviour.

- [ ] **Step 2: Add the `caddy` service to `docker-compose.yml`**

```yaml
  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    depends_on: [frontend, api, ai]
    environment:
      PUBLIC_DOMAIN: ${PUBLIC_DOMAIN}
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
    ports:
      - "127.0.0.1:8080:80"   # localhost only; cloudflared reaches caddy in-network
```

- [ ] **Step 3: Start Caddy and verify config validity**

```bash
docker compose up -d caddy
sleep 5
docker compose exec -T caddy caddy validate --config /etc/caddy/Caddyfile
```

Expected: `Valid configuration`

- [ ] **Step 4: Verify each hostname routes to the right service**

Caddy matches on `Host`, so test by setting it explicitly rather than editing
`/etc/hosts`.

```bash
curl -s -o /dev/null -w '%{http_code}\n' -H "Host: app.${PUBLIC_DOMAIN}" http://localhost:8080/
curl -s -o /dev/null -w '%{http_code}\n' -H "Host: api.${PUBLIC_DOMAIN}" http://localhost:8080/health
curl -s -o /dev/null -w '%{http_code}\n' -H "Host: ai.${PUBLIC_DOMAIN}"  http://localhost:8080/health
curl -s -w '%{http_code}\n' -H "Host: nope.${PUBLIC_DOMAIN}" http://localhost:8080/
```

Expected: `200`, `200`, `200`, then `unknown host404`.

A 404 on the `api` line usually means `TrustedHostMiddleware` rejected the host —
confirm `ALLOWED_HOST_PATTERNS` in the `api` service includes `*.${PUBLIC_DOMAIN}`.

- [ ] **Step 5: Commit**

```bash
git add Caddyfile docker-compose.yml
git commit -m "feat: add caddy reverse proxy with hostname routing"
```

---

### Task 7: Cloudflare Tunnel

**Files:**
- Modify: `../biz2bricks_stack/docker-compose.yml`

**Interfaces:**
- Consumes: `caddy`
- Produces: public HTTPS at `app.`, `api.`, `ai.` — no inbound router ports

- [ ] **Step 1: Create the tunnel in Cloudflare**

In the Cloudflare dashboard: **Zero Trust → Networks → Tunnels → Create a tunnel**,
choose *Cloudflared*, name it `biz2bricks`, and copy the token into
`CLOUDFLARE_TUNNEL_TOKEN` in `.env`.

Then add three public hostnames, all pointing at the same origin:

| Subdomain | Domain | Service |
|---|---|---|
| `app` | `${PUBLIC_DOMAIN}` | `http://caddy:80` |
| `api` | `${PUBLIC_DOMAIN}` | `http://caddy:80` |
| `ai` | `${PUBLIC_DOMAIN}` | `http://caddy:80` |

Caddy does the host-based routing, so every hostname targets the same origin.

- [ ] **Step 2: Add the `cloudflared` service to `docker-compose.yml`**

```yaml
  cloudflared:
    image: cloudflare/cloudflared:latest
    restart: unless-stopped
    depends_on: [caddy]
    command: tunnel --no-autoupdate run --token ${CLOUDFLARE_TUNNEL_TOKEN}
```

No ports are published. The container dials out to Cloudflare; nothing dials in.

- [ ] **Step 3: Start it and confirm the tunnel registered**

```bash
docker compose up -d cloudflared
sleep 20
docker compose logs cloudflared 2>&1 | grep -iE 'registered|connection.*established' | head -5
```

Expected: lines confirming registered tunnel connections (usually four edge connections).

- [ ] **Step 4: Verify from outside the machine**

Run these from a phone on cellular data, or any network that is not the Mac's,
so you are genuinely testing the public path.

```bash
curl -sf https://api.${PUBLIC_DOMAIN}/health
curl -sf https://ai.${PUBLIC_DOMAIN}/health
curl -s -o /dev/null -w '%{http_code}\n' https://app.${PUBLIC_DOMAIN}/
```

Expected: two health payloads and `200`.

- [ ] **Step 5: Confirm no inbound ports were opened**

```bash
docker compose ps --format '{{.Service}} {{.Ports}}'
```

Expected: only `127.0.0.1:` bindings appear. Any `0.0.0.0:` binding is a bug —
fix it before leaving the stack running.

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: expose stack via cloudflare tunnel"
```

---

### Task 8: `stack.sh` orchestration

**Files:**
- Create: `../biz2bricks_stack/stack.sh`

**Interfaces:**
- Consumes: everything above
- Produces: `./stack.sh up|down|rebuild|logs|status|backup`

- [ ] **Step 1: Write `stack.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

[[ -f .env ]] || { echo "ERROR: .env missing — copy .env.example and fill it in"; exit 1; }
set -a; source .env; set +a

for var in PUBLIC_DOMAIN POSTGRES_PASSWORD JWT_SECRET_KEY REFRESH_SECRET_KEY \
           GCP_PROJECT_ID GCS_BUCKET_NAME CLOUDFLARE_TUNNEL_TOKEN; do
    [[ -n "${!var:-}" ]] || { echo "ERROR: $var is empty in .env"; exit 1; }
done
[[ -f secrets/gcp-sa-key.json ]] || { echo "ERROR: secrets/gcp-sa-key.json missing"; exit 1; }

case "${1:-up}" in
  up)      docker compose up -d ;;
  down)    docker compose down ;;
  # The frontend bakes PUBLIC_DOMAIN at build time, so a domain change needs this.
  rebuild) docker compose build --no-cache frontend api ai && docker compose up -d ;;
  logs)    shift; docker compose logs -f "$@" ;;
  status)  docker compose ps --format 'table {{.Service}}\t{{.Status}}\t{{.Ports}}' ;;
  backup)  ./backup.sh ;;
  *)       echo "usage: $0 {up|down|rebuild|logs|status|backup}"; exit 1 ;;
esac
```

- [ ] **Step 2: Make it executable and verify the guard rails fire**

```bash
chmod +x stack.sh
mv .env .env.bak && ./stack.sh up; echo "exit=$?"; mv .env.bak .env
```

Expected: `ERROR: .env missing — copy .env.example and fill it in` and `exit=1`.

- [ ] **Step 3: Verify the happy path**

```bash
./stack.sh status
```

Expected: a table listing all seven services as running or healthy.

- [ ] **Step 4: Commit**

```bash
git add stack.sh
git commit -m "feat: add stack.sh orchestration wrapper"
```

---

### Task 9: Backups and unattended operation

**Files:**
- Create: `../biz2bricks_stack/backup.sh`
- Create: `../biz2bricks_stack/com.biz2bricks.backup.plist`
- Modify: `../biz2bricks_stack/README.md`

**Interfaces:**
- Consumes: the running stack
- Produces: nightly `pg_dump` to a local directory; documented Mac server settings

This task exists because the spec names backups as the single largest risk of
hosting customer data on this hardware. Time Machine cannot correctly capture a
live Postgres volume — restoring one reproduces corruption.

- [ ] **Step 1: Write `backup.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
set -a; source .env; set +a

DEST="${BACKUP_DIR:-$HOME/biz2bricks-backups}"
mkdir -p "$DEST"
STAMP=$(date +%Y%m%d-%H%M%S)
OUT="$DEST/pg-$STAMP.sql.gz"

docker compose exec -T postgres \
    pg_dump -U "$DATABASE_USER" -d "$DATABASE_NAME" --no-owner \
  | gzip > "$OUT"

# Fail loudly on a truncated dump rather than silently keeping a useless file.
if [[ $(stat -f%z "$OUT") -lt 1024 ]]; then
    echo "ERROR: dump suspiciously small ($OUT)" >&2
    exit 1
fi

find "$DEST" -name 'pg-*.sql.gz' -mtime +14 -delete
echo "backed up to $OUT"
```

- [ ] **Step 2: Verify a backup round-trips**

A backup that has never been restored is not a backup.

```bash
chmod +x backup.sh
./backup.sh
LATEST=$(ls -t ~/biz2bricks-backups/pg-*.sql.gz | head -1)
docker compose exec -T postgres psql -U postgres -c "CREATE DATABASE restoretest;"
gunzip -c "$LATEST" | docker compose exec -T postgres psql -U postgres -d restoretest >/dev/null
docker compose exec -T postgres psql -U postgres -d restoretest \
  -c "SELECT count(*) FROM subscription_tiers;"
docker compose exec -T postgres psql -U postgres -c "DROP DATABASE restoretest;"
```

Expected: the tier count matches the live database.

- [ ] **Step 3: Write the launchd job for nightly backups**

`com.biz2bricks.backup.plist` — substitute the real absolute path:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.biz2bricks.backup</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/USERNAME/Documents/biz_to_bricks/biz_2_bricks_v2/biz2bricks_stack/backup.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict><key>Hour</key><integer>3</integer><key>Minute</key><integer>0</integer></dict>
    <key>StandardOutPath</key><string>/tmp/biz2bricks-backup.log</string>
    <key>StandardErrorPath</key><string>/tmp/biz2bricks-backup.err</string>
</dict>
</plist>
```

- [ ] **Step 4: Install and verify the job is registered**

```bash
cp com.biz2bricks.backup.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.biz2bricks.backup.plist
launchctl list | grep biz2bricks
```

Expected: one line containing `com.biz2bricks.backup`.

- [ ] **Step 5: Apply the Mac server settings**

```bash
sudo pmset -a sleep 0 disablesleep 1 autorestart 1
sudo softwareupdate --schedule off
pmset -g | grep -E 'sleep|autorestart'
```

Expected: `sleep 0` and `autorestart 1`.

- [ ] **Step 6: Append an Operations section to `README.md`**

````markdown
## Operations

- Nightly `pg_dump` at 03:00 via launchd, 14-day retention, to `~/biz2bricks-backups`.
- **Off-machine copies are still required** — a dump on the same SSD does not
  survive the SSD. Sync `~/biz2bricks-backups` to external or offsite storage.
- Sleep disabled, auto-restart after power loss enabled, automatic macOS
  updates off (they reboot the machine).
- Verify a restore quarterly, not just that dumps exist.

### Object storage caveat (phase 1)

Documents live in GCS, not on this machine, so `backup.sh` covers the database
only. Once phase 3 moves storage to MinIO, the MinIO volume must be added here.
````

- [ ] **Step 7: Commit**

```bash
git add backup.sh com.biz2bricks.backup.plist README.md
git commit -m "feat: add nightly database backups and Mac server settings"
```

---

### Task 10: End-to-end smoke test

**Files:**
- Create: `../biz2bricks_stack/smoke-test.sh`

**Interfaces:**
- Consumes: the fully running stack
- Produces: a repeatable pass/fail check for the whole platform

- [ ] **Step 1: Write `smoke-test.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
set -a; source .env; set +a

API="https://api.${PUBLIC_DOMAIN}"
FAILED=0
check() { if eval "$2" >/dev/null 2>&1; then echo "  ok   $1"; else echo "  FAIL $1"; FAILED=1; fi }

echo "Health:"
check "api /health"     "curl -sf $API/health"
check "api /status"     "curl -sf $API/status"
check "ai /health"      "curl -sf https://ai.${PUBLIC_DOMAIN}/health"
check "frontend"        "curl -sf https://app.${PUBLIC_DOMAIN}/"

echo "Registration and auth:"
EMAIL="smoke-$(date +%s)@example.com"
REG=$(curl -sf -X POST "$API/api/v1/auth/register" \
      -H 'Content-Type: application/json' \
      -d "{\"email\":\"$EMAIL\",\"password\":\"SmokeTest123!\",\"organization_name\":\"Smoke $(date +%s)\"}" || echo '')
check "register"        "[ -n '$REG' ]"

TOKEN=$(printf '%s' "$REG" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("access_token",""))' 2>/dev/null || echo '')
check "access token"    "[ -n '$TOKEN' ]"
check "authed request"  "curl -sf -H 'Authorization: Bearer $TOKEN' $API/api/v1/folders"

echo
[ $FAILED -eq 0 ] && echo "PASS" || { echo "FAIL"; exit 1; }
```

- [ ] **Step 2: Run it**

```bash
chmod +x smoke-test.sh
./smoke-test.sh
```

Expected: every line `ok`, final line `PASS`.

If registration fails, check `docker compose logs api | tail -50`. The most
common cause is `PRODUCTION_CORS_ORIGINS` or `ALLOWED_HOST_PATTERNS` not matching
the real domain.

- [ ] **Step 3: Verify a full restart recovers cleanly**

This is what a power cut looks like. It is worth knowing it works before one happens.

```bash
./stack.sh down && ./stack.sh up
sleep 120
./smoke-test.sh
```

Expected: `PASS`. Data persists because Postgres uses a named volume.

- [ ] **Step 4: Commit**

```bash
git add smoke-test.sh
git commit -m "test: add end-to-end smoke test"
```

---

## What phase 1 does not deliver

Carried into the later plans, recorded here so nothing is assumed done:

- **Object storage is still GCS.** Documents leave the machine. MinIO arrives in phase 3.
- **`STORAGE_BACKEND` and `DEPLOYMENT_MODE` do not exist yet.** Phase 2.
- **The `files.` hostname is not routed.** Phase 3, with the presigned-URL host test.
- **Gemini File Search still stores document text at Google.** Out of scope entirely.
- **`agent_builder_v1` is not in this stack.** Out of scope entirely.
- **Backups cover the database only.** The MinIO volume joins `backup.sh` in phase 3.

## Follow-on plans

- **Phase 2 — Storage abstraction:** `biz2bricks_core/storage/` with `S3Backend` and `GCSBackend`, `STORAGE_BACKEND` and `DEPLOYMENT_MODE` flags, the compatibility-guarantee test, integration tests against a MinIO container. No consumer changes.
- **Phase 3 — Migration and MinIO:** migrate the AI service, then the backend API adapter (eleven members), add MinIO and `minio-init` to the stack, route `files.`, flip the flag, extend backups.
