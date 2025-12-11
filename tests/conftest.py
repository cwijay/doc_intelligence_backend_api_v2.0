"""
Pytest configuration and fixtures for the test suite.

This module provides shared fixtures for unit and integration tests.
"""

import os
import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, AsyncGenerator, Generator, List
from unittest.mock import Mock, MagicMock, AsyncMock, patch

import pytest
import pytest_asyncio
from faker import Faker
from httpx import AsyncClient, ASGITransport

# Set test environment before importing app modules
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-testing-purposes-only-32chars")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("USE_CLOUD_SQL_CONNECTOR", "false")
os.environ.setdefault("GCS_BUCKET_NAME", "test-bucket")
os.environ.setdefault("GCP_PROJECT_ID", "test-project")

fake = Faker()


# =============================================================================
# Pytest Configuration
# =============================================================================

def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests (API)")
    config.addinivalue_line("markers", "slow: Slow running tests")
    config.addinivalue_line("markers", "auth: Authentication tests")
    config.addinivalue_line("markers", "db: Database tests")
    config.addinivalue_line("markers", "api: API endpoint tests")


# =============================================================================
# Event Loop Configuration
# =============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# Test Data Generators
# =============================================================================

@pytest.fixture
def user_data() -> Dict[str, Any]:
    """Generate random user data for testing."""
    return {
        "id": str(uuid.uuid4()),
        "email": fake.email(),
        "username": fake.user_name()[:50],
        "full_name": fake.name(),
        "password": "SecurePass123!",
        "role": "user",
        "is_active": True,
        "org_id": str(uuid.uuid4()),
    }


@pytest.fixture
def org_data() -> Dict[str, Any]:
    """Generate random organization data for testing."""
    return {
        "id": str(uuid.uuid4()),
        "name": fake.company()[:100],
        "plan_type": "free",
        "domain": fake.domain_name(),
        "settings": {},
        "is_active": True,
    }


@pytest.fixture
def document_data() -> Dict[str, Any]:
    """Generate random document data for testing."""
    return {
        "id": str(uuid.uuid4()),
        "name": fake.file_name(extension="pdf"),
        "original_filename": fake.file_name(extension="pdf"),
        "file_type": "pdf",
        "file_size": fake.random_int(min=1024, max=10485760),
        "storage_path": f"orgs/{uuid.uuid4()}/documents/{uuid.uuid4()}.pdf",
        "status": "uploaded",
        "org_id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
    }


@pytest.fixture
def folder_data() -> Dict[str, Any]:
    """Generate random folder data for testing."""
    return {
        "id": str(uuid.uuid4()),
        "name": fake.word(),
        "path": f"/{fake.word()}",
        "org_id": str(uuid.uuid4()),
        "parent_id": None,
    }


# =============================================================================
# Authentication Fixtures
# =============================================================================

@pytest.fixture
def mock_jwt_secret():
    """Provide a consistent JWT secret for testing."""
    return "test-secret-key-for-testing-purposes-only-32chars"


@pytest.fixture
def valid_token_payload(user_data: Dict[str, Any], org_data: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a valid JWT token payload."""
    now = datetime.now(timezone.utc)
    return {
        "sub": user_data["id"],
        "org_id": org_data["id"],
        "email": user_data["email"],
        "role": user_data["role"],
        "token_type": "access",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(hours=2),
    }


@pytest.fixture
def expired_token_payload(valid_token_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Generate an expired JWT token payload."""
    payload = valid_token_payload.copy()
    payload["exp"] = datetime.now(timezone.utc) - timedelta(hours=1)
    return payload


@pytest.fixture
def mock_current_user(user_data: Dict[str, Any], org_data: Dict[str, Any]) -> Dict[str, Any]:
    """Mock current user data as returned by get_current_user_org."""
    return {
        "user_id": user_data["id"],
        "org_id": org_data["id"],
        "email": user_data["email"],
        "role": user_data["role"],
        "token_id": str(uuid.uuid4()),
        "issued_at": datetime.now(timezone.utc).timestamp(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=2)).timestamp(),
    }


# =============================================================================
# Mock Objects
# =============================================================================

@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.flush = AsyncMock()
    session.add = Mock()
    session.delete = Mock()
    return session


@pytest.fixture
def mock_gcs_client():
    """Create a mock GCS client."""
    client = Mock()
    client.bucket = Mock()
    client.upload_blob = AsyncMock()
    client.download_blob = AsyncMock()
    client.delete_blob = AsyncMock()
    client.generate_signed_url = Mock(return_value="https://storage.googleapis.com/test-signed-url")
    client.blob_exists = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_upload_file():
    """Create a mock UploadFile object."""
    file = Mock()
    file.filename = "test_document.pdf"
    file.content_type = "application/pdf"
    file.size = 1024 * 100  # 100KB
    file.file = Mock()
    file.read = AsyncMock(return_value=b"test file content")
    file.seek = AsyncMock()
    return file


# =============================================================================
# Application Fixtures
# =============================================================================

@pytest.fixture
def app():
    """Create a test FastAPI application instance."""
    # Import here to ensure test environment is set
    from app.main import app as fastapi_app
    return fastapi_app


@pytest_asyncio.fixture
async def async_client(app) -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for API testing."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        yield client


# =============================================================================
# Database Fixtures (for integration tests)
# =============================================================================

@pytest.fixture
def mock_database_manager():
    """Create a mock DatabaseManager."""
    manager = Mock()
    manager.session = MagicMock()
    manager.test_connection = AsyncMock(return_value=True)
    manager.create_tables = AsyncMock()
    manager.close = AsyncMock()
    return manager


# =============================================================================
# Service Fixtures
# =============================================================================

@pytest.fixture
def mock_user_service():
    """Create a mock UserService."""
    service = Mock()
    service.get_user = AsyncMock()
    service.create_user = AsyncMock()
    service.update_user = AsyncMock()
    service.delete_user = AsyncMock()
    service.list_users = AsyncMock()
    service.get_user_by_email = AsyncMock()
    service.get_user_by_email_global = AsyncMock()
    service.verify_password = Mock(return_value=True)
    return service


@pytest.fixture
def mock_org_service():
    """Create a mock OrgService."""
    service = Mock()
    service.get_organization = AsyncMock()
    service.create_organization = AsyncMock()
    service.update_organization = AsyncMock()
    service.delete_organization = AsyncMock()
    service.list_organizations = AsyncMock()
    return service


@pytest.fixture
def mock_document_service():
    """Create a mock DocumentService."""
    service = Mock()
    service.create_document = AsyncMock()
    service.get_document = AsyncMock()
    service.update_document = AsyncMock()
    service.delete_document = AsyncMock()
    service.list_documents = AsyncMock()
    return service


@pytest.fixture
def mock_folder_service():
    """Create a mock FolderService."""
    service = Mock()
    service.create_folder = AsyncMock()
    service.get_folder = AsyncMock()
    service.delete_folder = AsyncMock()
    service.list_folders = AsyncMock()
    service.get_folder_tree = AsyncMock()
    return service


@pytest.fixture
def mock_audit_service():
    """Create a mock AuditService."""
    service = Mock()
    service.log_event = AsyncMock()
    service.get_audit_logs = AsyncMock()
    service.get_user_activity = AsyncMock()
    return service


# =============================================================================
# Helper Functions
# =============================================================================

def create_mock_result(data: Any) -> Mock:
    """Create a mock SQLAlchemy result object."""
    result = Mock()
    result.scalar_one_or_none = Mock(return_value=data)
    result.scalars = Mock(return_value=Mock(all=Mock(return_value=[data] if data else [])))
    result.scalar = Mock(return_value=data)
    return result


def create_auth_header(token: str) -> Dict[str, str]:
    """Create an authorization header with a bearer token."""
    return {"Authorization": f"Bearer {token}"}


# =============================================================================
# GCS Cleanup Utilities
# =============================================================================

class GCSTestCleanup:
    """Track and cleanup GCS objects created during tests."""

    def __init__(self, bucket_name: str):
        self.bucket_name = bucket_name
        self.created_objects: List[str] = []
        self.test_prefix = f"test-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"

    def track(self, object_path: str):
        """Track an object path for cleanup."""
        self.created_objects.append(object_path)

    def get_test_path(self, filename: str) -> str:
        """Generate a test-prefixed path for isolation."""
        return f"{self.test_prefix}/{filename}"

    async def cleanup(self):
        """Delete all tracked objects from GCS."""
        # Import here to avoid circular imports during test collection
        try:
            from app.core.gcs_client import gcs_client
            if not gcs_client.is_initialized:
                return

            for path in self.created_objects:
                try:
                    gcs_client.delete_file(path)
                except Exception:
                    pass  # Ignore cleanup errors
        except ImportError:
            pass
        self.created_objects.clear()

    async def cleanup_prefix(self):
        """Delete all objects with the test prefix."""
        try:
            from app.core.gcs_client import gcs_client
            if not gcs_client.is_initialized:
                return

            # List and delete all objects with test prefix
            bucket = gcs_client.client.bucket(self.bucket_name)
            blobs = bucket.list_blobs(prefix=self.test_prefix)
            for blob in blobs:
                blob.delete()
        except Exception:
            pass


@pytest.fixture
def gcs_cleanup() -> Generator[GCSTestCleanup, None, None]:
    """
    Provide GCS cleanup utility that tracks and cleans up objects.
    Automatically cleans up after each test.
    """
    bucket_name = os.environ.get("GCS_BUCKET_NAME", "test-bucket")
    cleanup = GCSTestCleanup(bucket_name)
    yield cleanup
    # Synchronous cleanup for fixture teardown
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(cleanup.cleanup())
        else:
            loop.run_until_complete(cleanup.cleanup())
    except RuntimeError:
        pass


# =============================================================================
# File Content Fixtures
# =============================================================================

@pytest.fixture
def sample_pdf_content() -> bytes:
    """Generate minimal valid PDF content for testing."""
    pdf_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>
endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer
<< /Size 4 /Root 1 0 R >>
startxref
195
%%EOF"""
    return pdf_content


@pytest.fixture
def sample_xlsx_content() -> bytes:
    """Generate minimal XLSX content for testing."""
    # Try loading from sample_files directory first
    sample_path = Path(__file__).parent / "fixtures" / "sample_files" / "test_spreadsheet.xlsx"
    if sample_path.exists():
        return sample_path.read_bytes()

    # Fallback: return minimal valid xlsx header bytes
    return b'PK\x03\x04\x14\x00\x00\x00\x08\x00'


@pytest.fixture
def large_file_content() -> bytes:
    """Generate file content exceeding 50MB limit."""
    return b"x" * (51 * 1024 * 1024)  # 51MB


@pytest.fixture
def invalid_file_content() -> bytes:
    """Generate invalid file content (not PDF or XLSX)."""
    return b"This is not a valid PDF or XLSX file"


# =============================================================================
# Utility Fixtures
# =============================================================================

@pytest.fixture
def unique_email() -> str:
    """Generate a unique email address."""
    return f"user_{uuid.uuid4().hex[:12]}@test.example.com"


@pytest.fixture
def unique_org_name() -> str:
    """Generate a unique organization name."""
    return f"Test Org {uuid.uuid4().hex[:8]}"


@pytest.fixture
def unique_folder_name() -> str:
    """Generate a unique folder name."""
    return f"Folder {uuid.uuid4().hex[:8]}"


# =============================================================================
# Helper Functions
# =============================================================================

# Export helper functions
__all__ = [
    "fake",
    "create_mock_result",
    "create_auth_header",
    "GCSTestCleanup",
]
