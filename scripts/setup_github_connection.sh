#!/bin/bash
# ===========================================
# GitHub Connection Setup Script
# Sets up GitHub 2nd gen integration for Cloud Build
# ===========================================
#
# Usage:
#   chmod +x scripts/setup_github_connection.sh
#   ./scripts/setup_github_connection.sh
#
# This script:
# 1. Creates a GitHub connection in Cloud Build
# 2. Provides authorization URL for GitHub App installation
# 3. Links the GitHub repository to Cloud Build
#
# Prerequisites:
# - GitHub account with admin access to repository
# - Repository: https://github.com/cwijay/doc_intelligence_backend_api_v2.0.git
#

set -e

PROJECT_ID="biz2bricks-dev-v1"
REGION="us-central1"
CONNECTION_NAME="biz2bricks-github-connection"
REPO_NAME="doc-intelligence-repo"
REPO_URI="https://github.com/cwijay/doc_intelligence_backend_api_v2.0.git"

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

log_info "Setting up GitHub connection for Cloud Build"
echo ""
echo "📋 Configuration:"
echo "   Project ID: $PROJECT_ID"
echo "   Region: $REGION"
echo "   Connection Name: $CONNECTION_NAME"
echo "   Repository: $REPO_URI"
echo ""

# Enable required APIs
log_info "Enabling required APIs..."
gcloud services enable cloudbuild.googleapis.com --project=$PROJECT_ID
gcloud services enable secretmanager.googleapis.com --project=$PROJECT_ID
gcloud services enable run.googleapis.com --project=$PROJECT_ID

log_success "APIs enabled"
echo ""

# Create GitHub connection
log_info "Creating GitHub connection..."
if gcloud builds connections describe $CONNECTION_NAME --region=$REGION --project=$PROJECT_ID >/dev/null 2>&1; then
    log_warn "Connection '$CONNECTION_NAME' already exists"
else
    gcloud builds connections create github $CONNECTION_NAME \
        --region=$REGION \
        --project=$PROJECT_ID

    log_success "GitHub connection created"
fi

echo ""
log_info "Retrieving authorization URL..."

# Get authorization URL
AUTH_URL=$(gcloud builds connections describe $CONNECTION_NAME \
    --region=$REGION \
    --project=$PROJECT_ID \
    --format="value(installationState.actionUri)")

if [ -z "$AUTH_URL" ]; then
    log_warn "Connection may already be authorized. Checking status..."

    CONNECTION_STATUS=$(gcloud builds connections describe $CONNECTION_NAME \
        --region=$REGION \
        --project=$PROJECT_ID \
        --format="value(installationState.stage)")

    if [ "$CONNECTION_STATUS" == "COMPLETE" ]; then
        log_success "Connection is already authorized!"
    else
        log_error "Could not retrieve authorization URL. Current stage: $CONNECTION_STATUS"
        echo ""
        echo "To manually check connection status:"
        echo "  gcloud builds connections describe $CONNECTION_NAME --region=$REGION --project=$PROJECT_ID"
        exit 1
    fi
else
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📱 AUTHORIZATION REQUIRED"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "1. Open this URL in your browser:"
    echo ""
    echo "   ${BLUE}$AUTH_URL${NC}"
    echo ""
    echo "2. Sign in to GitHub if prompted"
    echo "3. Select the repository: cwijay/doc_intelligence_backend_api_v2.0"
    echo "4. Click 'Install & Authorize'"
    echo "5. Return here and press Enter to continue"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    read -p "Press Enter after completing GitHub App installation..."
fi

echo ""
log_info "Linking repository to Cloud Build..."

# Create repository linkage
if gcloud builds repositories describe $REPO_NAME \
    --connection=$CONNECTION_NAME \
    --region=$REGION \
    --project=$PROJECT_ID >/dev/null 2>&1; then
    log_warn "Repository '$REPO_NAME' is already linked"
else
    gcloud builds repositories create $REPO_NAME \
        --remote-uri=$REPO_URI \
        --connection=$CONNECTION_NAME \
        --region=$REGION \
        --project=$PROJECT_ID

    log_success "Repository linked to Cloud Build"
fi

echo ""
log_success "GitHub connection setup complete!"
echo ""
echo "📋 Connection details:"
gcloud builds repositories describe $REPO_NAME \
    --connection=$CONNECTION_NAME \
    --region=$REGION \
    --project=$PROJECT_ID

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✨ Next steps:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  1. Run: ./scripts/create_triggers.sh"
echo "  2. Make a test commit to 'develop' branch to verify pipeline"
echo "  3. View builds: https://console.cloud.google.com/cloud-build/builds"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
