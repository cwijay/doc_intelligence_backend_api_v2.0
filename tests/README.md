# API Test Suite Documentation

Comprehensive test suite for the Document Intelligence Backend API with support for local and Cloud Run testing.

## Table of Contents

- [Quick Start](#quick-start)
- [Test Structure](#test-structure)
- [Configuration](#configuration)
- [Running Tests](#running-tests)
- [Test Categories](#test-categories)
- [Writing New Tests](#writing-new-tests)
- [CI/CD Integration](#cicd-integration)
- [Troubleshooting](#troubleshooting)

## Quick Start

### Prerequisites

1. **Install dependencies:**
   ```bash
   uv sync
   ```

2. **Set up environment:**
   ```bash
   # Copy example env file
   cp .env.example .env.test

   # Edit .env.test with test configuration
   # - Firebase/Firestore credentials
   # - OpenAI API key (for AI tests)
   # - Test base URL
   ```

3. **Run all tests:**
   ```bash
   # Local server (start server first)
   ./run_dev.sh  # In one terminal
   uv run pytest tests/ -v  # In another terminal

   # Cloud Run endpoint
   TEST_BASE_URL=https://document-intelligence-api-726919062103.us-central1.run.app uv run pytest tests/ -v
   ```

## Test Structure

```
tests/
├── conftest.py                          # Shared fixtures and configuration
├── test_config.py                       # Test configuration and data factories
├── pytest.ini                           # Pytest configuration
├── README.md                            # This file
│
├── utils/                               # Test utilities
│   ├── test_helpers.py                  # Helper functions
│   ├── test_data_factory.py             # Covered in test_config.py
│   └── cleanup_manager.py               # Resource cleanup utilities
│
├── api/                                 # API endpoint tests
│   ├── test_auth.py                     # Authentication tests (18 tests)
│   ├── test_organizations.py            # Organization CRUD tests (11 tests)
│   ├── test_users.py                    # User management tests
│   ├── test_folders.py                  # Folder management tests
│   ├── test_document_upload.py          # Document upload tests (10 tests)
│   ├── test_document_management.py      # Document CRUD tests
│   ├── test_document_download.py        # Download tests
│   ├── test_document_processing.py      # LlamaParse tests
│   ├── test_document_ai.py              # AI content tests (15 tests)
│   └── test_document_sync.py            # Sync validation tests
│
└── integration/                         # Integration tests
    ├── test_full_lifecycle.py           # Complete workflow tests
    └── test_multi_user.py               # Multi-user scenarios
```

## Configuration

### Environment Variables

Set these in your environment or `.env.test` file:

```bash
# Target Environment
TEST_BASE_URL=http://localhost:8000           # Default: local server
# TEST_BASE_URL=https://your-app.run.app      # Cloud Run deployment

# Timeouts
TEST_TIMEOUT=30                                # Default request timeout
TEST_CLEANUP_ON_FAILURE=True                   # Cleanup even if test fails

# Logging
TEST_LOG_LEVEL=INFO                            # DEBUG, INFO, WARNING, ERROR

# Firebase/Firestore (required for tests)
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_DATABASE_ID=biz2bricks-docdb-v1

# AI Services (required for AI tests)
OPENAI_API_KEY=your-openai-key
LLAMAPARSE_API_KEY=your-llamaparse-key
```

### Test Configuration

The `tests/test_config.py` module provides:

```python
from tests.test_config import config, data_factory

# Configuration
config.base_url                  # Base URL for tests
config.api_prefix               # API prefix (/api/v1)
config.is_cloud_run             # Check if testing Cloud Run
config.get_endpoint(path)       # Get full endpoint URL

# Data Generation
data_factory.generate_org_name()         # Unique org name
data_factory.generate_email()            # Unique email
data_factory.generate_user_data()        # Complete user data
data_factory.generate_org_data()         # Complete org data
data_factory.generate_folder_data()      # Complete folder data
```

## Running Tests

### Basic Commands

```bash
# Run all tests
uv run pytest tests/ -v

# Run specific test file
uv run pytest tests/api/test_auth.py -v

# Run specific test class
uv run pytest tests/api/test_auth.py::TestAuthenticationFlow -v

# Run specific test
uv run pytest tests/api/test_auth.py::TestAuthenticationFlow::test_01_list_organizations -v

# Run with coverage
uv run pytest tests/ --cov=app --cov-report=html
```

### Test Selection by Markers

```bash
# Run only authentication tests
uv run pytest tests/ -m auth -v

# Run only AI tests (uses OpenAI API, costs money)
uv run pytest tests/ -m ai -v

# Skip slow tests
uv run pytest tests/ -m "not slow" -v

# Skip AI tests (save API costs)
uv run pytest tests/ -m "not ai" -v

# Run only integration tests
uv run pytest tests/ -m integration -v

# Run document-related tests
uv run pytest tests/ -m document -v

# Combine markers
uv run pytest tests/ -m "document and not ai" -v
```

### Testing Against Different Environments

```bash
# Local development server
TEST_BASE_URL=http://localhost:8000 uv run pytest tests/ -v

# Cloud Run deployment
TEST_BASE_URL=https://document-intelligence-api-726919062103.us-central1.run.app \
  uv run pytest tests/ -v

# Staging environment
TEST_BASE_URL=https://staging.your-app.run.app uv run pytest tests/ -v
```

### Parallel Test Execution

```bash
# Install pytest-xdist
uv add --dev pytest-xdist

# Run tests in parallel (4 workers)
uv run pytest tests/ -n 4 -v

# Auto-detect CPU cores
uv run pytest tests/ -n auto -v
```

## Test Categories

### Authentication Tests (`test_auth.py`)

**18 tests** covering:
- Organization lookup and availability
- User registration (with validation)
- Login/logout
- Token refresh
- Session validation
- Concurrent logins
- Error scenarios

```bash
# Run all auth tests
uv run pytest tests/api/test_auth.py -v

# Run only validation tests
uv run pytest tests/api/test_auth.py::TestAuthenticationValidation -v
```

### Organization Tests (`test_organizations.py`)

**11 tests** covering:
- CRUD operations
- Duplicate name handling
- Search and statistics
- Input validation

```bash
uv run pytest tests/api/test_organizations.py -v
```

### Document Upload Tests (`test_document_upload.py`)

**10 tests** covering:
- PDF, TXT, DOCX uploads
- Custom metadata
- Target path specification
- File validation
- Size limits
- Authentication requirements

```bash
uv run pytest tests/api/test_document_upload.py -v

# Skip slow large file tests
uv run pytest tests/api/test_document_upload.py -m "not slow" -v
```

### AI Content Tests (`test_document_ai.py`)

**15 tests** covering:
- Document summarization
- Question generation (1-20 count)
- FAQ generation (1-20 count)
- Custom prompts
- Caching behavior
- Error handling

**Note:** These tests use real OpenAI API calls and **cost money**. Skip if needed:

```bash
# Skip AI tests
uv run pytest tests/ -m "not ai" -v

# Run only AI tests
uv run pytest tests/api/test_document_ai.py -v
```

### Integration Tests (`test_full_lifecycle.py`)

**Complete end-to-end workflows:**

```bash
# Run full lifecycle test
uv run pytest tests/integration/test_full_lifecycle.py::TestCompleteDocumentLifecycle -v
```

This test covers:
1. Create organization
2. Register user
3. Login
4. Upload document
5. Generate AI content (summary, questions, FAQ)
6. Verify caching
7. Download document
8. Delete document
9. Logout
10. Cleanup

## Writing New Tests

### Using Fixtures

```python
import pytest

@pytest.mark.asyncio
async def test_my_endpoint(http_client, resource_tracker):
    """Test my endpoint."""
    # Use http_client for requests
    response = await http_client.get("/api/v1/health")
    assert response.status_code == 200

    # Track resources for cleanup
    resource_tracker.add_organization(org_id)
```

### Using Test Helpers

```python
from tests.utils.test_helpers import (
    create_test_user_session,
    upload_document,
    generate_summary
)

@pytest.mark.asyncio
async def test_with_helpers(http_client, sample_pdf_file, resource_tracker):
    """Test using helper functions."""
    # Create org, user, and login in one step
    org_id, credentials = await create_test_user_session(http_client)
    resource_tracker.add_organization(org_id)

    # Upload document
    doc = await upload_document(
        http_client,
        credentials,
        sample_pdf_file.read(),
        "test.pdf",
        "application/pdf"
    )

    # Use authenticated headers
    response = await http_client.get(
        "/api/v1/documents/",
        headers=credentials.auth_headers
    )
    assert response.status_code == 200
```

### Test Organization Best Practices

```python
@pytest.mark.document  # Mark test category
@pytest.mark.slow      # Mark if test is slow
class TestMyFeature:
    """Test suite for my feature."""

    @pytest.mark.asyncio
    async def test_01_first_operation(self, http_client):
        """Test first operation."""
        # Test implementation
        pass

    @pytest.mark.asyncio
    async def test_02_second_operation(self, http_client):
        """Test second operation."""
        # Test implementation
        pass
```

### Adding Custom Markers

1. **Add to `pytest.ini`:**
   ```ini
   markers =
       mymarker: Description of my marker
   ```

2. **Add to `conftest.py`:**
   ```python
   def pytest_configure(config):
       config.addinivalue_line("markers", "mymarker: Description")
   ```

3. **Use in tests:**
   ```python
   @pytest.mark.mymarker
   async def test_something():
       pass
   ```

## CI/CD Integration

### GitHub Actions

Example workflow (`.github/workflows/api-tests.yml`):

```yaml
name: API Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh

      - name: Install dependencies
        run: uv sync

      - name: Run tests (skip AI tests)
        env:
          TEST_BASE_URL: ${{ secrets.TEST_BASE_URL }}
          FIREBASE_PROJECT_ID: ${{ secrets.FIREBASE_PROJECT_ID }}
          FIREBASE_DATABASE_ID: ${{ secrets.FIREBASE_DATABASE_ID }}
        run: |
          uv run pytest tests/ -m "not ai" -v --cov=app --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

### Cloud Build

Add to `cloudbuild.yaml`:

```yaml
steps:
  # ... existing build steps ...

  - name: 'python:3.12'
    entrypoint: bash
    args:
      - '-c'
      - |
        curl -LsSf https://astral.sh/uv/install.sh | sh
        source $HOME/.cargo/env
        uv sync
        uv run pytest tests/ -m "not ai and not slow" -v
    env:
      - 'TEST_BASE_URL=${_TEST_BASE_URL}'
      - 'FIREBASE_PROJECT_ID=${PROJECT_ID}'
```

## Troubleshooting

### Common Issues

#### 1. **Connection Refused**

```
Error: Connection refused to localhost:8000
```

**Solution:**
- Ensure development server is running: `./run_dev.sh`
- Check if port 8000 is in use
- Verify `TEST_BASE_URL` is correct

#### 2. **Authentication Failures**

```
AssertionError: Failed to login: 401 - Unauthorized
```

**Solution:**
- Verify Firebase credentials are configured
- Check that organization was created successfully
- Ensure user registration completed
- Verify JWT secret is set

#### 3. **Cleanup Errors**

```
Failed to cleanup organization: 404 - Not Found
```

**Solution:**
- This is usually safe to ignore (resource already deleted)
- Check cleanup summary at end of test
- Set `TEST_CLEANUP_ON_FAILURE=False` to debug

#### 4. **AI Tests Timing Out**

```
Timeout after 30 seconds
```

**Solution:**
- AI operations can be slow
- Tests use extended timeout (`config.ai_operation_timeout = 120s`)
- Increase timeout if needed: `TEST_TIMEOUT=180`
- Skip AI tests if not needed: `-m "not ai"`

#### 5. **File Upload Failures**

```
Failed to upload document: 422 - Validation Error
```

**Solution:**
- Check file fixtures (`sample_pdf_file`, etc.)
- Verify file content type is correct
- Ensure file is not empty
- Check GCS bucket permissions

### Debug Mode

```bash
# Enable debug logging
TEST_LOG_LEVEL=DEBUG uv run pytest tests/ -v -s

# Show captured output
uv run pytest tests/ -v -s --capture=no

# Drop into debugger on failure
uv run pytest tests/ --pdb

# Show local variables in traceback
uv run pytest tests/ -v -l
```

### Viewing Test Logs

```bash
# Test logs are written to tests/test.log
tail -f tests/test.log

# View specific test output
uv run pytest tests/api/test_auth.py -v -s
```

## Test Coverage

```bash
# Generate coverage report
uv run pytest tests/ --cov=app --cov-report=html

# View report
open htmlcov/index.html

# Check coverage threshold
uv run pytest tests/ --cov=app --cov-fail-under=80
```

## Performance

### Test Execution Time

Approximate times (local server):

| Test Suite | Tests | Time | Notes |
|------------|-------|------|-------|
| Authentication | 18 | ~30s | Fast |
| Organizations | 11 | ~15s | Fast |
| Document Upload | 10 | ~45s | File I/O |
| AI Content | 15 | ~5-10min | OpenAI API calls |
| Integration | 3 | ~8-12min | Full workflow + AI |

**Tips for faster testing:**
- Skip AI tests: `-m "not ai"`
- Skip slow tests: `-m "not slow"`
- Run in parallel: `-n auto`
- Test specific modules only

## Support

For issues or questions:
1. Check this documentation
2. Review test code and comments
3. Check application logs: `tests/test.log`
4. Review API documentation: `/docs` (local server)
5. Consult CLAUDE.md for application details

## Contributing

When adding new tests:
1. Follow existing test structure and naming
2. Use appropriate markers (`@pytest.mark.xxx`)
3. Add docstrings explaining what the test does
4. Use test helpers and fixtures
5. Ensure cleanup with `resource_tracker`
6. Update this README if adding new test categories
7. Run full test suite before committing

## License

Same as main application.
