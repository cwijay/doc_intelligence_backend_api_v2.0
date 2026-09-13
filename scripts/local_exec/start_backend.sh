#!/usr/bin/env bash
# =============================================================================
# Run the backend API on the host, against the Docker infrastructure that
# setup_infra.sh brought up.
#
# The API runs natively (not containerised) so you get uvicorn hot reload.
#
# Usage:
#   ./start_backend.sh                 # 127.0.0.1:8000, reload on
#   ./start_backend.sh --port 8080
#   ./start_backend.sh --no-reload
#   ./start_backend.sh --host 0.0.0.0  # refuses unless --i-know, see below
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="$SCRIPT_DIR/.env.local"

RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'; BLUE=$'\033[0;34m'; NC=$'\033[0m'
info() { echo "${BLUE}[INFO]${NC} $*"; }
ok()   { echo "${GREEN}[OK]${NC} $*"; }
warn() { echo "${YELLOW}[WARN]${NC} $*"; }
die()  { echo "${RED}[ERROR]${NC} $*" >&2; exit 1; }

HOST=127.0.0.1
PORT=8000
RELOAD=true
FORCE_BIND=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --host) HOST="$2"; shift 2 ;;
        --port) PORT="$2"; shift 2 ;;
        --no-reload) RELOAD=false; shift ;;
        --i-know) FORCE_BIND=true; shift ;;
        -h|--help) sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) die "Unknown option: $1" ;;
    esac
done

# This API currently has unauthenticated endpoints (users, folders and
# organizations routers carry no auth dependency), so binding it to anything
# other than loopback exposes destructive, cross-tenant operations to the
# network. Refuse by default rather than make that easy to do by accident.
if [[ "$HOST" != "127.0.0.1" && "$HOST" != "localhost" && "$FORCE_BIND" != true ]]; then
    die "Refusing to bind to $HOST.
       This API has unauthenticated endpoints including DELETE routes.
       Pass --i-know only if you genuinely intend to expose it."
fi

[[ -f "$ENV_FILE" ]] || die "$ENV_FILE not found. Run ./setup_infra.sh first."
command -v uv >/dev/null || die "uv not found (https://docs.astral.sh/uv/)"

set -a; source "$ENV_FILE"; set +a

# ------------------------------------------------------- infra preflight ----
# Fail here with a clear message rather than letting the API start and then
# throw connection errors on the first request.
docker info >/dev/null 2>&1 || die "Docker daemon not reachable. Start Docker, then ./setup_infra.sh"
for c in b2blocal-postgres b2blocal-redis; do
    state=$(docker inspect "$c" --format '{{.State.Status}}' 2>/dev/null || echo missing)
    [[ "$state" == running ]] || die "Container $c is '$state'. Run ./setup_infra.sh first."
done
ok "Infrastructure containers running"

# --------------------------------------------------------------- app env ----
export ENVIRONMENT=development
export DEBUG=true
export LOG_LEVEL=DEBUG
export LOG_FORMAT=text
export HOST PORT

# Database — local container, Cloud SQL connector off.
export USE_CLOUD_SQL_CONNECTOR=false
export DATABASE_URL="postgresql+asyncpg://${DATABASE_USER}:${POSTGRES_PASSWORD}@localhost:${POSTGRES_HOST_PORT}/${DATABASE_NAME}"
export DATABASE_HOST=localhost
export DATABASE_PORT="${POSTGRES_HOST_PORT}"
export DATABASE_PASSWORD="${POSTGRES_PASSWORD}"
export DB_POOL_SIZE=2
export DB_MAX_OVERFLOW=5

# Cache — the containerised Redis.
export CACHE_ENABLED=true
export CACHE_BACKEND=redis
export REDIS_HOST=localhost
export REDIS_PORT="${REDIS_HOST_PORT}"

# Auth.
export JWT_SECRET_KEY REFRESH_SECRET_KEY

# CORS for a Next.js dev frontend.
export CORS_ORIGINS='["http://localhost:3000","http://127.0.0.1:3000"]'

# --------------------------------------------------------- object storage ----
# Use a service-account key so local dev hits the same GCS bucket as the
# self-hosted stack, and so signed-URL downloads work: user credentials from
# `gcloud auth application-default login` cannot sign URLs without an extra
# iam.serviceAccounts.signBlob grant, whereas a key signs locally.
#
# Unsetting GOOGLE_APPLICATION_CREDENTIALS does NOT disable GCS, which is what
# the previous version of this block assumed. _should_initialize() in
# app/core/gcs_client.py also accepts ambient ADC via google.auth.default(), so
# a leftover personal ADC on the machine makes the client initialise against
# the wrong identity and then fail the bucket probe. Blanking GCP_PROJECT_ID is
# what actually forces disabled mode, because _should_initialize() requires
# credentials AND a project id.
GCP_SA_KEY_FILE="${GCP_SA_KEY_FILE:-$REPO_ROOT/../biz2bricks_stack/secrets/gcp-sa-key.json}"
if [[ -f "$GCP_SA_KEY_FILE" ]]; then
    export GOOGLE_APPLICATION_CREDENTIALS="$GCP_SA_KEY_FILE"
    # GCS_BUCKET_NAME is read by pydantic from the repo .env, not by this
    # shell, so read it back for the banner rather than printing a guess.
    _bucket="${GCS_BUCKET_NAME:-$(sed -n 's/^GCS_BUCKET_NAME=//p' "$REPO_ROOT/.env" 2>/dev/null | tr -d '"' | head -1)}"
    STORAGE_DESC="gs://${_bucket:-unknown-bucket}"
    ok "Object storage enabled (key: $GCP_SA_KEY_FILE)"
else
    unset GOOGLE_APPLICATION_CREDENTIALS || true
    export GCP_PROJECT_ID=""
    STORAGE_DESC="disabled (no service-account key)"
    warn "No service-account key at $GCP_SA_KEY_FILE"
    warn "Object storage disabled - document upload and download will not work."
    warn "Set GCP_SA_KEY_FILE in $ENV_FILE to point at a key."
fi

# `redis` is an optional extra in pyproject.toml. Without it the cache layer
# silently falls back to in-memory, which hides Redis-specific bugs — exactly
# the class of bug that broke registration once already.
info "Syncing dependencies (including the redis extra)"
(cd "$REPO_ROOT" && uv sync --extra redis --quiet) || die "uv sync failed"

cd "$REPO_ROOT"
RELOAD_ARGS=()
# --reload-dir app matters: without it, changes under .venv retrigger reload
# endlessly and the server never settles.
[[ "$RELOAD" == true ]] && RELOAD_ARGS=(--reload --reload-dir app)

cat <<EOF

${GREEN}Starting backend API${NC}
  URL        http://${HOST}:${PORT}
  Docs       http://${HOST}:${PORT}/docs
  Database   localhost:${POSTGRES_HOST_PORT}/${DATABASE_NAME}
  Cache      redis localhost:${REDIS_HOST_PORT}
  Storage    ${STORAGE_DESC}
  Org ID     ${BOOTSTRAP_ORG_ID:-<run setup_infra.sh>}
  Reload     ${RELOAD}

EOF

# macOS ships bash 3.2, where "${arr[@]}" on an empty array trips `set -u`.
exec uv run uvicorn app.main:app --host "$HOST" --port "$PORT" ${RELOAD_ARGS[@]+"${RELOAD_ARGS[@]}"}
