"""
Shared utilities and dependencies for document API endpoints.

This module provides common functionality used across different document router modules,
following the DRY (Don't Repeat Yourself) principle.
"""

from typing import Dict, Any
from fastapi import Depends, HTTPException, status

from app.core.simple_auth import get_current_user_dict
from app.core.logging import get_api_logger
from app.services.document_service import (
    document_service,
    DocumentNotFoundError,
    DocumentValidationError,
    DocumentUploadError,
)

# Shared logger instance
logger = get_api_logger()


def get_document_dependencies() -> Dict[str, Any]:
    """Get common dependencies for document endpoints."""
    return {"document_service": document_service, "logger": logger}


async def get_user_context(
    current_user: Dict[str, Any] = Depends(get_current_user_dict),
) -> Dict[str, str]:
    """Extract user context information."""
    return {
        "org_id": current_user["org_id"],
        "user_id": current_user.get("user_id", "unknown"),
    }


def handle_document_not_found_error(
    e: DocumentNotFoundError, operation: str, **context
) -> HTTPException:
    """Handle DocumentNotFoundError consistently across endpoints."""
    logger.warning(f"Document not found for {operation}", error=str(e), **context)
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


def handle_document_validation_error(
    e: DocumentValidationError, operation: str, **context
) -> HTTPException:
    """Handle DocumentValidationError consistently across endpoints."""
    logger.warning(
        f"Document validation failed for {operation}", error=str(e), **context
    )
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def handle_document_upload_error(
    e: DocumentUploadError, operation: str, **context
) -> HTTPException:
    """Handle DocumentUploadError consistently across endpoints."""
    logger.error(f"Document upload error during {operation}", error=str(e), **context)
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="An error occurred while processing the document",
    )


def handle_generic_error(e: Exception, operation: str, **context) -> HTTPException:
    """Handle generic exceptions consistently across endpoints."""
    logger.error(f"Unexpected error during {operation}", error=str(e), **context)
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"An unexpected error occurred while {operation}",
    )


def log_operation_start(operation: str, **context) -> None:
    """Log the start of an operation consistently."""
    logger.info(f"{operation} started", **context)


def log_operation_success(operation: str, **context) -> None:
    """Log successful operation completion consistently."""
    logger.info(f"{operation} completed successfully", **context)


def log_operation_error(operation: str, error: str, **context) -> None:
    """Log operation errors consistently."""
    logger.error(f"{operation} failed", error=error, **context)
