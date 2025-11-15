"""
Unit Test Configuration and Fixtures

Provides mocked dependencies for isolated unit testing.
All external dependencies (Firebase, GCS, OpenAI) are mocked.
"""

import os
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from pathlib import Path
import pytest
from pydantic import BaseModel
from dotenv import load_dotenv

# Load test environment variables BEFORE importing app modules
test_env_file = Path(__file__).parent.parent.parent / ".env.test"
if test_env_file.exists():
    load_dotenv(test_env_file, override=True)


# ============================================================================
# Event Loop Configuration
# ============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# Mock Firebase Client
# ============================================================================

class MockFirestoreDocument:
    """Mock Firestore document."""

    def __init__(self, doc_id: str, data: Dict[str, Any]):
        self.id = doc_id
        self._data = data

    def to_dict(self) -> Dict[str, Any]:
        """Return document data."""
        return self._data.copy()

    async def get(self):
        """Mock async get."""
        return self

    def exists(self) -> bool:
        """Check if document exists."""
        return bool(self._data)


class MockFirestoreCollection:
    """Mock Firestore collection."""

    def __init__(self, documents: Optional[List[MockFirestoreDocument]] = None):
        self._documents = documents or []
        self._doc_map = {doc.id: doc for doc in self._documents}

    def document(self, doc_id: str) -> MockFirestoreDocument:
        """Get document reference."""
        if doc_id in self._doc_map:
            return self._doc_map[doc_id]
        return MockFirestoreDocument(doc_id, {})

    async def stream(self):
        """Stream all documents."""
        for doc in self._documents:
            yield doc

    def where(self, *args, **kwargs):
        """Return self for chaining."""
        return self

    def order_by(self, *args, **kwargs):
        """Return self for chaining."""
        return self

    def limit(self, count: int):
        """Limit results."""
        self._documents = self._documents[:count]
        return self

    async def add(self, data: Dict[str, Any]) -> tuple:
        """Add document."""
        doc_id = f"generated_{len(self._documents)}"
        doc = MockFirestoreDocument(doc_id, data)
        self._documents.append(doc)
        self._doc_map[doc_id] = doc
        return (None, doc)

    async def get(self):
        """Get all documents."""
        return self._documents


class MockFirestoreClient:
    """Mock Firestore async client."""

    def __init__(self):
        self._collections: Dict[str, MockFirestoreCollection] = {}

    def collection(self, collection_name: str) -> MockFirestoreCollection:
        """Get or create collection."""
        if collection_name not in self._collections:
            self._collections[collection_name] = MockFirestoreCollection()
        return self._collections[collection_name]

    def add_mock_document(self, collection_name: str, doc_id: str, data: Dict[str, Any]):
        """Add a mock document to a collection."""
        if collection_name not in self._collections:
            self._collections[collection_name] = MockFirestoreCollection()

        doc = MockFirestoreDocument(doc_id, data)
        self._collections[collection_name]._documents.append(doc)
        self._collections[collection_name]._doc_map[doc_id] = doc


@pytest.fixture
def mock_firestore_client():
    """Provide mock Firestore client."""
    return MockFirestoreClient()


@pytest.fixture
def mock_firebase_manager(mock_firestore_client):
    """Mock Firebase manager singleton."""
    manager = Mock()
    manager.db = mock_firestore_client
    manager.is_initialized = True
    manager.project_id = "test-project"
    manager.database_id = "test-database"
    return manager


# ============================================================================
# Mock GCS Client
# ============================================================================

class MockGCSBlob:
    """Mock GCS blob."""

    def __init__(self, name: str, bucket_name: str):
        self.name = name
        self.bucket = Mock()
        self.bucket.name = bucket_name
        self._content = b""
        self.metadata = {}
        self.content_type = "application/octet-stream"

    async def upload_from_file(self, file_obj, content_type: str = None):
        """Mock upload from file."""
        self._content = await file_obj.read()
        if content_type:
            self.content_type = content_type

    async def upload_from_string(self, data: bytes):
        """Mock upload from string."""
        self._content = data

    async def download_as_bytes(self) -> bytes:
        """Mock download."""
        return self._content

    async def delete(self):
        """Mock delete."""
        pass

    def generate_signed_url(self, expiration: timedelta, **kwargs) -> str:
        """Mock signed URL generation."""
        return f"https://storage.googleapis.com/test-bucket/{self.name}?signed=true"

    async def exists(self) -> bool:
        """Check if blob exists."""
        return bool(self._content)


class MockGCSBucket:
    """Mock GCS bucket."""

    def __init__(self, name: str):
        self.name = name
        self._blobs: Dict[str, MockGCSBlob] = {}

    def blob(self, blob_name: str) -> MockGCSBlob:
        """Get or create blob."""
        if blob_name not in self._blobs:
            self._blobs[blob_name] = MockGCSBlob(blob_name, self.name)
        return self._blobs[blob_name]

    async def list_blobs(self, prefix: str = None):
        """List blobs."""
        blobs = list(self._blobs.values())
        if prefix:
            blobs = [b for b in blobs if b.name.startswith(prefix)]
        return blobs


class MockGCSClient:
    """Mock GCS client."""

    def __init__(self, bucket_name: str = "test-bucket"):
        self.bucket_name = bucket_name
        self._bucket = MockGCSBucket(bucket_name)

    def get_bucket(self, bucket_name: str = None) -> MockGCSBucket:
        """Get bucket."""
        return self._bucket

    @property
    def bucket(self) -> MockGCSBucket:
        """Get default bucket."""
        return self._bucket


@pytest.fixture
def mock_gcs_client():
    """Provide mock GCS client."""
    return MockGCSClient()


@pytest.fixture
def mock_gcs_manager(mock_gcs_client):
    """Mock GCS manager singleton."""
    manager = Mock()
    manager.client = mock_gcs_client
    manager.bucket_name = "test-bucket"
    manager.is_initialized = True
    manager.get_bucket = Mock(return_value=mock_gcs_client.bucket)
    return manager


# ============================================================================
# Mock Settings/Config
# ============================================================================

@pytest.fixture
def mock_settings():
    """Provide mock application settings."""
    settings = Mock()

    # FastAPI Configuration
    settings.PROJECT_NAME = "Test Document Intelligence API"
    settings.VERSION = "1.0.0"
    settings.API_V1_STR = "/api/v1"
    settings.DEBUG = True
    settings.ENVIRONMENT = "test"

    # JWT Configuration
    settings.JWT_SECRET_KEY = "test-secret-key-for-unit-testing-only"
    settings.JWT_ALGORITHM = "HS256"
    settings.ACCESS_TOKEN_EXPIRE_MINUTES = 30
    settings.REFRESH_TOKEN_EXPIRE_DAYS = 30

    # Session Configuration
    settings.SESSION_DURATION_HOURS = 2
    settings.REFRESH_SESSION_DURATION_DAYS = 7
    settings.TOKEN_GRACE_PERIOD_MINUTES = 10
    settings.MAX_CONCURRENT_SESSIONS = 5
    settings.INVALIDATE_TOKENS_ON_LOGIN = True
    settings.ENABLE_TOKEN_ROTATION = True

    # Firebase/Firestore
    settings.FIREBASE_PROJECT_ID = "test-project"
    settings.FIREBASE_DATABASE_ID = "test-database"

    # GCS
    settings.GCP_PROJECT_ID = "test-project"
    settings.GCS_BUCKET_NAME = "test-bucket"
    settings.DOCUMENT_STORE_BASE_PATH = ""

    # Document Configuration
    settings.MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    settings.ALLOWED_FILE_TYPES = ["pdf", "xlsx", "docx", "txt"]
    settings.DOCUMENT_UPLOAD_TIMEOUT = 300
    settings.SIGNED_URL_EXPIRATION_MINUTES = 60

    # AI Configuration
    settings.OPENAI_API_KEY = "test-openai-key"
    settings.OPENAI_MODEL = "gpt-5-mini"
    settings.LLAMAPARSE_API_KEY = "test-llamaparse-key"

    # Logging
    settings.LOG_LEVEL = "DEBUG"
    settings.ENABLE_AUTH_AUDIT_LOGGING = True

    return settings


# ============================================================================
# Mock Model Instances
# ============================================================================

@pytest.fixture
def mock_user_data() -> Dict[str, Any]:
    """Provide mock user data."""
    return {
        "id": "user123",
        "org_id": "org123",
        "email": "test@example.com",
        "username": "testuser",
        "password_hash": "$2b$12$abc123",
        "full_name": "Test User",
        "role": "user",
        "is_active": True,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "last_login": None,
    }


@pytest.fixture
def mock_organization_data() -> Dict[str, Any]:
    """Provide mock organization data."""
    return {
        "id": "org123",
        "name": "Test Organization",
        "domain": "test.com",
        "settings": {},
        "plan_type": "free",
        "is_active": True,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }


@pytest.fixture
def mock_document_data() -> Dict[str, Any]:
    """Provide mock document data."""
    return {
        "id": "doc123",
        "organization_id": "org123",
        "folder_id": None,
        "filename": "test.pdf",
        "original_filename": "test.pdf",
        "file_type": "pdf",
        "file_size": 1024,
        "storage_path": "organizations/org123/documents/test.pdf",
        "gcs_path": "organizations/org123/documents/test.pdf",
        "download_url": None,
        "mime_type": "application/pdf",
        "description": "Test document",
        "tags": ["test"],
        "metadata": {},
        "is_active": True,
        "uploaded_by": "user123",
        "upload_status": "completed",
        "processing_status": "not_started",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "ai_summary": None,
        "ai_questions": None,
        "ai_faq": None,
        "parsed_content": None,
    }


@pytest.fixture
def mock_folder_data() -> Dict[str, Any]:
    """Provide mock folder data."""
    return {
        "id": "folder123",
        "organization_id": "org123",
        "name": "Test Folder",
        "parent_id": None,
        "description": "Test folder description",
        "metadata": {},
        "is_active": True,
        "created_by": "user123",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }


# ============================================================================
# Mock Password Hashing
# ============================================================================

@pytest.fixture
def mock_password_hasher():
    """Mock password hashing functions."""
    with patch("app.core.security.hash_password") as mock_hash, \
         patch("app.core.security.verify_password") as mock_verify:

        mock_hash.return_value = "$2b$12$mocked_hash"
        mock_verify.return_value = True

        yield {"hash": mock_hash, "verify": mock_verify}


# ============================================================================
# Mock JWT Functions
# ============================================================================

@pytest.fixture
def mock_jwt():
    """Mock JWT encoding/decoding."""
    def create_mock_token(data: Dict[str, Any]) -> str:
        """Create a mock token."""
        return f"mock_token_{data.get('sub', 'unknown')}"

    def decode_mock_token(token: str) -> Dict[str, Any]:
        """Decode a mock token."""
        return {
            "sub": "user123",
            "org_id": "org123",
            "session_id": "session123",
            "exp": (datetime.utcnow() + timedelta(hours=2)).timestamp(),
        }

    with patch("app.core.security.create_access_token", side_effect=create_mock_token), \
         patch("app.core.security.create_refresh_token", side_effect=create_mock_token), \
         patch("app.core.security.decode_token", side_effect=decode_mock_token):
        yield {
            "create_access_token": create_mock_token,
            "create_refresh_token": create_mock_token,
            "decode_token": decode_mock_token,
        }


# ============================================================================
# Mock File Upload
# ============================================================================

@pytest.fixture
def mock_upload_file():
    """Create mock UploadFile instance."""
    async def create_upload_file(
        filename: str = "test.pdf",
        content: bytes = b"test content",
        content_type: str = "application/pdf"
    ):
        """Create a mock upload file."""
        mock_file = Mock()
        mock_file.filename = filename
        mock_file.content_type = content_type
        mock_file.size = len(content)

        # Mock read method
        async def mock_read():
            return content

        # Mock seek method
        async def mock_seek(position: int):
            pass

        mock_file.read = mock_read
        mock_file.seek = mock_seek

        return mock_file

    return create_upload_file


# ============================================================================
# Mock OpenAI Client
# ============================================================================

@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client."""
    client = Mock()

    # Mock chat completions
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message.content = "This is a test AI response."

    client.chat.completions.create = AsyncMock(return_value=mock_response)

    return client


# ============================================================================
# Mock LlamaParse
# ============================================================================

@pytest.fixture
def mock_llamaparse():
    """Mock LlamaParse document parser."""
    parser = Mock()

    # Mock parse result
    mock_result = Mock()
    mock_result.text = "This is parsed document content."
    mock_result.metadata = {"pages": 1}

    parser.parse = AsyncMock(return_value=[mock_result])

    return parser


# ============================================================================
# Utility Fixtures
# ============================================================================

@pytest.fixture
def mock_datetime():
    """Mock datetime for consistent testing."""
    fixed_time = datetime(2024, 1, 1, 12, 0, 0)

    with patch("datetime.datetime") as mock_dt:
        mock_dt.utcnow.return_value = fixed_time
        mock_dt.now.return_value = fixed_time
        mock_dt.fromisoformat = datetime.fromisoformat

        yield fixed_time


@pytest.fixture
def sample_jwt_payload() -> Dict[str, Any]:
    """Sample JWT payload."""
    return {
        "sub": "user123",
        "org_id": "org123",
        "session_id": "session123",
        "exp": (datetime.utcnow() + timedelta(hours=2)).timestamp(),
        "iat": datetime.utcnow().timestamp(),
    }


# ============================================================================
# Cleanup Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def reset_mocks():
    """Reset all mocks after each test."""
    yield
    # Cleanup happens automatically via pytest
