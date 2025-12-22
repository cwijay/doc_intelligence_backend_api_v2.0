"""Pydantic schemas for API requests and responses.

This package contains all Pydantic models organized by domain:
- organization.py: Organization schemas
- user.py: User schemas
- folder.py: Folder schemas
- document.py: Document schemas
- errors.py: Error response schemas
- stats.py: Statistics and audit log schemas
- validators.py: Shared validator functions
- base.py: Base classes and pagination

All schemas are re-exported here for backwards compatibility.
Import from this module: `from app.models.schemas import UserResponse`
"""

# Re-export enums from domain models
from app.models.organization import PlanType
from app.models.user import UserRole
from app.models.document import DocumentStatus, FileType

# Base schemas
from app.models.schemas.base import PaginationParams

# Organization schemas
from app.models.schemas.organization import (
    OrganizationBase,
    OrganizationCreate,
    OrganizationUpdate,
    OrganizationResponse,
    OrganizationList,
    OrganizationCreateRequest,
    OrganizationUpdateRequest,
    OrganizationDeleteResponse,
    OrganizationFilters,
)

# User schemas
from app.models.schemas.user import (
    UserBase,
    UserCreate,
    UserUpdate,
    UserResponse,
    UserList,
    UserCreateRequest,
    UserUpdateRequest,
    UserDeleteResponse,
    UserFilters,
)

# Folder schemas
from app.models.schemas.folder import (
    FolderBase,
    FolderCreate,
    FolderUpdate,
    FolderMove,
    FolderResponse,
    FolderWithChildren,
    FolderList,
    FolderTree,
    FolderCreateRequest,
    FolderUpdateRequest,
    FolderMoveRequest,
    FolderDeleteResponse,
    FolderFilters,
)

# Document schemas
from app.models.schemas.document import (
    DocumentBase,
    DocumentCreate,
    DocumentUpload,
    DocumentUpdate,
    DocumentResponse,
    DocumentList,
    DocumentFilters,
    DocumentCreateRequest,
    DocumentUpdateRequest,
    DocumentDeleteResponse,
    DocumentUploadResponse,
    DocumentDownloadResponse,
    DocumentStatusUpdate,
)

# Error response schemas
from app.models.schemas.errors import (
    ErrorDetail,
    ErrorResponse,
    APIErrorResponse,
    ValidationErrorResponse,
    NotFoundErrorResponse,
    ConflictErrorResponse,
    UnauthorizedErrorResponse,
    ForbiddenErrorResponse,
    InternalServerErrorResponse,
)

# Stats response schemas
from app.models.schemas.stats import (
    UserStatsResponse,
    OrganizationStatsResponse,
    FolderStatsResponse,
    DocumentStatsResponse,
    AuditLogEntry,
    AuditLogListResponse,
    TokenValidationResponse,
)

# Export all schemas
__all__ = [
    # Enums (re-exported for convenience)
    "PlanType",
    "UserRole",
    "DocumentStatus",
    "FileType",
    # Base
    "PaginationParams",
    # Organization schemas
    "OrganizationBase",
    "OrganizationCreate",
    "OrganizationUpdate",
    "OrganizationResponse",
    "OrganizationList",
    "OrganizationCreateRequest",
    "OrganizationUpdateRequest",
    "OrganizationDeleteResponse",
    "OrganizationFilters",
    # User schemas
    "UserBase",
    "UserCreate",
    "UserUpdate",
    "UserResponse",
    "UserList",
    "UserCreateRequest",
    "UserUpdateRequest",
    "UserDeleteResponse",
    "UserFilters",
    # Folder schemas
    "FolderBase",
    "FolderCreate",
    "FolderUpdate",
    "FolderMove",
    "FolderResponse",
    "FolderWithChildren",
    "FolderList",
    "FolderTree",
    "FolderCreateRequest",
    "FolderUpdateRequest",
    "FolderMoveRequest",
    "FolderDeleteResponse",
    "FolderFilters",
    # Document schemas
    "DocumentBase",
    "DocumentCreate",
    "DocumentUpload",
    "DocumentUpdate",
    "DocumentResponse",
    "DocumentList",
    "DocumentFilters",
    "DocumentCreateRequest",
    "DocumentUpdateRequest",
    "DocumentDeleteResponse",
    "DocumentUploadResponse",
    "DocumentDownloadResponse",
    "DocumentStatusUpdate",
    # Error response schemas
    "ErrorDetail",
    "ErrorResponse",
    "APIErrorResponse",
    "ValidationErrorResponse",
    "NotFoundErrorResponse",
    "ConflictErrorResponse",
    "UnauthorizedErrorResponse",
    "ForbiddenErrorResponse",
    "InternalServerErrorResponse",
    # Stats response schemas
    "UserStatsResponse",
    "OrganizationStatsResponse",
    "FolderStatsResponse",
    "DocumentStatsResponse",
    "AuditLogEntry",
    "AuditLogListResponse",
    "TokenValidationResponse",
]
