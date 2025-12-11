import uuid
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, Optional

from pydantic import BaseModel, Field, field_validator, field_serializer, ConfigDict


class DocumentStatus(str, Enum):
    """Document processing status."""

    UPLOADING = "uploading"  # File upload in progress (sync prevention status)
    UPLOADED = "uploaded"
    FAILED = "failed"


class FileType(str, Enum):
    """Supported file types."""

    PDF = "pdf"
    XLSX = "xlsx"


class Document(BaseModel):
    """Document model for file management."""

    # Primary key - document ID
    id: Optional[str] = Field(None, description="Unique document identifier")

    # Multi-tenancy and organization
    org_id: str = Field(..., description="Organization ID (foreign key)")
    folder_id: Optional[str] = Field(None, description="Folder ID (foreign key)")

    # File information
    filename: str = Field(..., description="Sanitized filename for storage")
    original_filename: str = Field(..., description="Original filename as uploaded")
    file_type: FileType = Field(..., description="Document file type")
    file_size: int = Field(..., ge=0, description="File size in bytes")
    storage_path: str = Field(..., description="GCS storage path")

    # Processing status
    status: DocumentStatus = Field(
        default=DocumentStatus.UPLOADED, description="Document processing status"
    )

    # User tracking
    uploaded_by: str = Field(..., description="User ID who uploaded the document")

    # Metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Document metadata and processing info"
    )

    # Status tracking
    is_active: bool = Field(
        default=True, description="Whether document is active (for soft delete)"
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When document was uploaded",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When document was last updated",
    )

    model_config = ConfigDict(
        use_enum_values=True,
        validate_assignment=True,
    )

    @field_serializer("created_at", "updated_at")
    def serialize_datetime(self, value: datetime) -> Optional[str]:
        """Serialize datetime fields to ISO format."""
        return value.isoformat() if value else None

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        """Validate and sanitize filename."""
        if not v or not v.strip():
            raise ValueError("Filename cannot be empty")

        v = v.strip()

        # Check length
        if len(v) < 1 or len(v) > 255:
            raise ValueError("Filename must be between 1 and 255 characters")

        # Sanitize filename by removing dangerous characters
        # Keep alphanumeric, dots, hyphens, underscores
        sanitized = re.sub(r"[^a-zA-Z0-9._-]", "_", v)

        # Ensure it doesn't start or end with dots or spaces
        sanitized = sanitized.strip(".")

        # Ensure we have a valid filename
        if not sanitized:
            raise ValueError("Filename contains only invalid characters")

        return sanitized

    @field_validator("original_filename")
    @classmethod
    def validate_original_filename(cls, v: str) -> str:
        """Validate original filename."""
        if not v or not v.strip():
            raise ValueError("Original filename cannot be empty")

        v = v.strip()

        # Check length
        if len(v) < 1 or len(v) > 255:
            raise ValueError("Original filename must be between 1 and 255 characters")

        return v

    @field_validator("file_size")
    @classmethod
    def validate_file_size(cls, v: int) -> int:
        """Validate file size."""
        if v < 0:
            raise ValueError("File size cannot be negative")

        # 50MB limit
        max_size = 50 * 1024 * 1024  # 50MB in bytes
        if v > max_size:
            raise ValueError(f"File size cannot exceed {max_size // (1024 * 1024)}MB")

        return v

    @field_validator("storage_path")
    @classmethod
    def validate_storage_path(cls, v: str) -> str:
        """Validate GCS storage path."""
        if not v or not v.strip():
            raise ValueError("Storage path cannot be empty")

        v = v.strip()

        # Basic path validation - should not start or end with /
        if v.startswith("/") or v.endswith("/"):
            raise ValueError("Storage path should not start or end with '/'")

        # Should contain org/folder/filename structure
        path_parts = v.split("/")
        if len(path_parts) < 2:
            raise ValueError("Storage path must have at least org/filename structure")

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

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, filename='{self.filename}', org_id='{self.org_id}', status='{self.status}')>"

    def to_dict(self) -> Dict[str, Any]:
        """Convert document to dictionary for database."""
        data = self.model_dump(exclude={"id"})
        # Convert datetime objects to ISO format
        if "created_at" in data:
            data["created_at"] = self.created_at.isoformat()
        if "updated_at" in data:
            data["updated_at"] = self.updated_at.isoformat()
        return data

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], doc_id: Optional[str] = None
    ) -> "Document":
        """Create Document from database record data with enhanced error handling."""
        try:
            # Create a copy to avoid modifying original data
            clean_data = data.copy()

            # Handle datetime parsing with better error handling
            for field in ["created_at", "updated_at"]:
                if field in clean_data:
                    if isinstance(clean_data[field], str):
                        try:
                            clean_data[field] = datetime.fromisoformat(
                                clean_data[field]
                            )
                        except ValueError:
                            # If datetime parsing fails, use current time as fallback
                            clean_data[field] = datetime.now(timezone.utc)
                    elif clean_data[field] is None:
                        # Handle null datetime values
                        clean_data[field] = datetime.now(timezone.utc)

            # Ensure required fields have proper defaults
            if "file_size" in clean_data and (
                clean_data["file_size"] is None or clean_data["file_size"] == ""
            ):
                clean_data["file_size"] = 0

            if "metadata" in clean_data and clean_data["metadata"] is None:
                clean_data["metadata"] = {}

            if "is_active" not in clean_data:
                clean_data["is_active"] = True

            # Handle enum values - ensure they're valid
            if "status" in clean_data:
                if clean_data["status"] is None or clean_data["status"] == "":
                    clean_data["status"] = DocumentStatus.UPLOADED.value
                elif hasattr(clean_data["status"], "value"):
                    clean_data["status"] = clean_data["status"].value
                elif isinstance(clean_data["status"], str):
                    # Validate that it's a valid status
                    try:
                        DocumentStatus(clean_data["status"])
                    except ValueError:
                        clean_data["status"] = DocumentStatus.UPLOADED.value
            else:
                clean_data["status"] = DocumentStatus.UPLOADED.value

            if "file_type" in clean_data:
                if clean_data["file_type"] is None or clean_data["file_type"] == "":
                    # Try to determine from filename
                    filename = clean_data.get("filename") or clean_data.get(
                        "original_filename"
                    )
                    if filename:
                        extracted_type = cls.extract_file_type(filename)
                        clean_data["file_type"] = (
                            extracted_type.value
                            if extracted_type
                            else FileType.PDF.value
                        )
                    else:
                        clean_data["file_type"] = FileType.PDF.value
                elif hasattr(clean_data["file_type"], "value"):
                    clean_data["file_type"] = clean_data["file_type"].value
                elif isinstance(clean_data["file_type"], str):
                    # Validate that it's a valid file type
                    try:
                        FileType(clean_data["file_type"])
                    except ValueError:
                        clean_data["file_type"] = FileType.PDF.value
            else:
                # Missing file_type entirely
                filename = clean_data.get("filename") or clean_data.get(
                    "original_filename"
                )
                if filename:
                    extracted_type = cls.extract_file_type(filename)
                    clean_data["file_type"] = (
                        extracted_type.value if extracted_type else FileType.PDF.value
                    )
                else:
                    clean_data["file_type"] = FileType.PDF.value

            # Ensure required string fields are not None or empty
            for field in [
                "filename",
                "original_filename",
                "storage_path",
                "org_id",
                "uploaded_by",
            ]:
                if field in clean_data and (
                    clean_data[field] is None or clean_data[field] == ""
                ):
                    if field == "filename":
                        clean_data[field] = (
                            clean_data.get("original_filename") or "unknown_file"
                        )
                    elif field == "original_filename":
                        clean_data[field] = clean_data.get("filename") or "unknown_file"
                    elif field == "storage_path":
                        clean_data[field] = (
                            "unknown_org/original/unknown_folder/unknown_file"
                        )
                    elif field == "org_id":
                        clean_data[field] = "unknown_org_id"
                    elif field == "uploaded_by":
                        clean_data[field] = "unknown_user"

            # Add document ID if provided
            if doc_id:
                clean_data["id"] = doc_id

            return cls(**clean_data)

        except Exception as e:
            # Log the error and re-raise with more context
            import logging

            logger = logging.getLogger(__name__)
            logger.error(
                f"Failed to create Document from dict: {e}",
                extra={"data": data, "doc_id": doc_id},
            )
            raise ValueError(
                f"Failed to create Document from database data: {e}"
            ) from e

    def update_timestamp(self):
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now(timezone.utc)

    def update_status(self, new_status: DocumentStatus):
        """Update document processing status."""
        self.status = new_status
        self.update_timestamp()

        # Add status change to metadata
        if "status_history" not in self.metadata:
            self.metadata["status_history"] = []

        self.metadata["status_history"].append(
            {
                "status": new_status.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def mark_as_failed(self, error_message: str):
        """Mark document as failed with error information."""
        self.update_status(DocumentStatus.FAILED)
        self.metadata["error"] = {
            "message": error_message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @property
    def has_failed(self) -> bool:
        """Check if document processing has failed."""
        return self.status == DocumentStatus.FAILED

    @property
    def file_extension(self) -> str:
        """Get file extension from filename."""
        if "." in self.filename:
            return self.filename.split(".")[-1].lower()
        return ""

    @property
    def display_size(self) -> str:
        """Get human-readable file size."""
        size = self.file_size
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def generate_storage_path(
        self, org_name: str, folder_name: Optional[str] = None
    ) -> str:
        """
        Generate GCS storage path for the document.

        Args:
            org_name: Organization name
            folder_name: Folder name (optional)

        Returns:
            GCS storage path
        """
        if folder_name:
            return f"{org_name}/{folder_name}/{self.id}_{self.filename}"
        else:
            return f"{org_name}/root/{self.id}_{self.filename}"

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """
        Sanitize a filename to be safe for storage.

        Args:
            filename: Original filename

        Returns:
            Sanitized filename
        """
        if not filename:
            return "unnamed_file"

        # Keep only alphanumeric, dots, hyphens, underscores
        sanitized = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)

        # Remove leading/trailing dots and spaces
        sanitized = sanitized.strip(".")

        # Ensure we have something
        if not sanitized:
            return "unnamed_file"

        # Limit length
        if len(sanitized) > 200:
            name, ext = (
                sanitized.rsplit(".", 1) if "." in sanitized else (sanitized, "")
            )
            sanitized = f"{name[:190]}.{ext}" if ext else name[:200]

        return sanitized

    @staticmethod
    def generate_id() -> str:
        """Generate a new document ID."""
        return str(uuid.uuid4())

    @staticmethod
    def extract_file_type(filename: str) -> Optional[FileType]:
        """
        Extract file type from filename.

        Args:
            filename: Filename to check

        Returns:
            FileType if supported, None otherwise
        """
        if not filename:
            return None

        extension = filename.split(".")[-1].lower() if "." in filename else ""

        if extension == "pdf":
            return FileType.PDF
        elif extension in ["xlsx", "xls"]:
            return FileType.XLSX

        return None

    @staticmethod
    def is_supported_file_type(filename: str) -> bool:
        """
        Check if file type is supported.

        Args:
            filename: Filename to check

        Returns:
            True if supported, False otherwise
        """
        return Document.extract_file_type(filename) is not None

    def can_transition_to(self, new_status: DocumentStatus) -> bool:
        """
        Check if document can transition to new status.

        Args:
            new_status: Target status

        Returns:
            True if transition is valid, False otherwise
        """
        valid_transitions = {
            DocumentStatus.UPLOADING: [DocumentStatus.UPLOADED, DocumentStatus.FAILED],
            DocumentStatus.UPLOADED: [DocumentStatus.FAILED],
            DocumentStatus.FAILED: [DocumentStatus.UPLOADED],  # Can retry upload
        }

        return new_status in valid_transitions.get(self.status, [])
