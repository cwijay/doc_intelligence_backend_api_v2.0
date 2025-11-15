# Testing and Cleanup Guide

This guide explains how to run tests and clean up test data from GCP (Firestore and Cloud Storage).

## Table of Contents

- [Prerequisites](#prerequisites)
- [Environment Setup](#environment-setup)
- [Running Tests](#running-tests)
- [Viewing Test Data](#viewing-test-data)
- [Cleaning Up Test Data](#cleaning-up-test-data)
- [Troubleshooting](#troubleshooting)

## Prerequisites

1. **Python 3.12+** with `uv` installed
2. **GCP Credentials** configured (one of the following):
   - Service account key file (`GOOGLE_APPLICATION_CREDENTIALS` environment variable)
   - Application Default Credentials (for Cloud Shell or GCE instances)
3. **Environment variables** configured in `.env` file

## Environment Setup

### 1. Create .env File

Copy the example file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

```bash
# Firebase/Firestore
FIREBASE_PROJECT_ID="your-project-id"
FIREBASE_DATABASE_ID="your-database-id"

# GCP
GCP_PROJECT_ID="your-project-id"
GCS_BUCKET_NAME="your-bucket-name"

# Authentication
GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"
# OR use Application Default Credentials (leave above blank)

# API Keys (for AI tests)
OPENAI_API_KEY="your-openai-api-key"
LLAMAPARSE_API_KEY="your-llamaparse-api-key"
```

### 2. Install Dependencies

```bash
uv sync
```

## Running Tests

### Test Against Local Server

1. **Start the development server** (in one terminal):
   ```bash
   ./run_dev.sh
   ```

2. **Run tests** (in another terminal):
   ```bash
   # Run all tests (excluding slow and AI tests)
   uv run pytest tests/ -v -m "not slow and not ai"

   # Run smoke tests only (fast validation)
   uv run pytest tests/ -v -m "smoke"

   # Run specific test file
   uv run pytest tests/api/test_auth.py -v

   # Run specific test
   uv run pytest tests/api/test_auth.py::TestAuthenticationFlow::test_01_list_organizations_for_registration -v
   ```

### Test Against Deployed API

Set the `TEST_BASE_URL` environment variable:

```bash
# Set the deployed API URL
export TEST_BASE_URL="https://your-api-url.run.app"

# Run tests
uv run pytest tests/ -v -m "not slow and not ai"
```

**Note**: If running from a restricted network environment (like some CI/CD systems), you may encounter proxy issues preventing access to external URLs.

### Test Categories (Markers)

- `smoke`: Critical tests for fast deployment validation (15-25 seconds)
- `slow`: Long-running tests (skip with `-m "not slow"`)
- `ai`: Tests that use AI services and cost money (skip with `-m "not ai"`)
- `integration`: Full system integration tests
- `auth`: Authentication-related tests
- `document`: Document-related tests
- `org`: Organization-related tests

### Examples

```bash
# Smoke tests only (fastest)
uv run pytest tests/ -v -m "smoke"

# Skip slow and AI tests (recommended for CI/CD)
uv run pytest tests/ -v -m "not slow and not ai"

# Run integration tests only
uv run pytest tests/ -v -m "integration"

# Run auth tests with coverage
uv run pytest tests/api/test_auth.py -v --cov=app.api.v1.auth --cov-report=html
```

## Viewing Test Data

### Quick View

Use the convenience script to view all test organizations and statistics:

```bash
# List test organizations (name contains "Test")
./list_test_data.sh

# List ALL organizations
./list_test_data.sh --all

# List organizations matching a specific pattern
./list_test_data.sh --pattern "Demo"
```

### Using Python Script Directly

```bash
# View test organizations
uv run python scripts/list_test_data.py

# View all organizations
uv run python scripts/list_test_data.py --all

# Filter by pattern
uv run python scripts/list_test_data.py --pattern "YourPattern"
```

This will show:
- Organization names, IDs, and details
- Total counts of users, documents, folders, and sessions

## Cleaning Up Test Data

### Quick Cleanup (Recommended)

Use the convenience script:

```bash
# DRY RUN - See what would be deleted (safe, no actual deletions)
./cleanup_all_test_data.sh

# EXECUTE - Actually delete test organizations
./cleanup_all_test_data.sh --execute

# Delete organizations matching a specific pattern
./cleanup_all_test_data.sh --execute --pattern "Demo"

# Delete a specific organization by ID
./cleanup_all_test_data.sh --execute --org-id "abc123xyz"
```

### Using Python Script Directly

The cleanup script supports several modes:

#### 1. Clean Test Organizations (Safe Default)

Deletes organizations where the name contains "Test":

```bash
# Dry run (shows what would be deleted)
uv run python scripts/cleanup_test_data.py --all --dry-run

# Execute cleanup
uv run python scripts/cleanup_test_data.py --all
```

#### 2. Clean Organizations by Pattern

```bash
# Clean organizations with names containing "Demo"
uv run python scripts/cleanup_test_data.py --all --pattern "Demo"

# Dry run first
uv run python scripts/cleanup_test_data.py --all --pattern "Demo" --dry-run
```

#### 3. Clean Specific Organization

```bash
# Clean organization by ID
uv run python scripts/cleanup_test_data.py --org-id "abc123xyz"
```

#### 4. Clean Organizations Created After a Date

```bash
# Clean test organizations created after Nov 15, 2025
uv run python scripts/cleanup_test_data.py --all --since "2025-11-15"
```

#### 5. Clean ALL Organizations (DANGEROUS)

**⚠️ WARNING**: This will delete ALL organizations in the database!

```bash
# This requires typing 'DELETE ALL ORGANIZATIONS' to confirm
uv run python scripts/cleanup_test_data.py --force-clean-all
```

### What Gets Deleted

When you delete an organization, the cleanup script will automatically delete (in order):

1. **All Documents** in the organization (Firestore + GCS files)
2. **All Folders** in the organization
3. **All User Sessions** for users in the organization
4. **All Users** in the organization
5. **The Organization** itself

### Cleanup Safety Features

- **Dry Run by Default**: Always shows what would be deleted first
- **Confirmation Required**: Prompts for confirmation before deleting
- **Cascade Delete**: Automatically deletes all related data
- **Error Handling**: Continues cleanup even if some items fail
- **Summary Report**: Shows what was deleted after completion

## Troubleshooting

### Tests Failing with "Failed to create org: Access denied"

This usually means:
1. **Network restrictions**: You're behind a proxy that blocks external API calls
2. **GCP IAM**: The Cloud Run service requires authentication
3. **Credentials not configured**: Check your GCP credentials

**Solutions**:
- Run tests against local server instead: `./run_dev.sh`
- Check proxy settings: `echo $https_proxy`
- Verify GCP credentials: `gcloud auth application-default print-access-token`

### Cleanup Script Can't Connect to Firestore

**Error**: `google.auth.exceptions.DefaultCredentialsError`

**Solutions**:
1. Set `GOOGLE_APPLICATION_CREDENTIALS` in your `.env` file:
   ```bash
   GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"
   ```

2. Or use Application Default Credentials:
   ```bash
   gcloud auth application-default login
   ```

3. Verify credentials are working:
   ```bash
   uv run python -c "from app.core.firebase_client import init_firebase; import asyncio; asyncio.run(init_firebase())"
   ```

### Tests Creating Too Much Data

If you're concerned about test data accumulating:

1. **Run cleanup after test sessions**:
   ```bash
   # Run tests
   uv run pytest tests/ -v

   # Clean up immediately after
   ./cleanup_all_test_data.sh --execute
   ```

2. **Use cleanup hooks**: The test fixtures in `conftest.py` include automatic cleanup via `resource_tracker`

3. **Scheduled cleanup**: Add a cron job or GitHub Action to run cleanup periodically

### "Access denied" When Testing Against Cloud Run

If you get 403 errors when testing against the deployed API:

1. **Check if service allows unauthenticated access**:
   ```bash
   gcloud run services describe SERVICE_NAME --region=REGION
   ```

2. **Verify the service is publicly accessible**:
   ```bash
   curl https://your-service-url.run.app/health
   ```

3. **If behind corporate proxy**: Run tests locally or from Cloud Shell

## Best Practices

### 1. Always Dry Run First

```bash
# See what would be deleted
./cleanup_all_test_data.sh

# Then execute if it looks correct
./cleanup_all_test_data.sh --execute
```

### 2. Regular Cleanup

Clean up test data regularly to avoid:
- Accumulating stale data
- Hitting Firestore quotas
- Increased storage costs

```bash
# Clean up weekly or after major test runs
./cleanup_all_test_data.sh --execute
```

### 3. Use Smoke Tests for Quick Validation

```bash
# Fast validation (15-25 seconds)
uv run pytest tests/ -v -m "smoke"
```

### 4. Skip Expensive Tests in CI/CD

```bash
# Skip AI tests that cost money
uv run pytest tests/ -v -m "not ai"
```

### 5. Verify Cleanup Completed

```bash
# After cleanup, verify no test data remains
./list_test_data.sh
```

## Quick Reference

```bash
# VIEW TEST DATA
./list_test_data.sh                    # List test organizations
./list_test_data.sh --all              # List all organizations

# CLEANUP (DRY RUN)
./cleanup_all_test_data.sh             # Preview what would be deleted

# CLEANUP (EXECUTE)
./cleanup_all_test_data.sh --execute   # Delete test organizations
./cleanup_all_test_data.sh --execute --pattern "Demo"  # Delete by pattern
./cleanup_all_test_data.sh --execute --org-id ID       # Delete specific org

# RUN TESTS
uv run pytest tests/ -v -m "smoke"     # Smoke tests (fastest)
uv run pytest tests/ -v -m "not slow and not ai"  # Standard test run
uv run pytest tests/ -v                # All tests
```

## Support

For issues or questions:
1. Check the main `CLAUDE.md` file for project documentation
2. Review test logs in `tests/test.log`
3. Use `--dry-run` to preview cleanup operations
4. Run `./list_test_data.sh --all` to see current database state
