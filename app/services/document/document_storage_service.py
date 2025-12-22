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
from biz2bricks_core import DocumentModel
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

    async def check_duplicate_filename(
        self, org_id: str, folder_id: str | None, original_filename: str
    ) -> dict | None:
        """
        Check if a document with the same original filename exists in the folder.

        Args:
            org_id: Organization ID
            folder_id: Folder ID (None for root folder)
            original_filename: Original filename to check

        Returns:
            Dictionary with existing document info if duplicate exists, None otherwise
        """
        try:
            async with self.db.session() as session:
                stmt = (
                    select(DocumentModel)
                    .where(
                        DocumentModel.organization_id == org_id,
                        DocumentModel.folder_id == folder_id,
                        DocumentModel.original_filename == original_filename,
                        DocumentModel.is_active == True,
                    )
                    .limit(1)
                )
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    self.logger.info(
                        "Duplicate filename found",
                        org_id=org_id,
                        folder_id=folder_id,
                        original_filename=original_filename,
                        existing_doc_id=existing.id,
                    )
                    return {
                        "id": existing.id,
                        "filename": existing.original_filename,
                        "created_at": (
                            existing.created_at.isoformat()
                            if existing.created_at
                            else None
                        ),
                        "uploaded_by": existing.uploaded_by,
                    }
                return None

        except Exception as e:
            self.logger.error(
                "Error checking duplicate filename",
                org_id=org_id,
                folder_id=folder_id,
                original_filename=original_filename,
                error=str(e),
            )
            # On error, return None to allow upload (fail open for this check)
            return None

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
        Return the original storage path - duplicates are handled via silent overwrite.

        The system now uses silent overwrite behavior:
        - If a file with the same path exists, it will be overwritten in GCS
        - The old PostgreSQL record is soft-deleted before creating the new one
        - No timestamp suffixes are added to filenames

        Args:
            org_id: Organization ID
            storage_path: Desired storage path
            filename: Original filename (unused, kept for API compatibility)

        Returns:
            The original storage path (no modifications)
        """
        self.logger.debug(
            "Using original storage path (silent overwrite mode)",
            org_id=org_id,
            storage_path=storage_path,
        )
        return storage_path

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
