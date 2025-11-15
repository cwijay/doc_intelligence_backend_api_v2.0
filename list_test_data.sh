#!/bin/bash
# ===========================================
# List Test Data in GCP
# ===========================================
# This script lists all organizations and related data in Firestore
#
# Usage:
#   ./list_test_data.sh                 # List test organizations (name contains "Test")
#   ./list_test_data.sh --all           # List ALL organizations
#   ./list_test_data.sh --pattern "Demo"  # List organizations matching "Demo"

set -e

# Default pattern
PATTERN="Test"
SHOW_ALL=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --all)
            SHOW_ALL="--all"
            shift
            ;;
        --pattern)
            PATTERN="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --all             Show all organizations"
            echo "  --pattern PATTERN Filter by pattern (default: 'Test')"
            echo "  --help            Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                      # List test organizations"
            echo "  $0 --all                # List all organizations"
            echo "  $0 --pattern 'Demo'     # List organizations matching 'Demo'"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Build command
if [ -n "$SHOW_ALL" ]; then
    CMD="uv run python scripts/list_test_data.py --all"
else
    CMD="uv run python scripts/list_test_data.py --pattern '$PATTERN'"
fi

# Execute
eval $CMD
