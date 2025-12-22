"""
Document Service - Main orchestration facade implementing the original DocumentService interface.

This service acts as the main facade for all document operations, composing
specialized services while maintaining backward compatibility with the original API.
It implements the Facade pattern to provide a unified interface to a complex subsystem.

The service delegates operations to specialized services:
- DocumentValidationService: File validation and security
- DocumentStorageService: GCS operations and path management
- DocumentCrudService: Create, read, update, delete operations
- DocumentQueryService: Document listing and pagination
- DocumentDownloadService: Download URL generation
"""

from typing import Optional, Dict, Any, Tuple
from fastapi import UploadFile

from app.models.document import Document, DocumentStatus, FileType
from app.models.schemas import (
    DocumentResponse,
    DocumentList,
    DocumentUploadResponse,
    DocumentDownloadResponse,
    DocumentFilters,
    PaginationParams,
)

# Import specialized services
from .document_base_service import (
    DocumentBaseService,
)
from .document_validation_service import DocumentValidationService
from .document_storage_service import DocumentStorageService
from .document_crud_service import DocumentCrudService
from .document_query_service import DocumentQueryService
from .document_download_service import DocumentDownloadService


class DocumentService(DocumentBaseService):
    """
    Main document service implementing facade pattern.

    This service orchestrates all document operations by delegating to specialized services
    while maintaining the same interface as the original monolithic DocumentService.
    """

    def __init__(self):
        """Initialize the orchestration service with all specialized services."""
        super().__init__()

        # Initialize all specialized services
        self.validation_service = DocumentValidationService()
        self.storage_service = DocumentStorageService()
        self.crud_service = DocumentCrudService()
        self.query_service = DocumentQueryService()
        self.download_service = DocumentDownloadService()

    # ========================================
    # DELEGATED VALIDATION METHODS
    # ========================================

    def _validate_file_upload(self, file: UploadFile) -> Tuple[FileType, str]:
        """Delegate to validation service."""
        return self.validation_service._validate_file_upload(file)

    async def _basic_virus_scan(self, content: bytes, filename: str) -> bool:
        """Delegate to validation service."""
        return await self.validation_service._basic_virus_scan(content, filename)

    def _validate_target_path(self, target_path: str, filename: str) -> str:
        """Delegate to validation service."""
        return self.validation_service._validate_target_path(target_path, filename)

    def _extract_folder_from_storage_path(self, storage_path: str) -> Optional[str]:
        """Delegate to validation service."""
        return self.validation_service._extract_folder_from_storage_path(storage_path)

    def _ensure_safe_metadata(self, document: Document) -> Document:
        """Delegate to validation service."""
        return self.validation_service._ensure_safe_metadata(document)

    # ========================================
    # DELEGATED STORAGE METHODS
    # ========================================

    async def _check_storage_path_exists(self, org_id: str, storage_path: str) -> bool:
        """Delegate to storage service."""
        return await self.storage_service._check_storage_path_exists(
            org_id, storage_path
        )

    def _generate_unique_storage_path(
        self, base_storage_path: str, filename: str
    ) -> str:
        """Delegate to storage service."""
        return self.storage_service._generate_unique_storage_path(
            base_storage_path, filename
        )

    async def _ensure_unique_storage_path(
        self, org_id: str, storage_path: str, filename: str
    ) -> str:
        """Delegate to storage service."""
        return await self.storage_service._ensure_unique_storage_path(
            org_id, storage_path, filename
        )

    async def _enrich_document_metadata(self, document: Document) -> Document:
        """Delegate to storage service."""
        return await self.storage_service._enrich_document_metadata(document)

    # ========================================
    # DELEGATED CRUD METHODS
    # ========================================

    async def create_document(
        self,
        org_id: str,
        file: UploadFile,
        user_id: str,
        folder_id: Optional[str] = None,
        target_path: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        force_override: bool = False,
    ) -> DocumentUploadResponse:
        """Delegate to CRUD service."""
        return await self.crud_service.create_document(
            org_id=org_id,
            file=file,
            user_id=user_id,
            folder_id=folder_id,
            target_path=target_path,
            metadata=metadata,
            force_override=force_override,
            validation_service=self.validation_service,
            storage_service=self.storage_service,
        )

    async def get_document(self, org_id: str, document_id: str) -> DocumentResponse:
        """Delegate to CRUD service."""
        return await self.crud_service.get_document(
            org_id=org_id,
            document_id=document_id,
            storage_service=self.storage_service,
            validation_service=self.validation_service,
        )

    async def list_documents(
        self,
        org_id: str,
        pagination: PaginationParams,
        filters: Optional[DocumentFilters] = None,
    ) -> DocumentList:
        """Delegate to query service."""
        return await self.query_service.list_documents(
            org_id=org_id,
            pagination=pagination,
            filters=filters,
            storage_service=self.storage_service,
            validation_service=self.validation_service,
        )

    async def update_document_status(
        self,
        org_id: str,
        document_id: str,
        new_status: DocumentStatus,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DocumentResponse:
        """Delegate to CRUD service."""
        return await self.crud_service.update_document_status(
            org_id=org_id,
            document_id=document_id,
            new_status=new_status,
            metadata=metadata,
        )

    async def delete_document(self, org_id: str, document_id: str) -> Dict[str, Any]:
        """Delegate to CRUD service."""
        return await self.crud_service.delete_document(
            org_id=org_id, document_id=document_id
        )

    async def download_document(
        self, org_id: str, document_id: str, expiration_minutes: int = 60
    ) -> DocumentDownloadResponse:
        """Delegate to download service."""
        return await self.download_service.download_document(
            org_id=org_id,
            document_id=document_id,
            expiration_minutes=expiration_minutes,
            crud_service=self.crud_service,
        )


# Global service instance for backward compatibility
document_service = DocumentService()
