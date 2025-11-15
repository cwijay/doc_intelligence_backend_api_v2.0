#!/usr/bin/env bash

# ============================================================================
# Test-Only Script - Fast Smoke Test Validation
# ============================================================================
#
# Runs smoke tests against an already-deployed service without deploying.
# Use this for quick validation after deployment or to verify service health.
#
# Expected duration: 15-25 seconds
#
# Usage:
#   ./test_only.sh [SERVICE_URL]
#
# Examples:
#   # Test against production deployment
#   ./test_only.sh https://document-intelligence-api-726919062103.us-central1.run.app
#
#   # Test against default from .env.test
#   ./test_only.sh
#
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
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

# Parse arguments
SERVICE_URL="${1:-}"

if [ -n "$SERVICE_URL" ]; then
    export TEST_BASE_URL="$SERVICE_URL"
else
    # Try to get URL from .env.test
    if [ -f .env.test ]; then
        source .env.test
        if [ -z "${TEST_BASE_URL:-}" ]; then
            log_warn "TEST_BASE_URL not set in .env.test"
            log_warn "Using default: http://localhost:8000"
            export TEST_BASE_URL="http://localhost:8000"
        fi
    else
        log_warn ".env.test not found"
        log_error "Please provide SERVICE_URL or create .env.test with TEST_BASE_URL"
        echo ""
        echo "Usage: ./test_only.sh [SERVICE_URL]"
        echo "Example: ./test_only.sh https://document-intelligence-api-726919062103.us-central1.run.app"
        exit 1
    fi
fi

echo ""
log_info "🧪 Running smoke tests against: $TEST_BASE_URL"
echo ""

# Quick health check first
log_info "Checking service health..."
if curl -sf "$TEST_BASE_URL/health" > /dev/null 2>&1; then
    log_success "Service is responding"
else
    log_error "Service health check failed!"
    log_error "Make sure the service is deployed and accessible at: $TEST_BASE_URL"
    exit 1
fi

echo ""
log_info "Running smoke test suite..."
echo ""

# Run smoke tests
./scripts/run_smoke_tests.sh "$TEST_BASE_URL"

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    log_success "🎉 All smoke tests passed! Service is healthy and functional."
    echo ""
    echo "Service URL: $TEST_BASE_URL"
    echo "Test duration: ~15-25 seconds"
else
    log_error "❌ Some smoke tests failed. Service may have issues."
    echo ""
    echo "Troubleshooting:"
    echo "  1. Check service logs: gcloud run services logs read document-intelligence-api --region=us-central1"
    echo "  2. Verify Firestore connection"
    echo "  3. Check environment variables"
    exit $EXIT_CODE
fi
