import re
from typing import Optional, Dict, Any
from uuid import UUID
from urllib.parse import urlparse

try:
    import dns.resolver
    import dns.exception

    DNS_AVAILABLE = True
except ImportError:
    DNS_AVAILABLE = False

from pydantic import ValidationError


class ValidationError(Exception):
    """Custom validation error."""

    pass


def validate_organization_name(name: str) -> str:
    """
    Validate organization name.

    Args:
        name: Organization name to validate

    Returns:
        Cleaned and validated name

    Raises:
        ValidationError: If name is invalid
    """
    if not name or not isinstance(name, str):
        raise ValidationError("Organization name must be a non-empty string")

    # Remove extra whitespace and convert to proper case
    name = name.strip()

    if len(name) < 2:
        raise ValidationError("Organization name must be at least 2 characters long")

    if len(name) > 255:
        raise ValidationError("Organization name must be less than 255 characters")

    # Check for valid characters (letters, numbers, spaces, hyphens, underscores, dots)
    if not re.match(r"^[a-zA-Z0-9\s\-_.]+$", name):
        raise ValidationError(
            "Organization name can only contain letters, numbers, spaces, hyphens, underscores, and dots"
        )

    # Check for consecutive spaces or special characters
    if re.search(r"[\s\-_.]{2,}", name):
        raise ValidationError(
            "Organization name cannot have consecutive spaces or special characters"
        )

    # Ensure it doesn't start or end with special characters
    if name[0] in "-_.":
        raise ValidationError("Organization name cannot start with special characters")

    if name[-1] in "-_.":
        raise ValidationError("Organization name cannot end with special characters")

    return name


def validate_domain(domain: Optional[str]) -> Optional[str]:
    """
    Validate organization domain.

    Args:
        domain: Domain to validate (optional)

    Returns:
        Cleaned and validated domain or None

    Raises:
        ValidationError: If domain format is invalid
    """
    if not domain:
        return None

    if not isinstance(domain, str):
        raise ValidationError("Domain must be a string")

    # Clean and normalize
    domain = domain.strip().lower()

    if not domain:
        return None

    if len(domain) > 255:
        raise ValidationError("Domain must be less than 255 characters")

    # Basic domain format validation
    domain_pattern = r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"

    if not re.match(domain_pattern, domain):
        raise ValidationError("Invalid domain format")

    # Check for valid TLD (at least 2 characters)
    parts = domain.split(".")
    if len(parts) < 2 or len(parts[-1]) < 2:
        raise ValidationError("Domain must have a valid top-level domain")

    # Prevent localhost and internal domains in production
    invalid_domains = ["localhost", "127.0.0.1", "0.0.0.0", "internal", "local"]
    if any(invalid in domain for invalid in invalid_domains):
        raise ValidationError(
            "Invalid domain: localhost and internal domains not allowed"
        )

    return domain


def validate_domain_dns(domain: str) -> bool:
    """
    Validate domain by checking DNS records (optional, for enhanced validation).

    Args:
        domain: Domain to validate

    Returns:
        True if domain has valid DNS records, False otherwise

    Note:
        Requires dnspython package. Returns False if package not available.
    """
    if not DNS_AVAILABLE:
        # DNS validation not available, skip check
        return False

    try:
        dns.resolver.resolve(domain, "A")
        return True
    except (
        dns.resolver.NXDOMAIN,
        dns.resolver.NoAnswer,
        dns.resolver.Timeout,
        dns.resolver.NoNameservers,
    ):
        try:
            # Try MX record as fallback
            dns.resolver.resolve(domain, "MX")
            return True
        except (
            dns.resolver.NXDOMAIN,
            dns.resolver.NoAnswer,
            dns.resolver.Timeout,
            dns.resolver.NoNameservers,
            dns.exception.DNSException,
        ):
            return False
    except dns.exception.DNSException:
        # Catch any other DNS-specific exceptions
        return False


def validate_organization_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate organization settings dictionary.

    Args:
        settings: Settings dictionary to validate

    Returns:
        Validated settings dictionary

    Raises:
        ValidationError: If settings are invalid
    """
    if not isinstance(settings, dict):
        raise ValidationError("Settings must be a dictionary")

    # Define sensitive keys that shouldn't be in settings
    sensitive_keys = [
        "password",
        "secret",
        "token",
        "key",
        "api_key",
        "private_key",
        "auth_token",
        "bearer_token",
        "jwt",
        "credential",
        "passwd",
    ]

    # Check for sensitive keys
    for key in settings.keys():
        if not isinstance(key, str):
            raise ValidationError("All setting keys must be strings")

        key_lower = key.lower()
        if any(sensitive in key_lower for sensitive in sensitive_keys):
            raise ValidationError(f"Settings cannot contain sensitive key: {key}")

    # Validate values
    for key, value in settings.items():
        if not _is_json_serializable(value):
            raise ValidationError(
                f"Setting '{key}' contains non-JSON serializable value"
            )

    # Check total size (rough estimate)
    import json

    try:
        settings_json = json.dumps(settings)
        if len(settings_json) > 10000:  # 10KB limit
            raise ValidationError("Settings data is too large (max 10KB)")
    except (TypeError, ValueError) as e:
        raise ValidationError(f"Settings contain invalid data: {str(e)}")

    return settings


def validate_uuid(uuid_string: str, field_name: str = "ID") -> UUID:
    """
    Validate and convert string to UUID.

    Args:
        uuid_string: String to validate as UUID
        field_name: Name of the field for error messages

    Returns:
        UUID object

    Raises:
        ValidationError: If UUID is invalid
    """
    if not uuid_string:
        raise ValidationError(f"{field_name} cannot be empty")

    try:
        return UUID(str(uuid_string))
    except (ValueError, TypeError):
        raise ValidationError(f"Invalid {field_name} format: must be a valid UUID")


def validate_pagination_params(page: int, per_page: int) -> tuple[int, int]:
    """
    Validate pagination parameters.

    Args:
        page: Page number
        per_page: Items per page

    Returns:
        Tuple of validated (page, per_page)

    Raises:
        ValidationError: If parameters are invalid
    """
    if not isinstance(page, int) or page < 1:
        raise ValidationError("Page must be a positive integer starting from 1")

    if not isinstance(per_page, int) or per_page < 1:
        raise ValidationError("Per page must be a positive integer")

    if per_page > 100:
        raise ValidationError("Per page cannot exceed 100 items")

    if page > 10000:
        raise ValidationError("Page number cannot exceed 10000")

    return page, per_page


def validate_search_query(
    query: Optional[str], field_name: str = "search query"
) -> Optional[str]:
    """
    Validate and sanitize search query string.

    Args:
        query: Search query to validate
        field_name: Name of the field for error messages

    Returns:
        Sanitized query string or None

    Raises:
        ValidationError: If query is invalid
    """
    if not query:
        return None

    if not isinstance(query, str):
        raise ValidationError(f"{field_name} must be a string")

    query = query.strip()

    if not query:
        return None

    if len(query) > 100:
        raise ValidationError(f"{field_name} cannot exceed 100 characters")

    # Prevent SQL injection and XSS
    dangerous_patterns = [
        r"[;<>\"'`]",  # SQL injection characters
        r"script\s*>",  # XSS script tags
        r"javascript:",  # JavaScript protocol
        r"on\w+\s*=",  # Event handlers
        r"--",  # SQL comments
        r"/\*",  # SQL comments
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            raise ValidationError(f"{field_name} contains invalid characters")

    # Allow only alphanumeric, spaces, and basic punctuation
    if not re.match(r"^[a-zA-Z0-9\s\-_.@]+$", query):
        raise ValidationError(f"{field_name} contains invalid characters")

    return query


def validate_url(url: Optional[str], field_name: str = "URL") -> Optional[str]:
    """
    Validate URL format.

    Args:
        url: URL to validate
        field_name: Name of the field for error messages

    Returns:
        Validated URL or None

    Raises:
        ValidationError: If URL is invalid
    """
    if not url:
        return None

    if not isinstance(url, str):
        raise ValidationError(f"{field_name} must be a string")

    url = url.strip()

    if not url:
        return None

    if len(url) > 2048:
        raise ValidationError(f"{field_name} cannot exceed 2048 characters")

    try:
        parsed = urlparse(url)

        if not parsed.scheme:
            raise ValidationError(f"{field_name} must include a scheme (http/https)")

        if parsed.scheme not in ["http", "https"]:
            raise ValidationError(f"{field_name} must use http or https scheme")

        if not parsed.netloc:
            raise ValidationError(f"{field_name} must include a domain")

        return url

    except Exception as e:
        raise ValidationError(f"Invalid {field_name} format: {str(e)}")


def validate_email(email: Optional[str]) -> Optional[str]:
    """
    Validate email address format.

    Args:
        email: Email to validate

    Returns:
        Validated email or None

    Raises:
        ValidationError: If email is invalid
    """
    if not email:
        return None

    if not isinstance(email, str):
        raise ValidationError("Email must be a string")

    email = email.strip().lower()

    if not email:
        return None

    if len(email) > 254:
        raise ValidationError("Email address is too long")

    # Basic email validation regex
    email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

    if not re.match(email_pattern, email):
        raise ValidationError("Invalid email format")

    # Check for consecutive dots
    if ".." in email:
        raise ValidationError("Email cannot contain consecutive dots")

    # Check local part length
    local_part = email.split("@")[0]
    if len(local_part) > 64:
        raise ValidationError("Email local part is too long")

    return email


def _is_json_serializable(obj) -> bool:
    """
    Check if object is JSON serializable.

    Args:
        obj: Object to check

    Returns:
        True if serializable, False otherwise
    """
    import json

    try:
        json.dumps(obj)
        return True
    except (TypeError, ValueError):
        return False


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename for safe storage.

    Args:
        filename: Filename to sanitize

    Returns:
        Sanitized filename

    Raises:
        ValidationError: If filename is invalid
    """
    if not filename:
        raise ValidationError("Filename cannot be empty")

    if not isinstance(filename, str):
        raise ValidationError("Filename must be a string")

    # Remove path traversal attempts
    filename = filename.replace("../", "").replace("..\\", "")

    # Remove dangerous characters
    filename = re.sub(r'[<>:"/\\|?*]', "", filename)

    # Remove control characters
    filename = re.sub(r"[\x00-\x1f\x7f]", "", filename)

    # Limit length
    if len(filename) > 255:
        name, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
        filename = name[: 250 - len(ext)] + ("." + ext if ext else "")

    if not filename:
        raise ValidationError("Filename becomes empty after sanitization")

    return filename


def validate_file_size(size_bytes: int, max_size_mb: int = 50) -> bool:
    """
    Validate file size.

    Args:
        size_bytes: File size in bytes
        max_size_mb: Maximum allowed size in MB

    Returns:
        True if valid

    Raises:
        ValidationError: If file is too large
    """
    if not isinstance(size_bytes, int) or size_bytes < 0:
        raise ValidationError("File size must be a non-negative integer")

    max_bytes = max_size_mb * 1024 * 1024

    if size_bytes > max_bytes:
        raise ValidationError(
            f"File size exceeds maximum allowed size of {max_size_mb}MB"
        )

    if size_bytes == 0:
        raise ValidationError("File cannot be empty")

    return True


# Export commonly used validators
__all__ = [
    "ValidationError",
    "validate_organization_name",
    "validate_domain",
    "validate_domain_dns",
    "validate_organization_settings",
    "validate_uuid",
    "validate_pagination_params",
    "validate_search_query",
    "validate_url",
    "validate_email",
    "sanitize_filename",
    "validate_file_size",
]
