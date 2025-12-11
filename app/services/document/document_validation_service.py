"""
Document Validation Service - File validation, security checks, and path validation.

This service handles all validation aspects of document management:
- File upload validation (type, size, content)
- Security scanning and threat detection
- Storage path validation and sanitization
- Metadata safety and bulletproofing
- Directory traversal prevention
"""

import mimetypes
from typing import Tuple, Optional
from datetime import datetime, timezone
from fastapi import UploadFile

from app.models.document import Document, DocumentStatus, FileType
from .document_base_service import DocumentBaseService, DocumentValidationError


class DocumentValidationService(DocumentBaseService):
    """Service for document validation, security checks, and path management."""

    def _validate_file_upload(self, file: UploadFile) -> Tuple[FileType, str]:
        """
        Validate uploaded file for type, size, and basic security.

        Args:
            file: Uploaded file to validate

        Returns:
            Tuple of (file_type, content_type)

        Raises:
            DocumentValidationError: If validation fails
        """
        if not file.filename:
            raise DocumentValidationError("Filename is required")

        # Check file type
        file_type = Document.extract_file_type(file.filename)
        if file_type is None:
            raise DocumentValidationError(
                f"Unsupported file type. Allowed types: {', '.join([ft.value for ft in self.allowed_file_types])}"
            )

        # Check file size
        if file.size and file.size > self.max_file_size:
            max_mb = self.max_file_size // (1024 * 1024)
            raise DocumentValidationError(
                f"File size exceeds maximum limit of {max_mb}MB"
            )

        # Get content type
        content_type = file.content_type or mimetypes.guess_type(file.filename)[0]

        return file_type, content_type

    async def _basic_virus_scan(self, content: bytes, filename: str) -> bool:
        """
        Basic virus scanning and malicious content detection.

        Args:
            content: File content to scan
            filename: Filename for logging

        Returns:
            True if file is clean, False if suspicious
        """
        # Placeholder for basic file validation
        # In a production environment, integrate with actual antivirus service

        # Check for suspicious file patterns
        suspicious_patterns = [
            b"<script",
            b"javascript:",
            b"vbscript:",
            b"onload=",
            b"onerror=",
        ]

        content_lower = content.lower()
        for pattern in suspicious_patterns:
            if pattern in content_lower:
                self.logger.warning(
                    "Suspicious content detected in file",
                    filename=filename,
                    pattern=pattern.decode("utf-8", errors="ignore"),
                )
                return False

        return True

    def _validate_target_path(self, target_path: str, filename: str) -> str:
        """
        Validate and sanitize target path for security and format compliance.

        Args:
            target_path: Client-provided target path
            filename: Original filename for fallback

        Returns:
            Validated and sanitized target path

        Raises:
            DocumentValidationError: If path is invalid or unsafe
        """
        if not target_path or not target_path.strip():
            raise DocumentValidationError("Target path cannot be empty")

        # Basic sanitization
        target_path = target_path.strip()

        # Check path length
        if len(target_path) > self.max_path_length:
            raise DocumentValidationError(
                f"Target path too long (max {self.max_path_length} characters)"
            )

        # Check for directory traversal attacks
        dangerous_patterns = ["../", "../", "..\\", "..\\\\", "/..", "\\..", "~/", "./"]
        for pattern in dangerous_patterns:
            if pattern in target_path:
                raise DocumentValidationError(
                    "Target path contains unsafe characters. Directory traversal not allowed."
                )

        # Check for null bytes and other dangerous characters
        if "\x00" in target_path or "\r" in target_path or "\n" in target_path:
            raise DocumentValidationError("Target path contains invalid characters")

        # Validate path format: {org_name}/original/{folder_name}/{document_name}
        path_parts = target_path.split("/")

        if len(path_parts) != 4:
            raise DocumentValidationError(
                "Invalid target_path format. Must be: {org_name}/original/{folder_name}/{document_name}"
            )

        org_name, file_type_indicator, folder_name, document_name = path_parts

        # Validate each component
        if not org_name or not org_name.strip():
            raise DocumentValidationError(
                "Organization name in target_path cannot be empty"
            )

        if file_type_indicator != "original":
            raise DocumentValidationError(
                "Second segment of target_path must be 'original'"
            )

        if not folder_name or not folder_name.strip():
            raise DocumentValidationError("Folder name in target_path cannot be empty")

        if not document_name or not document_name.strip():
            raise DocumentValidationError(
                "Document name in target_path cannot be empty"
            )

        # Sanitize document name (remove dangerous characters but keep it functional)
        sanitized_document_name = Document.sanitize_filename(document_name)
        if not sanitized_document_name:
            # If sanitization results in empty name, use original filename
            sanitized_document_name = Document.sanitize_filename(filename)

        # Rebuild path with sanitized components
        sanitized_path = f"{org_name.strip()}/original/{folder_name.strip()}/{sanitized_document_name}"

        self.logger.info(
            "Target path validated and sanitized",
            original_path=target_path,
            sanitized_path=sanitized_path,
            org_name=org_name.strip(),
            folder_name=folder_name.strip(),
            document_name=sanitized_document_name,
        )

        return sanitized_path

    def _extract_folder_from_storage_path(self, storage_path: str) -> Optional[str]:
        """
        Extract folder name from storage_path.

        Args:
            storage_path: Storage path like "Google/original/invoices/document.pdf"

        Returns:
            Folder name like "invoices" or None if not found
        """
        if not storage_path:
            return None

        try:
            # Expected format: {org_name}/original/{folder_name}/{document_name}
            path_parts = storage_path.split("/")
            if len(path_parts) >= 4 and path_parts[1] == "original":
                folder_name = path_parts[2]
                return folder_name if folder_name and folder_name != "root" else None
            return None
        except Exception as e:
            self.logger.debug(
                "Error extracting folder from storage_path",
                storage_path=storage_path,
                error=str(e),
            )
            return None

    def _ensure_safe_metadata(self, document: Document) -> Document:
        """
        NUCLEAR APPROACH: Final safety net to ensure NO field can cause 'Unknown' values in frontend.
        This is bulletproof validation that catches ANY edge case before API response.

        Args:
            document: Document that may have any kind of malformed data

        Returns:
            Document with guaranteed safe values for all fields
        """
        try:
            # BULLETPROOF file_size - never null/undefined/NaN
            if (
                not hasattr(document, "file_size")
                or document.file_size is None
                or document.file_size == ""
                or document.file_size < 0
                or str(document.file_size).lower() in ["nan", "null", "undefined"]
            ):
                document.file_size = 0

            # BULLETPROOF file_type - never null/empty/unknown
            if (
                not hasattr(document, "file_type")
                or not document.file_type
                or document.file_type is None
                or document.file_type == ""
                or str(document.file_type).lower() in ["null", "undefined", "unknown"]
            ):
                document.file_type = FileType.PDF

            # BULLETPROOF filename - never empty/null
            if (
                not hasattr(document, "filename")
                or not document.filename
                or document.filename is None
                or document.filename.strip() == ""
                or str(document.filename).lower() in ["null", "undefined"]
            ):
                document.filename = "unknown_file.pdf"

            # BULLETPROOF original_filename - never empty/null
            if (
                not hasattr(document, "original_filename")
                or not document.original_filename
                or document.original_filename is None
                or document.original_filename.strip() == ""
                or str(document.original_filename).lower() in ["null", "undefined"]
            ):
                document.original_filename = document.filename or "unknown_file.pdf"

            # BULLETPROOF created_at - never null/invalid
            if (
                not hasattr(document, "created_at")
                or not document.created_at
                or document.created_at is None
                or str(document.created_at).lower() in ["null", "undefined"]
            ):
                document.created_at = datetime.now(timezone.utc)

            # BULLETPROOF updated_at - never null/invalid
            if (
                not hasattr(document, "updated_at")
                or not document.updated_at
                or document.updated_at is None
                or str(document.updated_at).lower() in ["null", "undefined"]
            ):
                document.updated_at = document.created_at or datetime.now(timezone.utc)

            # BULLETPROOF status - never null/empty
            if (
                not hasattr(document, "status")
                or not document.status
                or document.status is None
                or str(document.status).lower() in ["null", "undefined", ""]
            ):
                document.status = DocumentStatus.UPLOADED

            # BULLETPROOF storage_path - never empty
            if (
                not hasattr(document, "storage_path")
                or not document.storage_path
                or document.storage_path is None
                or document.storage_path.strip() == ""
                or str(document.storage_path).lower() in ["null", "undefined"]
            ):
                document.storage_path = (
                    "unknown_org/original/unknown_folder/unknown_file.pdf"
                )

            # BULLETPROOF org_id - never empty
            if (
                not hasattr(document, "org_id")
                or not document.org_id
                or document.org_id is None
                or document.org_id.strip() == ""
                or str(document.org_id).lower() in ["null", "undefined"]
            ):
                document.org_id = "unknown_org_id"

            # BULLETPROOF uploaded_by - never empty
            if (
                not hasattr(document, "uploaded_by")
                or not document.uploaded_by
                or document.uploaded_by is None
                or document.uploaded_by.strip() == ""
                or str(document.uploaded_by).lower() in ["null", "undefined"]
            ):
                document.uploaded_by = "unknown_user"

            # BULLETPROOF metadata - never null
            if (
                not hasattr(document, "metadata")
                or document.metadata is None
                or not isinstance(document.metadata, dict)
            ):
                document.metadata = {}

            # BULLETPROOF is_active - never null
            if not hasattr(document, "is_active") or document.is_active is None:
                document.is_active = True

            return document

        except Exception as e:
            # Even if this safety net fails, return document with minimal safe data
            self.logger.error(
                "Safety net validation failed, using emergency defaults",
                document_id=getattr(document, "id", "unknown"),
                error=str(e),
            )

            # Emergency fallback - create minimal safe document
            document.file_size = 0
            document.file_type = FileType.PDF
            document.filename = "unknown_file.pdf"
            document.original_filename = "unknown_file.pdf"
            document.created_at = datetime.now(timezone.utc)
            document.updated_at = datetime.now(timezone.utc)
            document.status = DocumentStatus.UPLOADED
            document.storage_path = (
                "unknown_org/original/unknown_folder/unknown_file.pdf"
            )
            document.org_id = getattr(document, "org_id", "unknown_org_id")
            document.uploaded_by = "unknown_user"
            document.metadata = {}
            document.is_active = True

            return document
