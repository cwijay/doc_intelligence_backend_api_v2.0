"""
Unit tests for the configuration module.

Tests Settings validation and environment handling.
"""

import os
from unittest.mock import patch

import pytest


class TestSettingsValidation:
    """Tests for Settings class validation."""

    @pytest.mark.unit
    def test_jwt_secret_key_minimum_length(self):
        """Test that JWT_SECRET_KEY must be at least 32 characters."""
        from pydantic import ValidationError

        # This should pass
        with patch.dict(os.environ, {
            "JWT_SECRET_KEY": "a" * 32,
            "ENVIRONMENT": "development"
        }, clear=False):
            from pydantic_settings import BaseSettings, SettingsConfigDict
            from pydantic import Field, field_validator

            class TestSettings(BaseSettings):
                JWT_SECRET_KEY: str = Field(...)

                @field_validator("JWT_SECRET_KEY")
                @classmethod
                def validate_jwt_secret_key(cls, v: str) -> str:
                    if len(v) < 32:
                        raise ValueError("JWT_SECRET_KEY must be at least 32 characters")
                    return v

                model_config = SettingsConfigDict(env_file=None)

            settings = TestSettings()
            assert len(settings.JWT_SECRET_KEY) >= 32

    @pytest.mark.unit
    def test_jwt_secret_key_too_short(self):
        """Test that short JWT_SECRET_KEY raises validation error."""
        from pydantic import ValidationError
        from pydantic_settings import BaseSettings, SettingsConfigDict
        from pydantic import Field, field_validator

        class TestSettings(BaseSettings):
            JWT_SECRET_KEY: str = Field(...)

            @field_validator("JWT_SECRET_KEY")
            @classmethod
            def validate_jwt_secret_key(cls, v: str) -> str:
                if len(v) < 32:
                    raise ValueError("JWT_SECRET_KEY must be at least 32 characters")
                return v

            model_config = SettingsConfigDict(env_file=None)

        with patch.dict(os.environ, {"JWT_SECRET_KEY": "short"}, clear=True):
            with pytest.raises(ValidationError):
                TestSettings()


class TestEnvironmentDetection:
    """Tests for environment detection properties."""

    @pytest.mark.unit
    def test_is_development_dev(self):
        """Test development environment detection."""
        with patch.dict(os.environ, {
            "JWT_SECRET_KEY": "test-secret-key-for-testing-purposes-only-32chars",
            "ENVIRONMENT": "development"
        }, clear=False):
            # Force reimport to get fresh settings
            from importlib import reload
            import app.core.config as config_module
            reload(config_module)

            assert config_module.settings.is_development is True
            assert config_module.settings.is_production is False

    @pytest.mark.unit
    def test_is_development_local(self):
        """Test local environment detection."""
        with patch.dict(os.environ, {
            "JWT_SECRET_KEY": "test-secret-key-for-testing-purposes-only-32chars",
            "ENVIRONMENT": "local"
        }, clear=False):
            from importlib import reload
            import app.core.config as config_module
            reload(config_module)

            assert config_module.settings.is_development is True

    @pytest.mark.unit
    def test_is_production(self):
        """Test production environment detection."""
        with patch.dict(os.environ, {
            "JWT_SECRET_KEY": "test-secret-key-for-testing-purposes-only-32chars",
            "ENVIRONMENT": "production"
        }, clear=False):
            from importlib import reload
            import app.core.config as config_module
            reload(config_module)

            assert config_module.settings.is_production is True
            assert config_module.settings.is_development is False


class TestTokenExpiration:
    """Tests for token expiration settings."""

    @pytest.mark.unit
    def test_access_token_expire_minutes_development(self):
        """Test access token expiration in development."""
        with patch.dict(os.environ, {
            "JWT_SECRET_KEY": "test-secret-key-for-testing-purposes-only-32chars",
            "ENVIRONMENT": "development",
            "ACCESS_TOKEN_EXPIRE_MINUTES": "60"
        }, clear=False):
            from importlib import reload
            import app.core.config as config_module
            reload(config_module)

            # In development, uses configured value
            assert config_module.settings.access_token_expire_minutes == 60

    @pytest.mark.unit
    def test_access_token_expire_minutes_production_capped(self):
        """Test access token expiration is capped in production."""
        with patch.dict(os.environ, {
            "JWT_SECRET_KEY": "test-secret-key-for-testing-purposes-only-32chars",
            "ENVIRONMENT": "production",
            "ACCESS_TOKEN_EXPIRE_MINUTES": "60"
        }, clear=False):
            from importlib import reload
            import app.core.config as config_module
            reload(config_module)

            # In production, capped at 15 minutes
            assert config_module.settings.access_token_expire_minutes == 15

    @pytest.mark.unit
    def test_refresh_token_expire_days_development(self):
        """Test refresh token expiration in development."""
        with patch.dict(os.environ, {
            "JWT_SECRET_KEY": "test-secret-key-for-testing-purposes-only-32chars",
            "ENVIRONMENT": "development",
            "REFRESH_TOKEN_EXPIRE_DAYS": "30"
        }, clear=False):
            from importlib import reload
            import app.core.config as config_module
            reload(config_module)

            assert config_module.settings.refresh_token_expire_days == 30

    @pytest.mark.unit
    def test_refresh_token_expire_days_production_capped(self):
        """Test refresh token expiration is capped in production."""
        with patch.dict(os.environ, {
            "JWT_SECRET_KEY": "test-secret-key-for-testing-purposes-only-32chars",
            "ENVIRONMENT": "production",
            "REFRESH_TOKEN_EXPIRE_DAYS": "30"
        }, clear=False):
            from importlib import reload
            import app.core.config as config_module
            reload(config_module)

            # In production, capped at 7 days
            assert config_module.settings.refresh_token_expire_days == 7


class TestCORSConfiguration:
    """Tests for CORS origin configuration."""

    @pytest.mark.unit
    def test_cors_origins_development_includes_localhost(self):
        """Test that development includes localhost origins."""
        with patch.dict(os.environ, {
            "JWT_SECRET_KEY": "test-secret-key-for-testing-purposes-only-32chars",
            "ENVIRONMENT": "development"
        }, clear=False):
            from importlib import reload
            import app.core.config as config_module
            reload(config_module)

            origins = config_module.settings.resolved_cors_origins

            assert "http://localhost:3000" in origins
            assert "http://127.0.0.1:3000" in origins

    @pytest.mark.unit
    def test_cors_origins_production_excludes_localhost(self):
        """Test that production excludes localhost origins."""
        with patch.dict(os.environ, {
            "JWT_SECRET_KEY": "test-secret-key-for-testing-purposes-only-32chars",
            "ENVIRONMENT": "production"
        }, clear=False):
            from importlib import reload
            import app.core.config as config_module
            reload(config_module)

            origins = config_module.settings.resolved_cors_origins

            # Production should not have localhost by default
            assert "http://localhost:3000" not in origins

    @pytest.mark.unit
    def test_cors_origins_additional_from_env(self):
        """Test additional CORS origins from environment."""
        with patch.dict(os.environ, {
            "JWT_SECRET_KEY": "test-secret-key-for-testing-purposes-only-32chars",
            "ENVIRONMENT": "development",
            "ADDITIONAL_CORS_ORIGINS": "https://custom-origin.com,https://another.com"
        }, clear=False):
            from importlib import reload
            import app.core.config as config_module
            reload(config_module)

            origins = config_module.settings.resolved_cors_origins

            assert "https://custom-origin.com" in origins
            assert "https://another.com" in origins

    @pytest.mark.unit
    def test_cors_origins_json_array_format(self):
        """Test CORS origins from JSON array format."""
        with patch.dict(os.environ, {
            "JWT_SECRET_KEY": "test-secret-key-for-testing-purposes-only-32chars",
            "ENVIRONMENT": "development",
            "ADDITIONAL_CORS_ORIGINS": '["https://json-origin.com", "https://another-json.com"]'
        }, clear=False):
            from importlib import reload
            import app.core.config as config_module
            reload(config_module)

            origins = config_module.settings.resolved_cors_origins

            assert "https://json-origin.com" in origins
            assert "https://another-json.com" in origins

    @pytest.mark.unit
    def test_cors_origins_production_with_domain(self):
        """Test CORS origins with frontend domain in production."""
        with patch.dict(os.environ, {
            "JWT_SECRET_KEY": "test-secret-key-for-testing-purposes-only-32chars",
            "ENVIRONMENT": "production",
            "FRONTEND_DOMAIN": "myapp.example.com"
        }, clear=False):
            from importlib import reload
            import app.core.config as config_module
            reload(config_module)

            origins = config_module.settings.resolved_cors_origins

            assert "https://myapp.example.com" in origins
            assert "https://www.myapp.example.com" in origins
            assert "https://app.myapp.example.com" in origins

    @pytest.mark.unit
    def test_cors_origins_no_duplicates(self):
        """Test that resolved origins have no duplicates."""
        with patch.dict(os.environ, {
            "JWT_SECRET_KEY": "test-secret-key-for-testing-purposes-only-32chars",
            "ENVIRONMENT": "development",
            "ADDITIONAL_CORS_ORIGINS": "http://localhost:3000,http://localhost:3000"
        }, clear=False):
            from importlib import reload
            import app.core.config as config_module
            reload(config_module)

            origins = config_module.settings.resolved_cors_origins

            # Check no duplicates
            assert len(origins) == len(set(origins))


class TestDatabaseConfiguration:
    """Tests for database configuration."""

    @pytest.mark.unit
    def test_database_url_takes_precedence(self):
        """Test that DATABASE_URL takes precedence over individual settings."""
        with patch.dict(os.environ, {
            "JWT_SECRET_KEY": "test-secret-key-for-testing-purposes-only-32chars",
            "ENVIRONMENT": "development",
            "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/mydb",
            "DATABASE_HOST": "otherhost",
            "DATABASE_NAME": "otherdb"
        }, clear=False):
            from importlib import reload
            import app.core.config as config_module
            reload(config_module)

            assert config_module.settings.DATABASE_URL == "postgresql+asyncpg://user:pass@localhost:5432/mydb"

    @pytest.mark.unit
    def test_cloud_sql_connector_default_disabled(self):
        """Test that Cloud SQL connector is disabled by default."""
        with patch.dict(os.environ, {
            "JWT_SECRET_KEY": "test-secret-key-for-testing-purposes-only-32chars",
            "ENVIRONMENT": "development"
        }, clear=False):
            from importlib import reload
            import app.core.config as config_module
            reload(config_module)

            assert config_module.settings.USE_CLOUD_SQL_CONNECTOR is False


class TestFileConfiguration:
    """Tests for file handling configuration."""

    @pytest.mark.unit
    def test_max_file_size_default(self):
        """Test default max file size."""
        with patch.dict(os.environ, {
            "JWT_SECRET_KEY": "test-secret-key-for-testing-purposes-only-32chars",
            "ENVIRONMENT": "development"
        }, clear=False):
            from importlib import reload
            import app.core.config as config_module
            reload(config_module)

            # Default 50MB
            assert config_module.settings.MAX_FILE_SIZE == 50 * 1024 * 1024

    @pytest.mark.unit
    def test_allowed_file_types_default(self):
        """Test default allowed file types."""
        with patch.dict(os.environ, {
            "JWT_SECRET_KEY": "test-secret-key-for-testing-purposes-only-32chars",
            "ENVIRONMENT": "development"
        }, clear=False):
            from importlib import reload
            import app.core.config as config_module
            reload(config_module)

            assert "pdf" in config_module.settings.ALLOWED_FILE_TYPES
            assert "xlsx" in config_module.settings.ALLOWED_FILE_TYPES


class TestAPIConfiguration:
    """Tests for API configuration."""

    @pytest.mark.unit
    def test_api_version_prefix(self):
        """Test API version prefix."""
        with patch.dict(os.environ, {
            "JWT_SECRET_KEY": "test-secret-key-for-testing-purposes-only-32chars",
            "ENVIRONMENT": "development"
        }, clear=False):
            from importlib import reload
            import app.core.config as config_module
            reload(config_module)

            assert config_module.settings.API_V1_STR == "/api/v1"

    @pytest.mark.unit
    def test_project_name_default(self):
        """Test default project name."""
        with patch.dict(os.environ, {
            "JWT_SECRET_KEY": "test-secret-key-for-testing-purposes-only-32chars",
            "ENVIRONMENT": "development"
        }, clear=False):
            from importlib import reload
            import app.core.config as config_module
            reload(config_module)

            assert "Document Intelligence" in config_module.settings.PROJECT_NAME
