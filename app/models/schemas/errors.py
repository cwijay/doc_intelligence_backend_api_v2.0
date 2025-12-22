"""Error response schemas for OpenAPI documentation."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Individual field error detail for validation errors."""

    field: str = Field(
        ...,
        description="Field name that caused the error",
        example="email",
    )
    message: str = Field(
        ...,
        description="Human-readable error message",
        example="Invalid email format",
    )
    type: str = Field(
        ...,
        description="Error type identifier",
        example="value_error",
    )


class ErrorResponse(BaseModel):
    """Standardized API error response body."""

    code: str = Field(
        ...,
        description="Error code for client-side handling",
        example="VALIDATION_ERROR",
    )
    message: str = Field(
        ...,
        description="Human-readable error message",
        example="Request validation failed",
    )
    error_id: Optional[str] = Field(
        None,
        description="Unique error ID for support tracking",
        example="err_abc12345",
    )
    details: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional error context and field-specific errors",
        example={
            "validation_errors": [{"field": "email", "message": "Invalid format"}]
        },
    )
    path: Optional[str] = Field(
        None,
        description="Request path that caused the error",
        example="/api/v1/users",
    )


class APIErrorResponse(BaseModel):
    """Wrapper for error responses (matches actual API error format)."""

    error: ErrorResponse = Field(..., description="Error details")


class ValidationErrorResponse(BaseModel):
    """422 Validation Error response."""

    detail: List[Dict[str, Any]] = Field(
        ...,
        description="List of validation errors",
        example=[
            {
                "type": "string_too_short",
                "loc": ["body", "password"],
                "msg": "String should have at least 8 characters",
                "input": "short",
            }
        ],
    )


class NotFoundErrorResponse(BaseModel):
    """404 Not Found error response."""

    error: ErrorResponse = Field(
        ...,
        description="Error details",
        example={
            "code": "NOT_FOUND",
            "message": "Resource not found",
            "error_id": "err_abc12345",
            "path": "/api/v1/documents/doc_123",
        },
    )


class ConflictErrorResponse(BaseModel):
    """409 Conflict error response."""

    error: ErrorResponse = Field(
        ...,
        description="Error details",
        example={
            "code": "CONFLICT",
            "message": "Resource already exists",
            "error_id": "err_def67890",
            "details": {"field": "email", "value": "user@example.com"},
        },
    )


class UnauthorizedErrorResponse(BaseModel):
    """401 Unauthorized error response."""

    error: ErrorResponse = Field(
        ...,
        description="Error details",
        example={
            "code": "TOKEN_INVALID",
            "message": "Invalid or expired session token",
            "error_id": "err_ghi11111",
        },
    )


class ForbiddenErrorResponse(BaseModel):
    """403 Forbidden error response."""

    error: ErrorResponse = Field(
        ...,
        description="Error details",
        example={
            "code": "FORBIDDEN",
            "message": "Access denied - insufficient permissions",
            "error_id": "err_jkl22222",
        },
    )


class InternalServerErrorResponse(BaseModel):
    """500 Internal Server Error response."""

    error: ErrorResponse = Field(
        ...,
        description="Error details",
        example={
            "code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred",
            "error_id": "err_mno33333",
        },
    )
