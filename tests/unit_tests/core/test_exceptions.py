"""
Unit tests for app/core/exceptions.py

Tests custom exception classes and error handling.
"""

import pytest
from unittest.mock import Mock
from fastapi import status

from app.core.exceptions import (
    DocumentIntelligenceError,
    DatabaseError,
    AuthenticationError,
    TokenExpiredError,
    TokenInvalidError,
    RefreshTokenExpiredError,
    RefreshTokenInvalidError,
    AuthorizationError,
    ValidationError,
    ExternalServiceError,
    RateLimitError,
    FileProcessingError,
    OrganizationError,
    OrganizationNotFoundError,
    OrganizationAlreadyExistsError,
    OrganizationValidationError,
    OrganizationInactiveError,
    OrganizationAccessDeniedError,
    create_error_response,
)


class TestBaseException:
    """Test DocumentIntelligenceError base exception."""

    def test_base_exception_creation(self):
        """Test creating base exception."""
        exc = DocumentIntelligenceError(
            message="Test error", error_code="TEST_ERROR", details={"key": "value"}
        )

        assert exc.message == "Test error"
        assert exc.error_code == "TEST_ERROR"
        assert exc.details == {"key": "value"}
        assert str(exc) == "Test error"

    def test_base_exception_default_error_code(self):
        """Test base exception with default error code."""
        exc = DocumentIntelligenceError(message="Test error")

        assert exc.error_code == "INTERNAL_ERROR"
        assert exc.details == {}


class TestDatabaseError:
    """Test DatabaseError exception."""

    def test_database_error_creation(self):
        """Test creating database error."""
        exc = DatabaseError(
            message="Database connection failed", details={"host": "localhost"}
        )

        assert exc.message == "Database connection failed"
        assert exc.error_code == "DATABASE_ERROR"
        assert exc.details["host"] == "localhost"


class TestAuthenticationErrors:
    """Test authentication-related exceptions."""

    def test_authentication_error(self):
        """Test basic authentication error."""
        exc = AuthenticationError(message="Invalid credentials")

        assert exc.message == "Invalid credentials"
        assert exc.error_code == "AUTHENTICATION_ERROR"

    def test_token_expired_error(self):
        """Test token expired error."""
        exc = TokenExpiredError(expires_at="2024-01-01T12:00:00")

        assert exc.error_code == "TOKEN_EXPIRED"
        assert exc.details["expired_at"] == "2024-01-01T12:00:00"
        assert exc.details["action"] == "refresh_token_or_relogin"

    def test_token_expired_error_default(self):
        """Test token expired error with defaults."""
        exc = TokenExpiredError()

        assert exc.message == "Access token has expired"
        assert exc.error_code == "TOKEN_EXPIRED"

    def test_token_invalid_error(self):
        """Test token invalid error."""
        exc = TokenInvalidError()

        assert exc.message == "Access token is invalid"
        assert exc.error_code == "TOKEN_INVALID"

    def test_refresh_token_expired_error(self):
        """Test refresh token expired error."""
        exc = RefreshTokenExpiredError()

        assert exc.message == "Refresh token has expired"
        assert exc.error_code == "REFRESH_TOKEN_EXPIRED"
        assert exc.details["action"] == "relogin_required"

    def test_refresh_token_invalid_error(self):
        """Test refresh token invalid error."""
        exc = RefreshTokenInvalidError()

        assert exc.message == "Refresh token is invalid"
        assert exc.error_code == "REFRESH_TOKEN_INVALID"
        assert exc.details["action"] == "relogin_required"


class TestAuthorizationError:
    """Test authorization error."""

    def test_authorization_error(self):
        """Test authorization error creation."""
        exc = AuthorizationError(
            message="Access denied", details={"resource": "document"}
        )

        assert exc.message == "Access denied"
        assert exc.error_code == "AUTHORIZATION_ERROR"
        assert exc.details["resource"] == "document"


class TestValidationError:
    """Test validation error."""

    def test_validation_error(self):
        """Test validation error creation."""
        exc = ValidationError(
            message="Invalid input", details={"field": "email", "reason": "invalid format"}
        )

        assert exc.message == "Invalid input"
        assert exc.error_code == "VALIDATION_ERROR"
        assert exc.details["field"] == "email"


class TestExternalServiceError:
    """Test external service error."""

    def test_external_service_error(self):
        """Test external service error creation."""
        exc = ExternalServiceError(
            message="OpenAI API failed",
            service="openai",
            details={"status_code": 500},
        )

        assert exc.message == "OpenAI API failed"
        assert exc.error_code == "EXTERNAL_SERVICE_ERROR"
        assert exc.details["service"] == "openai"
        assert exc.details["status_code"] == 500


class TestRateLimitError:
    """Test rate limit error."""

    def test_rate_limit_error_default(self):
        """Test rate limit error with default message."""
        exc = RateLimitError()

        assert exc.message == "Rate limit exceeded"
        assert exc.error_code == "RATE_LIMIT_ERROR"

    def test_rate_limit_error_custom(self):
        """Test rate limit error with custom details."""
        exc = RateLimitError(
            message="Too many requests",
            details={"retry_after": 60, "limit": 100},
        )

        assert exc.message == "Too many requests"
        assert exc.details["retry_after"] == 60
        assert exc.details["limit"] == 100


class TestFileProcessingError:
    """Test file processing error."""

    def test_file_processing_error(self):
        """Test file processing error creation."""
        exc = FileProcessingError(
            message="Failed to parse PDF", details={"filename": "test.pdf"}
        )

        assert exc.message == "Failed to parse PDF"
        assert exc.error_code == "FILE_PROCESSING_ERROR"
        assert exc.details["filename"] == "test.pdf"


class TestOrganizationErrors:
    """Test organization-related exceptions."""

    def test_organization_error(self):
        """Test base organization error."""
        exc = OrganizationError(message="Organization error")

        assert exc.message == "Organization error"
        assert exc.error_code == "ORGANIZATION_ERROR"

    def test_organization_not_found_error(self):
        """Test organization not found error."""
        exc = OrganizationNotFoundError(org_id="org123")

        assert exc.message == "Organization not found"
        assert exc.details["organization_id"] == "org123"

    def test_organization_not_found_error_no_id(self):
        """Test organization not found error without ID."""
        exc = OrganizationNotFoundError()

        assert exc.message == "Organization not found"
        assert exc.details is None

    def test_organization_already_exists_error(self):
        """Test organization already exists error."""
        exc = OrganizationAlreadyExistsError(org_name="Test Org")

        assert exc.message == "Organization already exists"
        assert exc.details["organization_name"] == "Test Org"

    def test_organization_validation_error(self):
        """Test organization validation error."""
        exc = OrganizationValidationError(
            message="Invalid organization name", field="name", value="@@@"
        )

        assert exc.message == "Invalid organization name"
        assert exc.details["field"] == "name"
        assert exc.details["value"] == "@@@"

    def test_organization_inactive_error(self):
        """Test organization inactive error."""
        exc = OrganizationInactiveError(org_id="org123")

        assert exc.message == "Organization is inactive"
        assert exc.details["organization_id"] == "org123"

    def test_organization_access_denied_error(self):
        """Test organization access denied error."""
        exc = OrganizationAccessDeniedError(org_id="org123")

        assert exc.message == "Access denied to organization"
        assert exc.details["organization_id"] == "org123"


class TestErrorResponseCreation:
    """Test error response creation helper."""

    def test_create_error_response_basic(self, mock_settings):
        """Test creating basic error response."""
        from unittest.mock import patch

        with patch("app.core.exceptions.settings", mock_settings):
            response = create_error_response(
                status_code=400, message="Bad request", error_code="BAD_REQUEST"
            )

        assert response.status_code == 400
        data = response.body.decode()
        assert "Bad request" in data
        assert "BAD_REQUEST" in data

    def test_create_error_response_with_details(self, mock_settings):
        """Test creating error response with details."""
        from unittest.mock import patch

        with patch("app.core.exceptions.settings", mock_settings):
            response = create_error_response(
                status_code=422,
                message="Validation failed",
                error_code="VALIDATION_ERROR",
                details={"field": "email", "reason": "invalid"},
            )

        assert response.status_code == 422
        data = response.body.decode()
        assert "Validation failed" in data

    def test_create_error_response_with_error_id(self, mock_settings):
        """Test creating error response with custom error ID."""
        from unittest.mock import patch

        with patch("app.core.exceptions.settings", mock_settings):
            response = create_error_response(
                status_code=500,
                message="Internal error",
                error_code="INTERNAL_ERROR",
                error_id="custom-error-id",
            )

        data = response.body.decode()
        assert "custom-error-id" in data

    def test_create_error_response_with_path(self, mock_settings):
        """Test creating error response with request path."""
        from unittest.mock import patch

        with patch("app.core.exceptions.settings", mock_settings):
            response = create_error_response(
                status_code=404,
                message="Not found",
                error_code="NOT_FOUND",
                request_path="/api/v1/documents/123",
            )

        data = response.body.decode()
        assert "/api/v1/documents/123" in data
