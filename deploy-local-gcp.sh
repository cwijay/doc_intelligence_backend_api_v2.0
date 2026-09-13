#!/usr/bin/env bash

# =============================================================================
# Local dev server -> GCP backends (Cloud SQL + GCS)
# =============================================================================
# Loads .env.local-gcp, verifies prerequisites (uv, gcloud ADC, env vars),
# then launches uvicorn with hot reload.
#
# First-time setup on a new machine:
#   gcloud auth login
#   gcloud auth application-default login
#   gcloud auth application-default set-quota-project biz2bricks-dev-v1
#   uv sync
#
# Usage:
#   ./deploy-local-gcp.sh                  # start server on 127.0.0.1:8000
#   ./deploy-local-gcp.sh --port 8080      # custom port
#   ./deploy-local-gcp.sh --host 0.0.0.0   # bind on all interfaces
#   ./deploy-local-gcp.sh --no-reload      # disable autoreload
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ENV_FILE=".env.local-gcp"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_ok()      { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }
die()         { log_error "$1"; exit 1; }

command_exists() { command -v "$1" >/dev/null 2>&1; }

# ---------------------------- arg parsing ----------------------------
HOST_OVERRIDE=""
PORT_OVERRIDE=""
RELOAD="true"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --host)       HOST_OVERRIDE="$2"; shift 2 ;;
        --port)       PORT_OVERRIDE="$2"; shift 2 ;;
        --no-reload)  RELOAD="false"; shift ;;
        -h|--help)
            sed -n '3,20p' "$0"
            exit 0
            ;;
        *) die "Unknown option: $1" ;;
    esac
done

# ---------------------------- prerequisites ----------------------------
[[ -f "$ENV_FILE" ]] || die "$ENV_FILE not found in $SCRIPT_DIR"
command_exists uv || die "uv not installed (https://docs.astral.sh/uv/)"
command_exists gcloud || die "gcloud CLI not installed"

log_info "Loading environment from $ENV_FILE"
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# Required vars sanity check
for var in GCP_PROJECT_ID CLOUD_SQL_INSTANCE GCS_BUCKET_NAME DATABASE_PASSWORD JWT_SECRET_KEY; do
    [[ -n "${!var:-}" ]] || die "$var is unset (check $ENV_FILE)"
done

# Verify ADC is configured - the Cloud SQL Connector and GCS client both rely on it.
if ! gcloud auth application-default print-access-token >/dev/null 2>&1; then
    die "Application Default Credentials missing. Run:
       gcloud auth application-default login
       gcloud auth application-default set-quota-project $GCP_PROJECT_ID"
fi
log_ok "ADC available for project $GCP_PROJECT_ID"

# Make sure the active gcloud project matches what the app expects (advisory only).
ACTIVE_PROJECT="$(gcloud config get-value project 2>/dev/null || true)"
if [[ -n "$ACTIVE_PROJECT" && "$ACTIVE_PROJECT" != "$GCP_PROJECT_ID" ]]; then
    log_warn "gcloud active project is '$ACTIVE_PROJECT' but env targets '$GCP_PROJECT_ID'."
    log_warn "ADC will still target $GCP_PROJECT_ID via env vars."
fi

# ---------------------------- launch ----------------------------
HOST="${HOST_OVERRIDE:-${HOST:-127.0.0.1}}"
PORT="${PORT_OVERRIDE:-${PORT:-8000}}"

echo ""
log_info "Starting Document Intelligence API (local -> GCP)"
echo "  Project:        $GCP_PROJECT_ID"
echo "  Cloud SQL:      $CLOUD_SQL_INSTANCE (${CLOUD_SQL_IP_TYPE:-PUBLIC})"
echo "  GCS bucket:     gs://$GCS_BUCKET_NAME"
echo "  Server:         http://$HOST:$PORT"
echo "  API docs:       http://$HOST:$PORT/docs"
echo ""

UVICORN_ARGS=(
    uv run uvicorn app.main:app
    --host "$HOST"
    --port "$PORT"
)

if [[ "$RELOAD" == "true" ]]; then
    UVICORN_ARGS+=(
        --reload
        --reload-dir app
        --reload-exclude '.venv/*'
        --reload-exclude '__pycache__'
        --reload-exclude '*.pyc'
    )
fi

exec "${UVICORN_ARGS[@]}"
