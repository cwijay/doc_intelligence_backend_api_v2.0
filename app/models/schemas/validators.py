"""Shared validators for Pydantic schemas.

This module contains reusable validator functions that were previously
duplicated across multiple schema files.
"""

import re
from typing import Any, Dict, Optional


def validate_filter_strings(
    v: Optional[str], extra_chars: str = "", allow_slashes: bool = False
) -> Optional[str]:
    """Validate and clean filter strings.

    Args:
        v: The string value to validate
        extra_chars: Additional characters to allow in the pattern
        allow_slashes: Whether to allow forward slashes (for GCS paths)

    Returns:
        Cleaned string or None if empty

    Raises:
        ValueError: If invalid characters are found
    """
    if v is None:
        return v

    v = v.strip()
    if not v:
        return None

    # Build pattern based on options
    base_pattern = r"^[a-zA-Z0-9\s\-_."
    if extra_chars:
        # Escape special regex chars in extra_chars
        for char in extra_chars:
            if char in r"\.^$*+?{}[]|()":
                base_pattern += "\\" + char
            else:
                base_pattern += char
    if allow_slashes:
        base_pattern += "/"
    base_pattern += "]+$"

    if not re.match(base_pattern, v):
        raise ValueError("Invalid characters in filter")

    return v


def validate_metadata(v: Dict[str, Any]) -> Dict[str, Any]:
    """Validate metadata dictionary.

    Ensures metadata doesn't contain sensitive keys that could
    expose credentials or secrets.

    Args:
        v: The metadata dictionary to validate

    Returns:
        The validated metadata dictionary

    Raises:
        ValueError: If metadata contains sensitive keys
    """
    if not isinstance(v, dict):
        raise ValueError("Metadata must be a dictionary")

    # Ensure metadata doesn't contain sensitive keys
    sensitive_keys = ["password", "secret", "key", "token", "credential"]
    for key in v.keys():
        if any(sensitive in key.lower() for sensitive in sensitive_keys):
            raise ValueError(f"Metadata cannot contain sensitive key: {key}")

    return v


def validate_settings(v: Dict[str, Any]) -> Dict[str, Any]:
    """Validate settings dictionary.

    Similar to metadata validation but specifically for organization settings.

    Args:
        v: The settings dictionary to validate

    Returns:
        The validated settings dictionary

    Raises:
        ValueError: If settings contains sensitive keys
    """
    if not isinstance(v, dict):
        raise ValueError("Settings must be a dictionary")

    # Ensure settings don't contain sensitive keys
    sensitive_keys = ["password", "secret", "key", "token"]
    for key in v.keys():
        if any(sensitive in key.lower() for sensitive in sensitive_keys):
            raise ValueError(f"Settings cannot contain sensitive key: {key}")

    return v
