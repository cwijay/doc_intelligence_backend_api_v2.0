# Cleanup and Utility Scripts

This directory contains utility scripts for managing test data and maintaining the application.

## Test Data Management

### List Test Data

**Script**: `list_test_data.py`
**Wrapper**: `../list_test_data.sh`

View all test organizations and database statistics without making any changes.

```bash
# From project root
./list_test_data.sh                    # List test organizations
./list_test_data.sh --all              # List all organizations
./list_test_data.sh --pattern "Demo"   # Filter by pattern

# Direct Python usage
uv run python scripts/list_test_data.py --all
```

### Clean Up Test Data

**Script**: `cleanup_test_data.py`
**Wrapper**: `../cleanup_all_test_data.sh`

Comprehensively clean up test data from Firestore and GCS.

```bash
# From project root - RECOMMENDED
./cleanup_all_test_data.sh                      # Dry run (preview)
./cleanup_all_test_data.sh --execute            # Execute cleanup
./cleanup_all_test_data.sh --execute --pattern "Demo"  # Custom pattern

# Direct Python usage
uv run python scripts/cleanup_test_data.py --all --dry-run
uv run python scripts/cleanup_test_data.py --all
uv run python scripts/cleanup_test_data.py --org-id "abc123"
uv run python scripts/cleanup_test_data.py --force-clean-all  # DANGEROUS
```

**Features**:
- ✅ Dry run by default (safe preview)
- ✅ Cascade deletes (documents, folders, users, sessions)
- ✅ GCS file cleanup
- ✅ Confirmation prompts
- ✅ Detailed summary reports
- ✅ Pattern-based filtering

## GCP Infrastructure Scripts

### Firestore Index Creation

**Script**: `../create_firestore_indexes.py`

Create required composite indexes for Firestore queries.

```bash
# From project root
uv run python create_firestore_indexes.py
```

### GCS Bucket Setup

**Script**: `../setup_gcp_bucket.py`

Interactive setup for Google Cloud Storage bucket with proper configuration.

```bash
# From project root
uv run python setup_gcp_bucket.py
```

### Firestore Index Deployment

**Script**: `deploy_firestore_indexes.py`

Deploy indexes using gcloud from index configuration.

```bash
# From scripts directory
python deploy_firestore_indexes.py
```

### GCP Authentication Helper

**Script**: `gcp_auth_helper.py`

Verify GCP authentication and permissions.

```bash
uv run python scripts/gcp_auth_helper.py
```

### GCS Setup Verification

**Script**: `verify_gcs_setup.py`

Verify Google Cloud Storage configuration.

```bash
uv run python scripts/verify_gcs_setup.py
```

## Maintenance Scripts

Located in `scripts/maintenance/`:

### Document Sync Diagnosis

**Script**: `diagnose_document_sync.py`

Troubleshoot document synchronization issues between Firestore and GCS.

```bash
uv run python scripts/maintenance/diagnose_document_sync.py
```

### Clean Up Duplicate Documents

**Script**: `cleanup_duplicate_documents.py`

Remove duplicate documents from Firestore.

```bash
uv run python scripts/maintenance/cleanup_duplicate_documents.py
```

### Clean Up Duplicate Storage Paths

**Script**: `cleanup_duplicate_storage_paths.py`

Clean up duplicate files in GCS.

```bash
uv run python scripts/maintenance/cleanup_duplicate_storage_paths.py
```

## Quick Reference

| Task | Command |
|------|---------|
| **List test data** | `./list_test_data.sh` |
| **Preview cleanup** | `./cleanup_all_test_data.sh` |
| **Execute cleanup** | `./cleanup_all_test_data.sh --execute` |
| **Clean specific org** | `./cleanup_all_test_data.sh --execute --org-id ID` |
| **Clean all orgs** | `uv run python scripts/cleanup_test_data.py --force-clean-all` |
| **Create indexes** | `uv run python create_firestore_indexes.py` |
| **Verify GCP** | `uv run python scripts/gcp_auth_helper.py` |

## Documentation

For detailed information, see:
- **[TESTING_AND_CLEANUP.md](../TESTING_AND_CLEANUP.md)** - Comprehensive guide to testing and cleanup
- **[CLAUDE.md](../CLAUDE.md)** - Project overview and development guide
- **[README.md](../README.md)** - General project information

## Safety Notes

⚠️ **Always run with `--dry-run` first** to preview what will be deleted

⚠️ **Backup important data** before running cleanup scripts

⚠️ **Never run `--force-clean-all` in production** - it deletes ALL organizations

✅ **Use Application Default Credentials** or service account with appropriate permissions

✅ **Verify cleanup results** with `./list_test_data.sh` after running cleanup
