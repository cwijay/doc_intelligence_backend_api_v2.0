#!/bin/bash
# ===========================================
# Cloud Build Permissions Setup Script
# Grants necessary IAM roles to Cloud Build service account
# ===========================================
#
# Usage:
#   chmod +x scripts/setup_cloudbuild_permissions.sh
#   ./scripts/setup_cloudbuild_permissions.sh
#
# This script grants Cloud Build service account the following roles:
# - roles/run.admin - Deploy and manage Cloud Run services
# - roles/iam.serviceAccountUser - Use service accounts
# - roles/storage.admin - Manage GCS buckets
# - roles/logging.logWriter - Write logs to Cloud Logging
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

log_info "Setting up Cloud Build permissions for project: $PROJECT_ID"
echo ""

# Get project number and Cloud Build service account
log_info "Retrieving Cloud Build service account..."
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")
CLOUD_BUILD_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

log_success "Cloud Build service account: $CLOUD_BUILD_SA"
echo ""

# Required roles for Cloud Build
ROLES=(
    "roles/run.admin"
    "roles/iam.serviceAccountUser"
    "roles/storage.admin"
    "roles/logging.logWriter"
)

ROLE_DESCRIPTIONS=(
    "Deploy and manage Cloud Run services"
    "Use service accounts for Cloud Run deployment"
    "Manage GCS buckets and objects"
    "Write logs to Cloud Logging"
)

log_info "Granting IAM roles to Cloud Build service account..."
echo ""

for i in "${!ROLES[@]}"; do
    role="${ROLES[$i]}"
    description="${ROLE_DESCRIPTIONS[$i]}"

    log_info "Granting $role"
    echo "   → $description"

    if gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:$CLOUD_BUILD_SA" \
        --role="$role" \
        --project=$PROJECT_ID \
        --condition=None \
        --quiet >/dev/null 2>&1; then
        log_success "Granted: $role"
    else
        log_warn "Role may already be granted: $role"
    fi
    echo ""
done

log_success "Permissions setup complete!"
echo ""
echo "📋 Verify permissions:"
echo "   gcloud projects get-iam-policy $PROJECT_ID \\"
echo "     --flatten=\"bindings[].members\" \\"
echo "     --filter=\"bindings.members:serviceAccount:$CLOUD_BUILD_SA\""
echo ""
echo "✨ Next steps:"
echo "  1. Run: ./scripts/setup_github_connection.sh"
echo "  2. Run: ./scripts/create_triggers.sh"
