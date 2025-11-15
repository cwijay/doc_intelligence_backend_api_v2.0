# Unit Tests Documentation

## Overview

Comprehensive unit test suite for the Document Intelligence Backend API. Tests are organized by application layer and use mocked dependencies for isolated testing.

**Status**: 216 passing tests, 31 tests need adjustment to match actual implementation
**Coverage**: Core, Models, Services, and Utilities layers

## Test Structure

```
tests/unit_tests/
├── conftest.py                 # Shared fixtures and mocks
├── core/                       # Core layer tests
│   ├── test_config.py         # Settings configuration
│   ├── test_security.py       # Password hashing, JWT, tokens
│   └── test_exceptions.py     # Custom exception classes
├── models/                     # Data model tests
│   ├── test_user.py           # User model
│   ├── test_organization.py   # Organization model
│   ├── test_document.py       # Document model (with AI content)
│   └── test_folder.py         # Folder model (hierarchical)
├── services/                   # Service layer tests
│   ├── test_auth_service.py   # Authentication service
│   ├── test_user_service.py   # User management service
│   └── document/
│       └── test_document_validation_service.py  # File validation
└── utils/                      # Utility tests
    └── test_validators.py     # Input validation functions
```

## Running Tests

### Run All Unit Tests
```bash
uv run pytest tests/unit_tests/ -v
```

### Run Specific Test Modules
```bash
# Test core layer
uv run pytest tests/unit_tests/core/ -v

# Test models layer
uv run pytest tests/unit_tests/models/ -v

# Test services layer
uv run pytest tests/unit_tests/services/ -v

# Test specific file
uv run pytest tests/unit_tests/core/test_security.py -v
```

### Run With Coverage
```bash
uv run pytest tests/unit_tests/ --cov=app --cov-report=html
```

### Run Fast (Skip Slow Tests)
```bash
uv run pytest tests/unit_tests/ -v -m "not slow"
```

## Test Environment

Unit tests use `.env.test` for configuration:
- Isolated test environment variables
- Mock credentials (not production)
- Test-specific settings

Key environment variables:
- `JWT_SECRET_KEY`: Test JWT secret
- `FIREBASE_PROJECT_ID`: test-project
- `GCS_BUCKET_NAME`: test-bucket
- `ENVIRONMENT`: test

## Test Fixtures (conftest.py)

### Mock Clients

- **mock_firestore_client**: In-memory Firestore mock
- **mock_firebase_manager**: Firebase singleton mock
- **mock_gcs_client**: GCS client mock
- **mock_gcs_manager**: GCS manager singleton mock

### Mock Data

- **mock_user_data**: Sample user dictionary
- **mock_organization_data**: Sample organization dictionary
- **mock_document_data**: Sample document dictionary
- **mock_folder_data**: Sample folder dictionary

### Mock Services

- **mock_settings**: Application settings mock
- **mock_password_hasher**: Password hashing functions mock
- **mock_jwt**: JWT token functions mock
- **mock_openai_client**: OpenAI API mock
- **mock_llamaparse**: LlamaParse document parser mock

### Utilities

- **mock_upload_file**: Factory for creating mock file uploads
- **mock_datetime**: Fixed datetime for consistent testing

## Test Coverage by Layer

### Core Layer (3 test files, 50+ tests)

**test_config.py**:
- Settings creation and defaults
- JWT configuration validation
- Session management settings
- Firebase/GCS configuration
- Document processing settings

**test_security.py**:
- Password hashing and verification
- Password strength validation
- JWT token creation and verification
- Token expiration and invalidation
- Token management (blacklisting, cleanup)
- Secure password generation

**test_exceptions.py**:
- All custom exception classes
- Error response creation
- HTTP status code mapping
- Error detail formatting

### Models Layer (4 test files, 80+ tests)

**test_user.py**:
- User model creation and validation
- User role properties (admin, user, viewer)
- Permission checks (can_modify, can_admin)
- Timestamp management
- User serialization (to_dict, from_dict)

**test_organization.py**:
- Organization model creation
- Plan type validation (free, starter, pro)
- Premium status checks
- Settings management
- Organization serialization

**test_document.py**:
- Document model creation and validation
- File type and size validation
- Filename sanitization
- Storage path validation
- Metadata security checks
- AI content management (summary, questions, FAQ)
- Document status tracking

**test_folder.py**:
- Folder model creation and validation
- Folder name validation (special chars, length)
- Path validation and sanitization
- Hierarchical path operations
- Folder depth limits (max 5 levels)
- Directory traversal prevention
- Folder tree building

### Services Layer (3 test files, 40+ tests)

**test_auth_service.py**:
- User authentication (login)
- Invalid credentials handling
- Inactive user/organization checks
- User registration
- Invitation token generation and verification

**test_user_service.py**:
- User creation and duplicate detection
- User retrieval (by ID, by email)
- User update and soft delete
- Password verification and updates
- User listing with pagination

**test_document_validation_service.py**:
- File upload validation (type, size)
- Virus scanning and threat detection
- Target path validation
- Directory traversal prevention
- Null byte and injection prevention
- Folder extraction from storage path

### Utilities Layer (1 test file, 40+ tests)

**test_validators.py**:
- Organization name validation
- Domain validation and DNS checks
- Organization settings validation
- UUID validation
- Pagination parameter validation
- Search query sanitization
- URL validation (scheme, length)
- Email format validation
- Filename sanitization
- File size validation

## Mocking Strategy

### Principle: Isolate Unit Tests

All external dependencies are mocked:
- **Firestore/Firebase**: In-memory mock collections
- **Google Cloud Storage**: In-memory blob storage
- **OpenAI API**: Mocked chat completions
- **LlamaParse**: Mocked document parsing
- **File System**: Mock file uploads using io.BytesIO

### Benefits

1. **Fast**: No external API calls
2. **Reliable**: No network dependencies
3. **Isolated**: Each test is independent
4. **Deterministic**: Consistent results
5. **Cost-effective**: No AI API charges

## Test Patterns

### Testing Models

```python
def test_model_creation(mock_data):
    """Test creating model with valid data."""
    model = ModelClass(**mock_data)

    assert model.field == "expected_value"
    assert isinstance(model.created_at, datetime)
```

### Testing Services (with mocks)

```python
@pytest.mark.asyncio
async def test_service_method(mock_firebase_manager):
    """Test service method with mocked dependencies."""
    service = ServiceClass()

    with patch("module.dependency") as mock_dep:
        mock_dep.return_value = expected_result

        result = await service.method()

        assert result == expected_result
```

### Testing Validators

```python
def test_validation_success():
    """Test validator with valid input."""
    result = validate_function("valid input")
    assert result == "expected output"

def test_validation_error():
    """Test validator with invalid input."""
    with pytest.raises(ValidationError) as exc_info:
        validate_function("invalid input")

    assert "expected error" in str(exc_info.value)
```

## Known Test Adjustments Needed

Some tests (31 total) need adjustments to match actual implementation:

### 1. Function Signature Mismatches
- Some tests assume methods that don't exist or have different signatures
- Fix: Update tests to match actual service/model interfaces

### 2. Model Validation Requirements
- Some tests don't provide all required fields
- Fix: Update test data to match model requirements

### 3. Missing Service Methods
- Some tests reference methods not yet implemented
- Fix: Either implement methods or remove tests

## Best Practices

1. **One Assertion Per Test**: Focus each test on one behavior
2. **Descriptive Names**: Test names describe what they test
3. **Arrange-Act-Assert**: Clear test structure
4. **Mock External Dependencies**: No real API calls in unit tests
5. **Test Edge Cases**: Not just happy path
6. **Use Fixtures**: Reuse common test data and mocks

## Contributing

When adding new tests:

1. **Choose Appropriate Layer**: Core, Models, Services, or Utils
2. **Use Existing Fixtures**: Reuse mocks from conftest.py
3. **Follow Naming Convention**: `test_<what_it_tests>`
4. **Add Docstrings**: Explain what the test validates
5. **Mock External Calls**: Use unittest.mock for dependencies
6. **Test Both Success and Failure**: Cover edge cases

## Continuous Integration

Unit tests are designed to run in CI/CD:

```yaml
# Example CI configuration
- name: Run Unit Tests
  run: |
    uv run pytest tests/unit_tests/ -v --cov=app --cov-report=xml
```

## Performance

- **Fast Execution**: ~60-80 seconds for full suite
- **Parallel Capable**: Can run with pytest-xdist
- **No External Dependencies**: All mocked

## Next Steps

1. **Fix Failing Tests**: Adjust 31 tests to match actual implementation
2. **Increase Coverage**: Add tests for uncovered code paths
3. **Add Integration Tests**: Test with real Firebase/GCS (separate suite)
4. **Performance Tests**: Add benchmarks for critical paths
5. **E2E Tests**: Full API workflow testing

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [unittest.mock Guide](https://docs.python.org/3/library/unittest.mock.html)
- [Pydantic Testing](https://docs.pydantic.dev/latest/concepts/validation/)
- [Async Testing](https://pytest-asyncio.readthedocs.io/)

## Support

For questions or issues with tests:
1. Check test output for specific error messages
2. Review mock fixtures in `conftest.py`
3. Verify `.env.test` configuration
4. Check actual implementation in `app/` directory
