"""Document schemas for API requests and responses."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator
from fastapi import UploadFile

from app.models.document import DocumentStatus, FileType
from app.models.schemas.validators import validate_filter_strings, validate_metadata


class DocumentBase(BaseModel):
    """Base document schema with common fields."""

    filename: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Document filename",
        example="invoice-2025-001.pdf",
    )
    folder_id: Optional[str] = Field(
        None,
        description="Folder ID where document belongs",
        example="folder_abc123",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Document metadata",
        example={"category": "invoice", "vendor": "Acme Corp", "amount": 1500.00},
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
    def validate_metadata_field(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Validate document metadata."""
        return validate_metadata(v)


class DocumentCreate(DocumentBase):
    """Schema for creating a new document (metadata only)."""

    pass


class DocumentUpload(BaseModel):
    """Schema for document file upload."""

    file: UploadFile = Field(
        ...,
        description="File to upload (PDF, XLSX, DOCX, etc.)",
    )
    folder_id: Optional[str] = Field(
        None,
        description="Target folder ID",
        example="folder_abc123",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Document metadata",
        example={"category": "invoice", "vendor": "Acme Corp"},
    )

    @field_validator("metadata")
    @classmethod
    def validate_metadata_field(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Validate document metadata."""
        return validate_metadata(v)


class DocumentUpdate(BaseModel):
    """Schema for updating a document (metadata and status only)."""

    filename: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="New filename",
        example="invoice-2025-001-updated.pdf",
    )
    folder_id: Optional[str] = Field(
        None,
        description="New folder ID",
        example="folder_newlocation456",
    )
    status: Optional[DocumentStatus] = Field(
        None,
        description="Document processing status",
        example="uploaded",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Updated metadata",
        example={"category": "invoice", "status": "paid", "paid_date": "2025-01-20"},
    )

    # Apply same validators as base class
    _validate_filename = field_validator("filename")(
        DocumentBase.validate_filename.__func__
    )
    _validate_metadata = field_validator("metadata")(
        DocumentBase.validate_metadata_field.__func__
    )


class DocumentResponse(DocumentBase):
    """Document response schema for API responses."""

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
    )

    @field_serializer("created_at", "updated_at", "parsed_at")
    def serialize_datetime(self, value: datetime) -> Optional[str]:
        """Serialize datetime fields to ISO format."""
        return value.isoformat() if value else None

    # Core document fields
    id: str = Field(
        ...,
        description="Document unique identifier (UUID)",
        example="doc_78258b82-db53-41a3-848a-ce45a32f99c7",
    )
    org_id: str = Field(
        ...,
        description="Organization ID for multi-tenant isolation",
        example="org_xyz789abc",
    )
    original_filename: str = Field(
        ...,
        description="Original filename as uploaded by user",
        example="invoice-2025-001.pdf",
    )
    file_type: FileType = Field(
        ...,
        description="Document file type (pdf, xlsx, docx, etc.)",
        example="pdf",
    )
    file_size: int = Field(
        ...,
        ge=0,
        description="File size in bytes (0 = unknown)",
        example=1048576,
    )
    storage_path: str = Field(
        ...,
        description="GCS storage path (e.g. 'Org/original/folder/file.pdf')",
        example="Acme-Corp/original/invoices/invoice-2025-001.pdf",
    )
    status: DocumentStatus = Field(
        ...,
        description="Processing status (uploading, uploaded, failed)",
        example="uploaded",
    )

    # Metadata fields
    uploaded_by: str = Field(
        ...,
        description="User ID who uploaded the document",
        example="user_abc123xyz",
    )
    is_active: bool = Field(
        ...,
        description="Whether document is active (false = soft deleted)",
        example=True,
    )
    created_at: datetime = Field(
        ...,
        description="Upload timestamp (ISO 8601)",
        example="2025-01-15T10:30:00Z",
    )
    updated_at: datetime = Field(
        ...,
        description="Last update timestamp (ISO 8601)",
        example="2025-01-15T14:45:00Z",
    )

    # Content hash and parsing fields
    file_hash: Optional[str] = Field(
        None,
        description="SHA-256 hash of file content (for deduplication)",
        example="a1b2c3d4e5f6789...",
    )
    parsed_path: Optional[str] = Field(
        None,
        description="GCS path to parsed markdown version",
        example="Acme-Corp/parsed/invoices/invoice-2025-001.md",
    )
    parsed_at: Optional[datetime] = Field(
        None,
        description="When document was parsed to markdown",
        example="2025-01-15T12:00:00Z",
    )

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

    @property
    def is_parsed(self) -> bool:
        """Check if document has been parsed to markdown."""
        return self.parsed_path is not None and self.parsed_at is not None


class DocumentList(BaseModel):
    """Schema for document list response with pagination."""

    documents: List[DocumentResponse] = Field(
        ...,
        description="List of documents",
    )
    total: int = Field(
        ...,
        description="Total number of documents",
        example=150,
    )
    page: int = Field(
        ...,
        description="Current page number",
        example=1,
    )
    per_page: int = Field(
        ...,
        description="Number of items per page",
        example=20,
    )
    total_pages: int = Field(
        ...,
        description="Total number of pages",
        example=8,
    )

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
        None,
        description="Filter by filename (partial match)",
        example="invoice",
    )
    file_type: Optional[FileType] = Field(
        None,
        description="Filter by file type",
        example="pdf",
    )
    status: Optional[DocumentStatus] = Field(
        None,
        description="Filter by processing status",
        example="uploaded",
    )
    folder_id: Optional[str] = Field(
        None,
        description="Filter by folder ID (legacy uploads)",
        example="folder_abc123",
    )
    folder_path: Optional[str] = Field(
        None,
        description="Filter by folder path from storage_path (target_path uploads)",
        example="Acme-Corp/original/invoices",
    )
    folder_name: Optional[str] = Field(
        None,
        description="Filter by folder name (exact match lookup)",
        example="invoices",
    )
    uploaded_by: Optional[str] = Field(
        None,
        description="Filter by uploader user ID",
        example="user_abc123",
    )

    @field_validator("filename", "folder_id")
    @classmethod
    def validate_filter_strings_field(cls, v: Optional[str]) -> Optional[str]:
        """Validate and clean filter strings."""
        return validate_filter_strings(v)

    @field_validator("folder_path")
    @classmethod
    def validate_folder_path_string(cls, v: Optional[str]) -> Optional[str]:
        """Validate folder path - allow forward slashes for GCS paths."""
        return validate_filter_strings(v, allow_slashes=True)


# Request/Response Models for API endpoints
class DocumentCreateRequest(DocumentCreate):
    """Request model for creating document metadata."""

    pass


class DocumentUpdateRequest(DocumentUpdate):
    """Request model for updating document."""

    pass


class DocumentDeleteResponse(BaseModel):
    """Response model for document deletion."""

    success: bool = Field(
        ...,
        description="Whether deletion was successful",
        example=True,
    )
    message: str = Field(
        ...,
        description="Deletion status message",
        example="Document 'invoice-2025-001.pdf' deleted successfully",
    )


class DocumentUploadResponse(BaseModel):
    """Response model for document upload."""

    success: bool = Field(
        ...,
        description="Whether upload was successful",
        example=True,
    )
    message: str = Field(
        ...,
        description="Upload status message",
        example="Document uploaded successfully",
    )
    document: Optional[DocumentResponse] = Field(
        None,
        description="Uploaded document details",
    )


class DocumentDownloadResponse(BaseModel):
    """Response model for document download."""

    download_url: str = Field(
        ...,
        description="Signed URL for downloading the document",
        example="https://storage.googleapis.com/bucket/path/file.pdf?X-Goog-Algorithm=...",
    )
    expires_at: datetime = Field(
        ...,
        description="When the download URL expires",
        example="2025-01-15T11:30:00Z",
    )
    filename: str = Field(
        ...,
        description="Filename for download",
        example="invoice-2025-001.pdf",
    )


class DocumentStatusUpdate(BaseModel):
    """Schema for updating document status."""

    status: DocumentStatus = Field(
        ...,
        description="New processing status",
        example="uploaded",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional metadata",
        example={"processed_at": "2025-01-15T10:30:00Z", "pages": 5},
    )

    @field_validator("metadata")
    @classmethod
    def validate_metadata_field(
        cls, v: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Validate metadata if provided."""
        if v is None:
            return v
        return validate_metadata(v)
