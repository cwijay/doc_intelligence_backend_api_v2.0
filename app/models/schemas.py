import re
from datetime import datetime
from typing import Dict, Any, Optional, List

from pydantic import BaseModel, Field, field_validator, ConfigDict
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
        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
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
    """
    Document response schema with AI content fields.

    🔥 ENHANCED WITH AI CONTENT:
    This response now includes AI-generated content fields for intelligent document analysis:
    - summary: AI-generated document summary
    - faq: Question/answer pairs extracted from content
    - questions: Important questions identified in the document

    📘 CLIENT INTEGRATION GUIDE:

    For Next.js/TypeScript developers:
    1. All AI fields are optional - existing code continues working unchanged
    2. Check `summary`, `faq.length`, `questions.length` for content availability
    3. Use TypeScript: DocumentResponse interface provides full type safety
    4. FAQ structure: Array of {question: string, answer: string} objects

    Example TypeScript usage:
    ```typescript
    interface FAQ {
      question: string;
      answer: string;
    }

    const hasAIContent = (doc: DocumentResponse): boolean => {
      return !!(doc.summary || doc.faq.length > 0 || doc.questions.length > 0);
    }

    // Safe access to AI content
    const summary = document.summary || 'No summary available';
    const faqItems = document.faq || [];
    const questionList = document.questions || [];
    ```

    🔄 MIGRATION NOTES:
    - All AI fields are optional with sensible defaults
    - Existing document fields remain unchanged
    - Backward compatibility: 100% maintained
    - New fields return empty arrays/null when no content exists
    """

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
        json_encoders={datetime: lambda dt: dt.isoformat() if dt else None},
    )

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
        description="Processing status (uploading, uploaded, parsing, parsed, failed)",
    )

    # Processing and content fields
    parsed_storage_path: Optional[str] = Field(
        None, description="GCS path to parsed markdown content"
    )
    parsing_metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Metadata from document parsing engine"
    )
    file_content: Optional[str] = Field(
        None, description="Parsed document content in markdown format"
    )

    # 🤖 AI-GENERATED CONTENT FIELDS (NEW)
    summary: Optional[str] = Field(
        None,
        description="AI-generated document summary. Use for previews, search, and quick insights.",
    )
    faq: List[Dict[str, str]] = Field(
        default_factory=list,
        description="AI-generated FAQ items. Each item has 'question' and 'answer' keys. Perfect for chatbots and help sections.",
    )
    questions: List[str] = Field(
        default_factory=list,
        description="AI-generated list of important questions from document. Use for search enhancement and content discovery.",
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
            return datetime.utcnow()
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
    def is_ready(self) -> bool:
        """Check if document is ready for use."""
        return self.status == DocumentStatus.PARSED

    @property
    def is_processing(self) -> bool:
        """Check if document is being processed."""
        return self.status == DocumentStatus.PARSING

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


# Firestore-specific Document Schemas
class DocumentSearchCriteria(BaseModel):
    """Search criteria used for Firestore document query."""

    filename: str = Field(..., description="Filename searched for")
    exact_match: bool = Field(..., description="Whether exact match was used")
    include_inactive: bool = Field(
        ..., description="Whether inactive documents were included"
    )


class DocumentFirestoreMetadata(BaseModel):
    """Firestore-specific metadata for document operations."""

    document_ref: str = Field(..., description="Firestore document reference path")
    query_method: str = Field(
        ..., description="Query method used (e.g., 'filename_exact_match')"
    )
    last_updated: datetime = Field(
        ..., description="When document was last updated in Firestore"
    )


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


class DocumentFirestoreResponse(BaseModel):
    """Enhanced response model for Firestore-based document operations."""

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
        json_encoders={datetime: lambda dt: dt.isoformat() if dt else None},
    )

    source: str = Field(default="firestore", description="Data source identifier")
    search_criteria: DocumentSearchCriteria = Field(
        ..., description="Search criteria used"
    )
    document: DocumentResponse = Field(..., description="Document information")
    firestore_metadata: DocumentFirestoreMetadata = Field(
        ..., description="Firestore-specific metadata"
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


class DocumentFirestoreFolderListResponse(BaseModel):
    """Enhanced response for folder-based document listing from Firestore."""

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
        json_encoders={datetime: lambda dt: dt.isoformat() if dt else None},
    )

    source: str = Field(default="firestore", description="Data source identifier")
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
    firestore_metadata: DocumentFirestoreMetadata = Field(
        ..., description="Firestore query metadata"
    )

    @property
    def has_next(self) -> bool:
        """Check if there are more pages."""
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        """Check if there are previous pages."""
        return self.page > 1


# Document Parsing Schemas
class DocumentParseRequest(BaseModel):
    """Request model for parsing a document from GCS storage."""

    storage_path: str = Field(
        ...,
        min_length=1,
        description="GCS storage path of the document to parse (e.g., 'Google/original/invoices/file.pdf')",
    )

    @field_validator("storage_path")
    @classmethod
    def validate_storage_path(cls, v: str) -> str:
        """Validate storage path format."""
        if not v or not v.strip():
            raise ValueError("Storage path cannot be empty")

        v = v.strip()

        # Basic validation - should have at least org/type/folder/file structure
        path_parts = v.split("/")
        if len(path_parts) < 3:
            raise ValueError(
                "Storage path must have at least 3 parts: org/type/folder or org/type/file"
            )

        # Check for unsafe characters
        if ".." in v or v.startswith("/") or v.endswith("/"):
            raise ValueError("Storage path contains unsafe characters")

        return v


class DocumentParseFileInfo(BaseModel):
    """File information for parsed document."""

    original_size: Optional[int] = Field(
        None, description="Original file size in bytes"
    )
    parsed_size: int = Field(..., description="Parsed content size in bytes")
    file_type: str = Field(..., description="File extension (e.g., '.pdf', '.xlsx')")
    content_type: Optional[str] = Field(None, description="MIME content type")


class DocumentParseResponse(BaseModel):
    """Response model for document parsing operation."""

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda dt: dt.isoformat() if dt else None},
    )

    success: bool = Field(..., description="Whether parsing was successful")
    storage_path: str = Field(..., description="Original GCS storage path")
    parsed_storage_path: str = Field(
        ..., description="GCS path where parsed content is stored"
    )
    parsed_content: str = Field(
        ..., description="Parsed document content in markdown format"
    )
    parsing_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata from parsing process (pages, headers, etc.)",
    )
    gcs_metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Original file metadata from GCS"
    )
    file_info: DocumentParseFileInfo = Field(
        ..., description="File size and type information"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When parsing was completed"
    )


class DocumentParseStatus(BaseModel):
    """Status model for document parsing operation."""

    storage_path: str = Field(..., description="GCS storage path")
    status: str = Field(
        ..., description="Parsing status (pending, processing, completed, failed)"
    )
    message: Optional[str] = Field(None, description="Status message or error details")
    progress: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Parsing progress (0.0 to 1.0)"
    )
    started_at: Optional[datetime] = Field(None, description="When parsing started")
    completed_at: Optional[datetime] = Field(None, description="When parsing completed")
    error_details: Optional[Dict[str, Any]] = Field(
        None, description="Detailed error information if failed"
    )


class ExistingDocumentParseResponse(BaseModel):
    """Response model for retrieving existing parsed document."""

    exists: bool = Field(..., description="Whether parsed version exists")
    storage_path: str = Field(..., description="Original GCS storage path")
    parsed_storage_path: str = Field(
        ..., description="GCS path where parsed content is stored"
    )
    parsed_content: Optional[str] = Field(
        None, description="Parsed document content (if exists)"
    )
    parsed_metadata: Optional[Dict[str, Any]] = Field(
        None, description="Metadata of parsed file"
    )
    message: Optional[str] = Field(None, description="Status message")


class SaveParsedDocumentRequest(BaseModel):
    """Request model for saving parsed document content directly to GCS."""

    target_path: str = Field(
        ...,
        min_length=1,
        description="Target organization folder path (e.g., 'Tech Innovations Corp/parsed/control-docs')",
    )
    content: str = Field(
        ..., min_length=1, description="Parsed document content in markdown format"
    )
    original_filename: str = Field(
        ...,
        min_length=1,
        description="Original document filename (will be converted to .md)",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Additional metadata for the parsed document"
    )

    @field_validator("target_path")
    @classmethod
    def validate_target_path(cls, v: str) -> str:
        """Validate target path format."""
        if not v or not v.strip():
            raise ValueError("Target path cannot be empty")

        v = v.strip()

        # Remove leading/trailing slashes
        v = v.strip("/")

        # Check path has at least org/parsed/folder format
        parts = v.split("/")
        if len(parts) < 3:
            raise ValueError(
                "Target path must have format: 'organization/parsed/folder'"
            )

        if parts[1] != "parsed":
            raise ValueError("Target path must include 'parsed' as second component")

        return v

    @field_validator("original_filename")
    @classmethod
    def validate_original_filename(cls, v: str) -> str:
        """Validate original filename."""
        if not v or not v.strip():
            raise ValueError("Original filename cannot be empty")

        v = v.strip()

        # Remove any path components, just keep filename
        v = v.split("/")[-1]

        if not v:
            raise ValueError("Invalid filename")

        return v


class DocumentIndexingInfo(BaseModel):
    """Information about document indexing status."""

    model_config = ConfigDict(from_attributes=True)

    enabled: bool = Field(..., description="Whether indexing was enabled")
    pinecone_indexed: bool = Field(
        ..., description="Whether document was indexed in Pinecone"
    )
    bm25_indexed: bool = Field(..., description="Whether document was indexed in BM25")
    embedding_dimension: Optional[int] = Field(
        None, description="Dimension of generated embedding"
    )
    token_count: Optional[int] = Field(
        None, description="Number of tokens for BM25 indexing"
    )
    indexed_at: Optional[str] = Field(None, description="ISO timestamp of indexing")
    error: Optional[str] = Field(None, description="Indexing error message if any")


class SaveParsedDocumentResponse(BaseModel):
    """Response model for saving parsed document content with indexing."""

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda dt: dt.isoformat() if dt else None},
    )

    success: bool = Field(..., description="Whether save operation was successful")
    gcs_path: str = Field(
        ..., description="Full GCS storage path where content was saved"
    )
    gcs_url: str = Field(..., description="Full GCS URL for accessing the file")
    target_path: str = Field(..., description="Original target path provided")
    final_filename: str = Field(..., description="Final filename used (.md extension)")
    file_size: int = Field(..., description="Size of saved content in bytes")
    overwritten: bool = Field(
        ..., description="Whether an existing file was overwritten"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When the file was saved"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )
    indexing: DocumentIndexingInfo = Field(
        ..., description="Document indexing information"
    )


class DocumentContentUpdateRequest(BaseModel):
    """Request model for updating document content."""

    content: str = Field(
        ..., min_length=0, description="Updated document content (markdown format)"
    )
    sync_to_gcs: bool = Field(
        default=True, description="Whether to sync the content to GCS storage"
    )

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Validate content size and format."""
        # Check content size limits (1MB for Firestore efficiency)
        max_content_size = 1024 * 1024  # 1MB
        if len(v.encode("utf-8")) > max_content_size:
            raise ValueError(
                f"Content exceeds maximum size of {max_content_size // 1024}KB"
            )
        return v


class DocumentContentUpdateResponse(BaseModel):
    """Response model for document content update."""

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda dt: dt.isoformat() if dt else None},
    )

    success: bool = Field(..., description="Whether update was successful")
    document_id: str = Field(..., description="Document ID that was updated")
    content_size: int = Field(..., description="Size of updated content in bytes")
    firestore_updated: bool = Field(..., description="Whether Firestore was updated")
    gcs_updated: bool = Field(..., description="Whether GCS was updated")
    gcs_path: Optional[str] = Field(
        None, description="GCS path where content was saved"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When the update occurred"
    )


class DocumentContentResponse(BaseModel):
    """Response model for retrieving document content."""

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda dt: dt.isoformat() if dt else None},
    )

    document_id: str = Field(..., description="Document ID")
    content: Optional[str] = Field(None, description="Document content")
    content_size: int = Field(..., description="Content size in bytes")
    source: str = Field(..., description="Content source (firestore/gcs/none)")
    last_modified: datetime = Field(..., description="When content was last modified")
    has_content: bool = Field(..., description="Whether document has content")


# Document Summarization Schemas
class DocumentSummarizeRequest(BaseModel):
    """Request model for document summarization."""

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    prompt: Optional[str] = Field(
        None,
        max_length=2000,
        description="Optional custom prompt for summarization. If not provided, uses default comprehensive summarization.",
    )

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, v: Optional[str]) -> Optional[str]:
        """Validate custom prompt."""
        if v is None:
            return v

        v = v.strip()
        if not v:
            return None

        return v


class DocumentSummaryMetadata(BaseModel):
    """Metadata for document summary."""

    model_config = ConfigDict(from_attributes=True)

    generated_at: str = Field(
        ..., description="When summary was generated (ISO format)"
    )
    model: str = Field(
        default="gpt-4o-mini", description="AI model used for summarization"
    )
    content_length: int = Field(
        ..., description="Original content length in characters"
    )
    summary_length: int = Field(..., description="Summary length in characters")
    has_custom_prompt: bool = Field(
        default=False, description="Whether custom prompt was used"
    )
    update_type: Optional[str] = Field(
        None, description="Type of update (generated, direct_update, regenerated)"
    )


class DocumentSummarizeResponse(BaseModel):
    """
    Response model for document summarization.

    This response uses a Firestore-first approach:
    - Summary is stored directly in Firestore ai_summary field
    - No GCS file storage required
    - Immediate access to generated content
    """

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda dt: dt.isoformat() if dt else None},
    )

    success: bool = Field(..., description="Whether summarization was successful")
    document_id: str = Field(..., description="Document ID that was summarized")
    filename: str = Field(..., description="Original document filename")
    ai_summary: str = Field(..., description="Generated AI summary in markdown format")
    summary_metadata: Dict[str, Any] = Field(
        ..., description="Summary generation metadata"
    )
    timestamp: str = Field(
        ..., description="Response generation timestamp (ISO format)"
    )


class DocumentSummaryUpdateRequest(BaseModel):
    """Request model for updating document summary."""

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    summary: Optional[str] = Field(None, description="Direct summary content to set")
    prompt: Optional[str] = Field(
        None, description="Custom prompt to regenerate summary"
    )

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, v: Optional[str]) -> Optional[str]:
        """Validate summary content."""
        if v is None:
            return v

        v = v.strip()
        if not v:
            return None

        return v

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, v: Optional[str]) -> Optional[str]:
        """Validate custom prompt."""
        if v is None:
            return v

        v = v.strip()
        if not v:
            return None

        return v


class DocumentAIContentRequest(BaseModel):
    """Request model for updating AI-generated content."""

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    summary: Optional[str] = Field(None, description="AI-generated document summary")
    faq: Optional[List[Dict[str, str]]] = Field(
        None, description="AI-generated FAQ items"
    )
    questions: Optional[List[str]] = Field(None, description="AI-generated questions")

    @field_validator("faq")
    @classmethod
    def validate_faq_structure(
        cls, v: Optional[List[Dict[str, str]]]
    ) -> Optional[List[Dict[str, str]]]:
        """Validate FAQ structure."""
        if v is None:
            return v

        for i, item in enumerate(v):
            if not isinstance(item, dict):
                raise ValueError(f"FAQ item {i} must be a dictionary")

            if "question" not in item or "answer" not in item:
                raise ValueError(
                    f"FAQ item {i} must contain 'question' and 'answer' keys"
                )

            if not isinstance(item["question"], str) or not isinstance(
                item["answer"], str
            ):
                raise ValueError(f"FAQ item {i} question and answer must be strings")

            if not item["question"].strip() or not item["answer"].strip():
                raise ValueError(f"FAQ item {i} question and answer cannot be empty")

        return v


class DocumentAIContentResponse(BaseModel):
    """Response model for AI-generated content."""

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda dt: dt.isoformat() if dt else None},
    )

    document_id: str = Field(..., description="Document ID")
    filename: str = Field(..., description="Document filename")
    summary: Optional[str] = Field(None, description="AI-generated document summary")
    faq: List[Dict[str, str]] = Field(
        default_factory=list, description="AI-generated FAQ items"
    )
    questions: List[str] = Field(
        default_factory=list, description="AI-generated questions"
    )
    has_ai_content: bool = Field(..., description="Whether document has any AI content")
    ai_content_size: int = Field(..., description="Total size of AI content in bytes")
    updated_at: datetime = Field(..., description="When AI content was last updated")


class DocumentSummaryResponse(BaseModel):
    """Response model for document summary retrieval requests."""

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda dt: dt.isoformat() if dt else None},
    )

    document_id: str = Field(..., description="Document unique identifier")
    filename: str = Field(..., description="Document filename")
    ai_summary: Optional[str] = Field(None, description="AI-generated document summary")
    summary_metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Summary generation metadata"
    )
    has_summary: bool = Field(
        ..., description="Whether document has a summary available"
    )
    summary_preview: str = Field(
        default="", description="Preview of summary (first 150 characters)"
    )
    updated_at: Optional[str] = Field(
        None, description="When summary was last updated (ISO format)"
    )


# FAQ Generation Schemas
class DocumentFAQRequest(BaseModel):
    """Request model for document FAQ generation."""

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    prompt: Optional[str] = Field(None, description="Custom prompt for FAQ generation")
    faq_count: int = Field(
        default=5, ge=1, le=10, description="Number of FAQs to generate (1-10)"
    )

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, v: Optional[str]) -> Optional[str]:
        """Validate custom prompt."""
        if v is None:
            return v

        v = v.strip()
        if not v:
            return None

        return v

    @field_validator("faq_count")
    @classmethod
    def validate_faq_count(cls, v: int) -> int:
        """Validate FAQ count."""
        if v < 1 or v > 10:
            raise ValueError("FAQ count must be between 1 and 10")
        return v


class DocumentFAQResponse(BaseModel):
    """Response model for document FAQ generation."""

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda dt: dt.isoformat() if dt else None},
    )

    success: bool = Field(..., description="Whether FAQ generation was successful")
    document_id: str = Field(
        ..., description="Document ID that FAQs were generated for"
    )
    filename: str = Field(..., description="Original document filename")
    ai_faq: List[Dict[str, str]] = Field(..., description="Generated AI FAQ items")
    faq_metadata: Dict[str, Any] = Field(..., description="FAQ generation metadata")
    timestamp: str = Field(
        ..., description="Response generation timestamp (ISO format)"
    )


class DocumentFAQUpdateRequest(BaseModel):
    """Request model for updating document FAQ."""

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    faq: Optional[List[Dict[str, str]]] = Field(
        None, description="Direct FAQ content to set"
    )
    prompt: Optional[str] = Field(None, description="Custom prompt to regenerate FAQ")
    faq_count: Optional[int] = Field(
        None,
        ge=1,
        le=10,
        description="Number of FAQs to generate when using prompt (1-10)",
    )

    @field_validator("faq")
    @classmethod
    def validate_faq_structure(
        cls, v: Optional[List[Dict[str, str]]]
    ) -> Optional[List[Dict[str, str]]]:
        """Validate FAQ structure."""
        if v is None:
            return v

        for i, item in enumerate(v):
            if not isinstance(item, dict):
                raise ValueError(f"FAQ item {i} must be a dictionary")

            if "question" not in item or "answer" not in item:
                raise ValueError(
                    f"FAQ item {i} must contain 'question' and 'answer' keys"
                )

            if not isinstance(item["question"], str) or not isinstance(
                item["answer"], str
            ):
                raise ValueError(f"FAQ item {i} question and answer must be strings")

            if not item["question"].strip() or not item["answer"].strip():
                raise ValueError(f"FAQ item {i} question and answer cannot be empty")

        return v

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, v: Optional[str]) -> Optional[str]:
        """Validate custom prompt."""
        if v is None:
            return v

        v = v.strip()
        if not v:
            return None

        return v

    @field_validator("faq_count")
    @classmethod
    def validate_faq_count(cls, v: Optional[int]) -> Optional[int]:
        """Validate FAQ count."""
        if v is None:
            return v
        if v < 1 or v > 10:
            raise ValueError("FAQ count must be between 1 and 10")
        return v


class DocumentFAQRetrievalResponse(BaseModel):
    """Response model for document FAQ retrieval requests."""

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda dt: dt.isoformat() if dt else None},
    )

    document_id: str = Field(..., description="Document unique identifier")
    filename: str = Field(..., description="Document filename")
    ai_faq: Optional[List[Dict[str, str]]] = Field(
        None, description="AI-generated FAQ items"
    )
    faq_metadata: Dict[str, Any] = Field(
        default_factory=dict, description="FAQ generation metadata"
    )
    has_faq: bool = Field(..., description="Whether document has FAQ available")
    faq_count: int = Field(default=0, description="Number of FAQ items")
    faq_preview: str = Field(
        default="", description="Preview of FAQ (first question and answer)"
    )
    updated_at: Optional[str] = Field(
        None, description="When FAQ was last updated (ISO format)"
    )


# ============================================================================
# Document AI Questions Schemas
# ============================================================================


class DocumentQuestionsRequest(BaseModel):
    """Request model for document questions generation."""

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    prompt: Optional[str] = Field(
        None, description="Custom prompt for questions generation"
    )
    question_count: int = Field(
        default=5, ge=1, le=20, description="Number of questions to generate (1-20)"
    )

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, v: Optional[str]) -> Optional[str]:
        """Validate custom prompt."""
        if v is None:
            return v

        v = v.strip()
        if not v:
            return None

        if len(v) > 1000:
            raise ValueError("Custom prompt cannot exceed 1000 characters")

        return v


class DocumentQuestionsResponse(BaseModel):
    """Response model for document questions generation."""

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda dt: dt.isoformat() if dt else None},
    )

    success: bool = Field(
        ..., description="Whether questions generation was successful"
    )
    document_id: str = Field(
        ..., description="Document ID that questions were generated for"
    )
    filename: str = Field(..., description="Original document filename")
    ai_questions: List[str] = Field(..., description="Generated AI questions")
    questions_metadata: Dict[str, Any] = Field(
        ..., description="Questions generation metadata"
    )
    timestamp: str = Field(
        ..., description="Response generation timestamp (ISO format)"
    )
    source: Optional[str] = Field(
        None, description="Source of questions - 'existing' or 'generated'"
    )
    update_type: Optional[str] = Field(
        None, description="Type of update performed - 'direct_update' or 'regenerated'"
    )


class DocumentQuestionsUpdateRequest(BaseModel):
    """Request model for updating document questions."""

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    questions: Optional[List[str]] = Field(
        None, description="Direct questions content to set"
    )
    prompt: Optional[str] = Field(
        None, description="Custom prompt to regenerate questions"
    )
    question_count: Optional[int] = Field(
        None,
        ge=1,
        le=20,
        description="Number of questions to generate when using prompt (1-20)",
    )

    @field_validator("questions")
    @classmethod
    def validate_questions_structure(
        cls, v: Optional[List[str]]
    ) -> Optional[List[str]]:
        """Validate questions structure."""
        if v is None:
            return v

        for i, question in enumerate(v):
            if not isinstance(question, str):
                raise ValueError(f"Question {i} must be a string")

            if not question.strip():
                raise ValueError(f"Question {i} cannot be empty")

            if len(question) > 500:
                raise ValueError(f"Question {i} cannot exceed 500 characters")

        if len(v) > 20:
            raise ValueError("Cannot have more than 20 questions")

        return v

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, v: Optional[str]) -> Optional[str]:
        """Validate custom prompt."""
        if v is None:
            return v

        v = v.strip()
        if not v:
            return None

        if len(v) > 1000:
            raise ValueError("Custom prompt cannot exceed 1000 characters")

        return v


class DocumentQuestionsRetrievalResponse(BaseModel):
    """Response model for document questions retrieval requests."""

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: lambda dt: dt.isoformat() if dt else None},
    )

    document_id: str = Field(..., description="Document unique identifier")
    filename: str = Field(..., description="Document filename")
    ai_questions: Optional[List[str]] = Field(
        None, description="AI-generated questions"
    )
    questions_metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Questions generation metadata"
    )
    has_questions: bool = Field(
        ..., description="Whether document has questions available"
    )
    questions_count: int = Field(default=0, description="Number of questions")
    questions_preview: str = Field(
        default="", description="Preview of questions (first 3 questions)"
    )
    updated_at: Optional[str] = Field(
        None, description="When questions were last updated (ISO format)"
    )


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
    # Firestore-specific document schemas
    "DocumentSearchCriteria",
    "DocumentFirestoreMetadata",
    "DocumentRelationshipOrganization",
    "DocumentRelationshipFolder",
    "DocumentRelationshipUploader",
    "DocumentRelationships",
    "DocumentFirestoreResponse",
    # Folder-based document listing schemas
    "DocumentFolderSearchCriteria",
    "DocumentFolderInfo",
    "DocumentFirestoreFolderListResponse",
    # Document parsing schemas
    "DocumentParseRequest",
    "DocumentParseFileInfo",
    "DocumentParseResponse",
    "DocumentParseStatus",
    "ExistingDocumentParseResponse",
    "SaveParsedDocumentRequest",
    "DocumentIndexingInfo",
    "SaveParsedDocumentResponse",
    "DocumentContentUpdateRequest",
    "DocumentContentUpdateResponse",
    "DocumentContentResponse",
    # Document summarization schemas
    "DocumentSummarizeRequest",
    "DocumentSummaryMetadata",
    "DocumentSummarizeResponse",
    "DocumentSummaryUpdateRequest",
    "DocumentSummaryResponse",
    # FAQ schemas
    "DocumentFAQRequest",
    "DocumentFAQResponse",
    "DocumentFAQUpdateRequest",
    "DocumentFAQRetrievalResponse",
    # Questions schemas
    "DocumentQuestionsRequest",
    "DocumentQuestionsResponse",
    "DocumentQuestionsUpdateRequest",
    "DocumentQuestionsRetrievalResponse",
]
