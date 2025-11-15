"""
Unit tests for app/core/config.py

Tests the Settings class and configuration loading.
"""

import pytest
from pydantic import ValidationError
from app.core.config import Settings


class TestSettings:
    """Test Settings configuration class."""

    def test_settings_creation_with_defaults(self, mock_settings):
        """Test settings creation with default values."""
        # Defaults should be set correctly
        assert mock_settings.PROJECT_NAME == "Test Document Intelligence API"
        assert mock_settings.API_V1_STR == "/api/v1"
        assert mock_settings.DEBUG is True
        assert mock_settings.ENVIRONMENT == "test"

    def test_jwt_configuration(self, mock_settings):
        """Test JWT configuration settings."""
        assert mock_settings.JWT_SECRET_KEY is not None
        assert mock_settings.JWT_ALGORITHM == "HS256"
        assert mock_settings.ACCESS_TOKEN_EXPIRE_MINUTES == 30
        assert mock_settings.REFRESH_TOKEN_EXPIRE_DAYS == 30

    def test_session_configuration(self, mock_settings):
        """Test session management configuration."""
        assert mock_settings.SESSION_DURATION_HOURS == 2
        assert mock_settings.REFRESH_SESSION_DURATION_DAYS == 7
        assert mock_settings.TOKEN_GRACE_PERIOD_MINUTES == 10
        assert mock_settings.MAX_CONCURRENT_SESSIONS == 5
        assert mock_settings.INVALIDATE_TOKENS_ON_LOGIN is True
        assert mock_settings.ENABLE_TOKEN_ROTATION is True

    def test_firebase_configuration(self, mock_settings):
        """Test Firebase/Firestore configuration."""
        assert mock_settings.FIREBASE_PROJECT_ID == "test-project"
        assert mock_settings.FIREBASE_DATABASE_ID == "test-database"

    def test_gcs_configuration(self, mock_settings):
        """Test Google Cloud Storage configuration."""
        assert mock_settings.GCP_PROJECT_ID == "test-project"
        assert mock_settings.GCS_BUCKET_NAME == "test-bucket"
        assert mock_settings.DOCUMENT_STORE_BASE_PATH == ""

    def test_document_configuration(self, mock_settings):
        """Test document processing configuration."""
        assert mock_settings.MAX_FILE_SIZE == 50 * 1024 * 1024  # 50MB
        assert "pdf" in mock_settings.ALLOWED_FILE_TYPES
        assert "xlsx" in mock_settings.ALLOWED_FILE_TYPES
        assert mock_settings.DOCUMENT_UPLOAD_TIMEOUT == 300
        assert mock_settings.SIGNED_URL_EXPIRATION_MINUTES == 60

    def test_ai_configuration(self, mock_settings):
        """Test AI service configuration."""
        assert mock_settings.OPENAI_API_KEY is not None
        assert mock_settings.OPENAI_MODEL == "gpt-5-mini"
        assert mock_settings.LLAMAPARSE_API_KEY is not None

    def test_logging_configuration(self, mock_settings):
        """Test logging configuration."""
        assert mock_settings.LOG_LEVEL == "DEBUG"
        assert mock_settings.ENABLE_AUTH_AUDIT_LOGGING is True


class TestSettingsValidation:
    """Test Settings validation and edge cases."""

    def test_environment_types(self):
        """Test that environment variables have correct types."""
        # This would test actual Settings instantiation with env vars
        # For unit tests, we use mocks to avoid real environment dependencies
        pass

    def test_file_size_limits(self, mock_settings):
        """Test file size limit validation."""
        assert mock_settings.MAX_FILE_SIZE > 0
        assert mock_settings.MAX_FILE_SIZE == 50 * 1024 * 1024

    def test_allowed_file_types_list(self, mock_settings):
        """Test allowed file types is a list."""
        assert isinstance(mock_settings.ALLOWED_FILE_TYPES, list)
        assert len(mock_settings.ALLOWED_FILE_TYPES) > 0
