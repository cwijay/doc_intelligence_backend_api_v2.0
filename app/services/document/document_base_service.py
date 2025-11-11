"""
Document Base Service - Common utilities and shared functionality.

This service provides the foundation for all document services with:
- Common exception classes
- Shared configuration and logging
- Firestore collection access
- Organization and folder name lookups
- Base constants and settings
"""

from typing import Optional
from app.core.firebase_client import get_collection
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


class DocumentBaseService:
    """Base service with common functionality shared across all document services."""

    def __init__(self):
        """Initialize base service with common configuration."""
        self.logger = get_service_logger("document")

        # File constraints
        self.max_file_size = 50 * 1024 * 1024  # 50MB
        self.allowed_file_types = {FileType.PDF, FileType.XLSX}
        self.max_path_length = 1024  # Maximum storage path length

        # Import here to avoid circular imports
        from app.services.org_service import organization_service
        from app.services.folder_service import folder_service

        self.org_service = organization_service
        self.folder_service = folder_service

    def _get_collection(self, org_id: str):
        """
        Get the documents collection for an organization.

        Args:
            org_id: Organization ID

        Returns:
            Firestore collection reference
        """
        return get_collection(f"organizations/{org_id}/documents")

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
            # For GCS-only approach, folder_id IS the folder name/path
            # Try to get folder from service, but if it doesn't exist in GCS yet,
            # we can still use the folder_id as the folder name for upload
            try:
                folder_response = await self.folder_service.get_folder(
                    org_id, folder_id
                )
                # Extract folder name from path (remove leading slash and get last part)
                path_parts = folder_response.path.strip("/").split("/")
                return path_parts[-1] if path_parts and path_parts[0] else None
            except Exception:
                # If folder doesn't exist in GCS yet, use folder_id as folder name
                # This allows uploading to folders that will be created on demand
                self.logger.info(
                    "Folder not found in GCS, using folder_id as folder name",
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
