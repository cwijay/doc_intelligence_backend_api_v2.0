"""
Document Storage Service - GCS operations and storage path management.

This service handles all storage-related operations:
- Storage path uniqueness and generation
- GCS file operations and metadata enrichment
- Path validation and existence checking
- Storage path manipulation and generation
- File metadata extraction from GCS
"""

from pathlib import Path
from datetime import datetime

from sqlalchemy import select

from app.models.document import Document, DocumentStatus, FileType
from app.core.gcs_client import gcs_client
from app.core.db_models import DocumentModel
from .document_base_service import DocumentBaseService


class DocumentStorageService(DocumentBaseService):
    """Service for GCS operations and storage path management."""

    async def _check_storage_path_exists(self, org_id: str, storage_path: str) -> bool:
        """
        Check if a storage_path already exists in PostgreSQL.

        Args:
            org_id: Organization ID
            storage_path: Storage path to check

        Returns:
            True if path exists, False otherwise
        """
        try:
            async with self.db.session() as session:
                stmt = (
                    select(DocumentModel.id)
                    .where(
                        DocumentModel.organization_id == org_id,
                        DocumentModel.storage_path == storage_path,
                        DocumentModel.is_active == True,
                    )
                    .limit(1)
                )
                result = await session.execute(stmt)
                exists = result.scalar_one_or_none() is not None
                return exists

        except Exception as e:
            self.logger.error(
                "Error checking storage path existence",
                org_id=org_id,
                storage_path=storage_path,
                error=str(e),
            )
            # On error, assume it exists to be safe
            return True

    def _generate_unique_storage_path(
        self, base_storage_path: str, filename: str
    ) -> str:
        """
        Generate a unique storage path by appending incremental suffix if needed.

        Args:
            base_storage_path: Original storage path
            filename: Original filename for fallback

        Returns:
            Unique storage path
        """
        # Parse the base path
        path_obj = Path(base_storage_path)
        directory = str(path_obj.parent)
        name = path_obj.stem
        extension = path_obj.suffix

        # Try incremental suffixes: file.pdf -> file-1.pdf -> file-2.pdf
        counter = 1
        while counter <= 1000:  # Prevent infinite loop
            if counter == 1:
                # First try: add timestamp microseconds for uniqueness
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[
                    :19
                ]  # Remove last 3 microsecond digits
                unique_name = f"{name}_{timestamp}{extension}"
            else:
                # Subsequent tries: simple incremental counter
                unique_name = f"{name}-{counter}{extension}"

            unique_path = f"{directory}/{unique_name}"
            return unique_path

        # Fallback: use document ID as filename (this should never happen)
        document_id = Document.generate_id()
        fallback_path = (
            f"{directory}/{document_id}_{Document.sanitize_filename(filename)}"
        )

        self.logger.warning(
            "Generated fallback unique path after many attempts",
            base_path=base_storage_path,
            fallback_path=fallback_path,
        )

        return fallback_path

    async def _ensure_unique_storage_path(
        self, org_id: str, storage_path: str, filename: str
    ) -> str:
        """
        Ensure the storage path is unique by checking PostgreSQL and generating alternatives if needed.

        Args:
            org_id: Organization ID
            storage_path: Desired storage path
            filename: Original filename for fallback

        Returns:
            Guaranteed unique storage path
        """
        original_path = storage_path

        # Check if original path is available
        if not await self._check_storage_path_exists(org_id, storage_path):
            self.logger.debug(
                "Storage path is available", org_id=org_id, storage_path=storage_path
            )
            return storage_path

        # Original path exists, generate unique alternative
        self.logger.info(
            "Storage path already exists, generating unique alternative",
            org_id=org_id,
            original_path=original_path,
        )

        max_attempts = 10
        for attempt in range(max_attempts):
            unique_path = self._generate_unique_storage_path(storage_path, filename)

            if not await self._check_storage_path_exists(org_id, unique_path):
                self.logger.info(
                    "Generated unique storage path",
                    org_id=org_id,
                    original_path=original_path,
                    unique_path=unique_path,
                    attempt=attempt + 1,
                )
                return unique_path

            # Path still exists, try again with different base
            storage_path = unique_path

        # This should never happen, but provide ultimate fallback
        fallback_path = self._generate_unique_storage_path(original_path, filename)
        self.logger.warning(
            "Used fallback unique path generation",
            org_id=org_id,
            original_path=original_path,
            fallback_path=fallback_path,
        )

        return fallback_path

    async def _enrich_document_metadata(self, document: Document) -> Document:
        """
        Enrich document metadata by fetching missing information from GCS if available.

        Args:
            document: Document instance that may have incomplete metadata

        Returns:
            Document with enriched metadata and validated fields
        """
        try:
            # Ensure file_size is valid
            if not document.file_size or document.file_size <= 0:
                self.logger.debug(
                    "Document has invalid file_size, attempting to fetch from GCS",
                    document_id=document.id,
                    current_file_size=document.file_size,
                    storage_path=document.storage_path,
                )

                # Try to get file size from GCS
                if gcs_client.is_initialized and document.storage_path:
                    try:
                        gcs_metadata = gcs_client.get_document_metadata(
                            document.storage_path
                        )
                        if gcs_metadata and gcs_metadata.get("size") is not None:
                            document.file_size = gcs_metadata["size"]
                            self.logger.info(
                                "Enriched file_size from GCS metadata",
                                document_id=document.id,
                                storage_path=document.storage_path,
                                file_size=document.file_size,
                            )
                        else:
                            # Fallback to 0 if no size found
                            document.file_size = 0
                            self.logger.warning(
                                "Could not determine file size from GCS, using fallback",
                                document_id=document.id,
                                storage_path=document.storage_path,
                            )
                    except Exception as e:
                        self.logger.warning(
                            "Failed to fetch metadata from GCS, using fallback",
                            document_id=document.id,
                            storage_path=document.storage_path,
                            error=str(e),
                        )
                        document.file_size = 0
                else:
                    # Fallback to 0 if GCS is not available
                    document.file_size = 0
                    self.logger.debug(
                        "GCS not initialized, using fallback file_size",
                        document_id=document.id,
                    )

            # Ensure file_type is valid
            if not document.file_type:
                # Try to determine file type from filename
                if document.filename:
                    extracted_type = Document.extract_file_type(document.filename)
                    if extracted_type:
                        document.file_type = extracted_type
                        self.logger.debug(
                            "Set file_type from filename",
                            document_id=document.id,
                            filename=document.filename,
                            file_type=document.file_type.value,
                        )
                    else:
                        document.file_type = FileType.PDF  # Default fallback
                        self.logger.warning(
                            "Could not determine file_type, using default",
                            document_id=document.id,
                            filename=document.filename,
                        )
                else:
                    document.file_type = FileType.PDF  # Default fallback
                    self.logger.warning(
                        "Missing filename, using default file_type",
                        document_id=document.id,
                    )

            # Ensure status is valid
            if not document.status:
                document.status = DocumentStatus.UPLOADED  # Default status
                self.logger.debug(
                    "Set missing status to default",
                    document_id=document.id,
                    status=document.status.value,
                )

            return document

        except Exception as e:
            self.logger.error(
                "Failed to enrich document metadata",
                document_id=getattr(document, "id", "unknown"),
                error=str(e),
            )
            return document
