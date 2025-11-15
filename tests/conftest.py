"""
Pytest Configuration and Shared Fixtures

Provides shared fixtures for all API tests including HTTP client,
authentication, and resource cleanup.
"""

import asyncio
import io
from typing import Dict, List, Optional, AsyncGenerator
from pathlib import Path
import pytest
import httpx
from dotenv import load_dotenv

# Load test environment variables before test_config initializes
# This ensures TEST_BASE_URL is available when TestConfig reads os.getenv()
test_env_file = Path(__file__).parent.parent / ".env.test"
if test_env_file.exists():
    load_dotenv(test_env_file)

from test_config import config, data_factory, TestCredentials


# ============================================================================
# Pytest Configuration
# ============================================================================

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")
    config.addinivalue_line("markers", "ai: marks tests that use AI services (costs money)")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "auth: marks authentication-related tests")
    config.addinivalue_line("markers", "document: marks document-related tests")


# ============================================================================
# HTTP Client Fixtures
# ============================================================================

@pytest.fixture
async def http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """
    Provide async HTTP client for API requests.

    Yields:
        httpx.AsyncClient configured with base URL and timeout

    Example:
        async def test_endpoint(http_client):
            response = await http_client.get("/health")
            assert response.status_code == 200
    """
    async with httpx.AsyncClient(
        base_url=config.base_url,
        timeout=config.default_timeout
    ) as client:
        yield client


@pytest.fixture
async def ai_http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """
    Provide async HTTP client with extended timeout for AI operations.

    Yields:
        httpx.AsyncClient with longer timeout for AI endpoints

    Example:
        async def test_ai_summary(ai_http_client):
            response = await ai_http_client.post("/documents/summarize", ...)
    """
    async with httpx.AsyncClient(
        base_url=config.base_url,
        timeout=config.ai_operation_timeout
    ) as client:
        yield client


# ============================================================================
# Resource Cleanup Tracking
# ============================================================================

class ResourceTracker:
    """Track created resources for cleanup after tests."""

    def __init__(self):
        self.organizations: List[str] = []
        self.users: List[Dict[str, str]] = []  # [{"org_id": "...", "user_id": "..."}]
        self.documents: List[Dict[str, str]] = []  # [{"org_id": "...", "doc_id": "..."}]
        self.folders: List[Dict[str, str]] = []  # [{"org_id": "...", "folder_id": "..."}]

    def add_organization(self, org_id: str):
        """Track created organization."""
        if org_id and org_id not in self.organizations:
            self.organizations.append(org_id)

    def add_user(self, org_id: str, user_id: str):
        """Track created user."""
        if org_id and user_id:
            self.users.append({"org_id": org_id, "user_id": user_id})

    def add_document(self, org_id: str, doc_id: str):
        """Track created document."""
        if org_id and doc_id:
            self.documents.append({"org_id": org_id, "doc_id": doc_id})

    def add_folder(self, org_id: str, folder_id: str):
        """Track created folder."""
        if org_id and folder_id:
            self.folders.append({"org_id": org_id, "folder_id": folder_id})

    async def cleanup_all(self, client: httpx.AsyncClient, headers: Optional[Dict] = None):
        """
        Cleanup all tracked resources in reverse order.

        Args:
            client: HTTP client for making cleanup requests
            headers: Optional auth headers for cleanup operations
        """
        # Cleanup documents first
        for doc in reversed(self.documents):
            try:
                await client.delete(
                    f"{config.api_prefix}/documents/{doc['doc_id']}",
                    headers=headers
                )
            except Exception as e:
                print(f"Failed to cleanup document {doc['doc_id']}: {e}")

        # Cleanup folders
        for folder in reversed(self.folders):
            try:
                await client.delete(
                    f"{config.api_prefix}/organizations/{folder['org_id']}/folders/{folder['folder_id']}",
                    headers=headers
                )
            except Exception as e:
                print(f"Failed to cleanup folder {folder['folder_id']}: {e}")

        # Cleanup users
        for user in reversed(self.users):
            try:
                await client.delete(
                    f"{config.api_prefix}/organizations/{user['org_id']}/users/{user['user_id']}",
                    headers=headers
                )
            except Exception as e:
                print(f"Failed to cleanup user {user['user_id']}: {e}")

        # Cleanup organizations last
        for org_id in reversed(self.organizations):
            try:
                await client.delete(
                    f"{config.api_prefix}/organizations/{org_id}",
                    headers=headers
                )
            except Exception as e:
                print(f"Failed to cleanup organization {org_id}: {e}")


@pytest.fixture
async def resource_tracker(http_client) -> AsyncGenerator[ResourceTracker, None]:
    """
    Provide resource tracker with automatic cleanup.

    Yields:
        ResourceTracker instance

    The tracker will automatically cleanup all tracked resources after the test.

    Example:
        async def test_create_org(http_client, resource_tracker):
            response = await http_client.post("/organizations", json={...})
            org_id = response.json()["id"]
            resource_tracker.add_organization(org_id)
            # Org will be auto-cleaned up after test
    """
    tracker = ResourceTracker()
    yield tracker

    # Cleanup after test (even if test failed, unless configured otherwise)
    try:
        await tracker.cleanup_all(http_client)
    except Exception as e:
        print(f"Error during resource cleanup: {e}")


# ============================================================================
# Authentication Fixtures
# ============================================================================

@pytest.fixture
async def test_org_and_user(http_client, resource_tracker) -> AsyncGenerator[Dict, None]:
    """
    Create test organization and user, then clean up.

    Yields:
        Dict with:
            - org_id: Organization ID
            - org_name: Organization name
            - user_id: User ID
            - email: User email
            - password: User password
            - credentials: TestCredentials object

    Example:
        async def test_something(http_client, test_org_and_user):
            org_id = test_org_and_user["org_id"]
            headers = test_org_and_user["credentials"].auth_headers
    """
    # Generate unique test data
    org_data = data_factory.generate_org_data()
    user_data = data_factory.generate_user_data()

    # Create organization
    org_response = await http_client.post(
        f"{config.api_prefix}/organizations",
        json=org_data
    )
    assert org_response.status_code == 201, f"Failed to create org: {org_response.text}"
    org_result = org_response.json()
    org_id = org_result["id"]
    resource_tracker.add_organization(org_id)

    # Register user
    register_data = {
        **user_data,
        "org_id": org_id
    }
    register_response = await http_client.post(
        f"{config.api_prefix}/auth/register",
        json=register_data
    )
    assert register_response.status_code == 200, f"Failed to register user: {register_response.text}"

    # Login user
    login_response = await http_client.post(
        f"{config.api_prefix}/auth/login",
        json={
            "email": user_data["email"],
            "password": user_data["password"]
        }
    )
    assert login_response.status_code == 200, f"Failed to login: {login_response.text}"
    login_result = login_response.json()

    # Create credentials object
    credentials = TestCredentials(
        email=user_data["email"],
        password=user_data["password"]
    )
    credentials.update_from_login_response(login_result)
    resource_tracker.add_user(org_id, credentials.user_id)

    yield {
        "org_id": org_id,
        "org_name": org_data["name"],
        "user_id": credentials.user_id,
        "email": credentials.email,
        "password": credentials.password,
        "username": credentials.username,
        "credentials": credentials
    }

    # Cleanup will happen via resource_tracker


@pytest.fixture
async def authenticated_client(http_client, test_org_and_user) -> AsyncGenerator[tuple, None]:
    """
    Provide authenticated HTTP client with test user credentials.

    Yields:
        Tuple of (client, test_data) where:
            - client: httpx.AsyncClient (same as http_client)
            - test_data: Dict with org_id, user_id, credentials, etc.

    Example:
        async def test_protected_endpoint(authenticated_client):
            client, test_data = authenticated_client
            headers = test_data["credentials"].auth_headers
            response = await client.get("/documents/", headers=headers)
    """
    yield http_client, test_org_and_user


# ============================================================================
# Test File Fixtures
# ============================================================================

@pytest.fixture
def sample_pdf_file() -> io.BytesIO:
    """
    Provide sample PDF file for upload tests.

    Returns:
        io.BytesIO with minimal PDF content

    Example:
        def test_upload(sample_pdf_file):
            files = {"file": ("test.pdf", sample_pdf_file, "application/pdf")}
    """
    # Minimal valid PDF content
    pdf_content = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/Resources <<
/Font <<
/F1 <<
/Type /Font
/Subtype /Type1
/BaseFont /Helvetica
>>
>>
>>
/MediaBox [0 0 612 792]
/Contents 4 0 R
>>
endobj
4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
100 700 Td
(Test PDF Document) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000317 00000 n
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
410
%%EOF
"""
    return io.BytesIO(pdf_content)


@pytest.fixture
def sample_txt_file() -> io.BytesIO:
    """
    Provide sample text file for upload tests.

    Returns:
        io.BytesIO with text content

    Example:
        def test_upload(sample_txt_file):
            files = {"file": ("test.txt", sample_txt_file, "text/plain")}
    """
    content = b"""Test Document Content

This is a test document for API testing.
It contains multiple lines of text.

Key points:
- Point 1
- Point 2
- Point 3

End of document.
"""
    return io.BytesIO(content)


@pytest.fixture
def sample_docx_file() -> io.BytesIO:
    """
    Provide sample DOCX file for upload tests.

    Note: This is a minimal DOCX structure. For comprehensive DOCX testing,
    consider using python-docx library to generate proper documents.

    Returns:
        io.BytesIO with minimal DOCX content
    """
    # For simplicity, return a text file labeled as DOCX
    # In production tests, you'd want to use python-docx to create real DOCX files
    content = b"""PK\x03\x04Test DOCX Content"""
    return io.BytesIO(content)


# ============================================================================
# Event Loop Configuration
# ============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """
    Create event loop for async tests.

    This ensures all async tests share the same event loop.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# Test Data Fixtures
# ============================================================================

@pytest.fixture
def unique_org_data() -> Dict:
    """Generate unique organization data for each test."""
    return data_factory.generate_org_data()


@pytest.fixture
def unique_user_data() -> Dict:
    """Generate unique user data for each test."""
    return data_factory.generate_user_data()


@pytest.fixture
def unique_folder_data() -> Dict:
    """Generate unique folder data for each test."""
    return data_factory.generate_folder_data()


# ============================================================================
# Configuration Fixtures
# ============================================================================

@pytest.fixture
def test_config():
    """Provide test configuration."""
    return config


@pytest.fixture
def test_data_factory():
    """Provide test data factory."""
    return data_factory
