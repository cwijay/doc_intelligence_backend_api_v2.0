#!/bin/bash
# ===========================================
# Secret Manager Setup Script
# Migrates environment variables to Secret Manager
# ===========================================
#
# Usage:
#   chmod +x scripts/setup_secrets.sh
#   ./scripts/setup_secrets.sh
#
# This script:
# 1. Creates secrets from .env.dev (development)
# 2. Creates secrets from .env.production (production with -prod suffix)
# 3. Grants Cloud Build service account access to all secrets
#

set -e

PROJECT_ID="biz2bricks-dev-v1"

# Color codes
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

# Check if .env files exist
if [[ ! -f ".env.dev" ]]; then
    log_error ".env.dev file not found!"
    exit 1
fi

if [[ ! -f ".env.production" ]]; then
    log_error ".env.production file not found!"
    exit 1
fi

log_info "Starting Secret Manager setup for project: $PROJECT_ID"
echo ""

# Enable Secret Manager API
log_info "Enabling Secret Manager API..."
gcloud services enable secretmanager.googleapis.com --project=$PROJECT_ID

# Non-sensitive environment variables (will be set via --set-env-vars)
NON_SENSITIVE_VARS=(
    "ENVIRONMENT"
    "DEBUG"
    "LOG_LEVEL"
    "LOG_FORMAT"
    "HOST"
    "PORT"
    "PROJECT_NAME"
    "VERSION"
    "FIREBASE_PROJECT_ID"
    "FIREBASE_DATABASE_ID"
    "GCP_PROJECT_ID"
    "GCS_BUCKET_NAME"
    "FRONTEND_DOMAIN"
    "PRODUCTION_CORS_ORIGINS"
    "MAX_FILE_SIZE"
    "ALLOWED_FILE_TYPES"
    "SIGNED_URL_EXPIRATION_MINUTES"
    "DOCUMENT_UPLOAD_TIMEOUT"
    "SESSION_DURATION_HOURS"
    "REFRESH_SESSION_DURATION_DAYS"
    "ACCESS_TOKEN_EXPIRE_MINUTES"
    "JWT_ALGORITHM"
    "OPENAI_MODEL"
    "OPENAI_MAX_TOKENS"
    "OPENAI_TEMPERATURE"
    "PINECONE_ENVIRONMENT"
    "PINECONE_INDEX_NAME"
    "AI_CONTENT_CACHING"
    "AI_CACHE_TTL_HOURS"
    "CORS_ORIGINS"
    "CORS_CREDENTIALS"
)

is_sensitive() {
    local key="$1"
    for non_sensitive in "${NON_SENSITIVE_VARS[@]}"; do
        if [[ "$key" == "$non_sensitive" ]]; then
            return 1
        fi
    done
    return 0
}

create_secret() {
    local key="$1"
    local value="$2"
    local secret_name="$3"

    # Skip empty values
    if [[ -z "$value" ]]; then
        log_warn "Skipping $secret_name (empty value)"
        return
    fi

    log_info "Creating secret: $secret_name"

    # Create or update secret
    if gcloud secrets describe "$secret_name" --project=$PROJECT_ID >/dev/null 2>&1; then
        log_warn "Secret $secret_name already exists, adding new version..."
        echo -n "$value" | gcloud secrets versions add "$secret_name" \
            --data-file=- \
            --project=$PROJECT_ID
    else
        echo -n "$value" | gcloud secrets create "$secret_name" \
            --data-file=- \
            --replication-policy=automatic \
            --project=$PROJECT_ID
    fi

    log_success "Secret created: $secret_name"
}

# Process development secrets
log_info "Processing development secrets from .env.dev..."
echo ""

while IFS='=' read -r key value || [[ -n "$key" ]]; do
    # Skip comments and empty lines
    [[ "$key" =~ ^#.*$ ]] && continue
    [[ -z "$key" ]] && continue

    # Trim whitespace
    key=$(echo "$key" | xargs)
    value=$(echo "$value" | xargs)

    # Remove quotes if present
    value="${value#\"}"
    value="${value%\"}"
    value="${value#\'}"
    value="${value%\'}"

    # Only create secret for sensitive variables
    if is_sensitive "$key"; then
        create_secret "$key" "$value" "$key"
    else
        log_info "Skipping non-sensitive variable: $key (will be set via --set-env-vars)"
    fi
done < .env.dev

echo ""
log_info "Processing production secrets from .env.production..."
echo ""

while IFS='=' read -r key value || [[ -n "$key" ]]; do
    # Skip comments and empty lines
    [[ "$key" =~ ^#.*$ ]] && continue
    [[ -z "$key" ]] && continue

    # Trim whitespace
    key=$(echo "$key" | xargs)
    value=$(echo "$value" | xargs)

    # Remove quotes if present
    value="${value#\"}"
    value="${value%\"}"
    value="${value#\'}"
    value="${value%\'}"

    # Only create secret for sensitive variables with -prod suffix
    if is_sensitive "$key"; then
        create_secret "$key" "$value" "${key}-prod"
    else
        log_info "Skipping non-sensitive variable: $key (will be set via --set-env-vars)"
    fi
done < .env.production

echo ""
log_info "Granting Cloud Build service account access to secrets..."

# Get Cloud Build service account
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")
CLOUD_BUILD_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

log_info "Cloud Build service account: $CLOUD_BUILD_SA"

# Grant access to all secrets
for secret in $(gcloud secrets list --project=$PROJECT_ID --format="value(name)"); do
    log_info "Granting access to: $secret"
    gcloud secrets add-iam-policy-binding "$secret" \
        --member="serviceAccount:$CLOUD_BUILD_SA" \
        --role="roles/secretmanager.secretAccessor" \
        --project=$PROJECT_ID >/dev/null 2>&1
done

echo ""
log_success "Secret Manager setup complete!"
echo ""
echo "📋 Summary:"
gcloud secrets list --project=$PROJECT_ID --format="table(name,createTime)"
echo ""
echo "✨ Next steps:"
echo "  1. Run: ./scripts/setup_cloudbuild_permissions.sh"
echo "  2. Run: ./scripts/setup_github_connection.sh"
echo "  3. Run: ./scripts/create_triggers.sh"
