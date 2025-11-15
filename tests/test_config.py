"""
Test Configuration Module

Provides centralized configuration for API tests with support for both
local development and Cloud Run deployment testing.
"""

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class TestConfig:
    """
    Centralized test configuration.

    Environment Variables:
        TEST_BASE_URL: Base URL for API tests (default: http://localhost:8000)
        TEST_TIMEOUT: Request timeout in seconds (default: 30)
        TEST_CLEANUP_ON_FAILURE: Whether to cleanup on test failure (default: True)
        TEST_LOG_LEVEL: Logging level for tests (default: INFO)
    """

    # Base URLs
    base_url: str = field(default_factory=lambda: os.getenv(
        "TEST_BASE_URL",
        "http://localhost:8000"
    ))
    api_prefix: str = "/api/v1"

    # Timeouts
    default_timeout: float = float(os.getenv("TEST_TIMEOUT", "90"))  # Increased for Cloud Run cold starts
    ai_operation_timeout: float = 120.0  # AI operations can be slow
    upload_timeout: float = 90.0  # Increased for Cloud Run

    # Test behavior
    cleanup_on_failure: bool = os.getenv(
        "TEST_CLEANUP_ON_FAILURE",
        "True"
    ).lower() == "true"

    # Logging
    log_level: str = os.getenv("TEST_LOG_LEVEL", "INFO")

    # Cloud Run specific
    cloud_run_url: str = "https://document-intelligence-api-726919062103.us-central1.run.app"

    @property
    def is_cloud_run(self) -> bool:
        """Check if testing against Cloud Run deployment."""
        return "run.app" in self.base_url or "cloud" in self.base_url.lower()

    @property
    def full_api_url(self) -> str:
        """Get full API URL with prefix."""
        return f"{self.base_url}{self.api_prefix}"

    def get_endpoint(self, path: str) -> str:
        """
        Get full endpoint URL.

        Args:
            path: Endpoint path (e.g., '/auth/login')

        Returns:
            Full URL (e.g., 'http://localhost:8000/api/v1/auth/login')
        """
        path = path.lstrip("/")
        return f"{self.full_api_url}/{path}"


@dataclass
class TestDataFactory:
    """
    Factory for generating unique test data.

    Ensures test data is unique across test runs to avoid conflicts.
    """

    # Unique run identifier
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))

    def generate_org_name(self, prefix: str = "TestOrg") -> str:
        """Generate unique organization name."""
        return f"{prefix}_{self.run_id}_{self.timestamp}"

    def generate_email(self, username: str = "user") -> str:
        """Generate unique email address."""
        return f"{username}_{self.run_id}@test-{self.timestamp}.com"

    def generate_username(self, prefix: str = "testuser") -> str:
        """Generate unique username."""
        return f"{prefix}_{self.run_id}_{self.timestamp}"

    def generate_folder_name(self, prefix: str = "TestFolder") -> str:
        """Generate unique folder name."""
        return f"{prefix}_{self.run_id}"

    def generate_document_name(self, prefix: str = "test_doc", extension: str = "pdf") -> str:
        """Generate unique document filename."""
        return f"{prefix}_{self.run_id}.{extension}"

    @staticmethod
    def generate_password() -> str:
        """Generate valid test password."""
        return "TestPass123!@#"

    @staticmethod
    def generate_user_data(email: Optional[str] = None, username: Optional[str] = None) -> dict:
        """
        Generate complete user data for registration.

        Args:
            email: Custom email (will be generated if None)
            username: Custom username (will be generated if None)

        Returns:
            Dict with user data including email, password, full_name, username
        """
        factory = TestDataFactory()
        return {
            "email": email or factory.generate_email(),
            "password": factory.generate_password(),
            "full_name": "Test User",
            "username": username or factory.generate_username()
        }

    @staticmethod
    def generate_org_data(name: Optional[str] = None) -> dict:
        """
        Generate complete organization data.

        Args:
            name: Custom organization name (will be generated if None)

        Returns:
            Dict with organization data
        """
        factory = TestDataFactory()
        org_name = name or factory.generate_org_name()
        return {
            "name": org_name,
            "plan_type": "free",
            "domain": None,
            "settings": {}
        }

    @staticmethod
    def generate_folder_data(name: Optional[str] = None, parent_id: Optional[str] = None) -> dict:
        """
        Generate folder data.

        Args:
            name: Custom folder name (will be generated if None)
            parent_id: Parent folder ID (None for root folder)

        Returns:
            Dict with folder data
        """
        factory = TestDataFactory()
        folder_data = {
            "name": name or factory.generate_folder_name(),
            "description": "Test folder"
        }
        if parent_id:
            folder_data["parent_id"] = parent_id
        return folder_data


@dataclass
class TestCredentials:
    """
    Store test credentials and tokens.

    Used to track authenticated sessions during tests.
    """

    email: str
    password: str
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    user_id: Optional[str] = None
    org_id: Optional[str] = None
    session_id: Optional[str] = None
    full_name: Optional[str] = None
    username: Optional[str] = None
    role: Optional[str] = None

    @property
    def is_authenticated(self) -> bool:
        """Check if credentials have valid access token."""
        return self.access_token is not None

    @property
    def auth_headers(self) -> dict:
        """Get authorization headers for API requests."""
        if not self.is_authenticated:
            raise ValueError("No access token available. Please authenticate first.")
        return {"Authorization": f"Bearer {self.access_token}"}

    def update_from_login_response(self, response_data: dict) -> None:
        """
        Update credentials from login response.

        Args:
            response_data: Login response JSON data
        """
        self.access_token = response_data.get("access_token")
        self.refresh_token = response_data.get("refresh_token")

        user_data = response_data.get("user", {})
        self.user_id = user_data.get("user_id")
        self.org_id = user_data.get("org_id")
        self.session_id = user_data.get("session_id")
        self.full_name = user_data.get("full_name")
        self.username = user_data.get("username")
        self.role = user_data.get("role")


# Global test configuration instance
config = TestConfig()

# Global test data factory instance
data_factory = TestDataFactory()


# Test file samples for document upload tests
TEST_FILES = {
    "pdf": {
        "filename": "test_sample.pdf",
        "content_type": "application/pdf",
        "size_kb": 100
    },
    "docx": {
        "filename": "test_sample.docx",
        "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "size_kb": 50
    },
    "txt": {
        "filename": "test_sample.txt",
        "content_type": "text/plain",
        "size_kb": 10
    }
}


# Test organization data (for tests that need consistent org)
DEFAULT_TEST_ORG = {
    "name": "TestOrganization",
    "display_name": "Test Organization",
    "description": "Organization for API testing",
    "plan_type": "free"
}


# Test user data (for tests that need consistent user)
DEFAULT_TEST_USER = {
    "email": "testuser@example.com",
    "password": "TestPass123!@#",
    "full_name": "Test User",
    "username": "testuser"
}
