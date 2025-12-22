"""
Document CRUD Service - Basic CRUD operations for document lifecycle management.

This service handles core document lifecycle operations:
- Document creation with two-phase commit (GCS + PostgreSQL)
- Document retrieval with metadata enrichment
- Document status updates and transitions
- Document deletion with cleanup operations
- Organization and folder name resolution
"""

import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from fastapi import UploadFile

from app.models.document import Document, DocumentStatus
from app.models.schemas import DocumentResponse, DocumentUploadResponse
from app.core.gcs_client import gcs_client, GCSClientError
from biz2bricks_core import DocumentModel, AuditAction, AuditEntityType
from app.services.audit_service import audit_service
from app.services.usage_enforcement import (
    update_storage_after_upload,
    update_storage_after_delete,
)
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

    def _model_to_pydantic(self, model: DocumentModel) -> Document:
        """Convert SQLAlchemy model to Pydantic model."""
        return Document(
            id=model.id,
            org_id=model.organization_id,
            folder_id=model.folder_id,
            filename=model.filename,
            original_filename=model.original_filename,
            file_type=model.file_type,
            file_size=model.file_size,
            storage_path=model.storage_path,
            status=model.status,
            uploaded_by=model.uploaded_by,
            is_active=model.is_active,
            metadata=model.doc_metadata or {},
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def create_document(
        self,
        org_id: str,
        file: UploadFile,
        user_id: str,
        folder_id: Optional[str] = None,
        target_path: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        force_override: bool = False,  # Deprecated: silent overwrite is always used
        validation_service=None,
        storage_service=None,
        ip_address: Optional[str] = None,
        session_id: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> DocumentUploadResponse:
        """
        Upload and create a new document with two-phase commit.

        Uses silent overwrite behavior: if a file with the same name exists in the
        same folder, the existing document is soft-deleted and replaced with the new one.
        GCS automatically overwrites the file at the same storage path.

        Args:
            org_id: Organization ID
            file: Uploaded file
            user_id: ID of user uploading the document
            folder_id: Target folder ID (optional)
            target_path: Custom path where file should be saved (optional)
            metadata: Additional metadata (optional)
            force_override: Deprecated, silent overwrite is always used
            validation_service: Validation service dependency
            storage_service: Storage service dependency
            ip_address: Client IP address (for audit)
            session_id: Session ID (for audit)
            user_agent: Client user agent (for audit)

        Returns:
            Document upload response

        Raises:
            DocumentValidationError: If validation fails
            DocumentUploadError: If upload fails
        """
        document_id = None

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

            # Basic virus scan
            if not await validation_service._basic_virus_scan(content, file.filename):
                raise DocumentValidationError("File failed security scan")

            # Generate document ID and sanitize filename
            document_id = str(uuid4())
            sanitized_filename = Document.sanitize_filename(file.filename)

            # Path handling
            if target_path:
                self.logger.info(
                    "Using client-specified target_path",
                    org_id=org_id,
                    original_target_path=target_path,
                )
                storage_path = validation_service._validate_target_path(
                    target_path, file.filename
                )
            else:
                self.logger.info(
                    "Using legacy folder_id approach",
                    org_id=org_id,
                    folder_id=folder_id,
                )
                org_name = await self._get_organization_name(org_id)
                folder_name = (
                    await self._get_folder_name(org_id, folder_id)
                    if folder_id
                    else None
                )

                if folder_name:
                    storage_path = (
                        f"{org_name}/original/{folder_name}/{sanitized_filename}"
                    )
                else:
                    storage_path = f"{org_name}/original/root/{sanitized_filename}"

            # Ensure storage path is unique
            original_storage_path = storage_path
            storage_path = await storage_service._ensure_unique_storage_path(
                org_id, storage_path, file.filename
            )

            if storage_path != original_storage_path:
                self.logger.info(
                    "Storage path modified for uniqueness",
                    org_id=org_id,
                    original_path=original_storage_path,
                    unique_path=storage_path,
                )

            # Check for duplicate filename in the same folder
            # Silent overwrite: always soft-delete existing document if found
            existing_doc = await storage_service.check_duplicate_filename(
                org_id=org_id,
                folder_id=folder_id,
                original_filename=file.filename,
            )

            if existing_doc:
                # Silent overwrite: soft-delete the existing document
                self.logger.info(
                    "Silent overwrite: deleting existing document",
                    org_id=org_id,
                    existing_doc_id=existing_doc["id"],
                    filename=file.filename,
                )
                await self.delete_document(
                    org_id=org_id,
                    document_id=existing_doc["id"],
                    deleted_by_user_id=user_id,
                )

            # Ensure GCS is available
            if not gcs_client.is_initialized:
                error_msg = "GCS client not initialized"
                if gcs_client.initialization_error:
                    error_msg += f": {gcs_client.initialization_error}"
                raise DocumentUploadError(error_msg)

            # TWO-PHASE COMMIT
            now = datetime.now(timezone.utc)
            status_value = (
                DocumentStatus.UPLOADING.value
                if hasattr(DocumentStatus.UPLOADING, "value")
                else DocumentStatus.UPLOADING
            )

            async with self.db.session() as session:
                # Phase 1: Create placeholder document in PostgreSQL
                doc_model = DocumentModel(
                    id=document_id,
                    organization_id=org_id,
                    folder_id=folder_id,
                    filename=sanitized_filename,
                    original_filename=file.filename,
                    file_type=(
                        file_type.value if hasattr(file_type, "value") else file_type
                    ),
                    file_size=actual_size,
                    storage_path=storage_path,
                    status=status_value,
                    uploaded_by=user_id,
                    is_active=True,
                    doc_metadata=metadata or {},
                    created_at=now,
                    updated_at=now,
                )

                session.add(doc_model)
                await session.flush()

                self.logger.info(
                    "Phase 1: Document path reserved in PostgreSQL",
                    org_id=org_id,
                    document_id=document_id,
                    storage_path=storage_path,
                )

                # Phase 2: Upload file to GCS
                try:
                    actual_storage_path = gcs_client.upload_file_to_path(
                        storage_path=storage_path,
                        content=content,
                        content_type=content_type,
                    )

                    self.logger.info(
                        "Phase 2: Document uploaded to GCS",
                        org_id=org_id,
                        document_id=document_id,
                        storage_path=actual_storage_path,
                    )

                except GCSClientError as e:
                    self.logger.error(
                        "Phase 2 failed: GCS upload failed",
                        org_id=org_id,
                        document_id=document_id,
                        error=str(e),
                    )
                    raise DocumentUploadError(f"Failed to upload file to storage: {e}")

                # Phase 3: Update PostgreSQL document status
                uploaded_status = (
                    DocumentStatus.UPLOADED.value
                    if hasattr(DocumentStatus.UPLOADED, "value")
                    else DocumentStatus.UPLOADED
                )
                doc_model.status = uploaded_status
                doc_model.storage_path = actual_storage_path
                doc_model.updated_at = datetime.now(timezone.utc)

                await session.flush()

                self.logger.info(
                    "Phase 3: Document status updated to UPLOADED",
                    org_id=org_id,
                    document_id=document_id,
                )

                document = self._model_to_pydantic(doc_model)
                document_response = DocumentResponse.model_validate(document)

                # Audit logging (non-blocking)
                asyncio.create_task(
                    audit_service.log_event(
                        org_id=org_id,
                        action=AuditAction.UPLOAD,
                        entity_type=AuditEntityType.DOCUMENT,
                        entity_id=document_id,
                        user_id=user_id,
                        details={
                            "filename": sanitized_filename,
                            "original_filename": file.filename,
                            "file_type": (
                                file_type.value
                                if hasattr(file_type, "value")
                                else file_type
                            ),
                            "file_size": actual_size,
                            "storage_path": actual_storage_path,
                            "folder_id": folder_id,
                            "operation": "upload",
                        },
                        ip_address=ip_address,
                        session_id=session_id,
                        user_agent=user_agent,
                    )
                )

                # Update storage usage (non-blocking)
                asyncio.create_task(update_storage_after_upload(org_id, actual_size))

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
            async with self.db.session() as session:
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

                document = self._model_to_pydantic(doc_model)

                # Enrich document metadata
                if storage_service:
                    document = await storage_service._enrich_document_metadata(document)

                # Safety validation
                if validation_service:
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
        updated_by_user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        session_id: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> DocumentResponse:
        """
        Update document status with optional metadata.

        Args:
            org_id: Organization ID
            document_id: Document ID
            new_status: New document status
            metadata: Additional metadata updates
            updated_by_user_id: ID of user who updated the document (for audit)
            ip_address: Client IP address (for audit)
            session_id: Session ID (for audit)
            user_agent: Client user agent (for audit)

        Returns:
            Updated document response

        Raises:
            DocumentNotFoundError: If document not found
        """
        try:
            async with self.db.session() as session:
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

                old_status = doc_model.status
                status_value = (
                    new_status.value if hasattr(new_status, "value") else new_status
                )
                doc_model.status = status_value
                doc_model.updated_at = datetime.now(timezone.utc)

                if metadata:
                    current_metadata = doc_model.doc_metadata or {}
                    current_metadata.update(metadata)
                    doc_model.doc_metadata = current_metadata

                await session.flush()

                document = self._model_to_pydantic(doc_model)

                self.logger.info(
                    "Document status updated",
                    org_id=org_id,
                    document_id=document_id,
                    old_status=old_status,
                    new_status=status_value,
                )

                # Audit logging (non-blocking)
                asyncio.create_task(
                    audit_service.log_event(
                        org_id=org_id,
                        action=AuditAction.UPDATE,
                        entity_type=AuditEntityType.DOCUMENT,
                        entity_id=document_id,
                        user_id=updated_by_user_id,
                        details={
                            "old_status": old_status,
                            "new_status": status_value,
                            "metadata_updated": metadata is not None,
                            "operation": "update",
                        },
                        ip_address=ip_address,
                        session_id=session_id,
                        user_agent=user_agent,
                    )
                )

                return DocumentResponse.model_validate(document)

        except DocumentNotFoundError:
            raise
        except Exception as e:
            self.logger.error(
                "Error updating document status",
                org_id=org_id,
                document_id=document_id,
                error=str(e),
            )
            raise DocumentUploadError(f"Failed to update document status: {e}")

    async def delete_document(
        self,
        org_id: str,
        document_id: str,
        deleted_by_user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        session_id: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Soft delete document with cleanup operations.

        Args:
            org_id: Organization ID
            document_id: Document ID
            deleted_by_user_id: ID of user who deleted the document (for audit)
            ip_address: Client IP address (for audit)
            session_id: Session ID (for audit)
            user_agent: Client user agent (for audit)

        Returns:
            Deletion result with cleanup status
        """
        try:
            async with self.db.session() as session:
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

                filename = doc_model.filename
                storage_path = doc_model.storage_path
                file_size = doc_model.file_size

                # Soft delete
                deleted_status = (
                    DocumentStatus.DELETED.value
                    if hasattr(DocumentStatus.DELETED, "value")
                    else DocumentStatus.DELETED
                )
                doc_model.is_active = False
                doc_model.status = deleted_status
                doc_model.updated_at = datetime.now(timezone.utc)

                await session.flush()

                self.logger.info(
                    "Document soft deleted",
                    org_id=org_id,
                    document_id=document_id,
                    filename=filename,
                    storage_path=storage_path,
                )

                # Audit logging (non-blocking)
                asyncio.create_task(
                    audit_service.log_event(
                        org_id=org_id,
                        action=AuditAction.DELETE,
                        entity_type=AuditEntityType.DOCUMENT,
                        entity_id=document_id,
                        user_id=deleted_by_user_id,
                        details={
                            "deleted_values": {
                                "filename": filename,
                                "storage_path": storage_path,
                            },
                            "operation": "delete",
                        },
                        ip_address=ip_address,
                        session_id=session_id,
                        user_agent=user_agent,
                    )
                )

                # Update storage usage (non-blocking)
                asyncio.create_task(update_storage_after_delete(org_id, file_size))

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
