#!/usr/bin/env bash

# Comprehensive Cloud Run deployment script for the Document Intelligence backend.
# Combines prerequisite checks, IAM configuration, GCS/Firestore validation,
# container build/push, and Cloud Run rollout in a single, idempotent workflow.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"

cd "$REPO_ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warn() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

exit_with_error() {
    log_error "$1"
    exit 1
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

trim() {
    local var="$1"
    var="${var#"${var%%[![:space:]]*}"}"
    var="${var%"${var##*[![:space:]]}"}"
    printf '%s' "$var"
}

ENV_KEYS=()
ENV_VALUES=()

env_set() {
    local key="$1"
    local value="$2"
    local i
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
    local key="$1"
    local default="${2-}"
    local i
    for i in "${!ENV_KEYS[@]}"; do
        if [[ "${ENV_KEYS[$i]}" == "$key" ]]; then
            echo "${ENV_VALUES[$i]}"
            return
        fi
    done
    echo "$default"
}

parse_env_file() {
    local file="$1"
    if [[ ! -f "$file" ]]; then
        log_warn "Environment file '$file' not found. Will rely on overrides."
        return
    fi

    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line%%#*}"
        line="$(trim "$line")"
        [[ -z "$line" ]] && continue
        [[ "$line" == "---" ]] && continue

        if [[ "$line" =~ ^([A-Za-z0-9_]+)[[:space:]]*[:=][[:space:]]*(.*)$ ]]; then
            local key value
            key="${BASH_REMATCH[1]}"
            value="${BASH_REMATCH[2]}"
            value="$(trim "$value")"
            if [[ "${#value}" -ge 2 ]]; then
                if [[ "${value:0:1}" == "'" && "${value: -1}" == "'" ]]; then
                    value="${value:1:${#value}-2}"
                elif [[ "${value:0:1}" == "\"" && "${value: -1}" == "\"" ]]; then
                    value="${value:1:${#value}-2}"
                fi
            fi
            env_set "$key" "$value"
        fi
    done < "$file"
}

format_env_value() {
    local value="$1"
    local escaped="${value//\\/\\\\}"
    escaped="${escaped//\"/\\\"}"
    printf '"%s"' "$escaped"
}

write_env_file() {
    local target="$1"
    : > "$target"
    if [[ "${#ENV_KEYS[@]}" -eq 0 ]]; then
        log_warn "No environment variables collected; Cloud Run will run with minimal defaults."
        return
    fi

    local sorted_keys
    sorted_keys=$(printf '%s\n' "${ENV_KEYS[@]}" | awk '!seen[$0]++' | sort)
    while IFS= read -r key; do
        local value
        value="$(env_get "$key")"
        [[ -z "$value" ]] && continue
        printf '%s: %s\n' "$key" "$(format_env_value "$value")" >> "$target"
    done <<< "$sorted_keys"
}

ensure_command() {
    local cmd="$1"
    command_exists "$cmd" || exit_with_error "Required command '$cmd' not found. Please install it and re-run."
}

ensure_api_enabled() {
    local api="$1"
    if ! gcloud services list --enabled --filter="NAME:$api" --format="value(NAME)" | grep -q "$api"; then
        log_info "Enabling API: $api"
        gcloud services enable "$api" --quiet
    else
        log_info "API already enabled: $api"
    fi
}

ensure_service_account() {
    local email="$1"
    local project="$2"

    if gcloud iam service-accounts describe "$email" --project="$project" --format="value(email)" >/dev/null 2>&1; then
        log_info "Service account exists: $email"
        return
    fi

    local sa_project
    if [[ "$email" == *"@"* ]]; then
        local prefix="${email%%@*}"
        local domain="${email##*@}"
        if [[ "$domain" == "appspot.gserviceaccount.com" ]]; then
            sa_project="$prefix"
        else
            sa_project="${domain%%.*}"
        fi
    else
        sa_project=""
    fi
    if [[ "$sa_project" != "$project" ]]; then
        exit_with_error "Service account '$email' does not belong to project '$project'. Provide a valid account."
    fi

    local sa_id="${email%%@*}"
    log_info "Creating service account '$email'"
    if gcloud iam service-accounts create "$sa_id" \
        --project="$project" \
        --display-name="Document Intelligence Cloud Run" \
        --quiet >/dev/null 2>&1; then
        log_success "Created service account $email"
    else
        if gcloud iam service-accounts describe "$email" --project="$project" --format="value(email)" >/dev/null 2>&1; then
            log_warn "Service account $email already exists; continuing"
        else
            exit_with_error "Failed to create service account '$email'."
        fi
    fi
}

bind_project_role() {
    local project="$1"
    local member="$2"
    local role="$3"
    gcloud projects add-iam-policy-binding "$project" \
        --member="$member" \
        --role="$role" \
        --quiet >/dev/null
}

bind_service_account_role() {
    local project="$1"
    local service_account="$2"
    local member="$3"
    local role="$4"
    gcloud iam service-accounts add-iam-policy-binding "$service_account" \
        --project="$project" \
        --member="$member" \
        --role="$role" \
        --quiet >/dev/null
}

ensure_bucket() {
    local bucket="$1"
    local project="$2"
    local region="$3"

    if gcloud storage buckets describe "gs://$bucket" --project="$project" >/dev/null 2>&1; then
        log_info "GCS bucket exists: gs://$bucket"
    else
        log_info "Creating GCS bucket: gs://$bucket"
        if ! gcloud storage buckets create "gs://$bucket" \
            --project="$project" \
            --location="$region" \
            --uniform-bucket-level-access \
            --quiet >/dev/null 2>&1; then
            exit_with_error "Failed to create GCS bucket '$bucket'. Choose a unique bucket name with --bucket or ensure you have access."
        fi
        log_success "Created GCS bucket: gs://$bucket"
    fi

    if gcloud storage buckets describe "gs://$bucket" --project="$project" >/dev/null 2>&1; then
        log_info "Ensuring GCS bucket versioning and lifecycle"
        gcloud storage buckets update "gs://$bucket" --project="$project" --versioning --quiet >/dev/null 2>&1 || true
        gcloud storage buckets update "gs://$bucket" --project="$project" --lifecycle-file=- --quiet >/dev/null 2>&1 <<'YAML' || true
rule:
  - action:
      type: Delete
    condition:
      numNewerVersions: 5
YAML
    else
        log_warn "Unable to verify bucket gs://$bucket after creation attempt; skipping lifecycle configuration."
    fi
}

deploy_firestore_indexes() {
    local project="$1"

    if [[ -f "firestore.indexes.json" ]]; then
        log_info "Deploying Firestore indexes via deploy_firestore_indexes.py (firebase method)"
        if python3 deploy_firestore_indexes.py --project-id "$project" --method firebase; then
            return
        fi
        log_warn "Firebase CLI deployment failed, attempting gcloud method"
        python3 deploy_firestore_indexes.py --project-id "$project" --method gcloud || log_warn "Automated Firestore index deployment failed. Please run create_firestore_indexes.py manually if needed."
    elif [[ -f "create_firestore_indexes.py" ]]; then
        log_info "Running create_firestore_indexes.py to list required indexes"
        python3 create_firestore_indexes.py --project-id "$project" || log_warn "Index helper script encountered an error. Create indexes manually if required."
    else
        log_warn "No Firestore index helper scripts found."
    fi
}

build_and_push_image() {
    local image="$1"
    local tags=("$@")
    tags=("${tags[@]:1}")

    log_info "Building Docker image for Cloud Run (linux/amd64)"
    local build_args=(docker build --platform linux/amd64)
    local tag
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
    local service="$1"
    local region="$2"
    local image="$3"
    local env_file="$4"
    local memory="$5"
    local cpu="$6"
    local concurrency="$7"
    local max_instances="$8"
    local timeout="$9"
    local service_account="${10}"

    log_info "Deploying Cloud Run service '$service' in region '$region'"
    gcloud run deploy "$service" \
        --image "$image" \
        --region "$region" \
        --platform managed \
        --allow-unauthenticated \
        --memory "$memory" \
        --cpu "$cpu" \
        --concurrency "$concurrency" \
        --max-instances "$max_instances" \
        --timeout "$timeout" \
        --service-account "$service_account" \
        --env-vars-file "$env_file"
    log_success "Cloud Run deployment completed"
}

health_check() {
    local url="$1"
    local attempts=5
    local delay=10

    if ! command_exists curl; then
        log_warn "curl not found; skipping HTTP health check."
        return
    fi

    log_info "Checking service health at $url/health"
    for ((i=1; i<=attempts; i++)); do
        if curl -fs "$url/health" >/dev/null; then
            log_success "Health endpoint responded successfully"
            return
        fi
        log_warn "Health check attempt $i/$attempts failed; retrying in ${delay}s"
        sleep "$delay"
    done
    log_warn "Health check did not succeed. The service may still be warming up."
}

main() {
    local project_id=""
    local region="us-central1"
    local service_name="document-intelligence-api"
    local env_file="production-env.yaml"
    local service_account=""
    local memory="1Gi"
    local cpu="1"
    local concurrency="80"
    local max_instances="10"
    local timeout="300"
    local skip_indexes="false"
    local bucket_name=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --project-id)
                project_id="$2"; shift 2 ;;
            --region)
                region="$2"; shift 2 ;;
            --service-name)
                service_name="$2"; shift 2 ;;
            --env-file)
                env_file="$2"; shift 2 ;;
            --service-account)
                service_account="$2"; shift 2 ;;
            --memory)
                memory="$2"; shift 2 ;;
            --cpu)
                cpu="$2"; shift 2 ;;
            --concurrency)
                concurrency="$2"; shift 2 ;;
            --max-instances)
                max_instances="$2"; shift 2 ;;
            --timeout)
                timeout="$2"; shift 2 ;;
            --bucket)
                bucket_name="$2"; shift 2 ;;
            --skip-indexes)
                skip_indexes="true"; shift ;;
            --help|-h)
                cat <<EOF
Usage: $0 --project-id PROJECT_ID [options]

Options:
  --project-id        (required) Google Cloud project ID
  --region            Cloud Run region (default: us-central1)
  --service-name      Cloud Run service name (default: document-intelligence-api)
  --env-file          Environment file (YAML or KEY=VALUE) (default: production-env.yaml)
  --service-account   Service account email (default: detect existing or create document-int-run@PROJECT.iam.gserviceaccount.com)
  --bucket            GCS bucket name override
  --memory            Memory allocation (default: 1Gi)
  --cpu               CPU allocation (default: 1)
  --concurrency       Request concurrency (default: 80)
  --max-instances     Max instances (default: 10)
  --timeout           Request timeout seconds (default: 300)
  --skip-indexes      Skip Firestore index deployment
  -h, --help          Show this help message
EOF
                exit 0
                ;;
            *)
                exit_with_error "Unknown option: $1"
                ;;
        esac
    done

    [[ -z "$project_id" ]] && exit_with_error "--project-id is required"

    ensure_command gcloud
    ensure_command docker
    ensure_command python3

    if [[ ! -f "Dockerfile" ]]; then
        exit_with_error "Dockerfile not found in repository root."
    fi
    if [[ ! -f "pyproject.toml" ]]; then
        exit_with_error "pyproject.toml not found in repository root."
    fi
    if [[ ! -f "uv.lock" ]]; then
        log_warn "uv.lock not found. Consider running 'uv sync' to lock dependencies."
    fi

    log_info "Setting active GCP project to $project_id"
    gcloud config set project "$project_id" --quiet >/dev/null

    if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q '.'; then
        exit_with_error "No active gcloud account detected. Run 'gcloud auth login' first."
    fi

    gcloud auth configure-docker --quiet >/dev/null

    log_info "Checking required APIs"
    local apis=(
        run.googleapis.com
        cloudbuild.googleapis.com
        containerregistry.googleapis.com
        iam.googleapis.com
        firestore.googleapis.com
        storage-component.googleapis.com
    )
    for api in "${apis[@]}"; do
        ensure_api_enabled "$api"
    done

    parse_env_file "$env_file"

    env_set "ENVIRONMENT" "production"
    env_set "FIREBASE_PROJECT_ID" "$(env_get "FIREBASE_PROJECT_ID" "$project_id")"
    env_set "GCP_PROJECT_ID" "$project_id"
    env_set "GOOGLE_CLOUD_PROJECT" "$project_id"
    env_set "LOG_LEVEL" "$(env_get "LOG_LEVEL" "INFO")"
    env_set "LOG_FORMAT" "$(env_get "LOG_FORMAT" "json")"

    if [[ -z "$bucket_name" ]]; then
        bucket_name="$(env_get "GCS_BUCKET_NAME")"
    fi
    if [[ -z "$bucket_name" ]]; then
        bucket_name="${project_id}-document-intelligence"
        log_warn "No GCS bucket found in env file. Defaulting to $bucket_name"
        env_set "GCS_BUCKET_NAME" "$bucket_name"
    else
        env_set "GCS_BUCKET_NAME" "$bucket_name"
    fi

    if [[ -z "$service_account" ]]; then
        log_info "Attempting to detect existing Cloud Run service for service account reuse"
        service_account="$(gcloud run services describe "$service_name" --region "$region" --format="value(spec.template.spec.serviceAccountName)" 2>/dev/null || true)"
    fi
    if [[ -z "$service_account" ]]; then
        service_account="$(gcloud iam service-accounts list --project="$project_id" --format="value(email)" | head -n 1)"
        if [[ -n "$service_account" ]]; then
            log_info "Reusing existing service account: $service_account"
        fi
    fi
    if [[ -z "$service_account" ]]; then
        service_account="document-int-run@$project_id.iam.gserviceaccount.com"
        log_warn "No service account provided or detected. Defaulting to new account $service_account"
    fi

    ensure_service_account "$service_account" "$project_id"

    local current_account
    current_account="$(gcloud config get-value account 2>/dev/null || true)"
    if [[ -n "$current_account" ]]; then
        log_info "Granting roles/iam.serviceAccountUser on $service_account to $current_account"
        bind_service_account_role "$project_id" "$service_account" "user:$current_account" "roles/iam.serviceAccountUser"
    fi

    log_info "Granting required project roles to $service_account"
    local sa_roles=(
        roles/run.invoker
        roles/datastore.user
        roles/storage.objectAdmin
        roles/logging.logWriter
        roles/cloudtrace.agent
    )
    for role in "${sa_roles[@]}"; do
        bind_project_role "$project_id" "serviceAccount:$service_account" "$role"
    done

    ensure_bucket "$bucket_name" "$project_id" "$region"

    local tmp_env_file
    tmp_env_file="$(mktemp)"
    TMP_ENV_FILE="$tmp_env_file"
    trap '[[ -n "${TMP_ENV_FILE:-}" ]] && rm -f "$TMP_ENV_FILE"' EXIT
    write_env_file "$tmp_env_file"
    log_info "Prepared environment variable file at $tmp_env_file"

    if [[ "$skip_indexes" != "true" ]]; then
        deploy_firestore_indexes "$project_id"
    else
        log_info "Skipping Firestore index deployment as requested"
    fi

    local image="gcr.io/$project_id/$service_name"
    local timestamp_tag="$image:$(date +%s)"
    local latest_tag="$image:latest"
    build_and_push_image "$image" "$latest_tag" "$timestamp_tag"

    deploy_cloud_run "$service_name" "$region" "$latest_tag" "$tmp_env_file" "$memory" "$cpu" "$concurrency" "$max_instances" "$timeout" "$service_account"

    local service_url
    service_url="$(gcloud run services describe "$service_name" --region "$region" --format="value(status.url)" 2>/dev/null || true)"
    if [[ -n "$service_url" ]]; then
        log_success "Service URL: $service_url"
        health_check "$service_url"
    else
        log_warn "Unable to retrieve Cloud Run service URL."
    fi

    log_success "Deployment complete!"
    echo ""
    echo "Next steps:"
    echo " - Review logs: gcloud run services logs tail $service_name --region=$region"
    echo " - Validate Firestore indexes if any warnings were emitted"
    echo " - Update frontend or clients to use: $service_url"

    rm -f "$tmp_env_file"
    TMP_ENV_FILE=""
}

main "$@"
