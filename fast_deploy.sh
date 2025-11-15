#!/usr/bin/env bash

# ============================================================================
# Fast Deployment Script - Optimized for Quick Iterations
# ============================================================================
#
# Quick deployment wrapper for code changes.
# Skips Firestore indexes and runs only smoke tests for faster iteration.
#
# Expected duration: 3-5 minutes (vs 6-9 minutes for full deployment)
#
# Usage:
#   ./fast_deploy.sh [--project-id PROJECT_ID] [--skip-tests]
#
# Examples:
#   # Fast deploy with smoke tests
#   ./fast_deploy.sh
#
#   # Fast deploy without any tests (fastest)
#   ./fast_deploy.sh --skip-tests
#
#   # Fast deploy to specific project
#   ./fast_deploy.sh --project-id biz2bricks-dev-v1
#
# Time savings:
#   - Skip Firestore indexes: ~30-60 seconds
#   - Smoke tests only: ~2-3 minutes saved
#   - Total savings: ~40-70% faster
#
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
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

# Default values
PROJECT_ID="${GCP_PROJECT_ID:-biz2bricks-dev-v1}"
REGION="us-central1"
BUCKET="biz2bricks-dev-v1-document-store"
ENV_FILE=".env.production"
SKIP_TESTS=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --project-id)
            PROJECT_ID="$2"
            shift 2
            ;;
        --skip-tests)
            SKIP_TESTS=true
            shift
            ;;
        --help|-h)
            cat << EOF
Fast Deployment Script - Optimized for Quick Iterations

Usage:
  ./fast_deploy.sh [OPTIONS]

Options:
  --project-id PROJECT_ID    GCP project ID (default: biz2bricks-dev-v1)
  --skip-tests               Skip all tests for fastest deployment
  --help, -h                 Show this help message

Examples:
  ./fast_deploy.sh
  ./fast_deploy.sh --skip-tests
  ./fast_deploy.sh --project-id my-project

Time Comparison:
  Full deployment:  6-9 minutes (all tests + indexes)
  Fast deployment:  3-5 minutes (smoke tests, skip indexes)
  Ultra-fast:       2-3 minutes (no tests, skip indexes)

EOF
            exit 0
            ;;
        *)
            log_warn "Unknown option: $1"
            echo "Run './fast_deploy.sh --help' for usage information"
            exit 1
            ;;
    esac
done

echo ""
log_info "🚀 Starting FAST deployment..."
log_info "Project: $PROJECT_ID"
log_info "Region: $REGION"
log_info "Environment: production"
echo ""

# Build deploy command
DEPLOY_CMD="./deploy_full.sh \
  --project-id $PROJECT_ID \
  --env-file $ENV_FILE \
  --timeout 60 \
  --region $REGION \
  --bucket $BUCKET \
  --skip-indexes"

if [ "$SKIP_TESTS" = true ]; then
    log_warn "Skipping all tests for ultra-fast deployment"
    DEPLOY_CMD="$DEPLOY_CMD --skip-tests"
    echo ""
else
    log_info "Running smoke tests only (not full test suite)"
    DEPLOY_CMD="$DEPLOY_CMD --smoke-only"
    echo ""
fi

# Execute deployment
START_TIME=$(date +%s)

$DEPLOY_CMD

EXIT_CODE=$?

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
MINUTES=$((DURATION / 60))
SECONDS=$((DURATION % 60))

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    log_success "🎉 Fast deployment completed successfully!"
    echo ""
    echo "Deployment time: ${MINUTES}m ${SECONDS}s"
    echo "Service URL: https://document-intelligence-api-726919062103.us-central1.run.app"
    echo ""
    log_info "Next steps:"
    echo "  - Run smoke tests: ./test_only.sh"
    echo "  - View logs: gcloud run services logs tail document-intelligence-api --region=us-central1"
else
    log_warn "Deployment completed with errors (exit code: $EXIT_CODE)"
    echo ""
    echo "Time elapsed: ${MINUTES}m ${SECONDS}s"
    exit $EXIT_CODE
fi
