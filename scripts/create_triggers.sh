#!/bin/bash
# ===========================================
# Cloud Build Triggers Creation Script
# Creates automated deployment triggers for develop and master branches
# ===========================================
#
# Usage:
#   chmod +x scripts/create_triggers.sh
#   ./scripts/create_triggers.sh
#
# This script creates:
# 1. Develop branch trigger (automatic deployment)
# 2. Master branch trigger (requires manual approval)
#
# Prerequisites:
# - GitHub connection must be set up (run setup_github_connection.sh first)
#

set -e

PROJECT_ID="biz2bricks-dev-v1"
REGION="us-central1"
CONNECTION_NAME="biz2bricks-github-connection"
REPO_NAME="doc-intelligence-repo"
REPO_PATH="projects/$PROJECT_ID/locations/$REGION/connections/$CONNECTION_NAME/repositories/$REPO_NAME"

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

log_info "Creating Cloud Build triggers for automated deployments"
echo ""
echo "📋 Configuration:"
echo "   Project ID: $PROJECT_ID"
echo "   Region: $REGION"
echo "   Repository: $REPO_PATH"
echo ""

# Verify GitHub connection exists
log_info "Verifying GitHub connection..."
if ! gcloud builds repositories describe $REPO_NAME \
    --connection=$CONNECTION_NAME \
    --region=$REGION \
    --project=$PROJECT_ID >/dev/null 2>&1; then
    log_error "GitHub repository not connected!"
    echo ""
    echo "Please run setup_github_connection.sh first:"
    echo "  ./scripts/setup_github_connection.sh"
    exit 1
fi

log_success "GitHub connection verified"
echo ""

# Create Develop branch trigger (automatic deployment)
log_info "Creating trigger for 'develop' branch (automatic deployment)..."
if gcloud builds triggers describe deploy-dev-on-push --region=$REGION --project=$PROJECT_ID >/dev/null 2>&1; then
    log_warn "Trigger 'deploy-dev-on-push' already exists"
else
    gcloud builds triggers create github \
        --name="deploy-dev-on-push" \
        --region=$REGION \
        --project=$PROJECT_ID \
        --repository="$REPO_PATH" \
        --branch-pattern="^develop$" \
        --build-config="cloudbuild.develop.yaml" \
        --description="Auto-deploy to development environment on develop branch push"

    log_success "Created trigger: deploy-dev-on-push"
fi

echo ""

# Create Master branch trigger (with manual approval)
log_info "Creating trigger for 'master' branch (requires manual approval)..."
if gcloud builds triggers describe deploy-prod-on-master --region=$REGION --project=$PROJECT_ID >/dev/null 2>&1; then
    log_warn "Trigger 'deploy-prod-on-master' already exists"
else
    gcloud builds triggers create github \
        --name="deploy-prod-on-master" \
        --region=$REGION \
        --project=$PROJECT_ID \
        --repository="$REPO_PATH" \
        --branch-pattern="^master$" \
        --build-config="cloudbuild.production.yaml" \
        --require-approval \
        --description="Deploy to production on master push (requires manual approval + gradual rollout)"

    log_success "Created trigger: deploy-prod-on-master (with approval requirement)"
fi

echo ""
log_success "Cloud Build triggers created successfully!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 Trigger Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
gcloud builds triggers list --region=$REGION --project=$PROJECT_ID --format="table(name,github.push.branch,description,createTime)"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 CI/CD Pipeline is now active!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📍 How it works:"
echo ""
echo "  Development (develop branch):"
echo "    1. Push code to 'develop' branch"
echo "    2. Cloud Build automatically runs tests"
echo "    3. Builds Docker image"
echo "    4. Deploys to document-intelligence-api-dev"
echo "    5. Runs health checks"
echo "    Timeline: ~5-7 minutes"
echo ""
echo "  Production (master branch):"
echo "    1. Push code to 'master' branch"
echo "    2. Cloud Build waits for MANUAL APPROVAL"
echo "    3. After approval: runs tests, builds image"
echo "    4. Deploys with gradual rollout (10% → 50% → 100%)"
echo "    5. Continuous monitoring during rollout"
echo "    Timeline: ~15-20 minutes after approval"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✨ Next steps:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  1. Test pipeline:"
echo "     git checkout develop"
echo "     echo '# Test CI/CD' >> README.md"
echo "     git commit -am 'Test CI/CD pipeline'"
echo "     git push origin develop"
echo ""
echo "  2. Monitor build:"
echo "     https://console.cloud.google.com/cloud-build/builds?project=$PROJECT_ID"
echo ""
echo "  3. View deployed service:"
echo "     gcloud run services describe document-intelligence-api-dev --region=$REGION"
echo ""
echo "  4. Review logs:"
echo "     gcloud run services logs read document-intelligence-api-dev --region=$REGION --limit=50"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
