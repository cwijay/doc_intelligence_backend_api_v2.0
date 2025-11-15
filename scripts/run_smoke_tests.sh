#!/usr/bin/env bash

# ============================================================================
# Smoke Test Runner
# ============================================================================
#
# Runs critical smoke tests for fast deployment validation.
# Expected duration: 15-25 seconds
#
# Usage:
#   ./scripts/run_smoke_tests.sh [TEST_BASE_URL]
#
# Examples:
#   ./scripts/run_smoke_tests.sh
#   ./scripts/run_smoke_tests.sh https://document-intelligence-api-726919062103.us-central1.run.app
#
# Environment Variables:
#   TEST_BASE_URL - Base URL of the deployed service (optional)
#
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$REPO_ROOT"

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

# Parse arguments
TEST_URL="${1:-}"

if [ -n "$TEST_URL" ]; then
    export TEST_BASE_URL="$TEST_URL"
    log_info "Testing against: $TEST_BASE_URL"
elif [ -n "${TEST_BASE_URL:-}" ]; then
    log_info "Using TEST_BASE_URL from environment: $TEST_BASE_URL"
else
    log_warn "No TEST_BASE_URL specified, using default from .env.test"
fi

# Run smoke tests
log_info "Running smoke tests..."
echo ""

uv run pytest tests/ \
    -v \
    -m "smoke" \
    --tb=short \
    --asyncio-mode=auto \
    --durations=5

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    log_success "All smoke tests passed! Deployment is healthy."
else
    log_warn "Some smoke tests failed. Check the output above."
    exit $EXIT_CODE
fi
