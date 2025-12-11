"""
Audit context utilities for extracting request metadata.

Provides helper functions for extracting audit-relevant information
from FastAPI requests and building audit details for different operations.
"""

from typing import Dict, Any, Optional
from fastapi import Request


def extract_audit_context(
    request: Request, current_user: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Extract audit context from FastAPI request and user data.

    Args:
        request: FastAPI Request object
        current_user: Current user dict from authentication

    Returns:
        Dictionary with audit context (ip_address, session_id, user_agent, user_id, org_id)
    """
    # Extract IP address (handle proxies)
    ip_address = None
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        # Take the first IP in the chain (original client)
        ip_address = forwarded_for.split(",")[0].strip()
    elif request.client:
        ip_address = request.client.host

    # Extract user agent (limit length for storage)
    user_agent = request.headers.get("user-agent", "")[:512]

    # Extract session ID from user context
    session_id = current_user.get("session_id")

    return {
        "ip_address": ip_address,
        "session_id": session_id,
        "user_agent": user_agent,
        "user_id": current_user.get("user_id"),
        "org_id": current_user.get("org_id"),
    }


def get_audit_details_for_create(entity_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build audit details for CREATE actions.

    Args:
        entity_data: Dictionary of the created entity's data

    Returns:
        Audit details dictionary
    """
    # Filter out sensitive fields
    safe_data = _filter_sensitive_fields(entity_data)

    return {
        "new_values": safe_data,
        "operation": "create",
    }


def get_audit_details_for_update(
    old_values: Dict[str, Any],
    new_values: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build audit details for UPDATE actions.

    Calculates the diff between old and new values.

    Args:
        old_values: Dictionary of old field values
        new_values: Dictionary of new field values

    Returns:
        Audit details dictionary with changes
    """
    # Filter sensitive fields
    safe_old = _filter_sensitive_fields(old_values)
    safe_new = _filter_sensitive_fields(new_values)

    # Calculate changed fields
    changes = {}
    for key in safe_new:
        if key in safe_old and safe_old[key] != safe_new[key]:
            changes[key] = {
                "old": safe_old[key],
                "new": safe_new[key],
            }
        elif key not in safe_old:
            changes[key] = {
                "old": None,
                "new": safe_new[key],
            }

    return {
        "old_values": safe_old,
        "new_values": safe_new,
        "changes": changes,
        "operation": "update",
    }


def get_audit_details_for_delete(entity_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build audit details for DELETE actions.

    Args:
        entity_data: Dictionary of the deleted entity's data

    Returns:
        Audit details dictionary
    """
    # Filter out sensitive fields
    safe_data = _filter_sensitive_fields(entity_data)

    return {
        "deleted_values": safe_data,
        "operation": "delete",
    }


def get_audit_details_for_login(
    success: bool,
    email: str,
    failure_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build audit details for LOGIN actions.

    Args:
        success: Whether login was successful
        email: Email used for login attempt
        failure_reason: Reason for failure if unsuccessful

    Returns:
        Audit details dictionary
    """
    details = {
        "operation": "login",
        "success": success,
        "email": email,
    }

    if not success and failure_reason:
        details["failure_reason"] = failure_reason

    return details


def get_audit_details_for_logout(session_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Build audit details for LOGOUT actions.

    Args:
        session_id: Session ID being logged out

    Returns:
        Audit details dictionary
    """
    return {
        "operation": "logout",
        "session_id": session_id,
    }


def get_audit_details_for_upload(
    filename: str,
    file_type: str,
    file_size: int,
    storage_path: str,
    folder_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build audit details for UPLOAD actions.

    Args:
        filename: Name of uploaded file
        file_type: Type of file (pdf, xlsx, etc.)
        file_size: Size in bytes
        storage_path: GCS storage path
        folder_id: Optional folder ID

    Returns:
        Audit details dictionary
    """
    return {
        "operation": "upload",
        "filename": filename,
        "file_type": file_type,
        "file_size": file_size,
        "storage_path": storage_path,
        "folder_id": folder_id,
    }


def get_audit_details_for_download(
    filename: str,
    file_type: str,
    storage_path: str,
) -> Dict[str, Any]:
    """
    Build audit details for DOWNLOAD actions.

    Args:
        filename: Name of downloaded file
        file_type: Type of file
        storage_path: GCS storage path

    Returns:
        Audit details dictionary
    """
    return {
        "operation": "download",
        "filename": filename,
        "file_type": file_type,
        "storage_path": storage_path,
    }


def get_audit_details_for_move(
    old_path: str,
    new_path: str,
    old_parent_id: Optional[str] = None,
    new_parent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build audit details for MOVE actions.

    Args:
        old_path: Previous path
        new_path: New path
        old_parent_id: Previous parent folder ID
        new_parent_id: New parent folder ID

    Returns:
        Audit details dictionary
    """
    return {
        "operation": "move",
        "old_path": old_path,
        "new_path": new_path,
        "old_parent_id": old_parent_id,
        "new_parent_id": new_parent_id,
    }


def _filter_sensitive_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Filter out sensitive fields from audit data.

    Args:
        data: Dictionary that may contain sensitive fields

    Returns:
        Dictionary with sensitive fields removed
    """
    sensitive_fields = {
        "password",
        "password_hash",
        "secret",
        "token",
        "api_key",
        "credentials",
        "private_key",
    }

    return {
        key: value for key, value in data.items() if key.lower() not in sensitive_fields
    }
