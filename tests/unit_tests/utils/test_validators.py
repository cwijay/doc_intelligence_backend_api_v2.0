"""
Unit tests for app/utils/validators.py

Tests all validation functions.
"""

import pytest
from uuid import uuid4

from app.utils.validators import (
    ValidationError,
    validate_organization_name,
    validate_domain,
    validate_organization_settings,
    validate_uuid,
    validate_pagination_params,
    validate_search_query,
    validate_url,
    validate_email,
    sanitize_filename,
    validate_file_size,
)


class TestOrganizationNameValidation:
    """Test organization name validation."""

    def test_valid_organization_name(self):
        """Test valid organization names."""
        valid_names = [
            "Test Organization",
            "Company123",
            "My-Company",
            "Company_Name",
            "Test.Org",
        ]

        for name in valid_names:
            result = validate_organization_name(name)
            assert result == name.strip()

    def test_organization_name_empty_raises_error(self):
        """Test that empty name raises error."""
        with pytest.raises(ValidationError) as exc_info:
            validate_organization_name("")

        assert "non-empty string" in str(exc_info.value)

    def test_organization_name_too_short_raises_error(self):
        """Test that too short name raises error."""
        with pytest.raises(ValidationError) as exc_info:
            validate_organization_name("A")

        assert "at least 2 characters" in str(exc_info.value)

    def test_organization_name_too_long_raises_error(self):
        """Test that too long name raises error."""
        long_name = "a" * 256

        with pytest.raises(ValidationError) as exc_info:
            validate_organization_name(long_name)

        assert "less than 255 characters" in str(exc_info.value)

    def test_organization_name_invalid_characters_raises_error(self):
        """Test that invalid characters raise error."""
        invalid_names = ["Test@Org", "Org!Company", "Test#Name"]

        for name in invalid_names:
            with pytest.raises(ValidationError) as exc_info:
                validate_organization_name(name)

            assert "can only contain" in str(exc_info.value)

    def test_organization_name_consecutive_chars_raises_error(self):
        """Test that consecutive special chars raise error."""
        with pytest.raises(ValidationError) as exc_info:
            validate_organization_name("Test--Company")

        assert "consecutive" in str(exc_info.value)

    def test_organization_name_starts_with_special_char_raises_error(self):
        """Test that name starting with special char raises error."""
        with pytest.raises(ValidationError) as exc_info:
            validate_organization_name("-TestOrg")

        assert "cannot start with" in str(exc_info.value)

    def test_organization_name_ends_with_special_char_raises_error(self):
        """Test that name ending with special char raises error."""
        with pytest.raises(ValidationError) as exc_info:
            validate_organization_name("TestOrg-")

        assert "cannot end with" in str(exc_info.value)


class TestDomainValidation:
    """Test domain validation."""

    def test_valid_domain(self):
        """Test valid domains."""
        valid_domains = [
            "example.com",
            "subdomain.example.com",
            "test-domain.com",
            "my-company.co.uk",
        ]

        for domain in valid_domains:
            result = validate_domain(domain)
            assert result == domain.lower()

    def test_domain_empty_returns_none(self):
        """Test that empty domain returns None."""
        assert validate_domain("") is None
        assert validate_domain(None) is None

    def test_domain_too_long_raises_error(self):
        """Test that too long domain raises error."""
        long_domain = "a" * 256 + ".com"

        with pytest.raises(ValidationError) as exc_info:
            validate_domain(long_domain)

        assert "less than 255 characters" in str(exc_info.value)

    def test_domain_invalid_format_raises_error(self):
        """Test that invalid domain format raises error."""
        invalid_domains = [
            "invalid",
            "-invalid.com",
            "invalid-.com",
            "inv@lid.com",
        ]

        for domain in invalid_domains:
            with pytest.raises(ValidationError):
                validate_domain(domain)

    def test_domain_invalid_tld_raises_error(self):
        """Test that invalid TLD raises error."""
        with pytest.raises(ValidationError) as exc_info:
            validate_domain("example.a")

        assert "valid top-level domain" in str(exc_info.value)

    def test_domain_localhost_raises_error(self):
        """Test that localhost raises error."""
        invalid_domains = ["localhost", "127.0.0.1.com", "internal.local"]

        for domain in invalid_domains:
            with pytest.raises(ValidationError) as exc_info:
                validate_domain(domain)

            assert "not allowed" in str(exc_info.value)


class TestOrganizationSettingsValidation:
    """Test organization settings validation."""

    def test_valid_settings(self):
        """Test valid settings."""
        valid_settings = {
            "feature_flags": {"ai_enabled": True},
            "limits": {"max_documents": 100},
            "theme": "dark",
        }

        result = validate_organization_settings(valid_settings)

        assert result == valid_settings

    def test_settings_not_dict_raises_error(self):
        """Test that non-dict settings raise error."""
        with pytest.raises(ValidationError) as exc_info:
            validate_organization_settings("not a dict")  # type: ignore

        assert "must be a dictionary" in str(exc_info.value)

    def test_settings_with_sensitive_keys_raises_error(self):
        """Test that sensitive keys raise error."""
        sensitive_settings = [
            {"password": "secret"},
            {"api_key": "12345"},
            {"secret_token": "abc"},
            {"private_key": "xyz"},
        ]

        for settings in sensitive_settings:
            with pytest.raises(ValidationError) as exc_info:
                validate_organization_settings(settings)

            assert "sensitive key" in str(exc_info.value)

    def test_settings_too_large_raises_error(self):
        """Test that overly large settings raise error."""
        large_settings = {"data": "x" * 15000}

        with pytest.raises(ValidationError) as exc_info:
            validate_organization_settings(large_settings)

        assert "too large" in str(exc_info.value)


class TestUUIDValidation:
    """Test UUID validation."""

    def test_valid_uuid(self):
        """Test valid UUID."""
        valid_uuid = str(uuid4())

        result = validate_uuid(valid_uuid)

        assert str(result) == valid_uuid

    def test_uuid_empty_raises_error(self):
        """Test that empty UUID raises error."""
        with pytest.raises(ValidationError) as exc_info:
            validate_uuid("")

        assert "cannot be empty" in str(exc_info.value)

    def test_uuid_invalid_format_raises_error(self):
        """Test that invalid UUID format raises error."""
        with pytest.raises(ValidationError) as exc_info:
            validate_uuid("not-a-uuid")

        assert "valid UUID" in str(exc_info.value)


class TestPaginationParamsValidation:
    """Test pagination parameters validation."""

    def test_valid_pagination_params(self):
        """Test valid pagination parameters."""
        page, per_page = validate_pagination_params(1, 10)

        assert page == 1
        assert per_page == 10

    def test_pagination_page_zero_raises_error(self):
        """Test that page 0 raises error."""
        with pytest.raises(ValidationError) as exc_info:
            validate_pagination_params(0, 10)

        assert "positive integer" in str(exc_info.value)

    def test_pagination_page_negative_raises_error(self):
        """Test that negative page raises error."""
        with pytest.raises(ValidationError) as exc_info:
            validate_pagination_params(-1, 10)

        assert "positive integer" in str(exc_info.value)

    def test_pagination_per_page_too_large_raises_error(self):
        """Test that per_page > 100 raises error."""
        with pytest.raises(ValidationError) as exc_info:
            validate_pagination_params(1, 101)

        assert "cannot exceed 100" in str(exc_info.value)

    def test_pagination_page_too_large_raises_error(self):
        """Test that page > 10000 raises error."""
        with pytest.raises(ValidationError) as exc_info:
            validate_pagination_params(10001, 10)

        assert "cannot exceed 10000" in str(exc_info.value)


class TestSearchQueryValidation:
    """Test search query validation."""

    def test_valid_search_query(self):
        """Test valid search queries."""
        valid_queries = ["test", "search query", "query-123", "user@example.com"]

        for query in valid_queries:
            result = validate_search_query(query)
            assert result == query.strip()

    def test_search_query_empty_returns_none(self):
        """Test that empty query returns None."""
        assert validate_search_query("") is None
        assert validate_search_query(None) is None
        assert validate_search_query("   ") is None

    def test_search_query_too_long_raises_error(self):
        """Test that too long query raises error."""
        long_query = "a" * 101

        with pytest.raises(ValidationError) as exc_info:
            validate_search_query(long_query)

        assert "cannot exceed 100 characters" in str(exc_info.value)

    def test_search_query_dangerous_patterns_raises_error(self):
        """Test that dangerous patterns raise error."""
        dangerous_queries = [
            "test<script>",
            "query; DROP TABLE",
            "javascript:alert()",
            "test--comment",
        ]

        for query in dangerous_queries:
            with pytest.raises(ValidationError):
                validate_search_query(query)


class TestURLValidation:
    """Test URL validation."""

    def test_valid_url(self):
        """Test valid URLs."""
        valid_urls = [
            "http://example.com",
            "https://www.example.com",
            "https://example.com/path?query=value",
        ]

        for url in valid_urls:
            result = validate_url(url)
            assert result == url

    def test_url_empty_returns_none(self):
        """Test that empty URL returns None."""
        assert validate_url("") is None
        assert validate_url(None) is None

    def test_url_no_scheme_raises_error(self):
        """Test that URL without scheme raises error."""
        with pytest.raises(ValidationError) as exc_info:
            validate_url("example.com")

        assert "must include a scheme" in str(exc_info.value)

    def test_url_invalid_scheme_raises_error(self):
        """Test that invalid scheme raises error."""
        with pytest.raises(ValidationError) as exc_info:
            validate_url("ftp://example.com")

        assert "http or https" in str(exc_info.value)

    def test_url_too_long_raises_error(self):
        """Test that too long URL raises error."""
        long_url = "https://example.com/" + ("a" * 2048)

        with pytest.raises(ValidationError) as exc_info:
            validate_url(long_url)

        assert "cannot exceed 2048" in str(exc_info.value)


class TestEmailValidation:
    """Test email validation."""

    def test_valid_email(self):
        """Test valid emails."""
        valid_emails = [
            "test@example.com",
            "user.name@example.com",
            "user+tag@example.co.uk",
        ]

        for email in valid_emails:
            result = validate_email(email)
            assert result == email.lower()

    def test_email_empty_returns_none(self):
        """Test that empty email returns None."""
        assert validate_email("") is None
        assert validate_email(None) is None

    def test_email_invalid_format_raises_error(self):
        """Test that invalid email format raises error."""
        invalid_emails = [
            "invalid",
            "@example.com",
            "user@",
            "user@@example.com",
        ]

        for email in invalid_emails:
            with pytest.raises(ValidationError):
                validate_email(email)

    def test_email_consecutive_dots_raises_error(self):
        """Test that consecutive dots raise error."""
        with pytest.raises(ValidationError) as exc_info:
            validate_email("user..name@example.com")

        assert "consecutive dots" in str(exc_info.value)

    def test_email_too_long_raises_error(self):
        """Test that too long email raises error."""
        long_email = "a" * 250 + "@example.com"

        with pytest.raises(ValidationError):
            validate_email(long_email)


class TestFilenameValidation:
    """Test filename sanitization."""

    def test_sanitize_valid_filename(self):
        """Test sanitizing valid filename."""
        filename = "document.pdf"
        result = sanitize_filename(filename)

        assert result == filename

    def test_sanitize_filename_removes_dangerous_chars(self):
        """Test that dangerous characters are removed."""
        dangerous_filename = 'test<>:"|?.pdf'
        result = sanitize_filename(dangerous_filename)

        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert "|" not in result
        assert "?" not in result

    def test_sanitize_filename_removes_path_traversal(self):
        """Test that path traversal is removed."""
        dangerous_filename = "../../../etc/passwd"
        result = sanitize_filename(dangerous_filename)

        assert ".." not in result
        assert "/" not in result

    def test_sanitize_filename_limits_length(self):
        """Test that long filenames are truncated."""
        long_filename = "a" * 300 + ".pdf"
        result = sanitize_filename(long_filename)

        assert len(result) <= 255

    def test_sanitize_filename_empty_raises_error(self):
        """Test that empty filename raises error."""
        with pytest.raises(ValidationError) as exc_info:
            sanitize_filename("")

        assert "cannot be empty" in str(exc_info.value)


class TestFileSizeValidation:
    """Test file size validation."""

    def test_valid_file_size(self):
        """Test valid file size."""
        assert validate_file_size(1024 * 1024) is True  # 1MB

    def test_file_size_zero_raises_error(self):
        """Test that zero size raises error."""
        with pytest.raises(ValidationError) as exc_info:
            validate_file_size(0)

        assert "cannot be empty" in str(exc_info.value)

    def test_file_size_negative_raises_error(self):
        """Test that negative size raises error."""
        with pytest.raises(ValidationError) as exc_info:
            validate_file_size(-1)

        assert "non-negative integer" in str(exc_info.value)

    def test_file_size_exceeds_limit_raises_error(self):
        """Test that size exceeding limit raises error."""
        with pytest.raises(ValidationError) as exc_info:
            validate_file_size(51 * 1024 * 1024, max_size_mb=50)

        assert "exceeds maximum" in str(exc_info.value)
