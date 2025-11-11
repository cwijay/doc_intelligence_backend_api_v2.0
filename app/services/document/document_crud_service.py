"""
Document CRUD Service - Basic CRUD operations for document lifecycle management.

This service handles core document lifecycle operations:
- Document creation with two-phase commit (GCS + Firestore)
- Document retrieval with metadata enrichment
- Document status updates and transitions
- Document deletion with cleanup operations
- Organization and folder name resolution
"""

from typing import Optional, Dict, Any
from datetime import datetime
from fastapi import UploadFile

from app.models.document import Document, DocumentStatus
from app.models.schemas import DocumentResponse, DocumentUploadResponse
from app.core.gcs_client import gcs_client, GCSClientError
from .document_base_service import (
    DocumentBaseService,
    DocumentNotFoundError,
    DocumentValidationError,
    DocumentUploadError,
)


class DocumentCrudService(DocumentBaseService):
    """Service for basic document CRUD operations."""

    def __init__(self):
        """Initialize the CRUD service with dependencies."""
        super().__init__()

        # Import here to avoid circular imports
        from app.services.org_service import organization_service
        from app.services.folder_service import folder_service

        self.org_service = organization_service
        self.folder_service = folder_service

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
            folder_response = await self.folder_service.get_folder(org_id, folder_id)
            return folder_response.name
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

    async def create_document(
        self,
        org_id: str,
        file: UploadFile,
        user_id: str,
        folder_id: Optional[str] = None,
        target_path: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        validation_service=None,
        storage_service=None,
    ) -> DocumentUploadResponse:
        """
        Upload and create a new document with two-phase commit.

        Args:
            org_id: Organization ID
            file: Uploaded file
            user_id: ID of user uploading the document
            folder_id: Target folder ID (optional)
            target_path: Custom path where file should be saved (optional, overrides folder_id)
            metadata: Additional metadata (optional)
            validation_service: Validation service dependency
            storage_service: Storage service dependency

        Returns:
            Document upload response

        Raises:
            DocumentValidationError: If validation fails
            DocumentUploadError: If upload fails
        """
        try:
            # Validate file using validation service
            file_type, content_type = validation_service._validate_file_upload(file)

            # Read file content
            content = await file.read()
            actual_size = len(content)

            # Validate actual file size
            if actual_size > self.max_file_size:
                max_mb = self.max_file_size // (1024 * 1024)
                raise DocumentValidationError(
                    f"File size exceeds maximum limit of {max_mb}MB"
                )

            # Basic virus scan using validation service
            if not await validation_service._basic_virus_scan(content, file.filename):
                raise DocumentValidationError("File failed security scan")

            # Generate document ID and sanitize filename
            document_id = Document.generate_id()
            sanitized_filename = Document.sanitize_filename(file.filename)

            # Enhanced path handling with target_path prioritization
            if target_path:
                # PRIMARY: Use client-specified target path with validation
                self.logger.info(
                    "Using client-specified target_path",
                    org_id=org_id,
                    original_target_path=target_path,
                )

                # Validate and sanitize target path for security
                storage_path = validation_service._validate_target_path(
                    target_path, file.filename
                )

                self.logger.info(
                    "Target path validated and will be used",
                    org_id=org_id,
                    final_storage_path=storage_path,
                )
            else:
                # FALLBACK: Use legacy folder_id approach for backward compatibility
                self.logger.info(
                    "No target_path provided, using legacy folder_id approach",
                    org_id=org_id,
                    folder_id=folder_id,
                )

                org_name = await self._get_organization_name(org_id)
                folder_name = (
                    await self._get_folder_name(org_id, folder_id)
                    if folder_id
                    else None
                )

                # Validate folder exists if specified
                if folder_id and not folder_name:
                    raise DocumentValidationError(f"Folder {folder_id} not found")

                # Build default path structure
                if folder_name:
                    storage_path = (
                        f"{org_name}/original/{folder_name}/{sanitized_filename}"
                    )
                else:
                    storage_path = f"{org_name}/original/root/{sanitized_filename}"

                self.logger.info(
                    "Legacy path generated",
                    org_id=org_id,
                    folder_id=folder_id,
                    folder_name=folder_name,
                    final_storage_path=storage_path,
                )

            # Ensure storage path is unique using storage service
            original_storage_path = storage_path
            storage_path = await storage_service._ensure_unique_storage_path(
                org_id, storage_path, file.filename
            )

            if storage_path != original_storage_path:
                self.logger.info(
                    "Storage path was modified for uniqueness",
                    org_id=org_id,
                    original_path=original_storage_path,
                    unique_path=storage_path,
                    reason="path_already_exists",
                )

            # Ensure GCS is available
            if not gcs_client.is_initialized:
                error_msg = "GCS client not initialized"
                if gcs_client.initialization_error:
                    error_msg += f": {gcs_client.initialization_error}"
                raise DocumentUploadError(error_msg)

            # TWO-PHASE COMMIT: Phase 1 - Reserve path in Firestore
            document = Document(
                id=document_id,
                org_id=org_id,
                folder_id=folder_id,
                filename=sanitized_filename,
                original_filename=file.filename,
                file_type=file_type,
                file_size=actual_size,
                storage_path=storage_path,
                status=DocumentStatus.UPLOADING,  # Indicates incomplete upload
                uploaded_by=user_id,
                metadata=metadata or {},
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )

            # Phase 1: Create placeholder document in Firestore to reserve the path
            doc_ref = self._get_collection(org_id).document(document_id)
            try:
                await doc_ref.set(document.to_dict())
                self.logger.info(
                    "✅ Phase 1: Document path reserved in Firestore",
                    org_id=org_id,
                    document_id=document_id,
                    storage_path=storage_path,
                    status="uploading",
                )
            except Exception as e:
                self.logger.error(
                    "❌ Phase 1 failed: Could not reserve document path in Firestore",
                    org_id=org_id,
                    document_id=document_id,
                    storage_path=storage_path,
                    error=str(e),
                )
                raise DocumentUploadError(f"Failed to reserve document path: {e}")

            # Phase 2: Upload file to GCS
            actual_storage_path = None
            try:
                self.logger.info(
                    "Phase 2: Uploading file to GCS",
                    org_id=org_id,
                    document_id=document_id,
                    original_filename=file.filename,
                    sanitized_filename=sanitized_filename,
                    client_target_path=target_path,
                    final_storage_path=storage_path,
                    file_size=actual_size,
                    content_type=content_type,
                    path_source="target_path" if target_path else "legacy_folder_id",
                )

                # Upload directly to the validated storage path
                actual_storage_path = gcs_client.upload_file_to_path(
                    storage_path=storage_path,
                    content=content,
                    content_type=content_type,
                )

                self.logger.info(
                    "✅ Phase 2: Document uploaded successfully to GCS",
                    org_id=org_id,
                    document_id=document_id,
                    filename=sanitized_filename,
                    storage_path=actual_storage_path,
                    file_size=actual_size,
                    content_type=content_type,
                    used_target_path=target_path is not None,
                    client_specified_path=target_path,
                )

            except GCSClientError as e:
                self.logger.error(
                    "❌ Phase 2 failed: GCS upload failed, rolling back Firestore",
                    org_id=org_id,
                    document_id=document_id,
                    filename=file.filename,
                    error=str(e),
                )

                # Rollback Phase 1: Delete the placeholder document
                try:
                    await doc_ref.delete()
                    self.logger.info(
                        "🔄 Rollback successful: Removed placeholder document from Firestore",
                        org_id=org_id,
                        document_id=document_id,
                    )
                except Exception as rollback_error:
                    self.logger.error(
                        "🚨 Rollback failed: Could not remove placeholder document",
                        org_id=org_id,
                        document_id=document_id,
                        rollback_error=str(rollback_error),
                    )

                raise DocumentUploadError(f"Failed to upload file to storage: {e}")

            # Phase 3: Update Firestore document to mark as successfully uploaded
            try:
                document.status = DocumentStatus.UPLOADED
                document.storage_path = (
                    actual_storage_path  # Use actual path returned by GCS
                )
                document.updated_at = datetime.utcnow()

                # Ensure status is properly converted to string value
                status_value = (
                    document.status.value
                    if hasattr(document.status, "value")
                    else document.status
                )

                await doc_ref.update(
                    {
                        "status": status_value,
                        "storage_path": actual_storage_path,
                        "updated_at": document.updated_at,
                    }
                )

                self.logger.info(
                    "✅ Phase 3: Document status updated to UPLOADED in Firestore",
                    org_id=org_id,
                    document_id=document_id,
                    filename=sanitized_filename,
                    final_storage_path=actual_storage_path,
                )

            except Exception as e:
                self.logger.error(
                    "❌ Phase 3 failed: Could not update document status, cleaning up",
                    org_id=org_id,
                    document_id=document_id,
                    error=str(e),
                )

                # Rollback: Delete both GCS file and Firestore document
                cleanup_errors = []

                # Try to delete GCS file
                if actual_storage_path:
                    try:
                        gcs_client.delete_document_file(actual_storage_path)
                        self.logger.info(
                            "🔄 Rollback: Cleaned up GCS file",
                            storage_path=actual_storage_path,
                        )
                    except Exception as gcs_cleanup_error:
                        cleanup_errors.append(
                            f"GCS cleanup failed: {gcs_cleanup_error}"
                        )
                        self.logger.error(
                            "🚨 GCS cleanup failed during rollback",
                            storage_path=actual_storage_path,
                            error=str(gcs_cleanup_error),
                        )

                # Try to delete Firestore document
                try:
                    await doc_ref.delete()
                    self.logger.info(
                        "🔄 Rollback: Removed document from Firestore",
                        org_id=org_id,
                        document_id=document_id,
                    )
                except Exception as firestore_cleanup_error:
                    cleanup_errors.append(
                        f"Firestore cleanup failed: {firestore_cleanup_error}"
                    )
                    self.logger.error(
                        "🚨 Firestore cleanup failed during rollback",
                        org_id=org_id,
                        document_id=document_id,
                        error=str(firestore_cleanup_error),
                    )

                error_msg = f"Failed to finalize document upload: {e}"
                if cleanup_errors:
                    error_msg += f" (Cleanup issues: {'; '.join(cleanup_errors)})"

                raise DocumentUploadError(error_msg)

            document_response = DocumentResponse.model_validate(document)

            return DocumentUploadResponse(
                success=True,
                message="Document uploaded successfully",
                document=document_response,
            )

        except (DocumentValidationError, DocumentUploadError):
            raise
        except Exception as e:
            self.logger.error(
                "Error creating document",
                org_id=org_id,
                filename=file.filename if file else "unknown",
                error=str(e),
            )
            raise DocumentUploadError(f"Unexpected error during upload: {e}")

    async def get_document(
        self,
        org_id: str,
        document_id: str,
        storage_service=None,
        validation_service=None,
    ) -> DocumentResponse:
        """
        Get document by ID with metadata enrichment.

        Args:
            org_id: Organization ID
            document_id: Document ID
            storage_service: Storage service dependency
            validation_service: Validation service dependency

        Returns:
            Document response

        Raises:
            DocumentNotFoundError: If document not found
        """
        try:
            doc_ref = self._get_collection(org_id).document(document_id)
            doc = await doc_ref.get()

            if not doc.exists:
                raise DocumentNotFoundError(f"Document with ID {document_id} not found")

            document_data = doc.to_dict()
            document = Document.from_dict(document_data, doc.id)

            if not document.is_active:
                raise DocumentNotFoundError(f"Document with ID {document_id} not found")

            # Enrich document metadata to ensure complete data
            document = await storage_service._enrich_document_metadata(document)

            # NUCLEAR SAFETY NET: Final validation to guarantee no "Unknown" values
            document = validation_service._ensure_safe_metadata(document)

            self.logger.debug(
                "Document retrieved", org_id=org_id, document_id=document_id
            )

            return DocumentResponse.model_validate(document)

        except DocumentNotFoundError:
            raise
        except Exception as e:
            self.logger.error(
                "Error retrieving document",
                org_id=org_id,
                document_id=document_id,
                error=str(e),
            )
            raise DocumentNotFoundError(f"Failed to retrieve document: {e}")

    async def update_document_status(
        self,
        org_id: str,
        document_id: str,
        new_status: DocumentStatus,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DocumentResponse:
        """
        Update document status with optional metadata.

        Args:
            org_id: Organization ID
            document_id: Document ID
            new_status: New document status
            metadata: Additional metadata updates

        Returns:
            Updated document response

        Raises:
            DocumentNotFoundError: If document not found
        """
        try:
            doc_ref = self._get_collection(org_id).document(document_id)
            doc = await doc_ref.get()

            if not doc.exists:
                raise DocumentNotFoundError(f"Document with ID {document_id} not found")

            document_data = doc.to_dict()
            document = Document.from_dict(document_data, doc.id)

            if not document.is_active:
                raise DocumentNotFoundError(f"Document with ID {document_id} not found")

            # Prepare update data
            update_data = {
                "status": (
                    new_status.value if hasattr(new_status, "value") else new_status
                ),
                "updated_at": datetime.utcnow(),
            }

            # Add metadata updates if provided
            if metadata:
                current_metadata = document.metadata or {}
                current_metadata.update(metadata)
                update_data["metadata"] = current_metadata

            # Update document in Firestore
            await doc_ref.update(update_data)

            # Update local document object
            document.status = new_status
            document.updated_at = update_data["updated_at"]
            if metadata:
                document.metadata = update_data["metadata"]

            self.logger.info(
                "Document status updated",
                org_id=org_id,
                document_id=document_id,
                old_status=document_data.get("status"),
                new_status=(
                    new_status.value if hasattr(new_status, "value") else new_status
                ),
                has_metadata_updates=bool(metadata),
            )

            return DocumentResponse.model_validate(document)

        except DocumentNotFoundError:
            raise
        except Exception as e:
            self.logger.error(
                "Error updating document status",
                org_id=org_id,
                document_id=document_id,
                new_status=(
                    new_status.value if hasattr(new_status, "value") else new_status
                ),
                error=str(e),
            )
            raise DocumentUploadError(f"Failed to update document status: {e}")

    async def delete_document(self, org_id: str, document_id: str) -> Dict[str, Any]:
        """
        Soft delete document with cleanup operations.

        Args:
            org_id: Organization ID
            document_id: Document ID

        Returns:
            Deletion result with cleanup status
        """
        try:
            doc_ref = self._get_collection(org_id).document(document_id)
            doc = await doc_ref.get()

            if not doc.exists:
                raise DocumentNotFoundError(f"Document with ID {document_id} not found")

            document_data = doc.to_dict()
            document = Document.from_dict(document_data, doc.id)

            if not document.is_active:
                raise DocumentNotFoundError(f"Document with ID {document_id} not found")

            # Soft delete: Mark as inactive
            update_data = {
                "is_active": False,
                "status": DocumentStatus.DELETED.value,
                "updated_at": datetime.utcnow(),
            }

            await doc_ref.update(update_data)

            self.logger.info(
                "Document soft deleted",
                org_id=org_id,
                document_id=document_id,
                filename=document.filename,
                storage_path=document.storage_path,
            )

            return {
                "success": True,
                "message": "Document deleted successfully",
                "document_id": document_id,
                "cleanup_performed": "soft_delete_only",
            }

        except DocumentNotFoundError:
            raise
        except Exception as e:
            self.logger.error(
                "Error deleting document",
                org_id=org_id,
                document_id=document_id,
                error=str(e),
            )
            raise DocumentUploadError(f"Failed to delete document: {e}")
