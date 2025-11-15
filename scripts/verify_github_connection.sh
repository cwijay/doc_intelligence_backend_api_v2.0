#!/bin/bash

# ===========================================
# GitHub Connection Verification Script
# Document Intelligence Backend API
# ===========================================
#
# This script checks if your GitHub repository is properly
# connected to Cloud Build and provides guidance if not.

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() { echo -e "${BLUE}ℹ ${NC}$1"; }
print_success() { echo -e "${GREEN}✓${NC} $1"; }
print_warning() { echo -e "${YELLOW}⚠${NC} $1"; }
print_error() { echo -e "${RED}✗${NC} $1"; }
print_header() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

# Default values
PROJECT_ID="${1:-biz2bricks-dev-v1}"
REGION="${2:-us-central1}"

print_header "GitHub Connection Verification"
print_info "Project: $PROJECT_ID"
print_info "Region: $REGION"
echo ""

# Check if any triggers exist
print_info "Checking existing triggers..."
TRIGGER_COUNT=$(gcloud builds triggers list --project="$PROJECT_ID" --region="$REGION" --format="value(name)" 2>/dev/null | wc -l | tr -d ' ')

if [ "$TRIGGER_COUNT" -gt 0 ]; then
    print_success "Found $TRIGGER_COUNT existing trigger(s)"
    gcloud builds triggers list --project="$PROJECT_ID" --region="$REGION"
else
    print_warning "No triggers found"
fi

echo ""

# Try to list GitHub connections (2nd gen)
print_info "Checking for GitHub connections (2nd gen)..."
if gcloud builds connections list --project="$PROJECT_ID" --region="$REGION" 2>/dev/null | grep -q "NAME"; then
    print_success "Found GitHub connections:"
    gcloud builds connections list --project="$PROJECT_ID" --region="$REGION"
    CONNECTION_EXISTS=true
else
    print_warning "No GitHub connections found"
    CONNECTION_EXISTS=false
fi

echo ""

# Provide guidance
if [ "$CONNECTION_EXISTS" = false ]; then
    print_header "GitHub Repository Not Connected"
    echo ""
    print_error "Your GitHub repository is NOT connected to Cloud Build."
    print_error "This is why the trigger creation is failing."
    echo ""
    print_warning "You MUST connect your repository first before creating triggers."
    echo ""
    
    print_header "How to Connect Your GitHub Repository"
    echo ""
    echo "METHOD 1: Using Web Console (RECOMMENDED)"
    echo "----------------------------------------"
    echo "1. Open this URL in your browser:"
    echo "   ${BLUE}https://console.cloud.google.com/cloud-build/triggers/connect?project=$PROJECT_ID${NC}"
    echo ""
    echo "2. Click 'CONNECT REPOSITORY'"
    echo ""
    echo "3. Select source: 'GitHub (Cloud Build GitHub App)'"
    echo "   ${YELLOW}Note: Make sure to select the GitHub App option, not the legacy integration${NC}"
    echo ""
    echo "4. Click 'Continue' and authenticate with GitHub"
    echo ""
    echo "5. Install or configure the Cloud Build app on your GitHub account"
    echo ""
    echo "6. Select your repository: cwijay/doc_intelligence_backend_api_v2.0"
    echo ""
    echo "7. Click 'Connect'"
    echo ""
    echo "8. Click 'Done' (don't create a trigger yet)"
    echo ""
    
    echo "METHOD 2: Using gcloud CLI (Advanced)"
    echo "-------------------------------------"
    echo "# Create a GitHub connection"
    echo "gcloud builds connections create github github-connection \\"
    echo "  --project=$PROJECT_ID \\"
    echo "  --region=$REGION"
    echo ""
    echo "# Follow the prompts to authenticate and select your repository"
    echo ""
    
    print_header "After Connecting"
    echo ""
    echo "Once you've connected your repository, run:"
    echo "  ${GREEN}./scripts/verify_github_connection.sh${NC}"
    echo ""
    echo "Then run the trigger setup script:"
    echo "  ${GREEN}./scripts/setup_cloud_build_triggers.sh \\${NC}"
    echo "    ${GREEN}--project-id biz2bricks-dev-v1 \\${NC}"
    echo "    ${GREEN}--repo-owner cwijay \\${NC}"
    echo "    ${GREEN}--repo-name doc_intelligence_backend_api_v2.0${NC}"
    echo ""
    
    exit 1
else
    print_header "Connection Status: OK"
    print_success "Your GitHub repository appears to be connected!"
    echo ""
    print_info "You can now create triggers using:"
    echo "  ./scripts/setup_cloud_build_triggers.sh \\"
    echo "    --project-id biz2bricks-dev-v1 \\"
    echo "    --repo-owner cwijay \\"
    echo "    --repo-name doc_intelligence_backend_api_v2.0"
    echo ""
    
    exit 0
fi

