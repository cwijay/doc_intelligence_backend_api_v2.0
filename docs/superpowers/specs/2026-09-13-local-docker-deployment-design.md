# Local Docker Deployment — Design

**Date:** 2026-09-13
**Status:** Approved for planning
**Scope:** Add a self-hosted Docker deployment option for the Biz2Bricks platform, running on a dedicated Mac mini and exposed to the internet via Cloudflare Tunnel.

---

## Goal

Run the Biz2Bricks platform entirely on owned hardware — one `docker compose up` brings up the backend API, AI service, frontend, object storage, database, and cache — and expose it to prospective customers over a public HTTPS hostname.

Remote LLM and document-parsing APIs stay remote. This is a deployment-topology project, not an inference project.

## Non-goals

These are explicitly out of scope. Each is a defensible separate project; none blocks this one.

- **Replacing Gemini File Search with local pgvector RAG.** Document text continues to reach Google via the RAG path. This limits the "your data never leaves the building" claim and is the natural next project.
- **Local LLM inference.** See "Local inference" below for why, and what would change if it is taken on.
- **Folding `agent_builder_v1` into this stack.** It keeps its own compose file and its own Postgres on 5433.
- **Registry-based image distribution.** Phase 2 (see "Packaging").
- **Any change to GCP/Cloud Run behaviour.** See "The compatibility guarantee".

## The compatibility guarantee

GCP deployment is left exactly as it is. Local is an additive option selected by a flag that **defaults to GCP**.

A Cloud Run deployment that sets none of the new environment variables must behave identically before and after this work. This is a testable property, not an aspiration: a test asserts that the resolved settings object and the selected storage backend class are unchanged for the existing production environment file.

Consequences that follow from this:

- `GCSBackend` is kept and stays the default. No GCS code is deleted.
- New settings all have defaults that reproduce today's behaviour.
- The storage refactor is an adapter, not a rewrite: the backend API's `gcs_client` keeps its current method names so no call site changes in the same pass.

---

## Architecture

### Topology

```
                Internet
                    │
         Cloudflare edge  ← TLS terminates here
                    │  (outbound-only tunnel; no inbound ports on the router)
              cloudflared
                    │
                 Caddy :80
   ┌────────────┬───┴────────┬──────────────┐
 app.*        api.*         ai.*         files.*
   │            │            │              │
frontend:3000  api:8000   ai:8001      minio:9000
                │            │              │
                └─────┬──────┘         minio-data (volume)
                      │
             postgres:5432 (pgvector)  +  redis:6379
                      │
                  pg-data (volume)
```

### Containers

| Container | Image | Purpose |
|---|---|---|
| `caddy` | `caddy:2-alpine` | Hostname routing, `Host` preservation for MinIO |
| `cloudflared` | `cloudflare/cloudflared` | Outbound tunnel to the Cloudflare edge |
| `frontend` | built from `document_intelligence_fe_v2` | Next.js standalone |
| `api` | built from `doc_intelligence_backend_api_v2.0` | Backend API |
| `ai` | built from `doc_intelligence_ai_v3.0` | AI service |
| `postgres` | `pgvector/pgvector:pg16` | Database, named volume |
| `redis` | `redis:7-alpine` | Cache backend |
| `minio` | `minio/minio` | S3-compatible object storage, named volume |
| `minio-init` | `minio/mc` | One-shot: create bucket + scoped service account |

All images have arm64 builds, so the stack builds natively on Apple Silicon with no emulation.

### Why four hostnames rather than paths

Two independent reasons, and the second is the one that bites:

1. The frontend bakes `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_AI_API_URL` at **image build time**, and the browser calls both APIs directly. Each needs a real origin with CORS configured.
2. An S3 presigned URL's signature covers the `Host` header. If MinIO signs for `minio:9000` but the browser requests `files.example.com`, signature verification fails. Caddy must proxy `files.*` to MinIO preserving `Host`, and the application must presign against the **public** endpoint.

Hiding MinIO behind a path prefix on the API hostname breaks downloads. This is the first thing to get wrong and the least obvious to debug.

**Build-time consequence:** changing the public domain requires rebuilding the frontend image, not just restarting it. `stack.sh` takes the domain as input and threads it through as build args so this is not rediscovered the hard way.

---

## Configuration flags

Two of the four required flags already exist. This is why the change is additive.

| Concern | Flag | Values | Status |
|---|---|---|---|
| Database | `USE_CLOUD_SQL_CONNECTOR` | `true` \| `false` | exists; `false` already routes through `DATABASE_URL` |
| Cache | `CACHE_BACKEND` | `memory` \| `redis` | exists |
| Object storage | `STORAGE_BACKEND` | `gcs` \| `s3` | **new** |
| Secrets | Secret Manager vs `.env` | — | already env-driven |

Above them sits one convenience flag:

```
DEPLOYMENT_MODE = gcp | local      # default: gcp
```

`DEPLOYMENT_MODE` sets defaults for the other three. Individually-set flags still win, so the escape hatch for mixed configurations (local containers against a real GCS bucket, say) stays open.

### `DEPLOYMENT_MODE` is orthogonal to `ENVIRONMENT`

`ENVIRONMENT` (`development` | `production`) already exists and controls debug behaviour, `/docs` exposure, and CORS strictness. `DEPLOYMENT_MODE` must **not** be folded into it.

All four combinations are real:

| | `ENVIRONMENT=development` | `ENVIRONMENT=production` |
|---|---|---|
| `DEPLOYMENT_MODE=local` | laptop development | **customer pilot on the Mac mini** |
| `DEPLOYMENT_MODE=gcp` | Cloud Run dev project | Cloud Run production |

The bottom-left cell is the whole point of this project, and overloading one variable to mean both "how strict is the runtime" and "where does the infrastructure live" makes it unreachable.

---

## Storage abstraction

### Placement

A new `storage/` package in `biz2bricks_core`, mirroring the existing `db/` package. This follows the precedent already set by `DatabaseManager`: infrastructure that both services need lives in core, API contracts stay local.

```
src/biz2bricks_core/storage/
├── base.py      # StorageBackend protocol
├── s3.py        # S3Backend (aioboto3) — MinIO and any S3 service
├── gcs.py       # GCSBackend — current behaviour preserved
├── config.py    # StorageSettings; STORAGE_BACKEND selects
└── paths.py     # org-scoped key construction, shared by both services
```

The protocol is lifted from the AI service's existing `StorageBackend` ABC (`src/storage/base.py`), extended with the operations the backend API needs: `presign_get`, `presign_put`, `upload_bytes`, `stat`, and the folder-placeholder operations.

### The two-client presigning pattern

`S3Backend` holds two boto3 clients:

- **Internal client** — `http://minio:9000`, used for all server-side reads and writes.
- **Presign client** — configured with the public endpoint (`https://files.example.com`), used only to generate presigned URLs.

Presigning is an offline computation (HMAC over a canonical request); the presign client never opens a connection. It exists solely so the signature matches the host the browser will use. Configuring a single client with the public endpoint instead would force all server-side traffic out through Cloudflare and back, which is both slow and fragile.

### Consumer surface

The backend API's `GCSClient` is ~600 lines with 26 methods, but the application only uses eleven. The adapter surface is therefore small:

| Member | Used by |
|---|---|
| `is_initialized` (property) | crud, download, query, storage services; folder service |
| `initialization_error` (property) | crud, download, query services |
| `health_check()` | `documents_main.py` |
| `upload_file_to_path()` | `document_crud_service.py` |
| `download_document_file()` | `document_download.py` |
| `generate_signed_url()` | `document_download_service.py` |
| `get_document_metadata()` | `document_storage_service.py` |
| `list_files_in_path()` | `document_query_service.py` |
| `create_folder_structure_async()` | `folder_service.py` |
| `delete_folder_structure_async()` | `folder_service.py` |
| `move_folder_structure_async()` | `folder_service.py` |

The remaining fifteen methods are unreferenced. They are not migrated; whether to delete them is a separate cleanup decision recorded but not acted on here.

`generate_signed_url()` is the single biggest simplification: ~110 lines of ADC-versus-service-account branching and IAM `signBlob` fallback collapses to one presign call when the backend is S3. The GCS path keeps its current implementation unchanged.

### Migration sequencing

Deliberately never mid-migration in two repos at once:

1. **Core first.** Build `storage/` with both backends, tested against a MinIO container. Nothing consumes it yet.
2. **AI service.** Smallest change — it already has the right shape. `get_storage()` returns the core backend; `src/storage/gcs.py` is deleted. Two direct `storage.Client()` uses need rerouting: `src/bulk/folder_manager.py:45` and `src/rag/gemini_file_store.py:375`.
3. **Backend API.** `app/core/gcs_client.py` becomes a thin adapter over the core backend, preserving all eleven member names so no call site changes.

`biz2bricks-core` is pinned by git URL in both consumers, so each step includes a pin bump.

### Risk

This touches the upload and download path of a working system across two repos and a shared library. It is the highest-risk part of the project — substantially more so than anything Docker-related — and the plan sequences it accordingly, with MinIO-backed integration tests before either consumer is touched.

---

## Packaging

**Phase 1 (this project):** a new `biz2bricks_stack` repo beside the existing checkouts, holding `docker-compose.yml`, `Caddyfile`, env templates, and `stack.sh`. Build contexts point at sibling directories.

**Phase 2 (later):** multi-arch images in a registry, so the compose file plus a `.env` becomes the artifact handed to a customer who wants to self-host. The phase-1 layout is chosen so that swapping `build:` for `image:` is a small change.

Going straight to phase 2 would mean debugging CI before ever seeing the stack boot.

---

## Operating the Mac mini

### Sizing

Memory is the only spec that matters. Measured against the configured bulk limits (`BULK_CONCURRENT_DOCUMENTS=3`, `BULK_MAX_FILE_SIZE_MB=50`):

| | Idle | Under a bulk job |
|---|---|---|
| postgres + redis + minio | ~1.5 GB | ~2.5 GB |
| api + frontend + caddy + cloudflared | ~0.9 GB | ~1.2 GB |
| ai service (pandas + DuckDB) | ~0.8 GB | 2–4 GB |
| Docker VM + macOS | ~6 GB | ~6 GB |
| **Total** | **~9 GB** | **~14 GB** |

- **16 GB** swaps during bulk processing. Workable for solo development, poor in front of a prospect.
- **24 GB** is the working minimum.
- **32 GB** is the recommendation, and the floor if local inference is ever added.

CPU is not the bottleneck — the stack is mostly blocked on remote API calls. Storage: 512 GB floor, 1 TB if customers upload real volume; Docker images alone are ~10 GB and MinIO grows without bound.

**Upstream bandwidth bottlenecks before the Mac does.** Every document download traverses the office internet connection; on ~20–40 Mbps upstream a 50 MB PDF takes 10–20 seconds to reach a customer. Cloudflare Tunnel does not change this.

### Operational requirements

In descending order of consequence:

1. **Backups.** Time Machine does not correctly capture a live Postgres or MinIO volume — a restore would reproduce corruption. Required: scheduled `pg_dump` plus MinIO replication off the machine. **This must be in place before the first customer pilot**, and it is the single largest risk of hosting customer data on this hardware.
2. **Use Colima, not Docker Desktop.** Docker Desktop requires a logged-in GUI session, which forces auto-login, which conflicts with FileVault. Colima runs headless and is scriptable.
3. **Unattended operation.** `sudo pmset -a sleep 0 disablesleep 1 autorestart 1`; disable automatic macOS updates.
4. **Hardware honesty.** No ECC, consumer SSD, single PSU. Appropriate for demos and pilots given the backup story above; a customer's production data needs an explicit recovery-time conversation.
5. **Dedicated machine.** A second Mac mini isolates the demo from development reboots and `docker compose down`. Worth it for that alone.

---

## Local inference

**Decision: all LLM and parsing calls stay remote.** Recorded here because it will be asked again.

**Mechanical constraint:** Docker Desktop and Colima on macOS have no GPU passthrough. A containerised Ollama runs CPU-only and is unusably slow. Any local inference must run natively on the host with Metal and be reached at `host.docker.internal:11434`. It does not belong in the compose file.

| Workload | Local? | Reasoning |
|---|---|---|
| Embeddings | **Yes, eventually** | `bge-m3` / `nomic-embed-text` ~1 GB, fast, low quality sensitivity |
| PII detection | Yes | Small model, or Presidio with no LLM |
| DocumentAgent (summaries, FAQs) | Maybe | 12–14B summarizes acceptably; Ollama effectively serializes requests |
| SheetsAgent | No | Multi-turn ReAct tool-calling over DuckDB — where local models degrade most |
| ExtractorAgent | No | Strict JSON-schema adherence needs constrained decoding |
| Document parsing (PDF→markdown) | No | Layout-aware multimodal OCR; local alternatives are slower and weaker on tables |

**Concurrency is the deciding factor for demos.** Two or three simultaneous users against a 14B model on one Mac mini means multi-second to multi-minute waits. Remote APIs give effectively unlimited concurrency, and for a prospect demo latency *is* the impression.

Local inference is a **data-residency feature, not a cost saving** — and that claim is currently blocked by Gemini File Search regardless. Honest sequencing:

1. Docker stack with remote models (this project).
2. Replace Gemini File Search with pgvector RAG + local embeddings — document text now genuinely stays on the box.
3. Optional local generation, accepting the parse-quality and concurrency cost.

Step 2 is where local models start to matter.

**Model IDs** are all already environment variables (`OPENAI_SHEET_MODEL`, `DOCUMENT_AGENT_MODEL`, `EXTRACTOR_AGENT_MODEL`, `GEMINI_PARSE_MODEL`, …). Swapping providers or model versions is configuration, not code.

---

## Testing

| Layer | Approach |
|---|---|
| Core storage | Integration tests against a MinIO container; the same suite runs against both `S3Backend` and `GCSBackend` to prove behavioural parity |
| Compatibility guarantee | Assert resolved settings and selected backend class are unchanged for the existing production env file |
| Backend API adapter | Existing document service tests run unmodified — the adapter preserves all eleven member names |
| Stack | Smoke test: register an org, upload a PDF, parse it, generate a summary, download via presigned URL |
| Presigned URLs | Explicit test that a URL signed for the public endpoint verifies when served through Caddy with `Host` preserved |

The presigned-URL test earns its place: it is the failure mode most likely to appear only once the tunnel is in front of the stack.

---

## Open questions

None blocking. Recorded for later:

- Whether to delete the fifteen unreferenced `GCSClient` methods.
- Whether `agent_builder_v1` should eventually share this stack's Postgres.
- Whether phase-2 registry images are built in GitHub Actions or Cloud Build.
