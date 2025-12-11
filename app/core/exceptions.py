import uuid
import traceback
from typing import Any, Dict, Optional
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from google.api_core.exceptions import GoogleAPIError
from pydantic import ValidationError

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class DocumentIntelligenceError(Exception):
    """Base exception for Document Intelligence application."""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.error_code = error_code or "INTERNAL_ERROR"
        self.details = details or {}
        super().__init__(self.message)


class DatabaseError(DocumentIntelligenceError):
    """Database related errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "DATABASE_ERROR", details)


class AuthenticationError(DocumentIntelligenceError):
    """Authentication related errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "AUTHENTICATION_ERROR", details)


class TokenExpiredError(AuthenticationError):
    """Token expired error."""

    def __init__(
        self,
        message: str = "Access token has expired",
        expires_at: Optional[str] = None,
    ):
        details = {}
        if expires_at:
            details["expired_at"] = expires_at
            details["action"] = "refresh_token_or_relogin"
        super().__init__(message, details)
        self.error_code = "TOKEN_EXPIRED"


class TokenInvalidError(AuthenticationError):
    """Token invalid error."""

    def __init__(self, message: str = "Access token is invalid"):
        super().__init__(message)
        self.error_code = "TOKEN_INVALID"


class RefreshTokenExpiredError(AuthenticationError):
    """Refresh token expired error."""

    def __init__(self, message: str = "Refresh token has expired"):
        details = {"action": "relogin_required"}
        super().__init__(message, details)
        self.error_code = "REFRESH_TOKEN_EXPIRED"


class RefreshTokenInvalidError(AuthenticationError):
    """Refresh token invalid error."""

    def __init__(self, message: str = "Refresh token is invalid"):
        details = {"action": "relogin_required"}
        super().__init__(message, details)
        self.error_code = "REFRESH_TOKEN_INVALID"


class AuthorizationError(DocumentIntelligenceError):
    """Authorization related errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "AUTHORIZATION_ERROR", details)


class ValidationError(DocumentIntelligenceError):
    """Validation related errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "VALIDATION_ERROR", details)


class ExternalServiceError(DocumentIntelligenceError):
    """External service related errors."""

    def __init__(
        self, message: str, service: str, details: Optional[Dict[str, Any]] = None
    ):
        details = details or {}
        details["service"] = service
        super().__init__(message, "EXTERNAL_SERVICE_ERROR", details)


class RateLimitError(DocumentIntelligenceError):
    """Rate limiting errors."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, "RATE_LIMIT_ERROR", details)


class FileProcessingError(DocumentIntelligenceError):
    """File processing related errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "FILE_PROCESSING_ERROR", details)


# Organization Management Exceptions
class OrganizationError(DocumentIntelligenceError):
    """Base class for organization-related errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "ORGANIZATION_ERROR", details)


class OrganizationNotFoundError(OrganizationError):
    """Organization not found error."""

    def __init__(
        self, message: str = "Organization not found", org_id: Optional[str] = None
    ):
        details = {"organization_id": org_id} if org_id else None
        super().__init__(message, details)


class OrganizationAlreadyExistsError(OrganizationError):
    """Organization already exists error."""

    def __init__(
        self,
        message: str = "Organization already exists",
        org_name: Optional[str] = None,
    ):
        details = {"organization_name": org_name} if org_name else None
        super().__init__(message, details)


class OrganizationValidationError(OrganizationError):
    """Organization validation error."""

    def __init__(
        self, message: str, field: Optional[str] = None, value: Optional[str] = None
    ):
        details = {}
        if field:
            details["field"] = field
        if value:
            details["value"] = value
        super().__init__(message, details)


class OrganizationInactiveError(OrganizationError):
    """Organization is inactive error."""

    def __init__(
        self, message: str = "Organization is inactive", org_id: Optional[str] = None
    ):
        details = {"organization_id": org_id} if org_id else None
        super().__init__(message, details)


class OrganizationAccessDeniedError(OrganizationError):
    """Access denied to organization error."""

    def __init__(
        self,
        message: str = "Access denied to organization",
        org_id: Optional[str] = None,
    ):
        details = {"organization_id": org_id} if org_id else None
        super().__init__(message, details)


def create_error_response(
    status_code: int,
    message: str,
    error_code: str = "INTERNAL_ERROR",
    details: Optional[Dict[str, Any]] = None,
    error_id: Optional[str] = None,
    request_path: Optional[str] = None,
) -> JSONResponse:
    """Create standardized error response."""

    error_id = error_id or str(uuid.uuid4())[:8]

    error_response = {
        "error": {
            "code": error_code,
            "message": message,
            "error_id": error_id,
        }
    }

    if details:
        error_response["error"]["details"] = details

    if request_path:
        error_response["error"]["path"] = request_path

    if settings.is_development:
        error_response["error"]["timestamp"] = str(uuid.uuid4())

    return JSONResponse(status_code=status_code, content=error_response)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTP exceptions."""
    error_id = str(uuid.uuid4())[:8]

    logger.warning(
        "HTTP exception occurred",
        status_code=exc.status_code,
        detail=exc.detail,
        path=request.url.path,
        method=request.method,
        error_id=error_id,
    )

    return create_error_response(
        status_code=exc.status_code,
        message=exc.detail,
        error_code="HTTP_ERROR",
        error_id=error_id,
        request_path=str(request.url.path),
    )


async def starlette_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Handle Starlette HTTP exceptions."""
    error_id = str(uuid.uuid4())[:8]

    logger.warning(
        "Starlette HTTP exception occurred",
        status_code=exc.status_code,
        detail=exc.detail,
        path=request.url.path,
        method=request.method,
        error_id=error_id,
    )

    return create_error_response(
        status_code=exc.status_code,
        message=exc.detail,
        error_code="HTTP_ERROR",
        error_id=error_id,
        request_path=str(request.url.path),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle request validation errors."""
    error_id = str(uuid.uuid4())[:8]

    logger.warning(
        "Validation exception occurred",
        errors=exc.errors(),
        path=request.url.path,
        method=request.method,
        error_id=error_id,
    )

    # Format validation errors
    formatted_errors = []
    for error in exc.errors():
        formatted_error = {
            "field": ".".join(str(x) for x in error["loc"]),
            "message": error["msg"],
            "type": error["type"],
        }
        if "input" in error:
            formatted_error["input"] = error["input"]
        formatted_errors.append(formatted_error)

    return create_error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        message="Request validation failed",
        error_code="VALIDATION_ERROR",
        details={"validation_errors": formatted_errors},
        error_id=error_id,
        request_path=str(request.url.path),
    )


async def document_intelligence_exception_handler(
    request: Request, exc: DocumentIntelligenceError
) -> JSONResponse:
    """Handle custom application exceptions."""
    error_id = str(uuid.uuid4())[:8]

    # Determine status code based on error type
    status_code_map = {
        "AUTHENTICATION_ERROR": status.HTTP_401_UNAUTHORIZED,
        "TOKEN_EXPIRED": status.HTTP_401_UNAUTHORIZED,
        "TOKEN_INVALID": status.HTTP_401_UNAUTHORIZED,
        "REFRESH_TOKEN_EXPIRED": status.HTTP_401_UNAUTHORIZED,
        "REFRESH_TOKEN_INVALID": status.HTTP_401_UNAUTHORIZED,
        "AUTHORIZATION_ERROR": status.HTTP_403_FORBIDDEN,
        "VALIDATION_ERROR": status.HTTP_400_BAD_REQUEST,
        "DATABASE_ERROR": status.HTTP_500_INTERNAL_SERVER_ERROR,
        "EXTERNAL_SERVICE_ERROR": status.HTTP_502_BAD_GATEWAY,
        "RATE_LIMIT_ERROR": status.HTTP_429_TOO_MANY_REQUESTS,
        "FILE_PROCESSING_ERROR": status.HTTP_400_BAD_REQUEST,
        "ORGANIZATION_ERROR": status.HTTP_400_BAD_REQUEST,
    }

    status_code = status_code_map.get(
        exc.error_code, status.HTTP_500_INTERNAL_SERVER_ERROR
    )

    logger.error(
        "Application exception occurred",
        error_code=exc.error_code,
        message=exc.message,
        details=exc.details,
        path=request.url.path,
        method=request.method,
        error_id=error_id,
    )

    return create_error_response(
        status_code=status_code,
        message=exc.message,
        error_code=exc.error_code,
        details=exc.details,
        error_id=error_id,
        request_path=str(request.url.path),
    )


async def google_api_exception_handler(
    request: Request, exc: GoogleAPIError
) -> JSONResponse:
    """Handle Google Cloud API errors (GCS, etc.)."""
    error_id = str(uuid.uuid4())[:8]

    logger.error(
        "Google API exception occurred",
        error=str(exc),
        path=request.url.path,
        method=request.method,
        error_id=error_id,
        exc_info=True,
    )

    # Don't expose internal errors in production
    message = "Cloud service error occurred" if settings.is_production else str(exc)

    return create_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message=message,
        error_code="CLOUD_SERVICE_ERROR",
        error_id=error_id,
        request_path=str(request.url.path),
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle all other unhandled exceptions."""
    error_id = str(uuid.uuid4())[:8]

    logger.error(
        "Unhandled exception occurred",
        error=str(exc),
        error_type=type(exc).__name__,
        path=request.url.path,
        method=request.method,
        error_id=error_id,
        exc_info=True,
    )

    # Prepare error response
    if settings.is_development:
        # Include more details in development
        details = {
            "error_type": type(exc).__name__,
            "traceback": traceback.format_exc().split("\n"),
        }
        message = str(exc)
    else:
        # Generic message in production
        details = None
        message = "An unexpected error occurred"

    return create_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message=message,
        error_code="INTERNAL_ERROR",
        details=details,
        error_id=error_id,
        request_path=str(request.url.path),
    )


def setup_exception_handlers(app):
    """Setup all exception handlers for the FastAPI app."""

    # Custom application exceptions
    app.add_exception_handler(
        DocumentIntelligenceError, document_intelligence_exception_handler
    )

    # HTTP exceptions
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, starlette_exception_handler)

    # Validation errors
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    # Google Cloud API errors (GCS, etc.)
    app.add_exception_handler(GoogleAPIError, google_api_exception_handler)

    # General exception handler (catch-all)
    app.add_exception_handler(Exception, general_exception_handler)
