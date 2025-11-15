#!/bin/bash
# ===========================================
# Cleanup All Test Data from GCP
# ===========================================
# This script cleans up all test organizations and related data
# from Firestore and GCS.
#
# Usage:
#   ./cleanup_all_test_data.sh                 # Dry run (show what would be deleted)
#   ./cleanup_all_test_data.sh --execute       # Actually delete the data
#   ./cleanup_all_test_data.sh --force-all     # Delete ALL organizations (DANGEROUS)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default mode
DRY_RUN="--dry-run"
MODE="all"
PATTERN="Test"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --execute)
            DRY_RUN=""
            shift
            ;;
        --force-all)
            MODE="force-all"
            shift
            ;;
        --pattern)
            PATTERN="$2"
            shift 2
            ;;
        --org-id)
            MODE="single"
            ORG_ID="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --execute         Actually execute the cleanup (default: dry run)"
            echo "  --force-all       Delete ALL organizations (DANGEROUS)"
            echo "  --pattern PATTERN Match organizations by pattern (default: 'Test')"
            echo "  --org-id ID       Delete specific organization by ID"
            echo "  --help            Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                           # Dry run, show what would be deleted"
            echo "  $0 --execute                 # Delete all test organizations"
            echo "  $0 --execute --pattern 'Demo'  # Delete organizations matching 'Demo'"
            echo "  $0 --execute --org-id abc123  # Delete specific organization"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Print header
echo "=========================================="
echo "GCP TEST DATA CLEANUP"
echo "=========================================="
echo ""

# Check if .env file exists
if [ ! -f ".env" ] && [ ! -f ".env.production" ]; then
    echo -e "${YELLOW}⚠️  Warning: No .env or .env.production file found${NC}"
    echo "The script will try to use Application Default Credentials"
    echo ""
fi

# Show mode
if [ -n "$DRY_RUN" ]; then
    echo -e "${YELLOW}MODE: DRY RUN (no actual deletions)${NC}"
    echo "Run with --execute to actually delete data"
else
    echo -e "${RED}MODE: LIVE (will delete data!)${NC}"
fi
echo ""

# Build command
CMD="uv run python scripts/cleanup_test_data.py"

if [ "$MODE" = "force-all" ]; then
    CMD="$CMD --force-clean-all"
elif [ "$MODE" = "single" ]; then
    CMD="$CMD --org-id $ORG_ID"
else
    CMD="$CMD --all --pattern '$PATTERN'"
fi

if [ -n "$DRY_RUN" ]; then
    CMD="$CMD $DRY_RUN"
fi

# Execute
echo "Executing: $CMD"
echo ""
eval $CMD

# Print completion message
echo ""
if [ -n "$DRY_RUN" ]; then
    echo -e "${GREEN}✓ Dry run completed${NC}"
    echo "Run with --execute to actually delete the data"
else
    echo -e "${GREEN}✓ Cleanup completed${NC}"
fi
