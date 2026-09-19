#!/bin/bash
# =============================================================================
# Apply Artifact Registry Cleanup Policies
# =============================================================================
# Container images are never deleted by default, so every build is retained
# forever at $0.10/GB/month beyond the 0.5GB free tier. This applies a policy
# that keeps the 3 most recent versions and deletes anything older than 30
# days.
#
# Note on "tagState": "ANY" in the policy file -- every image this project
# builds carries a unique $BUILD_ID (cloudbuild.yaml) or timestamp (deploy.sh)
# tag, so an UNTAGGED-only policy would never match anything.
#
# This project pushes to two registries, and both are covered:
#   - us-central1-docker.pkg.dev/PROJECT/document-intelligence  (cloudbuild.yaml)
#   - gcr.io/PROJECT/document-intelligence-api-*                (deploy.sh)
#
# Usage:
#   ./scripts/gcp/setup_cleanup_policy.sh              # dry run (default)
#   ./scripts/gcp/setup_cleanup_policy.sh --apply      # actually enforce
#   ./scripts/gcp/setup_cleanup_policy.sh --list       # show current policies
#   ./scripts/gcp/setup_cleanup_policy.sh --project=my-project
#
# A dry-run policy is still installed on the repository, but Artifact Registry
# only logs what it *would* delete. Check those logs before using --apply.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POLICY_FILE="$SCRIPT_DIR/artifact-registry-cleanup-policy.json"

PROJECT_ID="${PROJECT_ID:-biz2bricks-dev-v1}"
DRY_RUN=true
LIST_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --project=*)
            PROJECT_ID="${1#*=}"
            shift
            ;;
        --apply)
            DRY_RUN=false
            shift
            ;;
        --list)
            LIST_ONLY=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [--apply] [--list] [--project=PROJECT_ID]"
            echo ""
            echo "Options:"
            echo "  --apply            Enforce the policy (default is dry-run)"
            echo "  --list             Show current policies and exit"
            echo "  --project=ID       GCP project (default: $PROJECT_ID)"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

[[ -f "$POLICY_FILE" ]] || { echo "Policy file not found: $POLICY_FILE" >&2; exit 1; }

echo "Project: $PROJECT_ID"
echo ""

# Discover every Docker repository rather than hardcoding, so the gcr.io
# repo created by deploy.sh is picked up too.
# gcloud's value()/table() output shortens `name` to the basename and leaves
# `location` empty, so neither yields the region. The JSON keeps the
# fully-qualified projects/P/locations/LOC/repositories/REPO, so parse that.
REPOS="$(gcloud artifacts repositories list \
    --project="$PROJECT_ID" \
    --format=json 2>/dev/null \
  | python3 -c '
import sys, json
try:
    repos = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for r in repos:
    if r.get("format") != "DOCKER":
        continue
    parts = r.get("name", "").split("/")
    if len(parts) >= 6:
        print(parts[-1] + "\t" + parts[3])
' || true)"

if [[ -z "$REPOS" ]]; then
    echo "No Docker repositories found (or insufficient permissions)."
    echo "Check 'gcloud auth login' and that the Artifact Registry API is enabled."
    exit 1
fi

while IFS=$'\t' read -r repo location; do
    [[ -z "$repo" || -z "$location" ]] && continue

    echo "--- $repo ($location) ---"

    if [[ "$LIST_ONLY" == "true" ]]; then
        gcloud artifacts repositories describe "$repo" \
            --location="$location" \
            --project="$PROJECT_ID" \
            --format="value(cleanupPolicies)" 2>/dev/null || echo "  (none)"
        echo ""
        continue
    fi

    # Report current size so the saving is visible before and after.
    size="$(gcloud artifacts repositories describe "$repo" \
        --location="$location" \
        --project="$PROJECT_ID" \
        --format="value(sizeBytes)" 2>/dev/null || echo "")"
    if [[ -n "$size" && "$size" != "0" ]]; then
        echo "  current size: $(( size / 1024 / 1024 )) MiB"
    fi

    dry_run_flag="--dry-run"
    [[ "$DRY_RUN" == "false" ]] && dry_run_flag="--no-dry-run"

    gcloud artifacts repositories set-cleanup-policies "$repo" \
        --location="$location" \
        --project="$PROJECT_ID" \
        --policy="$POLICY_FILE" \
        "$dry_run_flag"

    echo ""
done <<< "$REPOS"

if [[ "$LIST_ONLY" == "true" ]]; then
    exit 0
fi

if [[ "$DRY_RUN" == "true" ]]; then
    echo "Installed in DRY-RUN mode. Nothing will be deleted."
    echo "Artifact Registry logs what it would delete; review, then re-run with --apply."
else
    echo "Cleanup policies are now ENFORCED."
fi
