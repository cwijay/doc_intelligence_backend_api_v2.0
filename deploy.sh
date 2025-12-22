#!/usr/bin/env bash

# =============================================================================
# Unified Deployment Script for Document Intelligence Backend
# =============================================================================
#
# Single script for all deployment and development operations:
#   ./deploy.sh --dev                    # Start local dev server
#   ./deploy.sh --test [URL]             # Run smoke tests only
#   ./deploy.sh --deploy                 # Deploy to Cloud Run (development)
#   ./deploy.sh --deploy --env production # Deploy to Cloud Run (production)
#   ./deploy.sh --fast                   # Quick deploy (skip infra checks)
#
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# =============================================================================
# Colors and Logging
# =============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
exit_with_error() { log_error "$1"; exit 1; }

command_exists() { command -v "$1" >/dev/null 2>&1; }

# =============================================================================
# Environment Variable Helpers
# =============================================================================

ENV_KEYS=()
ENV_VALUES=()

env_set() {
    local key="$1" value="$2"
    for i in "${!ENV_KEYS[@]}"; do
        if [[ "${ENV_KEYS[$i]}" == "$key" ]]; then
            ENV_VALUES[$i]="$value"
            return
        fi
    done
    ENV_KEYS+=("$key")
    ENV_VALUES+=("$value")
}

env_get() {
    local key="$1" default="${2-}"
    for i in "${!ENV_KEYS[@]}"; do
        if [[ "${ENV_KEYS[$i]}" == "$key" ]]; then
            echo "${ENV_VALUES[$i]}"
            return
        fi
    done
    echo "$default"
}

trim() {
    local var="$1"
    var="${var#"${var%%[![:space:]]*}"}"
    var="${var%"${var##*[![:space:]]}"}"
    printf '%s' "$var"
}

parse_env_file() {
    local file="$1"
    [[ ! -f "$file" ]] && return

    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line%%#*}"
        line="$(trim "$line")"
        [[ -z "$line" || "$line" == "---" ]] && continue

        if [[ "$line" =~ ^([A-Za-z0-9_]+)[[:space:]]*[:=][[:space:]]*(.*)$ ]]; then
            local key="${BASH_REMATCH[1]}"
            local value="$(trim "${BASH_REMATCH[2]}")"
            # Remove quotes
            if [[ "${#value}" -ge 2 ]]; then
                if [[ "${value:0:1}" == "'" && "${value: -1}" == "'" ]] || \
                   [[ "${value:0:1}" == "\"" && "${value: -1}" == "\"" ]]; then
                    value="${value:1:${#value}-2}"
                fi
            fi
            env_set "$key" "$value"
        fi
    done < "$file"
}

write_env_file() {
    local target="$1"
    : > "$target"
    [[ "${#ENV_KEYS[@]}" -eq 0 ]] && return

    local sorted_keys
    sorted_keys=$(printf '%s\n' "${ENV_KEYS[@]}" | awk '!seen[$0]++' | sort)
    while IFS= read -r key; do
        local value="$(env_get "$key")"
        [[ -z "$value" ]] && continue
        local escaped="${value//\\/\\\\}"
        escaped="${escaped//\"/\\\"}"
        printf '%s: "%s"\n' "$key" "$escaped" >> "$target"
    done <<< "$sorted_keys"
}

# =============================================================================
# GCP Infrastructure Functions
# =============================================================================

ensure_api_enabled() {
    local api="$1"
    if ! gcloud services list --enabled --filter="NAME:$api" --format="value(NAME)" | grep -q "$api"; then
        log_info "Enabling API: $api"
        gcloud services enable "$api" --quiet
    fi
}

ensure_service_account() {
    local email="$1" project="$2"

    if gcloud iam service-accounts describe "$email" --project="$project" --format="value(email)" >/dev/null 2>&1; then
        log_info "Service account exists: $email"
        return
    fi

    local sa_id="${email%%@*}"
    log_info "Creating service account '$email'"
    gcloud iam service-accounts create "$sa_id" \
        --project="$project" \
        --display-name="Document Intelligence Cloud Run" \
        --quiet >/dev/null 2>&1 || true
}

bind_project_role() {
    local project="$1" member="$2" role="$3"
    gcloud projects add-iam-policy-binding "$project" \
        --member="$member" --role="$role" --quiet >/dev/null 2>&1 || true
}

bind_service_account_role() {
    local project="$1" sa="$2" member="$3" role="$4"
    gcloud iam service-accounts add-iam-policy-binding "$sa" \
        --project="$project" --member="$member" --role="$role" --quiet >/dev/null 2>&1 || true
}

ensure_bucket() {
    local bucket="$1" project="$2" region="$3"

    if gcloud storage buckets describe "gs://$bucket" --project="$project" >/dev/null 2>&1; then
        log_info "GCS bucket exists: gs://$bucket"
    else
        log_info "Creating GCS bucket: gs://$bucket"
        gcloud storage buckets create "gs://$bucket" \
            --project="$project" --location="$region" \
            --uniform-bucket-level-access --quiet >/dev/null 2>&1 || \
            exit_with_error "Failed to create GCS bucket"
        log_success "Created GCS bucket: gs://$bucket"
    fi

    # Enable versioning
    gcloud storage buckets update "gs://$bucket" --project="$project" --versioning --quiet >/dev/null 2>&1 || true
}

# =============================================================================
# Docker and Deployment Functions
# =============================================================================

build_and_push_image() {
    local image="$1"
    shift
    local tags=("$@")

    log_info "Building Docker image for Cloud Run (linux/amd64)"
    local build_args=(docker build --platform linux/amd64)
    for tag in "${tags[@]}"; do
        build_args+=(-t "$tag")
    done
    build_args+=(".")
    "${build_args[@]}"
    log_success "Docker image built"

    for tag in "${tags[@]}"; do
        log_info "Pushing image: $tag"
        docker push "$tag"
    done
    log_success "Docker images pushed to Container Registry"
}

deploy_cloud_run() {
    local service="$1" region="$2" image="$3" env_file="$4"
    local memory="$5" cpu="$6" concurrency="$7" max_instances="$8"
    local timeout="$9" service_account="${10}" cloud_sql_instance="${11}"

    log_info "Deploying Cloud Run service '$service' in region '$region'"

    # Build deploy command with optional Cloud SQL instance
    local deploy_cmd=(
        gcloud run deploy "$service"
        --image "$image"
        --region "$region"
        --platform managed
        --allow-unauthenticated
        --memory "$memory"
        --cpu "$cpu"
        --concurrency "$concurrency"
        --max-instances "$max_instances"
        --timeout "$timeout"
        --service-account "$service_account"
        --env-vars-file "$env_file"
    )

    # Add Cloud SQL instance if provided
    if [[ -n "$cloud_sql_instance" ]]; then
        log_info "Adding Cloud SQL instance: $cloud_sql_instance"
        deploy_cmd+=(--add-cloudsql-instances "$cloud_sql_instance")
    fi

    "${deploy_cmd[@]}"
    log_success "Cloud Run deployment completed"
}

health_check() {
    local url="$1" attempts="${2:-5}" delay="${3:-10}"

    command_exists curl || { log_warn "curl not found; skipping health check"; return; }

    log_info "Checking service health at $url/health"
    for ((i=1; i<=attempts; i++)); do
        if curl -fs "$url/health" >/dev/null; then
            log_success "Health check passed"
            return 0
        fi
        log_warn "Health check attempt $i/$attempts failed; retrying in ${delay}s"
        sleep "$delay"
    done
    log_warn "Health check did not succeed. Service may still be warming up."
    return 1
}

# =============================================================================
# MODE: Development Server (--dev)
# =============================================================================

run_dev_mode() {
    echo ""
    log_info "Starting Document Intelligence Backend (Development Mode)"
    echo "Working Directory: $(pwd)"
    echo ""

    # Check prerequisites
    [[ ! -f ".env" ]] && exit_with_error ".env file not found! Copy .env.example to .env and configure."
    command_exists uv || exit_with_error "uv is not installed! See: https://docs.astral.sh/uv/"

    echo "Server: http://127.0.0.1:8000"
    echo "API Docs: http://127.0.0.1:8000/docs"
    echo ""
    echo "Press Ctrl+C to stop"
    echo ""

    exec uv run uvicorn app.main:app \
        --reload \
        --host 127.0.0.1 \
        --port 8000 \
        --reload-dir app \
        --reload-exclude '.venv/*' \
        --reload-exclude '*.pyc' \
        --reload-exclude '__pycache__' \
        --reload-exclude '.git' \
        --reload-exclude 'node_modules' \
        --reload-exclude '.pytest_cache' \
        --reload-exclude '*.egg-info' \
        --reload-exclude 'build' \
        --reload-exclude 'dist' \
        --reload-exclude '*.log'
}

# =============================================================================
# MODE: Test Only (--test)
# =============================================================================

run_test_mode() {
    local test_url="${1:-}"

    echo ""
    log_info "Running Smoke Tests"

    # Determine test URL
    if [[ -z "$test_url" ]]; then
        if [[ -f ".env.test" ]]; then
            source .env.test
            test_url="${TEST_BASE_URL:-http://localhost:8000}"
        else
            test_url="http://localhost:8000"
        fi
    fi

    log_info "Target URL: $test_url"
    echo ""

    # Health check first
    log_info "Checking service health..."
    if curl -sf "$test_url/health" > /dev/null 2>&1; then
        log_success "Service is responding"
    else
        exit_with_error "Service health check failed! Make sure service is running at: $test_url"
    fi

    echo ""
    log_info "Running smoke test suite..."
    echo ""

    command_exists uv || exit_with_error "uv is not installed!"

    export TEST_BASE_URL="$test_url"
    uv run pytest tests/ -v -m "smoke" --asyncio-mode=auto --tb=short

    echo ""
    log_success "All smoke tests passed!"
}

# =============================================================================
# MODE: Deploy (--deploy / --fast)
# =============================================================================

run_deploy_mode() {
    local project_id="$1"
    local environment="$2"
    local region="$3"
    local fast_mode="$4"
    local skip_tests="$5"
    local bucket_override="$6"

    echo ""
    log_info "Deploying to Cloud Run"
    log_info "Environment: $environment"
    log_info "Project: $project_id"
    log_info "Region: $region"
    echo ""

    # Environment-specific settings
    local service_name log_level max_instances env_file
    if [[ "$environment" == "production" ]]; then
        service_name="document-intelligence-api"
        log_level="INFO"
        max_instances="10"
        env_file="production-env.yaml"
    else
        service_name="document-intelligence-api-dev"
        log_level="DEBUG"
        max_instances="5"
        env_file="development-env.yaml"
    fi

    local memory="1Gi"
    local cpu="1"
    local concurrency="80"
    local timeout="300"
    local service_account=""

    # Validate prerequisites
    command_exists gcloud || exit_with_error "gcloud is not installed!"
    command_exists docker || exit_with_error "docker is not installed!"
    [[ ! -f "Dockerfile" ]] && exit_with_error "Dockerfile not found!"
    [[ ! -f "pyproject.toml" ]] && exit_with_error "pyproject.toml not found!"

    # Set GCP project
    log_info "Setting GCP project to $project_id"
    gcloud config set project "$project_id" --quiet >/dev/null
    gcloud auth configure-docker --quiet >/dev/null

    # Full deploy mode: ensure infrastructure
    if [[ "$fast_mode" != "true" ]]; then
        log_info "Ensuring GCP APIs are enabled"
        local apis=(
            run.googleapis.com
            cloudbuild.googleapis.com
            containerregistry.googleapis.com
            iam.googleapis.com
            sqladmin.googleapis.com
            storage-component.googleapis.com
        )
        for api in "${apis[@]}"; do
            ensure_api_enabled "$api"
        done

        # Parse environment file
        parse_env_file "$env_file"

        # Determine bucket name
        local bucket_name="$bucket_override"
        [[ -z "$bucket_name" ]] && bucket_name="$(env_get "GCS_BUCKET_NAME")"
        [[ -z "$bucket_name" ]] && bucket_name="${project_id}-document-intelligence"
        env_set "GCS_BUCKET_NAME" "$bucket_name"

        # Detect or create service account
        service_account="$(gcloud run services describe "$service_name" --region "$region" --format="value(spec.template.spec.serviceAccountName)" 2>/dev/null || true)"
        if [[ -z "$service_account" ]]; then
            service_account="$(gcloud iam service-accounts list --project="$project_id" --format="value(email)" | head -n 1)"
        fi
        if [[ -z "$service_account" ]]; then
            service_account="document-int-run@$project_id.iam.gserviceaccount.com"
        fi

        ensure_service_account "$service_account" "$project_id"

        # Grant roles
        log_info "Granting required roles to $service_account"
        local roles=(
            roles/run.invoker
            roles/cloudsql.client
            roles/storage.objectAdmin
            roles/logging.logWriter
            roles/cloudtrace.agent
        )
        for role in "${roles[@]}"; do
            bind_project_role "$project_id" "serviceAccount:$service_account" "$role"
        done

        # Ensure bucket exists
        ensure_bucket "$bucket_name" "$project_id" "$region"
    else
        # Fast mode: minimal setup
        log_info "Fast mode: skipping infrastructure checks"
        parse_env_file "$env_file"

        # Get existing service account
        service_account="$(gcloud run services describe "$service_name" --region "$region" --format="value(spec.template.spec.serviceAccountName)" 2>/dev/null || true)"
        if [[ -z "$service_account" ]]; then
            service_account="$(gcloud iam service-accounts list --project="$project_id" --format="value(email)" | head -n 1)"
        fi
        [[ -z "$service_account" ]] && exit_with_error "No service account found. Run full deploy first."
    fi

    # Set common environment variables
    env_set "ENVIRONMENT" "$environment"
    env_set "GCP_PROJECT_ID" "$project_id"
    env_set "GOOGLE_CLOUD_PROJECT" "$project_id"
    env_set "LOG_LEVEL" "$log_level"
    env_set "LOG_FORMAT" "json"

    # Set database environment variables
    local cloud_sql_instance="$(env_get "CLOUD_SQL_INSTANCE")"
    if [[ -n "$cloud_sql_instance" ]]; then
        env_set "CLOUD_SQL_INSTANCE" "$cloud_sql_instance"
        env_set "DATABASE_NAME" "$(env_get "DATABASE_NAME" "doc_intelligence")"
        env_set "DATABASE_USER" "$(env_get "DATABASE_USER" "postgres")"
        env_set "USE_CLOUD_SQL_CONNECTOR" "true"
        env_set "CLOUD_SQL_IP_TYPE" "PUBLIC"
        log_info "Cloud SQL instance configured: $cloud_sql_instance"
    else
        log_warn "CLOUD_SQL_INSTANCE not set in env file - database connection may fail"
    fi

    # Create temp env file
    local tmp_env_file
    tmp_env_file="$(mktemp)"
    trap 'rm -f "$tmp_env_file"' EXIT
    write_env_file "$tmp_env_file"

    # Build and push image
    local image="gcr.io/$project_id/$service_name"
    local timestamp_tag="$image:$(date +%s)"
    local latest_tag="$image:latest"
    build_and_push_image "$image" "$latest_tag" "$timestamp_tag"

    # Deploy to Cloud Run
    deploy_cloud_run "$service_name" "$region" "$latest_tag" "$tmp_env_file" \
        "$memory" "$cpu" "$concurrency" "$max_instances" "$timeout" "$service_account" "$cloud_sql_instance"

    # Get service URL
    local service_url
    service_url="$(gcloud run services describe "$service_name" --region "$region" --format="value(status.url)" 2>/dev/null || true)"

    if [[ -n "$service_url" ]]; then
        log_success "Service URL: $service_url"
        health_check "$service_url"

        # Run smoke tests if not skipped
        if [[ "$skip_tests" != "true" ]]; then
            echo ""
            log_info "Running smoke tests..."
            export TEST_BASE_URL="$service_url"
            if command_exists uv; then
                uv run pytest tests/ -v -m "smoke" --asyncio-mode=auto --tb=short || \
                    log_warn "Some smoke tests failed"
            else
                log_warn "uv not found; skipping smoke tests"
            fi
        fi
    fi

    echo ""
    log_success "Deployment complete!"
    echo ""
    echo "Next steps:"
    echo "  - View logs: gcloud run services logs tail $service_name --region=$region"
    [[ -n "$service_url" ]] && echo "  - Service URL: $service_url"

    rm -f "$tmp_env_file"
}

# =============================================================================
# Help
# =============================================================================

show_help() {
    cat <<EOF
Document Intelligence Backend - Unified Deployment Script

USAGE:
    ./deploy.sh <MODE> [OPTIONS]

MODES:
    --dev                     Start local development server
    --test [URL]              Run smoke tests against URL (default: localhost:8000)
    --deploy                  Deploy to Cloud Run
    --fast                    Quick deploy (skip infrastructure checks)
    -h, --help                Show this help message

DEPLOY OPTIONS:
    --project-id PROJECT      GCP project ID (required for deploy)
    --env development|production  Target environment (default: development)
    --region REGION           Cloud Run region (default: us-central1)
    --bucket BUCKET           Override GCS bucket name
    --skip-tests              Skip smoke tests after deployment

EXAMPLES:
    # Local development
    ./deploy.sh --dev

    # Run tests against production
    ./deploy.sh --test https://my-api.run.app

    # Deploy to development
    ./deploy.sh --deploy --project-id my-project

    # Deploy to production
    ./deploy.sh --deploy --project-id my-project --env production

    # Quick deploy (skip infra checks)
    ./deploy.sh --fast --project-id my-project
EOF
}

# =============================================================================
# Main
# =============================================================================

main() {
    local mode=""
    local project_id="${GCP_PROJECT_ID:-}"
    local environment="development"
    local region="us-central1"
    local fast_mode="false"
    local skip_tests="false"
    local bucket_override=""
    local test_url=""

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dev)
                mode="dev"; shift ;;
            --test)
                mode="test"
                shift
                # Check if next arg is a URL (not starting with --)
                if [[ $# -gt 0 && ! "$1" =~ ^-- ]]; then
                    test_url="$1"; shift
                fi
                ;;
            --deploy)
                mode="deploy"; shift ;;
            --fast)
                mode="deploy"; fast_mode="true"; shift ;;
            --project-id)
                project_id="$2"; shift 2 ;;
            --env)
                environment="$2"; shift 2 ;;
            --region)
                region="$2"; shift 2 ;;
            --bucket)
                bucket_override="$2"; shift 2 ;;
            --skip-tests)
                skip_tests="true"; shift ;;
            -h|--help)
                show_help; exit 0 ;;
            *)
                exit_with_error "Unknown option: $1. Use --help for usage." ;;
        esac
    done

    # Default to help if no mode specified
    [[ -z "$mode" ]] && { show_help; exit 0; }

    # Execute mode
    case "$mode" in
        dev)
            run_dev_mode
            ;;
        test)
            run_test_mode "$test_url"
            ;;
        deploy)
            [[ -z "$project_id" ]] && exit_with_error "--project-id is required for deployment"
            run_deploy_mode "$project_id" "$environment" "$region" "$fast_mode" "$skip_tests" "$bucket_override"
            ;;
    esac
}

main "$@"
