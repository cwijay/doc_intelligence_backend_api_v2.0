import uuid
import re
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List

from pydantic import BaseModel, Field, field_validator, ConfigDict


class DocumentStatus(str, Enum):
    """Document processing status."""

    UPLOADING = "uploading"  # File upload in progress (sync prevention status)
    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    FAILED = "failed"


class FileType(str, Enum):
    """Supported file types."""

    PDF = "pdf"
    XLSX = "xlsx"


class Document(BaseModel):
    """Document Firestore model for file management."""

    # Primary key - Firestore document ID (managed by Firestore)
    id: Optional[str] = Field(
        None, description="Unique document identifier (Firestore document ID)"
    )

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

    # Parsing results (populated after document parsing)
    parsed_storage_path: Optional[str] = Field(
        None, description="GCS path to parsed content (markdown)"
    )
    parsing_metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Metadata from document parsing (pages, etc.)"
    )
    file_content: Optional[str] = Field(
        None, description="Parsed document content (markdown) - synced with GCS"
    )

    # AI-generated content (stored in Firestore)
    ai_summary: Optional[str] = Field(None, description="AI-generated document summary")
    summary_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata about summary generation (timestamp, model, etc.)",
    )
    ai_faq: Optional[List[Dict[str, str]]] = Field(
        None, description="AI-generated FAQ items as list of Q&A pairs"
    )
    faq_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata about FAQ generation (timestamp, model, count, etc.)",
    )
    ai_questions: Optional[List[str]] = Field(
        None, description="AI-generated questions as list of strings"
    )
    questions_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata about questions generation (timestamp, model, count, etc.)",
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
        default_factory=datetime.utcnow, description="When document was uploaded"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="When document was last updated"
    )

    model_config = ConfigDict(
        use_enum_values=True,
        json_encoders={datetime: lambda dt: dt.isoformat() if dt else None},
        validate_assignment=True,
    )

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

    @field_validator("file_content")
    @classmethod
    def validate_file_content(cls, v: Optional[str]) -> Optional[str]:
        """Validate file content."""
        if v is None:
            return v

        # Check content size limits (1MB for Firestore efficiency)
        max_content_size = 1024 * 1024  # 1MB
        if len(v.encode("utf-8")) > max_content_size:
            raise ValueError(
                f"File content exceeds maximum size of {max_content_size // 1024}KB"
            )

        # Basic validation for markdown-like content
        if not isinstance(v, str):
            raise ValueError("File content must be a string")

        # Strip excessive whitespace but preserve structure
        v = v.strip()

        return v

    @field_validator("ai_summary")
    @classmethod
    def validate_ai_summary(cls, v: Optional[str]) -> Optional[str]:
        """Validate AI-generated summary."""
        if v is None:
            return v

        if not isinstance(v, str):
            raise ValueError("AI summary must be a string")

        # Check summary size limits (10KB for Firestore efficiency)
        max_summary_size = 10 * 1024  # 10KB
        if len(v.encode("utf-8")) > max_summary_size:
            raise ValueError(
                f"AI summary exceeds maximum size of {max_summary_size // 1024}KB"
            )

        # Strip excessive whitespace
        v = v.strip()

        return v

    @field_validator("ai_faq")
    @classmethod
    def validate_ai_faq(
        cls, v: Optional[List[Dict[str, str]]]
    ) -> Optional[List[Dict[str, str]]]:
        """Validate AI-generated FAQ items."""
        if v is None:
            return v

        if not isinstance(v, list):
            raise ValueError("AI FAQ must be a list")

        # Check FAQ count limits (max 20 FAQs)
        if len(v) > 20:
            raise ValueError("AI FAQ cannot exceed 20 items")

        for i, item in enumerate(v):
            if not isinstance(item, dict):
                raise ValueError(f"FAQ item {i} must be a dictionary")

            # Check required keys
            if "question" not in item or "answer" not in item:
                raise ValueError(
                    f"FAQ item {i} must contain 'question' and 'answer' keys"
                )

            # Check data types
            if not isinstance(item["question"], str) or not isinstance(
                item["answer"], str
            ):
                raise ValueError(f"FAQ item {i} question and answer must be strings")

            # Check content
            if not item["question"].strip() or not item["answer"].strip():
                raise ValueError(f"FAQ item {i} question and answer cannot be empty")

            # Check individual item size (1KB per FAQ item)
            item_size = len(item["question"].encode("utf-8")) + len(
                item["answer"].encode("utf-8")
            )
            if item_size > 1024:  # 1KB
                raise ValueError(f"FAQ item {i} exceeds maximum size of 1KB")

        # Check total FAQ size (15KB for all FAQ items)
        total_size = sum(len(str(item).encode("utf-8")) for item in v)
        max_faq_size = 15 * 1024  # 15KB
        if total_size > max_faq_size:
            raise ValueError(
                f"Total AI FAQ size exceeds maximum of {max_faq_size // 1024}KB"
            )

        return v

    @field_validator("ai_questions")
    @classmethod
    def validate_ai_questions(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Validate AI-generated questions."""
        if v is None:
            return v

        if not isinstance(v, list):
            raise ValueError("AI questions must be a list")

        # Check questions count limits (max 20 questions)
        if len(v) > 20:
            raise ValueError("AI questions cannot exceed 20 items")

        for i, question in enumerate(v):
            if not isinstance(question, str):
                raise ValueError(f"Question {i} must be a string")

            # Check content
            if not question.strip():
                raise ValueError(f"Question {i} cannot be empty")

            # Check individual question size (500 bytes per question)
            if len(question.encode("utf-8")) > 500:
                raise ValueError(f"Question {i} exceeds maximum size of 500 bytes")

        # Check total questions size (10KB for all questions)
        total_size = sum(len(question.encode("utf-8")) for question in v)
        max_questions_size = 10 * 1024  # 10KB
        if total_size > max_questions_size:
            raise ValueError(
                f"Total AI questions size exceeds maximum of {max_questions_size // 1024}KB"
            )

        return v

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, filename='{self.filename}', org_id='{self.org_id}', status='{self.status}')>"

    def to_dict(self) -> Dict[str, Any]:
        """Convert document to dictionary for Firestore."""
        data = self.model_dump(exclude={"id"})
        # Convert datetime objects to ISO format for Firestore
        if "created_at" in data:
            data["created_at"] = self.created_at.isoformat()
        if "updated_at" in data:
            data["updated_at"] = self.updated_at.isoformat()
        return data

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], doc_id: Optional[str] = None
    ) -> "Document":
        """Create Document from Firestore document data with enhanced error handling."""
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
                            clean_data[field] = datetime.utcnow()
                    elif clean_data[field] is None:
                        # Handle null datetime values
                        clean_data[field] = datetime.utcnow()

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
                f"Failed to create Document from Firestore data: {e}"
            ) from e

    def update_timestamp(self):
        """Update the updated_at timestamp."""
        self.updated_at = datetime.utcnow()

    def update_status(self, new_status: DocumentStatus):
        """Update document processing status."""
        self.status = new_status
        self.update_timestamp()

        # Add status change to metadata
        if "status_history" not in self.metadata:
            self.metadata["status_history"] = []

        self.metadata["status_history"].append(
            {"status": new_status.value, "timestamp": datetime.utcnow().isoformat()}
        )

    def mark_as_failed(self, error_message: str):
        """Mark document as failed with error information."""
        self.update_status(DocumentStatus.FAILED)
        self.metadata["error"] = {
            "message": error_message,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def mark_as_parsed(
        self,
        parse_metadata: Optional[Dict[str, Any]] = None,
        content: Optional[str] = None,
    ):
        """Mark document as successfully parsed."""
        self.update_status(DocumentStatus.PARSED)
        if parse_metadata:
            self.metadata["parse_info"] = parse_metadata
        if content is not None:
            self.file_content = content

    @property
    def is_processing(self) -> bool:
        """Check if document is currently being processed."""
        return self.status == DocumentStatus.PARSING

    @property
    def is_ready(self) -> bool:
        """Check if document is ready for use."""
        return self.status == DocumentStatus.PARSED

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

    @property
    def has_content(self) -> bool:
        """Check if document has parsed content."""
        return self.file_content is not None and len(self.file_content.strip()) > 0

    @property
    def content_size(self) -> int:
        """Get size of file content in bytes."""
        if not self.file_content:
            return 0
        return len(self.file_content.encode("utf-8"))

    @property
    def content_preview(self) -> str:
        """Get preview of file content (first 200 characters)."""
        if not self.file_content:
            return ""
        content = self.file_content.strip()
        if len(content) <= 200:
            return content
        return content[:200] + "..."

    @property
    def has_ai_summary(self) -> bool:
        """Check if document has AI-generated summary."""
        return self.ai_summary is not None and len(self.ai_summary.strip()) > 0

    @property
    def summary_preview(self) -> str:
        """Get preview of AI summary (first 150 characters)."""
        if not self.ai_summary:
            return ""
        summary = self.ai_summary.strip()
        if len(summary) <= 150:
            return summary
        return summary[:150] + "..."

    @property
    def ai_content_size(self) -> int:
        """Get size of AI summary content in bytes."""
        if self.ai_summary:
            return len(self.ai_summary.encode("utf-8"))
        return 0

    @property
    def has_ai_faq(self) -> bool:
        """Check if document has AI-generated FAQ."""
        return self.ai_faq is not None and len(self.ai_faq) > 0

    @property
    def faq_count(self) -> int:
        """Get number of FAQ items."""
        return len(self.ai_faq) if self.ai_faq else 0

    @property
    def faq_preview(self) -> str:
        """Get preview of AI FAQ (first question and partial answer)."""
        if not self.ai_faq or len(self.ai_faq) == 0:
            return ""

        first_faq = self.ai_faq[0]
        question = first_faq.get("question", "").strip()
        answer = first_faq.get("answer", "").strip()

        if not question:
            return ""

        # Truncate answer to 100 characters
        if len(answer) > 100:
            answer = answer[:100] + "..."

        return f"Q: {question}\nA: {answer}"

    @property
    def ai_faq_size(self) -> int:
        """Get size of AI FAQ content in bytes."""
        if self.ai_faq:
            return sum(len(str(item).encode("utf-8")) for item in self.ai_faq)
        return 0

    @property
    def has_ai_questions(self) -> bool:
        """Check if document has AI-generated questions."""
        return self.ai_questions is not None and len(self.ai_questions) > 0

    @property
    def questions_count(self) -> int:
        """Get number of questions."""
        return len(self.ai_questions) if self.ai_questions else 0

    @property
    def questions_preview(self) -> str:
        """Get preview of AI questions (first 3 questions)."""
        if not self.ai_questions or len(self.ai_questions) == 0:
            return ""

        # Show up to first 3 questions
        preview_questions = self.ai_questions[:3]
        return "\n".join(
            f"{i+1}. {question}" for i, question in enumerate(preview_questions)
        )

    @property
    def ai_questions_size(self) -> int:
        """Get size of AI questions content in bytes."""
        if self.ai_questions:
            return sum(len(question.encode("utf-8")) for question in self.ai_questions)
        return 0

    def update_content(self, content: str):
        """Update document content and timestamp."""
        self.file_content = content
        self.update_timestamp()

        # Add content update to metadata
        if "content_history" not in self.metadata:
            self.metadata["content_history"] = []

        self.metadata["content_history"].append(
            {
                "action": "content_updated",
                "size": self.content_size,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    def clear_content(self):
        """Clear document content (e.g., when reverting to binary-only)."""
        self.file_content = None
        self.update_timestamp()

        # Add content clear to metadata
        if "content_history" not in self.metadata:
            self.metadata["content_history"] = []

        self.metadata["content_history"].append(
            {"action": "content_cleared", "timestamp": datetime.utcnow().isoformat()}
        )

    def update_ai_summary(
        self,
        summary: Optional[str],
        generation_metadata: Optional[Dict[str, Any]] = None,
    ):
        """Update AI-generated summary and timestamp."""
        self.ai_summary = summary
        self.update_timestamp()

        # Update summary metadata
        if generation_metadata:
            self.summary_metadata = generation_metadata

        # Add summary update to metadata
        if "ai_content_history" not in self.metadata:
            self.metadata["ai_content_history"] = []

        self.metadata["ai_content_history"].append(
            {
                "action": "summary_updated",
                "size": len(summary.encode("utf-8")) if summary else 0,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    def update_ai_faq(
        self,
        faq: Optional[List[Dict[str, str]]],
        generation_metadata: Optional[Dict[str, Any]] = None,
    ):
        """Update AI-generated FAQ and timestamp."""
        self.ai_faq = faq
        self.update_timestamp()

        # Update FAQ metadata
        if generation_metadata:
            self.faq_metadata = generation_metadata

        # Add FAQ update to metadata
        if "ai_content_history" not in self.metadata:
            self.metadata["ai_content_history"] = []

        self.metadata["ai_content_history"].append(
            {
                "action": "faq_updated",
                "count": len(faq) if faq else 0,
                "size": self.ai_faq_size,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    def update_ai_questions(
        self,
        questions: Optional[List[str]],
        generation_metadata: Optional[Dict[str, Any]] = None,
    ):
        """Update AI-generated questions and timestamp."""
        self.ai_questions = questions
        self.update_timestamp()

        # Update questions metadata
        if generation_metadata:
            self.questions_metadata = generation_metadata

        # Add questions update to metadata
        if "ai_content_history" not in self.metadata:
            self.metadata["ai_content_history"] = []

        self.metadata["ai_content_history"].append(
            {
                "action": "questions_updated",
                "count": len(questions) if questions else 0,
                "size": self.ai_questions_size,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    def clear_ai_summary(self):
        """Clear AI-generated summary."""
        self.ai_summary = None
        self.summary_metadata = {}
        self.update_timestamp()

        # Add AI content clear to metadata
        if "ai_content_history" not in self.metadata:
            self.metadata["ai_content_history"] = []

        self.metadata["ai_content_history"].append(
            {"action": "ai_summary_cleared", "timestamp": datetime.utcnow().isoformat()}
        )

    def clear_ai_faq(self):
        """Clear AI-generated FAQ."""
        self.ai_faq = None
        self.faq_metadata = {}
        self.update_timestamp()

        # Add AI content clear to metadata
        if "ai_content_history" not in self.metadata:
            self.metadata["ai_content_history"] = []

        self.metadata["ai_content_history"].append(
            {"action": "ai_faq_cleared", "timestamp": datetime.utcnow().isoformat()}
        )

    def clear_ai_questions(self):
        """Clear AI-generated questions."""
        self.ai_questions = None
        self.questions_metadata = {}
        self.update_timestamp()

        # Add AI content clear to metadata
        if "ai_content_history" not in self.metadata:
            self.metadata["ai_content_history"] = []

        self.metadata["ai_content_history"].append(
            {
                "action": "ai_questions_cleared",
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

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
            DocumentStatus.UPLOADED: [DocumentStatus.PARSING, DocumentStatus.FAILED],
            DocumentStatus.PARSING: [DocumentStatus.PARSED, DocumentStatus.FAILED],
            DocumentStatus.PARSED: [
                DocumentStatus.FAILED
            ],  # Can fail during later processing
            DocumentStatus.FAILED: [DocumentStatus.PARSING],  # Can retry
        }

        return new_status in valid_transitions.get(self.status, [])
