import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from pydantic import BaseModel, Field, field_validator, field_serializer, ConfigDict
from fastapi import UploadFile

from app.models.organization import PlanType
from app.models.user import UserRole
from app.models.document import DocumentStatus, FileType


# Organization Schemas
class OrganizationBase(BaseModel):
    """Base organization schema with common fields."""

    name: str = Field(
        ..., min_length=2, max_length=255, description="Organization name"
    )
    domain: Optional[str] = Field(
        None, max_length=255, description="Organization domain (optional)"
    )
    settings: Dict[str, Any] = Field(
        default_factory=dict, description="Organization settings and preferences"
    )
    plan_type: PlanType = Field(
        default=PlanType.FREE, description="Organization plan type"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate organization name."""
        if not v or not v.strip():
            raise ValueError("Organization name cannot be empty")

        # Remove extra whitespace
        v = v.strip()

        # Check for minimum length after stripping
        if len(v) < 2:
            raise ValueError("Organization name must be at least 2 characters long")

        # Check for special characters (allow letters, numbers, spaces, hyphens, underscores)
        if not re.match(r"^[a-zA-Z0-9\s\-_]+$", v):
            raise ValueError(
                "Organization name can only contain letters, numbers, spaces, hyphens, and underscores"
            )

        return v

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: Optional[str]) -> Optional[str]:
        """Validate organization domain."""
        if v is None:
            return v

        v = v.strip().lower()

        if not v:
            return None

        # Basic domain validation regex
        domain_pattern = r"^[a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9]*\.([a-zA-Z]{2,})$"
        if not re.match(domain_pattern, v):
            raise ValueError("Invalid domain format")

        return v

    @field_validator("settings")
    @classmethod
    def validate_settings(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Validate organization settings."""
        if not isinstance(v, dict):
            raise ValueError("Settings must be a dictionary")

        # Ensure settings don't contain sensitive keys
        sensitive_keys = ["password", "secret", "key", "token"]
        for key in v.keys():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                raise ValueError(f"Settings cannot contain sensitive key: {key}")

        return v


class OrganizationCreate(OrganizationBase):
    """Schema for creating a new organization."""

    pass


class OrganizationUpdate(BaseModel):
    """Schema for updating an organization (all fields optional)."""

    name: Optional[str] = Field(
        None, min_length=2, max_length=255, description="Organization name"
    )
    domain: Optional[str] = Field(
        None, max_length=255, description="Organization domain"
    )
    settings: Optional[Dict[str, Any]] = Field(
        None, description="Organization settings and preferences"
    )
    plan_type: Optional[PlanType] = Field(None, description="Organization plan type")

    # Apply same validators as base class
    _validate_name = field_validator("name")(OrganizationBase.validate_name.__func__)
    _validate_domain = field_validator("domain")(
        OrganizationBase.validate_domain.__func__
    )
    _validate_settings = field_validator("settings")(
        OrganizationBase.validate_settings.__func__
    )


class OrganizationResponse(OrganizationBase):
    """Schema for organization response."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Organization unique identifier")
    is_active: bool = Field(..., description="Whether organization is active")
    created_at: datetime = Field(..., description="When organization was created")
    updated_at: datetime = Field(..., description="When organization was last updated")

    @property
    def is_premium(self) -> bool:
        """Check if organization has premium plan."""
        return self.plan_type in [PlanType.STARTER, PlanType.PRO]

    @property
    def is_pro(self) -> bool:
        """Check if organization has pro plan."""
        return self.plan_type == PlanType.PRO


class OrganizationList(BaseModel):
    """Schema for organization list response with pagination."""

    items: List[OrganizationResponse] = Field(..., description="List of organizations")
    total: int = Field(..., description="Total number of organizations")
    page: int = Field(..., description="Current page number")
    per_page: int = Field(..., description="Number of items per page")
    total_pages: int = Field(..., description="Total number of pages")

    @property
    def has_next(self) -> bool:
        """Check if there are more pages."""
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        """Check if there are previous pages."""
        return self.page > 1

    @property
    def organizations(self) -> List[OrganizationResponse]:
        """Temporary compatibility alias for legacy callers."""
        return self.items


# Request/Response Models for API endpoints
class OrganizationCreateRequest(OrganizationCreate):
    """Request model for creating organization."""

    pass


class OrganizationUpdateRequest(OrganizationUpdate):
    """Request model for updating organization."""

    pass


class OrganizationDeleteResponse(BaseModel):
    """Response model for organization deletion."""

    success: bool = Field(..., description="Whether deletion was successful")
    message: str = Field(..., description="Deletion status message")


# Pagination Models
class PaginationParams(BaseModel):
    """Pagination parameters."""

    page: int = Field(default=1, ge=1, description="Page number (starts from 1)")
    per_page: int = Field(
        default=20, ge=1, le=100, description="Items per page (max 100)"
    )

    @property
    def offset(self) -> int:
        """Calculate database offset."""
        return (self.page - 1) * self.per_page


class OrganizationFilters(BaseModel):
    """Filters for organization listing."""

    name: Optional[str] = Field(
        None, description="Filter by organization name (partial match)"
    )
    domain: Optional[str] = Field(None, description="Filter by domain (partial match)")
    plan_type: Optional[PlanType] = Field(None, description="Filter by plan type")
    is_active: Optional[bool] = Field(None, description="Filter by active status")

    @field_validator("name", "domain")
    @classmethod
    def validate_filter_strings(cls, v: Optional[str]) -> Optional[str]:
        """Validate and clean filter strings."""
        if v is None:
            return v

        v = v.strip()
        if not v:
            return None

        # Prevent SQL injection by allowing only alphanumeric, spaces, and basic punctuation
        if not re.match(r"^[a-zA-Z0-9\s\-_.@]+$", v):
            raise ValueError("Invalid characters in filter")

        return v


# User Schemas
class UserBase(BaseModel):
    """Base user schema with common fields."""

    email: str = Field(
        ..., min_length=5, max_length=255, description="User email address"
    )
    username: str = Field(..., min_length=3, max_length=50, description="Username")
    full_name: str = Field(
        ..., min_length=2, max_length=100, description="User's full name"
    )
    role: UserRole = Field(default=UserRole.USER, description="User role")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Validate email format."""
        import re

        if not v or not v.strip():
            raise ValueError("Email cannot be empty")

        v = v.strip().lower()

        # Basic email validation regex
        # Allow underscores in domain for test environments (e.g., test-YYYYMMDD_HHMMSS.com)
        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9._-]+\.[a-zA-Z]{2,}$"
        if not re.match(email_pattern, v):
            raise ValueError("Invalid email format")

        return v

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username format."""
        import re

        if not v or not v.strip():
            raise ValueError("Username cannot be empty")

        v = v.strip().lower()

        # Username can contain letters, numbers, underscores, hyphens
        if not re.match(r"^[a-z0-9_-]+$", v):
            raise ValueError(
                "Username can only contain letters, numbers, underscores, and hyphens"
            )

        # Must start with letter or number
        if not re.match(r"^[a-z0-9]", v):
            raise ValueError("Username must start with a letter or number")

        # Check for reserved usernames
        reserved = ["admin", "api", "www", "mail", "support", "help", "info", "root"]
        if v in reserved:
            raise ValueError(f"Username '{v}' is reserved")

        return v

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        """Validate full name."""
        import re

        if not v or not v.strip():
            raise ValueError("Full name cannot be empty")

        v = v.strip()

        # Allow letters, spaces, apostrophes, hyphens
        if not re.match(r"^[a-zA-Z\s'-]+$", v):
            raise ValueError(
                "Full name can only contain letters, spaces, apostrophes, and hyphens"
            )

        return v


class UserCreate(UserBase):
    """Schema for creating a new user."""

    password: str = Field(
        ..., min_length=8, max_length=128, description="User password"
    )

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password strength."""
        from app.core.security import validate_password_strength

        is_valid, error_msg = validate_password_strength(v)
        if not is_valid:
            raise ValueError(error_msg)

        return v


class UserUpdate(BaseModel):
    """Schema for updating a user (all fields optional)."""

    email: Optional[str] = Field(
        None, min_length=5, max_length=255, description="User email address"
    )
    username: Optional[str] = Field(
        None, min_length=3, max_length=50, description="Username"
    )
    full_name: Optional[str] = Field(
        None, min_length=2, max_length=100, description="User's full name"
    )
    role: Optional[UserRole] = Field(None, description="User role")
    password: Optional[str] = Field(
        None, min_length=8, max_length=128, description="New password"
    )

    # Apply same validators as base class
    _validate_email = field_validator("email")(UserBase.validate_email.__func__)
    _validate_username = field_validator("username")(
        UserBase.validate_username.__func__
    )
    _validate_full_name = field_validator("full_name")(
        UserBase.validate_full_name.__func__
    )

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: Optional[str]) -> Optional[str]:
        """Validate password strength if provided."""
        if v is None:
            return v

        from app.core.security import validate_password_strength

        is_valid, error_msg = validate_password_strength(v)
        if not is_valid:
            raise ValueError(error_msg)

        return v


class UserResponse(UserBase):
    """Schema for user response."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="User unique identifier")
    org_id: str = Field(..., description="Organization ID")
    is_active: bool = Field(..., description="Whether user is active")
    created_at: datetime = Field(..., description="When user was created")
    last_login: Optional[datetime] = Field(None, description="When user last logged in")
    updated_at: datetime = Field(..., description="When user was last updated")

    # Remove password_hash from response
    model_config = ConfigDict(from_attributes=True, exclude={"password_hash"})

    @property
    def is_admin(self) -> bool:
        """Check if user is admin."""
        return self.role == UserRole.ADMIN

    @property
    def can_modify(self) -> bool:
        """Check if user can modify data."""
        return self.role in [UserRole.ADMIN, UserRole.USER]


class UserList(BaseModel):
    """Schema for user list response with pagination."""

    users: List[UserResponse] = Field(..., description="List of users")
    total: int = Field(..., description="Total number of users")
    page: int = Field(..., description="Current page number")
    per_page: int = Field(..., description="Number of items per page")
    total_pages: int = Field(..., description="Total number of pages")

    @property
    def has_next(self) -> bool:
        """Check if there are more pages."""
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        """Check if there are previous pages."""
        return self.page > 1


# Request/Response Models for API endpoints
class UserCreateRequest(UserCreate):
    """Request model for creating user."""

    pass


class UserUpdateRequest(UserUpdate):
    """Request model for updating user."""

    pass


class UserDeleteResponse(BaseModel):
    """Response model for user deletion."""

    success: bool = Field(..., description="Whether deletion was successful")
    message: str = Field(..., description="Deletion status message")


class UserFilters(BaseModel):
    """Filters for user listing within organization."""

    email: Optional[str] = Field(None, description="Filter by email (partial match)")
    username: Optional[str] = Field(
        None, description="Filter by username (partial match)"
    )
    full_name: Optional[str] = Field(
        None, description="Filter by full name (partial match)"
    )
    role: Optional[UserRole] = Field(None, description="Filter by role")
    is_active: Optional[bool] = Field(None, description="Filter by active status")

    @field_validator("email", "username", "full_name")
    @classmethod
    def validate_filter_strings(cls, v: Optional[str]) -> Optional[str]:
        """Validate and clean filter strings."""
        if v is None:
            return v

        v = v.strip()
        if not v:
            return None

        # Prevent injection by allowing only alphanumeric, spaces, and basic punctuation
        import re

        if not re.match(r"^[a-zA-Z0-9\s\-_.@']+$", v):
            raise ValueError("Invalid characters in filter")

        return v


# Folder Schemas
class FolderBase(BaseModel):
    """Base folder schema with common fields."""

    name: str = Field(..., min_length=1, max_length=255, description="Folder name")
    parent_folder_id: Optional[str] = Field(
        None, description="Parent folder ID (null for root folders)"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate folder name."""
        if not v or not v.strip():
            raise ValueError("Folder name cannot be empty")

        v = v.strip()

        # Check for invalid characters
        invalid_chars = ["/", "\\", ":", "*", "?", '"', "<", ">", "|", "\n", "\r", "\t"]
        for char in invalid_chars:
            if char in v:
                raise ValueError(f"Folder name cannot contain '{char}'")

        # Cannot be just dots
        if v in [".", ".."]:
            raise ValueError("Folder name cannot be '.' or '..'")

        return v


class FolderCreate(FolderBase):
    """Schema for creating a new folder."""

    pass


class FolderUpdate(BaseModel):
    """Schema for updating a folder (all fields optional)."""

    name: Optional[str] = Field(
        None, min_length=1, max_length=255, description="Folder name"
    )

    # Apply same validators as base class
    _validate_name = field_validator("name")(FolderBase.validate_name.__func__)


class FolderMove(BaseModel):
    """Schema for moving a folder."""

    new_parent_folder_id: Optional[str] = Field(
        None, description="New parent folder ID (null to move to root)"
    )


class FolderResponse(FolderBase):
    """Schema for folder response."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Folder unique identifier")
    org_id: str = Field(..., description="Organization ID")
    path: str = Field(..., description="Full folder path")
    created_by: str = Field(..., description="User ID who created the folder")
    is_active: bool = Field(..., description="Whether folder is active")
    created_at: datetime = Field(..., description="When folder was created")
    updated_at: datetime = Field(..., description="When folder was last updated")

    @property
    def depth(self) -> int:
        """Get folder depth."""
        return len([part for part in self.path.split("/") if part])

    @property
    def is_root(self) -> bool:
        """Check if this is a root folder."""
        return self.parent_folder_id is None


class FolderWithChildren(FolderResponse):
    """Schema for folder response with children."""

    children: List["FolderWithChildren"] = Field(
        default_factory=list, description="Child folders"
    )


class FolderList(BaseModel):
    """Schema for folder list response with pagination."""

    folders: List[FolderResponse] = Field(..., description="List of folders")
    total: int = Field(..., description="Total number of folders")
    page: int = Field(..., description="Current page number")
    per_page: int = Field(..., description="Number of items per page")
    total_pages: int = Field(..., description="Total number of pages")

    @property
    def has_next(self) -> bool:
        """Check if there are more pages."""
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        """Check if there are previous pages."""
        return self.page > 1


class FolderTree(BaseModel):
    """Schema for folder tree structure."""

    folders: List[FolderWithChildren] = Field(
        ..., description="Root folders with nested children"
    )
    total_folders: int = Field(..., description="Total number of folders")


# Request/Response Models for API endpoints
class FolderCreateRequest(FolderCreate):
    """Request model for creating folder."""

    pass


class FolderUpdateRequest(FolderUpdate):
    """Request model for updating folder."""

    pass


class FolderMoveRequest(FolderMove):
    """Request model for moving folder."""

    pass


class FolderDeleteResponse(BaseModel):
    """Response model for folder deletion."""

    success: bool = Field(..., description="Whether deletion was successful")
    message: str = Field(..., description="Deletion status message")
    deleted_folders: int = Field(default=0, description="Number of folders deleted")
    deleted_documents: int = Field(default=0, description="Number of documents deleted")


class FolderFilters(BaseModel):
    """Filters for folder listing."""

    name: Optional[str] = Field(
        None, description="Filter by folder name (partial match)"
    )
    parent_folder_id: Optional[str] = Field(
        None, description="Filter by parent folder ID"
    )
    created_by: Optional[str] = Field(None, description="Filter by creator user ID")
    is_active: Optional[bool] = Field(None, description="Filter by active status")

    @field_validator("name")
    @classmethod
    def validate_filter_strings(cls, v: Optional[str]) -> Optional[str]:
        """Validate and clean filter strings."""
        if v is None:
            return v

        v = v.strip()
        if not v:
            return None

        # Prevent injection by allowing only alphanumeric, spaces, and basic punctuation
        if not re.match(r"^[a-zA-Z0-9\s\-_.]+$", v):
            raise ValueError("Invalid characters in filter")

        return v


# Document Schemas
class DocumentBase(BaseModel):
    """Base document schema with common fields."""

    filename: str = Field(
        ..., min_length=1, max_length=255, description="Document filename"
    )
    folder_id: Optional[str] = Field(
        None, description="Folder ID where document belongs"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Document metadata"
    )

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        """Validate filename."""
        if not v or not v.strip():
            raise ValueError("Filename cannot be empty")

        v = v.strip()

        # Check for dangerous characters
        dangerous_chars = [
            "/",
            "\\",
            ":",
            "*",
            "?",
            '"',
            "<",
            ">",
            "|",
            "\n",
            "\r",
            "\t",
        ]
        for char in dangerous_chars:
            if char in v:
                raise ValueError(f"Filename cannot contain '{char}'")

        return v

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Validate document metadata."""
        if not isinstance(v, dict):
            raise ValueError("Metadata must be a dictionary")

        # Ensure metadata doesn't contain sensitive keys
        sensitive_keys = ["password", "secret", "key", "token", "credential"]
        for key in v.keys():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                raise ValueError(f"Metadata cannot contain sensitive key: {key}")

        return v


class DocumentCreate(DocumentBase):
    """Schema for creating a new document (metadata only)."""

    pass


class DocumentUpload(BaseModel):
    """Schema for document file upload."""

    file: UploadFile = Field(..., description="File to upload")
    folder_id: Optional[str] = Field(None, description="Target folder ID")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Document metadata"
    )

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Validate document metadata."""
        return DocumentBase.validate_metadata(v)


class DocumentUpdate(BaseModel):
    """Schema for updating a document (metadata and status only)."""

    filename: Optional[str] = Field(
        None, min_length=1, max_length=255, description="New filename"
    )
    folder_id: Optional[str] = Field(None, description="New folder ID")
    status: Optional[DocumentStatus] = Field(
        None, description="Document processing status"
    )
    metadata: Optional[Dict[str, Any]] = Field(None, description="Updated metadata")

    # Apply same validators as base class
    _validate_filename = field_validator("filename")(
        DocumentBase.validate_filename.__func__
    )
    _validate_metadata = field_validator("metadata")(
        DocumentBase.validate_metadata.__func__
    )


class DocumentResponse(DocumentBase):
    """Document response schema for API responses."""

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
    )

    @field_serializer("created_at", "updated_at")
    def serialize_datetime(self, value: datetime) -> Optional[str]:
        """Serialize datetime fields to ISO format."""
        return value.isoformat() if value else None

    # Core document fields
    id: str = Field(..., description="Document unique identifier (UUID)")
    org_id: str = Field(..., description="Organization ID for multi-tenant isolation")
    original_filename: str = Field(
        ..., description="Original filename as uploaded by user"
    )
    file_type: FileType = Field(..., description="Document file type (pdf, xlsx)")
    file_size: int = Field(..., ge=0, description="File size in bytes (0 = unknown)")
    storage_path: str = Field(
        ..., description="GCS storage path (e.g. 'Org/original/folder/file.pdf')"
    )
    status: DocumentStatus = Field(
        ...,
        description="Processing status (uploading, uploaded, failed)",
    )

    # Metadata fields
    uploaded_by: str = Field(..., description="User ID who uploaded the document")
    is_active: bool = Field(
        ..., description="Whether document is active (false = soft deleted)"
    )
    created_at: datetime = Field(..., description="Upload timestamp (ISO 8601)")
    updated_at: datetime = Field(..., description="Last update timestamp (ISO 8601)")

    @field_validator("file_size")
    @classmethod
    def validate_file_size(cls, v: int) -> int:
        """Ensure file_size is never negative."""
        if v is None:
            return 0
        return max(0, v)

    @field_validator("file_type")
    @classmethod
    def validate_file_type(cls, v) -> FileType:
        """Ensure file_type is always a valid enum value."""
        if v is None:
            return FileType.PDF  # Default to PDF for unknown types

        # If it's already a FileType enum, return it
        if isinstance(v, FileType):
            return v

        # If it's a string, try to convert it to FileType
        if isinstance(v, str):
            try:
                return FileType(v.lower())
            except ValueError:
                # If conversion fails, default to PDF
                return FileType.PDF

        # For any other type, default to PDF
        return FileType.PDF

    @field_validator("original_filename")
    @classmethod
    def validate_original_filename(cls, v: str) -> str:
        """Ensure original_filename is never empty."""
        if not v or not v.strip():
            return "unknown_file"
        return v.strip()

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, v: datetime) -> datetime:
        """Ensure timestamps are valid."""
        if v is None:
            return datetime.now(timezone.utc)
        return v

    @property
    def display_size(self) -> str:
        """Get human-readable file size."""
        size = self.file_size
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    @property
    def has_failed(self) -> bool:
        """Check if document processing failed."""
        return self.status == DocumentStatus.FAILED


class DocumentList(BaseModel):
    """Schema for document list response with pagination."""

    documents: List[DocumentResponse] = Field(..., description="List of documents")
    total: int = Field(..., description="Total number of documents")
    page: int = Field(..., description="Current page number")
    per_page: int = Field(..., description="Number of items per page")
    total_pages: int = Field(..., description="Total number of pages")

    @property
    def has_next(self) -> bool:
        """Check if there are more pages."""
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        """Check if there are previous pages."""
        return self.page > 1


class DocumentFilters(BaseModel):
    """Filters for document listing."""

    filename: Optional[str] = Field(
        None, description="Filter by filename (partial match)"
    )
    file_type: Optional[FileType] = Field(None, description="Filter by file type")
    status: Optional[DocumentStatus] = Field(
        None, description="Filter by processing status"
    )
    folder_id: Optional[str] = Field(
        None, description="Filter by folder ID (legacy uploads)"
    )
    folder_path: Optional[str] = Field(
        None,
        description="Filter by folder path from storage_path (target_path uploads)",
    )
    uploaded_by: Optional[str] = Field(None, description="Filter by uploader user ID")

    @field_validator("filename", "folder_id")
    @classmethod
    def validate_filter_strings(cls, v: Optional[str]) -> Optional[str]:
        """Validate and clean filter strings."""
        if v is None:
            return v

        v = v.strip()
        if not v:
            return None

        # Prevent injection by allowing only alphanumeric, spaces, and basic punctuation
        if not re.match(r"^[a-zA-Z0-9\s\-_.]+$", v):
            raise ValueError("Invalid characters in filter")

        return v

    @field_validator("folder_path")
    @classmethod
    def validate_folder_path_string(cls, v: Optional[str]) -> Optional[str]:
        """Validate folder path - allow forward slashes for GCS paths."""
        if v is None:
            return v

        v = v.strip()
        if not v:
            return None

        # Allow forward slashes for GCS paths like "Tech Innovations Corp/original/control-docs"
        if not re.match(r"^[a-zA-Z0-9\s\-_./]+$", v):
            raise ValueError("Invalid characters in folder_path")

        return v


# Request/Response Models for API endpoints
class DocumentCreateRequest(DocumentCreate):
    """Request model for creating document metadata."""

    pass


class DocumentUpdateRequest(DocumentUpdate):
    """Request model for updating document."""

    pass


class DocumentDeleteResponse(BaseModel):
    """Response model for document deletion."""

    success: bool = Field(..., description="Whether deletion was successful")
    message: str = Field(..., description="Deletion status message")


class DocumentUploadResponse(BaseModel):
    """Response model for document upload."""

    success: bool = Field(..., description="Whether upload was successful")
    message: str = Field(..., description="Upload status message")
    document: Optional[DocumentResponse] = Field(
        None, description="Uploaded document details"
    )


class DocumentDownloadResponse(BaseModel):
    """Response model for document download."""

    download_url: str = Field(
        ..., description="Signed URL for downloading the document"
    )
    expires_at: datetime = Field(..., description="When the download URL expires")
    filename: str = Field(..., description="Filename for download")


class DocumentStatusUpdate(BaseModel):
    """Schema for updating document status."""

    status: DocumentStatus = Field(..., description="New processing status")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Validate metadata if provided."""
        if v is None:
            return v
        return DocumentBase.validate_metadata(v)


class DocumentSyncValidationResponse(BaseModel):
    """Response model for document sync validation."""

    org_id: str = Field(..., description="Organization ID")
    folder_id: Optional[str] = Field(None, description="Folder ID (if filtered)")
    sync_status: str = Field(
        ..., description="Overall sync status: 'healthy', 'issues', 'error'"
    )
    summary: Dict[str, int] = Field(..., description="Summary counts")
    issues: List[Dict[str, Any]] = Field(
        default_factory=list, description="List of sync issues found"
    )
    recommendations: List[str] = Field(
        default_factory=list, description="Recommended actions"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When validation was performed"
    )


# Database-specific Document Schemas
class DocumentSearchCriteria(BaseModel):
    """Search criteria used for document query."""

    filename: str = Field(..., description="Filename searched for")
    exact_match: bool = Field(..., description="Whether exact match was used")
    include_inactive: bool = Field(
        ..., description="Whether inactive documents were included"
    )


class DocumentDatabaseMetadata(BaseModel):
    """Database-specific metadata for document operations."""

    document_ref: str = Field(..., description="Document reference path")
    query_method: str = Field(
        ..., description="Query method used (e.g., 'filename_exact_match')"
    )
    last_updated: datetime = Field(
        ..., description="When document was last updated in database"
    )

    @field_serializer("last_updated")
    def serialize_datetime(self, value: datetime) -> Optional[str]:
        """Serialize datetime fields to ISO format."""
        return value.isoformat() if value else None


class DocumentRelationshipOrganization(BaseModel):
    """Organization relationship information."""

    id: str = Field(..., description="Organization ID")
    name: str = Field(..., description="Organization name")


class DocumentRelationshipFolder(BaseModel):
    """Folder relationship information."""

    id: Optional[str] = Field(None, description="Folder ID")
    name: Optional[str] = Field(None, description="Folder name")
    path: Optional[str] = Field(None, description="Folder path")


class DocumentRelationshipUploader(BaseModel):
    """Uploader relationship information."""

    id: str = Field(..., description="User ID")
    email: str = Field(..., description="User email")
    full_name: str = Field(..., description="User full name")


class DocumentRelationships(BaseModel):
    """Related entity information for a document."""

    organization: DocumentRelationshipOrganization = Field(
        ..., description="Organization information"
    )
    folder: Optional[DocumentRelationshipFolder] = Field(
        None, description="Folder information"
    )
    uploader: DocumentRelationshipUploader = Field(
        ..., description="Uploader information"
    )


class DocumentDatabaseResponse(BaseModel):
    """Enhanced response model for database-based document operations."""

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
    )

    source: str = Field(default="postgresql", description="Data source identifier")
    search_criteria: DocumentSearchCriteria = Field(
        ..., description="Search criteria used"
    )
    document: DocumentResponse = Field(..., description="Document information")
    database_metadata: DocumentDatabaseMetadata = Field(
        ..., description="Database-specific metadata"
    )
    relationships: DocumentRelationships = Field(
        ..., description="Related entity information"
    )


# Folder-based Document Listing Schemas
class DocumentFolderSearchCriteria(BaseModel):
    """Search criteria used for folder-based document query."""

    folder_name: str = Field(..., description="Folder name searched for")
    exact_match: bool = Field(
        ..., description="Whether exact folder name match was used"
    )
    include_inactive: bool = Field(
        ..., description="Whether inactive documents were included"
    )
    additional_filters: Dict[str, Any] = Field(
        default_factory=dict, description="Additional filters applied"
    )


class DocumentFolderInfo(BaseModel):
    """Folder information for document listing."""

    id: str = Field(..., description="Folder ID")
    name: str = Field(..., description="Folder name")
    path: str = Field(..., description="Folder path")
    parent_folder_id: Optional[str] = Field(None, description="Parent folder ID")
    created_by: str = Field(..., description="User who created the folder")
    created_at: datetime = Field(..., description="When folder was created")
    document_count: int = Field(..., description="Total number of documents in folder")

    @field_serializer("created_at")
    def serialize_datetime(self, value: datetime) -> Optional[str]:
        """Serialize datetime fields to ISO format."""
        return value.isoformat() if value else None


class DocumentDatabaseFolderListResponse(BaseModel):
    """Enhanced response for folder-based document listing from database."""

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
    )

    source: str = Field(default="postgresql", description="Data source identifier")
    folder_info: DocumentFolderInfo = Field(..., description="Folder information")
    search_criteria: DocumentFolderSearchCriteria = Field(
        ..., description="Search criteria used"
    )
    documents: List[DocumentResponse] = Field(
        ..., description="List of documents in folder"
    )
    total: int = Field(..., description="Total number of documents in folder")
    page: int = Field(..., description="Current page number")
    per_page: int = Field(..., description="Number of items per page")
    total_pages: int = Field(..., description="Total number of pages")
    database_metadata: DocumentDatabaseMetadata = Field(
        ..., description="Database query metadata"
    )

    @property
    def has_next(self) -> bool:
        """Check if there are more pages."""
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        """Check if there are previous pages."""
        return self.page > 1


# Export commonly used schemas
__all__ = [
    # Organization schemas
    "PlanType",
    "OrganizationBase",
    "OrganizationCreate",
    "OrganizationUpdate",
    "OrganizationResponse",
    "OrganizationList",
    "OrganizationCreateRequest",
    "OrganizationUpdateRequest",
    "OrganizationDeleteResponse",
    "PaginationParams",
    "OrganizationFilters",
    # User schemas
    "UserRole",
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
    "DocumentStatus",
    "FileType",
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
    "DocumentSyncValidationResponse",
    # Database-specific document schemas
    "DocumentSearchCriteria",
    "DocumentDatabaseMetadata",
    "DocumentRelationshipOrganization",
    "DocumentRelationshipFolder",
    "DocumentRelationshipUploader",
    "DocumentRelationships",
    "DocumentDatabaseResponse",
    # Folder-based document listing schemas
    "DocumentFolderSearchCriteria",
    "DocumentFolderInfo",
    "DocumentDatabaseFolderListResponse",
]
