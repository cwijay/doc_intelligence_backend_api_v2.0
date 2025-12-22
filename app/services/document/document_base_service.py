"""
Document Base Service - Common utilities and shared functionality.

This service provides the foundation for all document services with:
- Common exception classes
- Shared configuration and logging
- Database session access
- Organization and folder name lookups
- Base constants and settings
"""

from typing import Optional
from biz2bricks_core import db
from app.core.logging import get_service_logger
from app.models.document import FileType


# Exception classes
class DocumentNotFoundError(Exception):
    """Document not found error."""

    pass


class DocumentValidationError(Exception):
    """Document validation error."""

    pass


class DocumentUploadError(Exception):
    """Document upload error."""

    pass


class DocumentDuplicateError(Exception):
    """Document with same name already exists in folder."""

    def __init__(self, message: str, existing_document: dict):
        super().__init__(message)
        self.existing_document = existing_document


class DocumentBaseService:
    """Base service with common functionality shared across all document services."""

    def __init__(self):
        """Initialize base service with common configuration."""
        self.logger = get_service_logger("document")

        # File constraints
        self.max_file_size = 50 * 1024 * 1024  # 50MB
        self.allowed_file_types = {
            FileType.PDF,
            FileType.XLSX,
            FileType.CSV,
            FileType.JPEG,
            FileType.PNG,
            FileType.DOCX,
            FileType.DOC,
            FileType.PPTX,
            FileType.PPT,
            FileType.TXT,
            FileType.GIF,
            FileType.WEBP,
            FileType.TIFF,
        }
        self.max_path_length = 1024  # Maximum storage path length

        # Import here to avoid circular imports
        from app.services.org_service import organization_service
        from app.services.folder_service import folder_service

        self.org_service = organization_service
        self.folder_service = folder_service

    @property
    def db(self):
        """Get database manager for session access."""
        return db

    async def _get_organization_name(self, org_id: str) -> str:
        """
        Get organization name from organization ID.

        Args:
            org_id: Organization ID

        Returns:
            Organization name

        Raises:
            DocumentValidationError: If organization not found
        """
        try:
            org_response = await self.org_service.get_organization(org_id)
            return org_response.name
        except Exception as e:
            self.logger.error(
                "Failed to get organization name", org_id=org_id, error=str(e)
            )
            raise DocumentValidationError(
                f"Could not fetch organization name for ID {org_id}: {e}"
            )

    async def _get_folder_name(
        self, org_id: str, folder_id: Optional[str]
    ) -> Optional[str]:
        """
        Get folder name from folder ID.

        Args:
            org_id: Organization ID
            folder_id: Folder ID (None for root)

        Returns:
            Folder name or None for root

        Raises:
            DocumentValidationError: If folder not found
        """
        if folder_id is None:
            return None

        try:
            try:
                folder_response = await self.folder_service.get_folder(
                    org_id, folder_id
                )
                # Extract folder name from path
                path_parts = folder_response.path.strip("/").split("/")
                return path_parts[-1] if path_parts and path_parts[0] else None
            except Exception:
                # If folder doesn't exist yet, use folder_id as folder name
                self.logger.info(
                    "Folder not found, using folder_id as folder name",
                    org_id=org_id,
                    folder_id=folder_id,
                )
                return folder_id

        except Exception as e:
            self.logger.error(
                "Failed to get folder name",
                org_id=org_id,
                folder_id=folder_id,
                error=str(e),
            )
            raise DocumentValidationError(
                f"Could not fetch folder name for ID {folder_id}: {e}"
            )
