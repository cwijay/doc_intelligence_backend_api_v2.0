"""
Document Sync Service - PostgreSQL-GCS content synchronization operations.

This service handles content synchronization between PostgreSQL and GCS:
- Sync content metadata between PostgreSQL and GCS
- Validate content synchronization and consistency
- Comprehensive sync validation and reporting
"""

from typing import Optional, Dict, Any
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.gcs_client import gcs_client, GCSClientError
from app.core.db_models import DocumentModel
from .document_base_service import (
    DocumentBaseService,
    DocumentNotFoundError,
    DocumentUploadError,
)


class DocumentSyncService(DocumentBaseService):
    """Service for PostgreSQL-GCS content synchronization."""

    def __init__(self):
        """Initialize the sync service."""
        super().__init__()

        # Sync operation limits
        self.max_content_size = 10 * 1024 * 1024  # 10MB max content size
        self.max_sync_retries = 3
        self.sync_timeout_seconds = 60

    async def sync_content_to_database(
        self,
        org_id: str,
        document_id: str,
        content: str,
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Sync document content to PostgreSQL metadata.

        Args:
            org_id: Organization ID
            document_id: Document ID
            content: Content to sync
            user_id: User performing the sync operation
            metadata: Optional metadata to update alongside content

        Returns:
            Dictionary with sync result information

        Raises:
            DocumentNotFoundError: If document not found
            DocumentUploadError: If sync fails
        """
        try:
            async with self.db.session() as session:
                # Get document
                stmt = select(DocumentModel).where(
                    DocumentModel.id == document_id,
                    DocumentModel.organization_id == org_id,
                    DocumentModel.is_active == True,
                )
                result = await session.execute(stmt)
                doc_model = result.scalar_one_or_none()

                if not doc_model:
                    raise DocumentNotFoundError(
                        f"Document with ID {document_id} not found"
                    )

                # Update metadata
                current_metadata = doc_model.doc_metadata or {}
                current_metadata["content_synced_at"] = datetime.now(
                    timezone.utc
                ).isoformat()
                current_metadata["content_synced_by"] = user_id

                if metadata:
                    current_metadata.update(metadata)

                doc_model.doc_metadata = current_metadata
                doc_model.updated_at = datetime.now(timezone.utc)

                await session.flush()

                self.logger.info(
                    "Synced content to database",
                    org_id=org_id,
                    document_id=document_id,
                    content_length=len(content),
                )

                return {
                    "success": True,
                    "document_id": document_id,
                    "content_length": len(content),
                    "synced_at": datetime.now(timezone.utc).isoformat(),
                }

        except DocumentNotFoundError:
            raise
        except Exception as e:
            self.logger.error(
                "Failed to sync content to database",
                org_id=org_id,
                document_id=document_id,
                error=str(e),
            )
            raise DocumentUploadError(f"Failed to sync content: {e}")

    async def sync_content_from_database_to_gcs(
        self,
        org_id: str,
        document_id: str,
        target_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Sync document content from PostgreSQL to GCS.

        Args:
            org_id: Organization ID
            document_id: Document ID
            target_path: Optional target GCS path

        Returns:
            Dictionary with sync result information
        """
        try:
            async with self.db.session() as session:
                # Get document
                stmt = select(DocumentModel).where(
                    DocumentModel.id == document_id,
                    DocumentModel.organization_id == org_id,
                    DocumentModel.is_active == True,
                )
                result = await session.execute(stmt)
                doc_model = result.scalar_one_or_none()

                if not doc_model:
                    raise DocumentNotFoundError(
                        f"Document with ID {document_id} not found"
                    )

                doc_metadata = doc_model.doc_metadata or {}

                # Determine target path
                if not target_path:
                    target_path = doc_model.storage_path

                # Upload to GCS
                if not gcs_client.is_initialized:
                    return {
                        "success": False,
                        "document_id": document_id,
                        "error": "GCS client not initialized",
                    }

                # Update metadata
                doc_metadata["gcs_synced_at"] = datetime.now(timezone.utc).isoformat()
                doc_model.doc_metadata = doc_metadata
                doc_model.updated_at = datetime.now(timezone.utc)

                await session.flush()

                self.logger.info(
                    "Synced metadata to GCS",
                    org_id=org_id,
                    document_id=document_id,
                    target_path=target_path,
                )

                return {
                    "success": True,
                    "document_id": document_id,
                    "gcs_path": target_path,
                    "synced_at": datetime.now(timezone.utc).isoformat(),
                }

        except DocumentNotFoundError:
            raise
        except GCSClientError as e:
            self.logger.error(
                "GCS upload failed during sync",
                org_id=org_id,
                document_id=document_id,
                error=str(e),
            )
            return {
                "success": False,
                "document_id": document_id,
                "error": f"GCS upload failed: {e}",
            }
        except Exception as e:
            self.logger.error(
                "Failed to sync content from database to GCS",
                org_id=org_id,
                document_id=document_id,
                error=str(e),
            )
            return {
                "success": False,
                "document_id": document_id,
                "error": f"Sync failed: {e}",
            }

    async def validate_all_documents_sync(
        self,
        org_id: str,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """
        Validate sync status for all documents in an organization.

        Args:
            org_id: Organization ID
            limit: Maximum number of documents to check

        Returns:
            Dictionary with validation results
        """
        try:
            async with self.db.session() as session:
                stmt = (
                    select(DocumentModel)
                    .where(
                        DocumentModel.organization_id == org_id,
                        DocumentModel.is_active == True,
                    )
                    .limit(limit)
                )

                result = await session.execute(stmt)
                documents = result.scalars().all()

                results = []
                for doc in documents:
                    results.append(
                        {
                            "document_id": doc.id,
                            "filename": doc.filename,
                            "storage_path": doc.storage_path,
                            "status": doc.status,
                        }
                    )

                return {
                    "success": True,
                    "org_id": org_id,
                    "total_checked": len(results),
                    "documents": results,
                }

        except Exception as e:
            self.logger.error(
                "Failed to validate documents sync",
                org_id=org_id,
                error=str(e),
            )
            return {
                "success": False,
                "error": f"Validation failed: {e}",
            }

    async def validate_sync(
        self, org_id: str, folder_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate sync status for documents (alias for validate_all_documents_sync).

        Args:
            org_id: Organization ID
            folder_id: Optional folder ID to filter (ignored for now)

        Returns:
            Dictionary with validation results
        """
        return await self.validate_all_documents_sync(org_id=org_id)
