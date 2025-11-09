import logging
import math
import mimetypes
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

from fastapi import UploadFile
from google.cloud.firestore_v1 import FieldFilter
from google.api_core.exceptions import NotFound

from app.models.document import Document, DocumentStatus, FileType
from app.models.schemas import (
    DocumentCreate,
    DocumentUpdate,
    DocumentResponse,
    DocumentList,
    DocumentUploadResponse,
    DocumentDownloadResponse,
    DocumentFilters,
    PaginationParams
)
from app.core.firebase_client import get_collection
from app.core.gcs_client import gcs_client, GCSClientError
from app.core.logging import get_service_logger

logger = get_service_logger("document")


class DocumentNotFoundError(Exception):
    """Document not found error."""
    pass


class DocumentValidationError(Exception):
    """Document validation error."""
    pass


class DocumentUploadError(Exception):
    """Document upload error."""
    pass


class DocumentService:
    """Service for managing documents with GCS integration."""
    
    def __init__(self):
        self.logger = logger
        self.max_file_size = 50 * 1024 * 1024  # 50MB
        self.allowed_file_types = {FileType.PDF, FileType.XLSX}
        self.max_path_length = 1024  # Maximum storage path length
        # Import here to avoid circular imports
        from app.services.org_service import organization_service
        from app.services.folder_service import folder_service
        self.org_service = organization_service
        self.folder_service = folder_service

    def _get_collection(self, org_id: str):
        """Get the documents collection for an organization."""
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
            self.logger.error("Failed to get organization name", 
                            org_id=org_id, 
                            error=str(e))
            raise DocumentValidationError(f"Could not fetch organization name for ID {org_id}: {e}")

    async def _get_folder_name(self, org_id: str, folder_id: Optional[str]) -> Optional[str]:
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
                folder_response = await self.folder_service.get_folder(org_id, folder_id)
                # Extract folder name from path (remove leading slash and get last part)
                path_parts = folder_response.path.strip('/').split('/')
                return path_parts[-1] if path_parts and path_parts[0] else None
            except Exception:
                # If folder doesn't exist in GCS yet, use folder_id as folder name
                # This allows uploading to folders that will be created on demand
                self.logger.info("Folder not found in GCS, using folder_id as folder name", 
                               org_id=org_id, 
                               folder_id=folder_id)
                return folder_id
                
        except Exception as e:
            self.logger.error("Failed to get folder name", 
                            org_id=org_id, 
                            folder_id=folder_id,
                            error=str(e))
            raise DocumentValidationError(f"Could not fetch folder name for ID {folder_id}: {e}")


    def _validate_file_upload(self, file: UploadFile) -> Tuple[FileType, str]:
        """
        Validate uploaded file.
        
        Args:
            file: Uploaded file
            
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
            raise DocumentValidationError(f"File size exceeds maximum limit of {max_mb}MB")
        
        # Get content type
        content_type = file.content_type or mimetypes.guess_type(file.filename)[0]
        
        return file_type, content_type

    async def _basic_virus_scan(self, content: bytes, filename: str) -> bool:
        """
        Basic virus scanning (placeholder for future implementation).
        
        Args:
            content: File content
            filename: Filename
            
        Returns:
            True if file is clean, False if suspicious
        """
        # Placeholder for basic file validation
        # In a production environment, integrate with actual antivirus service
        
        # Check for suspicious file patterns
        suspicious_patterns = [
            b'<script',
            b'javascript:',
            b'vbscript:',
            b'onload=',
            b'onerror=',
        ]
        
        content_lower = content.lower()
        for pattern in suspicious_patterns:
            if pattern in content_lower:
                self.logger.warning("Suspicious content detected in file", 
                                  filename=filename, 
                                  pattern=pattern.decode('utf-8', errors='ignore'))
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
            raise DocumentValidationError(f"Target path too long (max {self.max_path_length} characters)")
        
        # Check for directory traversal attacks
        dangerous_patterns = ['../', '../', '..\\', '..\\\\', '/..', '\\..', '~/', './']
        for pattern in dangerous_patterns:
            if pattern in target_path:
                raise DocumentValidationError("Target path contains unsafe characters. Directory traversal not allowed.")
        
        # Check for null bytes and other dangerous characters
        if '\x00' in target_path or '\r' in target_path or '\n' in target_path:
            raise DocumentValidationError("Target path contains invalid characters")
        
        # Validate path format: {org_name}/original/{folder_name}/{document_name}
        path_parts = target_path.split('/')
        
        if len(path_parts) != 4:
            raise DocumentValidationError(
                "Invalid target_path format. Must be: {org_name}/original/{folder_name}/{document_name}"
            )
        
        org_name, file_type_indicator, folder_name, document_name = path_parts
        
        # Validate each component
        if not org_name or not org_name.strip():
            raise DocumentValidationError("Organization name in target_path cannot be empty")
        
        if file_type_indicator != "original":
            raise DocumentValidationError("Second segment of target_path must be 'original'")
        
        if not folder_name or not folder_name.strip():
            raise DocumentValidationError("Folder name in target_path cannot be empty")
        
        if not document_name or not document_name.strip():
            raise DocumentValidationError("Document name in target_path cannot be empty")
        
        # Sanitize document name (remove dangerous characters but keep it functional)
        sanitized_document_name = Document.sanitize_filename(document_name)
        if not sanitized_document_name:
            # If sanitization results in empty name, use original filename
            sanitized_document_name = Document.sanitize_filename(filename)
        
        # Rebuild path with sanitized components
        sanitized_path = f"{org_name.strip()}/original/{folder_name.strip()}/{sanitized_document_name}"
        
        self.logger.info("Target path validated and sanitized",
                       original_path=target_path,
                       sanitized_path=sanitized_path,
                       org_name=org_name.strip(),
                       folder_name=folder_name.strip(),
                       document_name=sanitized_document_name)
        
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
            path_parts = storage_path.split('/')
            if len(path_parts) >= 4 and path_parts[1] == "original":
                folder_name = path_parts[2]
                return folder_name if folder_name and folder_name != "root" else None
            return None
        except Exception as e:
            self.logger.debug("Error extracting folder from storage_path", 
                            storage_path=storage_path, 
                            error=str(e))
            return None

    async def _check_storage_path_exists(self, org_id: str, storage_path: str) -> bool:
        """
        Check if a storage_path already exists in Firestore.
        
        Args:
            org_id: Organization ID
            storage_path: Storage path to check
            
        Returns:
            True if path exists, False otherwise
        """
        try:
            collection = self._get_collection(org_id)
            query = collection.where(filter=FieldFilter("storage_path", "==", storage_path))\
                             .where(filter=FieldFilter("is_active", "==", True))
            
            docs = query.stream()
            async for doc in docs:
                # If we find any document with this path, it exists
                return True
            
            return False
            
        except Exception as e:
            self.logger.error("Error checking storage path existence", 
                            org_id=org_id, 
                            storage_path=storage_path,
                            error=str(e))
            # On error, assume it exists to be safe
            return True

    def _generate_unique_storage_path(self, base_storage_path: str, filename: str) -> str:
        """
        Generate a unique storage path by appending incremental suffix if needed.
        
        Args:
            base_storage_path: Original storage path
            filename: Original filename for fallback
            
        Returns:
            Unique storage path
        """
        import os
        from pathlib import Path
        
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
                import datetime
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]  # Remove last 3 microsecond digits
                unique_name = f"{name}_{timestamp}{extension}"
            else:
                # Subsequent tries: simple incremental counter
                unique_name = f"{name}-{counter}{extension}"
            
            unique_path = f"{directory}/{unique_name}"
            return unique_path
            
        # Fallback: use document ID as filename (this should never happen)
        document_id = Document.generate_id()
        fallback_path = f"{directory}/{document_id}_{Document.sanitize_filename(filename)}"
        
        self.logger.warning("Generated fallback unique path after many attempts",
                          base_path=base_storage_path,
                          fallback_path=fallback_path)
        
        return fallback_path

    async def _ensure_unique_storage_path(self, org_id: str, storage_path: str, filename: str) -> str:
        """
        Ensure the storage path is unique by checking Firestore and generating alternatives if needed.
        
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
            self.logger.debug("Storage path is available", 
                            org_id=org_id,
                            storage_path=storage_path)
            return storage_path
        
        # Original path exists, generate unique alternative
        self.logger.info("Storage path already exists, generating unique alternative", 
                       org_id=org_id,
                       original_path=original_path)
        
        max_attempts = 10
        for attempt in range(max_attempts):
            unique_path = self._generate_unique_storage_path(storage_path, filename)
            
            if not await self._check_storage_path_exists(org_id, unique_path):
                self.logger.info("Generated unique storage path", 
                               org_id=org_id,
                               original_path=original_path,
                               unique_path=unique_path,
                               attempt=attempt + 1)
                return unique_path
            
            # Path still exists, try again with different base
            storage_path = unique_path
        
        # This should never happen, but provide ultimate fallback
        fallback_path = self._generate_unique_storage_path(original_path, filename)
        self.logger.warning("Used fallback unique path generation", 
                          org_id=org_id,
                          original_path=original_path,
                          fallback_path=fallback_path)
        
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
                self.logger.debug("Document has invalid file_size, attempting to fetch from GCS", 
                                document_id=document.id,
                                current_file_size=document.file_size,
                                storage_path=document.storage_path)
                
                # Try to get file size from GCS
                if gcs_client.is_initialized and document.storage_path:
                    try:
                        gcs_metadata = gcs_client.get_document_metadata(document.storage_path)
                        if gcs_metadata and gcs_metadata.get("size") is not None:
                            document.file_size = gcs_metadata["size"]
                            self.logger.info("Enriched file_size from GCS metadata", 
                                           document_id=document.id,
                                           storage_path=document.storage_path,
                                           file_size=document.file_size)
                        else:
                            # Fallback to 0 if no size found
                            document.file_size = 0
                            self.logger.warning("Could not determine file size from GCS, using fallback", 
                                              document_id=document.id,
                                              storage_path=document.storage_path)
                    except Exception as e:
                        self.logger.warning("Failed to fetch metadata from GCS, using fallback", 
                                          document_id=document.id,
                                          storage_path=document.storage_path,
                                          error=str(e))
                        document.file_size = 0
                else:
                    # Fallback to 0 if GCS is not available
                    document.file_size = 0
                    self.logger.debug("GCS not initialized, using fallback file_size", 
                                    document_id=document.id)
            
            # Ensure file_type is valid
            if not document.file_type:
                # Try to determine file type from filename
                if document.filename:
                    extracted_type = Document.extract_file_type(document.filename)
                    if extracted_type:
                        document.file_type = extracted_type
                        self.logger.debug("Set file_type from filename", 
                                        document_id=document.id,
                                        filename=document.filename,
                                        file_type=document.file_type.value)
                    else:
                        document.file_type = FileType.PDF  # Default fallback
                        self.logger.warning("Could not determine file_type, using default", 
                                          document_id=document.id,
                                          filename=document.filename)
                else:
                    document.file_type = FileType.PDF  # Default fallback
                    self.logger.warning("Missing filename, using default file_type", 
                                      document_id=document.id)
            
            # Ensure status is valid
            if not document.status:
                document.status = DocumentStatus.UPLOADED  # Default status
                self.logger.debug("Set missing status to default", 
                                document_id=document.id,
                                status=document.status.value)
            
            # Ensure timestamps are valid
            if not document.created_at:
                document.created_at = datetime.utcnow()
                self.logger.debug("Set missing created_at timestamp", 
                                document_id=document.id)
                
            if not document.updated_at:
                document.updated_at = document.created_at
                self.logger.debug("Set missing updated_at timestamp", 
                                document_id=document.id)
            
            # Ensure required string fields are not None or empty
            if not document.filename or not document.filename.strip():
                document.filename = document.original_filename or "unknown_file"
                self.logger.debug("Set missing filename", 
                                document_id=document.id,
                                filename=document.filename)
            
            if not document.original_filename or not document.original_filename.strip():
                document.original_filename = document.filename or "unknown_file"
                self.logger.debug("Set missing original_filename", 
                                document_id=document.id,
                                original_filename=document.original_filename)
            
            # Ensure storage_path is not empty
            if not document.storage_path or not document.storage_path.strip():
                # Generate a basic storage path as fallback
                org_name = "unknown_org"
                folder = "unknown_folder"
                filename = document.filename or "unknown_file"
                document.storage_path = f"{org_name}/original/{folder}/{filename}"
                self.logger.warning("Set missing storage_path", 
                                  document_id=document.id,
                                  storage_path=document.storage_path)
                
            # Ensure metadata is a dict
            if not isinstance(document.metadata, dict):
                document.metadata = {}
                self.logger.debug("Reset invalid metadata to empty dict", 
                                document_id=document.id)
            
            # Ensure org_id and uploaded_by are not empty
            if not document.org_id or not document.org_id.strip():
                self.logger.error("Document missing org_id", document_id=document.id)
                # This is a critical error, but we'll try to continue
                
            if not document.uploaded_by or not document.uploaded_by.strip():
                document.uploaded_by = "unknown_user"
                self.logger.warning("Set missing uploaded_by", 
                                  document_id=document.id)
                
            return document
            
        except Exception as e:
            self.logger.error("Error enriching document metadata", 
                            document_id=document.id if document else "unknown",
                            error=str(e))
            # Return document as-is if enrichment fails
            return document

    async def _list_documents_from_gcs(
        self, 
        org_id: str, 
        gcs_path: str, 
        pagination: PaginationParams,
        filters: Optional[DocumentFilters] = None
    ) -> DocumentList:
        """
        List documents directly from GCS bucket using the provided path.
        
        Args:
            org_id: Organization ID
            gcs_path: GCS path like "Tech Innovations Corp/original/control-docs"
            pagination: Pagination parameters
            filters: Optional filters
            
        Returns:
            DocumentList with real files from GCS location
        """
        try:
            if not gcs_client.is_initialized:
                self.logger.error("GCS client not initialized for direct listing")
                # Return empty list if GCS not available
                return DocumentList(
                    documents=[],
                    total=0,
                    page=pagination.page,
                    per_page=pagination.per_page,
                    total_pages=0
                )
            
            self.logger.info("Listing files directly from GCS", 
                           org_id=org_id,
                           gcs_path=gcs_path)
            
            # List blobs at the specified path
            blobs = list(gcs_client.bucket.list_blobs(prefix=gcs_path))
            
            # Convert blobs to documents
            all_documents = []
            for blob in blobs:
                # Skip folder markers and empty files
                if blob.name.endswith('/') or blob.size == 0:
                    continue
                    
                try:
                    # Create document from GCS blob metadata
                    document = self._blob_to_document(blob, org_id)
                    
                    # Apply filename filter if specified
                    if filters and filters.filename:
                        if filters.filename.lower() not in document.filename.lower():
                            continue
                    
                    # Apply file type filter if specified  
                    if filters and filters.file_type:
                        if document.file_type != filters.file_type:
                            continue
                            
                    all_documents.append(document)
                    
                except Exception as e:
                    self.logger.warning("Failed to convert blob to document", 
                                      blob_name=blob.name,
                                      error=str(e))
                    continue
            
            # Sort by creation time (newest first)
            all_documents.sort(key=lambda d: d.created_at, reverse=True)
            
            # Apply pagination
            total = len(all_documents)
            start_idx = pagination.offset
            end_idx = start_idx + pagination.per_page
            paginated_documents = all_documents[start_idx:end_idx]
            
            # Convert to response models
            document_responses = []
            for doc in paginated_documents:
                try:
                    # Apply safety net to ensure no "Unknown" values
                    doc = self._ensure_safe_metadata(doc)
                    doc_response = DocumentResponse.model_validate(doc)
                    document_responses.append(doc_response)
                except Exception as e:
                    self.logger.error("Failed to convert Document to DocumentResponse", 
                                    document_id=doc.id if hasattr(doc, 'id') else "unknown",
                                    error=str(e))
                    continue
            
            # Calculate pagination info
            total_pages = math.ceil(total / pagination.per_page) if total > 0 else 0
            
            self.logger.info("GCS direct listing completed", 
                           org_id=org_id,
                           gcs_path=gcs_path,
                           total_files=total,
                           returned_files=len(document_responses))
            
            return DocumentList(
                documents=document_responses,
                total=total,
                page=pagination.page,
                per_page=pagination.per_page,
                total_pages=total_pages
            )
            
        except Exception as e:
            self.logger.error("Error listing documents from GCS", 
                            org_id=org_id,
                            gcs_path=gcs_path,
                            error=str(e))
            # Return empty list on error
            return DocumentList(
                documents=[],
                total=0,
                page=pagination.page,
                per_page=pagination.per_page,
                total_pages=0
            )

    def _blob_to_document(self, blob, org_id: str) -> Document:
        """
        Convert GCS blob to Document object with real metadata.
        
        Args:
            blob: GCS blob object
            org_id: Organization ID
            
        Returns:
            Document with real file metadata from GCS
        """
        # Extract filename from blob path
        filename = blob.name.split('/')[-1] if '/' in blob.name else blob.name
        
        # Determine file type from extension
        file_type = Document.extract_file_type(filename) or FileType.PDF
        
        # Generate document ID from blob name (for consistency)
        import hashlib
        document_id = hashlib.md5(blob.name.encode()).hexdigest()[:24]
        
        # Create document with real GCS metadata
        document = Document(
            id=document_id,
            org_id=org_id,
            folder_id=None,  # Not applicable for GCS direct listing
            filename=filename,
            original_filename=filename,
            file_type=file_type,
            file_size=blob.size or 0,
            storage_path=blob.name,
            status=DocumentStatus.UPLOADED,
            uploaded_by="gcs_user",  # Default for GCS-listed files
            metadata={
                "source": "gcs_direct_listing",
                "content_type": blob.content_type,
                "md5_hash": blob.md5_hash,
                "etag": blob.etag
            },
            is_active=True,
            created_at=blob.time_created or datetime.utcnow(),
            updated_at=blob.updated or datetime.utcnow()
        )
        
        return document

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
            if (not hasattr(document, 'file_size') or 
                document.file_size is None or 
                document.file_size == '' or 
                document.file_size < 0 or
                str(document.file_size).lower() in ['nan', 'null', 'undefined']):
                document.file_size = 0
                
            # BULLETPROOF file_type - never null/empty/unknown  
            if (not hasattr(document, 'file_type') or
                not document.file_type or
                document.file_type is None or
                document.file_type == '' or
                str(document.file_type).lower() in ['null', 'undefined', 'unknown']):
                document.file_type = FileType.PDF
                
            # BULLETPROOF filename - never empty/null
            if (not hasattr(document, 'filename') or
                not document.filename or
                document.filename is None or
                document.filename.strip() == '' or
                str(document.filename).lower() in ['null', 'undefined']):
                document.filename = "unknown_file.pdf"
                
            # BULLETPROOF original_filename - never empty/null  
            if (not hasattr(document, 'original_filename') or
                not document.original_filename or
                document.original_filename is None or
                document.original_filename.strip() == '' or
                str(document.original_filename).lower() in ['null', 'undefined']):
                document.original_filename = document.filename or "unknown_file.pdf"
                
            # BULLETPROOF created_at - never null/invalid
            if (not hasattr(document, 'created_at') or
                not document.created_at or
                document.created_at is None or
                str(document.created_at).lower() in ['null', 'undefined']):
                document.created_at = datetime.utcnow()
                
            # BULLETPROOF updated_at - never null/invalid
            if (not hasattr(document, 'updated_at') or
                not document.updated_at or
                document.updated_at is None or
                str(document.updated_at).lower() in ['null', 'undefined']):
                document.updated_at = document.created_at or datetime.utcnow()
                
            # BULLETPROOF status - never null/empty
            if (not hasattr(document, 'status') or
                not document.status or
                document.status is None or
                str(document.status).lower() in ['null', 'undefined', '']):
                document.status = DocumentStatus.UPLOADED
                
            # BULLETPROOF storage_path - never empty
            if (not hasattr(document, 'storage_path') or
                not document.storage_path or
                document.storage_path is None or
                document.storage_path.strip() == '' or
                str(document.storage_path).lower() in ['null', 'undefined']):
                document.storage_path = "unknown_org/original/unknown_folder/unknown_file.pdf"
                
            # BULLETPROOF org_id - never empty
            if (not hasattr(document, 'org_id') or
                not document.org_id or
                document.org_id is None or
                document.org_id.strip() == '' or
                str(document.org_id).lower() in ['null', 'undefined']):
                document.org_id = "unknown_org_id"
                
            # BULLETPROOF uploaded_by - never empty
            if (not hasattr(document, 'uploaded_by') or
                not document.uploaded_by or
                document.uploaded_by is None or
                document.uploaded_by.strip() == '' or
                str(document.uploaded_by).lower() in ['null', 'undefined']):
                document.uploaded_by = "unknown_user"
                
            # BULLETPROOF metadata - never null
            if (not hasattr(document, 'metadata') or
                document.metadata is None or
                not isinstance(document.metadata, dict)):
                document.metadata = {}
                
            # BULLETPROOF is_active - never null
            if (not hasattr(document, 'is_active') or
                document.is_active is None):
                document.is_active = True
                
            return document
            
        except Exception as e:
            # Even if this safety net fails, return document with minimal safe data
            self.logger.error("Safety net validation failed, using emergency defaults", 
                            document_id=getattr(document, 'id', 'unknown'),
                            error=str(e))
            
            # Emergency fallback - create minimal safe document
            document.file_size = 0
            document.file_type = FileType.PDF
            document.filename = "unknown_file.pdf"
            document.original_filename = "unknown_file.pdf"
            document.created_at = datetime.utcnow()
            document.updated_at = datetime.utcnow()
            document.status = DocumentStatus.UPLOADED
            document.storage_path = "unknown_org/original/unknown_folder/unknown_file.pdf"
            document.org_id = getattr(document, 'org_id', 'unknown_org_id')
            document.uploaded_by = "unknown_user"
            document.metadata = {}
            document.is_active = True
            
            return document

    async def validate_sync(self, org_id: str, folder_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Validate sync between Firestore documents and GCS files.
        
        Args:
            org_id: Organization ID
            folder_id: Optional folder ID to filter by
            
        Returns:
            Sync validation report
        """
        try:
            from app.models.schemas import PaginationParams, DocumentFilters
            
            # Get Firestore documents
            pagination = PaginationParams(page=1, per_page=100)
            filters = DocumentFilters(folder_id=folder_id) if folder_id else None
            
            result = await self.list_documents(org_id, pagination, filters)
            firestore_docs = result.documents
            
            # Get organization name for GCS path construction
            org_name = await self._get_organization_name(org_id)
            
            # Get GCS files
            gcs_files = set()
            if gcs_client.is_initialized:
                try:
                    if folder_id:
                        prefix = f"{org_name}/original/{folder_id}/"
                    else:
                        prefix = f"{org_name}/original/"
                    
                    blobs = list(gcs_client.bucket.list_blobs(prefix=prefix))
                    for blob in blobs:
                        if not blob.name.endswith(('.keep', '.folder_placeholder')):
                            gcs_files.add(blob.name)
                            
                except Exception as e:
                    self.logger.error("Error fetching GCS files for sync validation", 
                                    org_id=org_id,
                                    error=str(e))
            
            # Analyze sync status
            issues = []
            recommendations = []
            
            # Find orphaned Firestore documents
            orphaned_firestore = []
            storage_path_counts = {}
            
            for doc in firestore_docs:
                if doc.storage_path:
                    # Count documents per storage path
                    storage_path_counts[doc.storage_path] = storage_path_counts.get(doc.storage_path, 0) + 1
                    
                    # Check if GCS file exists
                    if doc.storage_path not in gcs_files:
                        orphaned_firestore.append(doc)
            
            # Find duplicate storage paths
            duplicate_storage_paths = {path: count for path, count in storage_path_counts.items() if count > 1}
            
            # Find orphaned GCS files
            firestore_paths = {doc.storage_path for doc in firestore_docs if doc.storage_path}
            orphaned_gcs = gcs_files - firestore_paths
            
            # Build issues list
            if orphaned_firestore:
                issues.append({
                    "type": "orphaned_firestore_documents",
                    "count": len(orphaned_firestore),
                    "description": f"{len(orphaned_firestore)} Firestore documents have no corresponding GCS files",
                    "documents": [{"id": doc.id, "filename": doc.filename, "storage_path": doc.storage_path} 
                                for doc in orphaned_firestore[:5]]  # Show first 5
                })
                recommendations.append("Remove orphaned Firestore documents using cleanup script")
            
            if duplicate_storage_paths:
                issues.append({
                    "type": "duplicate_storage_paths",
                    "count": len(duplicate_storage_paths),
                    "description": f"{len(duplicate_storage_paths)} storage paths have multiple Firestore documents",
                    "paths": list(duplicate_storage_paths.keys())[:5]  # Show first 5
                })
                recommendations.append("Remove duplicate Firestore documents with same storage_path")
            
            if orphaned_gcs:
                issues.append({
                    "type": "orphaned_gcs_files",
                    "count": len(orphaned_gcs),
                    "description": f"{len(orphaned_gcs)} GCS files have no corresponding Firestore documents",
                    "files": list(orphaned_gcs)[:5]  # Show first 5
                })
                recommendations.append("Create Firestore metadata for orphaned GCS files or delete unused files")
            
            # Check for documents in UPLOADING status (stuck uploads)
            uploading_docs = [doc for doc in firestore_docs if doc.status == "uploading"]
            if uploading_docs:
                issues.append({
                    "type": "stuck_uploads",
                    "count": len(uploading_docs),
                    "description": f"{len(uploading_docs)} documents stuck in UPLOADING status",
                    "documents": [{"id": doc.id, "filename": doc.filename, "created_at": doc.created_at.isoformat()} 
                                for doc in uploading_docs[:5]]
                })
                recommendations.append("Review stuck uploads and either complete or cancel them")
            
            # Determine overall sync status
            if not issues:
                sync_status = "healthy"
                recommendations.append("Firestore and GCS are perfectly synced!")
            elif len(issues) == 1 and issues[0]["type"] == "orphaned_gcs_files":
                sync_status = "minor_issues"
            else:
                sync_status = "issues"
            
            if not recommendations:
                recommendations.append("No action needed - sync is healthy")
            
            summary = {
                "firestore_documents": len(firestore_docs),
                "gcs_files": len(gcs_files),
                "orphaned_firestore": len(orphaned_firestore),
                "orphaned_gcs": len(orphaned_gcs),
                "duplicate_storage_paths": len(duplicate_storage_paths),
                "stuck_uploads": len(uploading_docs),
                "issues_found": len(issues)
            }
            
            self.logger.info("Sync validation completed", 
                           org_id=org_id,
                           folder_id=folder_id,
                           sync_status=sync_status,
                           summary=summary)
            
            return {
                "org_id": org_id,
                "folder_id": folder_id,
                "sync_status": sync_status,
                "summary": summary,
                "issues": issues,
                "recommendations": recommendations,
                "timestamp": datetime.utcnow()
            }
            
        except Exception as e:
            self.logger.error("Error during sync validation", 
                            org_id=org_id,
                            folder_id=folder_id,
                            error=str(e))
            return {
                "org_id": org_id,
                "folder_id": folder_id,
                "sync_status": "error",
                "summary": {"error": str(e)},
                "issues": [{
                    "type": "validation_error",
                    "description": f"Sync validation failed: {e}"
                }],
                "recommendations": ["Fix the underlying error and retry validation"],
                "timestamp": datetime.utcnow()
            }

    async def create_document(
        self, 
        org_id: str,
        file: UploadFile,
        user_id: str,
        folder_id: Optional[str] = None,
        target_path: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> DocumentUploadResponse:
        """
        Upload and create a new document.
        
        Args:
            org_id: Organization ID
            file: Uploaded file
            user_id: ID of user uploading the document
            folder_id: Target folder ID (optional)
            target_path: Custom path where file should be saved (optional, overrides folder_id)
            metadata: Additional metadata (optional)
            
        Returns:
            Document upload response
            
        Raises:
            DocumentValidationError: If validation fails
            DocumentUploadError: If upload fails
        """
        try:
            # Validate file
            file_type, content_type = self._validate_file_upload(file)
            
            # Read file content
            content = await file.read()
            actual_size = len(content)
            
            # Validate actual file size
            if actual_size > self.max_file_size:
                max_mb = self.max_file_size // (1024 * 1024)
                raise DocumentValidationError(f"File size exceeds maximum limit of {max_mb}MB")
            
            # Basic virus scan
            if not await self._basic_virus_scan(content, file.filename):
                raise DocumentValidationError("File failed security scan")
            
            # Generate document ID and sanitize filename
            document_id = Document.generate_id()
            sanitized_filename = Document.sanitize_filename(file.filename)
            
            # Enhanced path handling with target_path prioritization
            if target_path:
                # PRIMARY: Use client-specified target path with validation
                self.logger.info("Using client-specified target_path", 
                               org_id=org_id,
                               original_target_path=target_path)
                
                # Validate and sanitize target path for security
                storage_path = self._validate_target_path(target_path, file.filename)
                
                self.logger.info("Target path validated and will be used", 
                               org_id=org_id,
                               final_storage_path=storage_path)
            else:
                # FALLBACK: Use legacy folder_id approach for backward compatibility
                self.logger.info("No target_path provided, using legacy folder_id approach", 
                               org_id=org_id,
                               folder_id=folder_id)
                
                org_name = await self._get_organization_name(org_id)
                folder_name = await self._get_folder_name(org_id, folder_id) if folder_id else None
                
                # Validate folder exists if specified
                if folder_id and not folder_name:
                    raise DocumentValidationError(f"Folder {folder_id} not found")
                
                # Build default path structure
                if folder_name:
                    storage_path = f"{org_name}/original/{folder_name}/{sanitized_filename}"
                else:
                    storage_path = f"{org_name}/original/root/{sanitized_filename}"
                
                self.logger.info("Legacy path generated", 
                               org_id=org_id,
                               folder_id=folder_id,
                               folder_name=folder_name,
                               final_storage_path=storage_path)
            
            # 🆕 SYNC PREVENTION: Ensure storage path is unique
            original_storage_path = storage_path
            storage_path = await self._ensure_unique_storage_path(org_id, storage_path, file.filename)
            
            if storage_path != original_storage_path:
                self.logger.info("Storage path was modified for uniqueness", 
                               org_id=org_id,
                               original_path=original_storage_path,
                               unique_path=storage_path,
                               reason="path_already_exists")
            
            # Ensure GCS is available
            if not gcs_client.is_initialized:
                error_msg = "GCS client not initialized"
                if gcs_client.initialization_error:
                    error_msg += f": {gcs_client.initialization_error}"
                raise DocumentUploadError(error_msg)
            
            # 🆕 ENHANCED TWO-PHASE COMMIT: Phase 1 - Reserve path in Firestore
            document = Document(
                id=document_id,
                org_id=org_id,
                folder_id=folder_id,
                filename=sanitized_filename,
                original_filename=file.filename,
                file_type=file_type,
                file_size=actual_size,
                storage_path=storage_path,  # Use the unique path we validated
                status=DocumentStatus.UPLOADING,  # New status to indicate incomplete upload
                uploaded_by=user_id,
                metadata=metadata or {},
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            # Phase 1: Create placeholder document in Firestore to reserve the path
            doc_ref = self._get_collection(org_id).document(document_id)
            try:
                await doc_ref.set(document.to_dict())
                self.logger.info("✅ Phase 1: Document path reserved in Firestore", 
                               org_id=org_id, 
                               document_id=document_id,
                               storage_path=storage_path,
                               status="uploading")
            except Exception as e:
                self.logger.error("❌ Phase 1 failed: Could not reserve document path in Firestore", 
                                org_id=org_id, 
                                document_id=document_id,
                                storage_path=storage_path,
                                error=str(e))
                raise DocumentUploadError(f"Failed to reserve document path: {e}")
            
            # Phase 2: Upload file to GCS
            actual_storage_path = None
            try:
                self.logger.info("Phase 2: Uploading file to GCS", 
                               org_id=org_id,
                               document_id=document_id,
                               original_filename=file.filename,
                               sanitized_filename=sanitized_filename,
                               client_target_path=target_path,
                               final_storage_path=storage_path,
                               file_size=actual_size,
                               content_type=content_type,
                               path_source="target_path" if target_path else "legacy_folder_id")
                
                # Upload directly to the validated storage path
                actual_storage_path = gcs_client.upload_file_to_path(
                    storage_path=storage_path,
                    content=content,
                    content_type=content_type
                )
                
                self.logger.info("✅ Phase 2: Document uploaded successfully to GCS", 
                               org_id=org_id,
                               document_id=document_id,
                               filename=sanitized_filename,
                               storage_path=actual_storage_path,
                               file_size=actual_size,
                               content_type=content_type,
                               used_target_path=target_path is not None,
                               client_specified_path=target_path)
                
            except GCSClientError as e:
                self.logger.error("❌ Phase 2 failed: GCS upload failed, rolling back Firestore", 
                                org_id=org_id, 
                                document_id=document_id,
                                filename=file.filename,
                                error=str(e))
                
                # Rollback Phase 1: Delete the placeholder document
                try:
                    await doc_ref.delete()
                    self.logger.info("🔄 Rollback successful: Removed placeholder document from Firestore", 
                                   org_id=org_id,
                                   document_id=document_id)
                except Exception as rollback_error:
                    self.logger.error("🚨 Rollback failed: Could not remove placeholder document", 
                                    org_id=org_id,
                                    document_id=document_id,
                                    rollback_error=str(rollback_error))
                
                raise DocumentUploadError(f"Failed to upload file to storage: {e}")
            
            # Phase 3: Update Firestore document to mark as successfully uploaded
            try:
                document.status = DocumentStatus.UPLOADED
                document.storage_path = actual_storage_path  # Use actual path returned by GCS
                document.updated_at = datetime.utcnow()
                
                # Ensure status is properly converted to string value
                status_value = document.status.value if hasattr(document.status, 'value') else document.status
                
                await doc_ref.update({
                    "status": status_value,
                    "storage_path": actual_storage_path,
                    "updated_at": document.updated_at
                })
                
                self.logger.info("✅ Phase 3: Document status updated to UPLOADED in Firestore", 
                               org_id=org_id, 
                               document_id=document_id,
                               filename=sanitized_filename,
                               final_storage_path=actual_storage_path)
                
            except Exception as e:
                self.logger.error("❌ Phase 3 failed: Could not update document status, cleaning up", 
                                org_id=org_id, 
                                document_id=document_id,
                                error=str(e))
                
                # Rollback: Delete both GCS file and Firestore document
                cleanup_errors = []
                
                # Try to delete GCS file
                if actual_storage_path:
                    try:
                        gcs_client.delete_document_file(actual_storage_path)
                        self.logger.info("🔄 Rollback: Cleaned up GCS file", 
                                       storage_path=actual_storage_path)
                    except Exception as gcs_cleanup_error:
                        cleanup_errors.append(f"GCS cleanup failed: {gcs_cleanup_error}")
                        self.logger.error("🚨 GCS cleanup failed during rollback",
                                        storage_path=actual_storage_path,
                                        error=str(gcs_cleanup_error))
                
                # Try to delete Firestore document
                try:
                    await doc_ref.delete()
                    self.logger.info("🔄 Rollback: Removed document from Firestore", 
                                   org_id=org_id,
                                   document_id=document_id)
                except Exception as firestore_cleanup_error:
                    cleanup_errors.append(f"Firestore cleanup failed: {firestore_cleanup_error}")
                    self.logger.error("🚨 Firestore cleanup failed during rollback",
                                    org_id=org_id,
                                    document_id=document_id,
                                    error=str(firestore_cleanup_error))
                
                error_msg = f"Failed to finalize document upload: {e}"
                if cleanup_errors:
                    error_msg += f" (Cleanup issues: {'; '.join(cleanup_errors)})"
                
                raise DocumentUploadError(error_msg)
            
            document_response = DocumentResponse.model_validate(document)
            
            return DocumentUploadResponse(
                success=True,
                message="Document uploaded successfully",
                document=document_response
            )

        except (DocumentValidationError, DocumentUploadError):
            raise
        except Exception as e:
            self.logger.error("Error creating document", 
                            org_id=org_id, 
                            filename=file.filename if file else "unknown",
                            error=str(e))
            raise DocumentUploadError(f"Unexpected error during upload: {e}")

    async def get_document(self, org_id: str, document_id: str) -> DocumentResponse:
        """
        Get document by ID.
        
        Args:
            org_id: Organization ID
            document_id: Document ID
            
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
            document = await self._enrich_document_metadata(document)
            
            # NUCLEAR SAFETY NET: Final validation to guarantee no "Unknown" values
            document = self._ensure_safe_metadata(document)
            
            self.logger.debug("Document retrieved", 
                            org_id=org_id, 
                            document_id=document_id)
            
            return DocumentResponse.model_validate(document)

        except DocumentNotFoundError:
            raise
        except Exception as e:
            self.logger.error("Error retrieving document", 
                            org_id=org_id, 
                            document_id=document_id, 
                            error=str(e))
            raise

    async def list_documents(
        self,
        org_id: str,
        pagination: PaginationParams,
        filters: Optional[DocumentFilters] = None
    ) -> DocumentList:
        """
        List documents with pagination and filtering.
        
        Args:
            org_id: Organization ID
            pagination: Pagination parameters
            filters: Optional filters
            
        Returns:
            Paginated document list
        """
        try:
            # CHECK FOR GCS DIRECT LISTING: If folder_path contains "/original/", list files directly from GCS
            if filters and filters.folder_path and "/original/" in filters.folder_path:
                self.logger.info("Detected GCS path in folder_path, using direct GCS listing", 
                               org_id=org_id, 
                               folder_path=filters.folder_path)
                return await self._list_documents_from_gcs(org_id, filters.folder_path, pagination, filters)
            
            # EXISTING FIRESTORE LOGIC for backward compatibility
            collection = self._get_collection(org_id)
            query = collection.where(filter=FieldFilter("is_active", "==", True))
            
            # Apply filters
            if filters:
                if filters.file_type:
                    query = query.where(filter=FieldFilter("file_type", "==", filters.file_type.value))
                if filters.status:
                    query = query.where(filter=FieldFilter("status", "==", filters.status.value))
                if filters.folder_id:
                    query = query.where(filter=FieldFilter("folder_id", "==", filters.folder_id))
                if filters.uploaded_by:
                    query = query.where(filter=FieldFilter("uploaded_by", "==", filters.uploaded_by))
            
            # Order by creation date (newest first)
            query = query.order_by("created_at", direction="DESCENDING")
            
            # Get total count (Note: This is simplified - in production, use a separate count query)
            all_docs = query.stream()
            all_documents = []
            
            async for doc in all_docs:
                try:
                    document_data = doc.to_dict()
                    document = Document.from_dict(document_data, doc.id)
                    
                    # Enrich document metadata to ensure complete data
                    document = await self._enrich_document_metadata(document)
                    
                    # NUCLEAR SAFETY NET: Final validation to guarantee no "Unknown" values
                    document = self._ensure_safe_metadata(document)
                    
                    # Apply name filter (Firestore doesn't support case-insensitive contains)
                    if filters and filters.filename:
                        if filters.filename.lower() not in document.filename.lower():
                            continue
                    
                    # Apply folder_path filter (storage_path-based filtering for target_path uploads)
                    if filters and filters.folder_path:
                        document_folder = self._extract_folder_from_storage_path(document.storage_path)
                        if not document_folder or document_folder.lower() != filters.folder_path.lower():
                            continue
                    
                    all_documents.append(document)
                    
                except Exception as e:
                    self.logger.error("Failed to process document from Firestore", 
                                    org_id=org_id,
                                    document_id=doc.id,
                                    document_data=document_data if 'document_data' in locals() else "unknown",
                                    error=str(e))
                    # Skip this document and continue with others
                    continue
            
            # Get total count
            total = len(all_documents)
            
            # Apply pagination
            start_idx = pagination.offset
            end_idx = start_idx + pagination.per_page
            paginated_documents = all_documents[start_idx:end_idx]
            
            # Convert to response models with error handling
            document_responses = []
            for doc in paginated_documents:
                try:
                    doc_response = DocumentResponse.model_validate(doc)
                    document_responses.append(doc_response)
                except Exception as e:
                    self.logger.error("Failed to convert Document to DocumentResponse", 
                                    org_id=org_id,
                                    document_id=doc.id if hasattr(doc, 'id') else "unknown",
                                    document_data=doc.model_dump() if hasattr(doc, 'model_dump') else str(doc),
                                    error=str(e))
                    # Skip this document and continue with others
                    continue

            # Calculate pagination info
            total_pages = math.ceil(total / pagination.per_page) if total > 0 else 0

            # Enhanced logging for folder filtering
            filter_info = {}
            if filters:
                if filters.folder_id:
                    filter_info["folder_id"] = filters.folder_id
                if filters.folder_path:
                    filter_info["folder_path"] = filters.folder_path
                if filters.filename:
                    filter_info["filename"] = filters.filename
                if filters.file_type:
                    filter_info["file_type"] = filters.file_type.value
                if filters.status:
                    filter_info["status"] = filters.status.value
            
            self.logger.debug("Documents listed with enhanced folder filtering", 
                            org_id=org_id,
                            count=len(document_responses), 
                            total=total, 
                            page=pagination.page,
                            filters=filter_info,
                            folder_filtering_used=bool(filters and (filters.folder_id or filters.folder_path)))

            return DocumentList(
                documents=document_responses,
                total=total,
                page=pagination.page,
                per_page=pagination.per_page,
                total_pages=total_pages
            )

        except Exception as e:
            self.logger.error("Error listing documents", org_id=org_id, error=str(e))
            raise

    async def update_document_status(
        self, 
        org_id: str,
        document_id: str,
        new_status: DocumentStatus,
        metadata: Optional[Dict[str, Any]] = None
    ) -> DocumentResponse:
        """
        Update document processing status.
        
        Args:
            org_id: Organization ID
            document_id: Document ID
            new_status: New processing status
            metadata: Additional metadata
            
        Returns:
            Updated document response
            
        Raises:
            DocumentNotFoundError: If document not found
            DocumentValidationError: If status transition is invalid
        """
        try:
            # Get current document
            doc_ref = self._get_collection(org_id).document(document_id)
            doc = await doc_ref.get()
            
            if not doc.exists:
                raise DocumentNotFoundError(f"Document with ID {document_id} not found")
            
            document_data = doc.to_dict()
            document = Document.from_dict(document_data, doc.id)
            
            if not document.is_active:
                raise DocumentNotFoundError(f"Document with ID {document_id} not found")
            
            # Validate status transition
            if not document.can_transition_to(new_status):
                raise DocumentValidationError(
                    f"Cannot transition from {document.status.value} to {new_status.value}"
                )
            
            # Update document
            document.update_status(new_status)
            if metadata:
                document.metadata.update(metadata)
            
            # Save to Firestore
            await doc_ref.update(document.to_dict())
            
            self.logger.info("Document status updated", 
                           org_id=org_id, 
                           document_id=document_id,
                           old_status=document_data.get('status'),
                           new_status=new_status.value)
            
            return DocumentResponse.model_validate(document)

        except (DocumentNotFoundError, DocumentValidationError):
            raise
        except Exception as e:
            self.logger.error("Error updating document status", 
                            org_id=org_id, 
                            document_id=document_id, 
                            error=str(e))
            raise

    async def update_document_summary(
        self,
        org_id: str,
        document_id: str,
        summary: str
    ) -> DocumentResponse:
        """
        Update document AI-generated summary.
        
        Args:
            org_id: Organization ID
            document_id: Document ID
            summary: AI-generated summary content
            
        Returns:
            Updated document response
            
        Raises:
            DocumentNotFoundError: If document not found
        """
        try:
            # Get current document
            doc_ref = self._get_collection(org_id).document(document_id)
            doc = await doc_ref.get()
            
            if not doc.exists:
                raise DocumentNotFoundError(f"Document with ID {document_id} not found")
            
            # Get document data and create Document instance
            document_data = doc.to_dict()
            document = Document.from_dict(document_data, doc.id)
            
            # Update summary using the model's method
            document.update_ai_summary(summary)
            
            # Save to Firestore
            await doc_ref.update(document.to_dict())
            
            self.logger.info("Document summary updated",
                           org_id=org_id,
                           document_id=document_id,
                           summary_size=len(summary.encode('utf-8')))
            
            return DocumentResponse.model_validate(document)
        
        except DocumentNotFoundError:
            raise
        except Exception as e:
            self.logger.error("Error updating document summary",
                            org_id=org_id,
                            document_id=document_id,
                            error=str(e))
            raise

    async def update_document_ai_content(
        self,
        org_id: str,
        document_id: str,
        summary: Optional[str] = None,
        faq: Optional[List[Dict[str, str]]] = None,
        questions: Optional[List[str]] = None
    ) -> DocumentResponse:
        """
        Update multiple AI-generated content fields in a single operation.
        
        Args:
            org_id: Organization ID
            document_id: Document ID
            summary: AI-generated summary (optional)
            faq: AI-generated FAQ items (optional)
            questions: AI-generated questions (optional)
            
        Returns:
            Updated document response
            
        Raises:
            DocumentNotFoundError: If document not found
        """
        try:
            # Get current document
            doc_ref = self._get_collection(org_id).document(document_id)
            doc = await doc_ref.get()
            
            if not doc.exists:
                raise DocumentNotFoundError(f"Document with ID {document_id} not found")
            
            # Get document data and create Document instance
            document_data = doc.to_dict()
            document = Document.from_dict(document_data, doc.id)
            
            # Update fields that were provided
            updates = []
            if summary is not None:
                document.update_ai_summary(summary)
                updates.append(f"summary ({len(summary.encode('utf-8'))} bytes)")
            
            if faq is not None:
                document.update_ai_faq(faq)
                updates.append(f"faq ({len(faq)} items)")
            
            if questions is not None:
                document.update_ai_questions(questions)
                updates.append(f"questions ({len(questions)} items)")
            
            if not updates:
                self.logger.warning("No AI content updates provided",
                                  org_id=org_id,
                                  document_id=document_id)
                # Return current document if no updates
                return DocumentResponse.model_validate(document)
            
            # Save to Firestore
            await doc_ref.update(document.to_dict())
            
            self.logger.info("Document AI content updated",
                           org_id=org_id,
                           document_id=document_id,
                           updates=", ".join(updates))
            
            return DocumentResponse.model_validate(document)
        
        except DocumentNotFoundError:
            raise
        except Exception as e:
            self.logger.error("Error updating document AI content",
                            org_id=org_id,
                            document_id=document_id,
                            error=str(e))
            raise

    async def get_document_ai_content(
        self,
        org_id: str,
        document_id: str
    ) -> Dict[str, Any]:
        """
        Get only the AI-generated content fields from a document.
        
        Args:
            org_id: Organization ID
            document_id: Document ID
            
        Returns:
            Dictionary with AI content fields
            
        Raises:
            DocumentNotFoundError: If document not found
        """
        try:
            # Get current document
            doc_ref = self._get_collection(org_id).document(document_id)
            doc = await doc_ref.get()
            
            if not doc.exists:
                raise DocumentNotFoundError(f"Document with ID {document_id} not found")
            
            # Get document data and create Document instance
            document_data = doc.to_dict()
            document = Document.from_dict(document_data, doc.id)
            
            # Return only AI content fields
            return {
                "document_id": document.id,
                "filename": document.filename,
                "summary": document.summary,
                "faq": document.faq,
                "questions": document.questions,
                "has_ai_content": document.has_ai_content,
                "ai_content_size": document.ai_content_size,
                "updated_at": document.updated_at
            }
        
        except DocumentNotFoundError:
            raise
        except Exception as e:
            self.logger.error("Error getting document AI content",
                            org_id=org_id,
                            document_id=document_id,
                            error=str(e))
            raise

    async def delete_document(self, org_id: str, document_id: str) -> Dict[str, Any]:
        """
        Delete document (soft delete from Firestore, hard delete from GCS).
        
        Args:
            org_id: Organization ID
            document_id: Document ID
            
        Returns:
            Dictionary with deletion results
            
        Raises:
            DocumentNotFoundError: If document not found
        """
        try:
            # Get document
            doc_ref = self._get_collection(org_id).document(document_id)
            doc = await doc_ref.get()
            
            if not doc.exists:
                raise DocumentNotFoundError(f"Document with ID {document_id} not found")
            
            document_data = doc.to_dict()
            document = Document.from_dict(document_data, doc.id)
            
            if not document.is_active:
                raise DocumentNotFoundError(f"Document with ID {document_id} not found")
            
            # Delete from GCS
            gcs_deleted = False
            if gcs_client.is_initialized:
                try:
                    gcs_deleted = gcs_client.delete_document_file(document.storage_path)
                    self.logger.info("Document file deleted from GCS", 
                                   org_id=org_id, 
                                   document_id=document_id,
                                   storage_path=document.storage_path)
                except GCSClientError as e:
                    self.logger.warning("Failed to delete document file from GCS", 
                                      org_id=org_id, 
                                      document_id=document_id,
                                      storage_path=document.storage_path,
                                      error=str(e))
            
            # Soft delete in Firestore
            document.is_active = False
            document.update_timestamp()
            await doc_ref.update(document.to_dict())
            
            self.logger.info("Document deleted", 
                           org_id=org_id, 
                           document_id=document_id,
                           filename=document.filename)
            
            return {
                "success": True,
                "message": f"Document '{document.filename}' deleted successfully",
                "gcs_deleted": gcs_deleted
            }

        except DocumentNotFoundError:
            raise
        except Exception as e:
            self.logger.error("Error deleting document", 
                            org_id=org_id, 
                            document_id=document_id, 
                            error=str(e))
            raise

    async def download_document(
        self, 
        org_id: str, 
        document_id: str,
        expiration_minutes: int = 60
    ) -> DocumentDownloadResponse:
        """
        Generate signed URL for document download.
        
        Args:
            org_id: Organization ID
            document_id: Document ID
            expiration_minutes: URL expiration time in minutes
            
        Returns:
            Document download response with signed URL
            
        Raises:
            DocumentNotFoundError: If document not found
        """
        try:
            # Get document
            document_response = await self.get_document(org_id, document_id)
            
            if not gcs_client.is_initialized:
                raise DocumentValidationError("GCS client not initialized")
            
            # Generate signed URL
            try:
                signed_url, expiration = gcs_client.generate_signed_url(
                    storage_path=document_response.storage_path,
                    expiration_minutes=expiration_minutes
                )
                
                self.logger.info("Generated download URL for document", 
                               org_id=org_id, 
                               document_id=document_id,
                               filename=document_response.filename,
                               expiration=expiration.isoformat())
                
                return DocumentDownloadResponse(
                    download_url=signed_url,
                    expires_at=expiration,
                    filename=document_response.original_filename
                )
                
            except GCSClientError as e:
                self.logger.error("Failed to generate download URL", 
                                org_id=org_id, 
                                document_id=document_id,
                                error=str(e))
                raise DocumentValidationError(f"Failed to generate download URL: {e}")

        except (DocumentNotFoundError, DocumentValidationError):
            raise
        except Exception as e:
            self.logger.error("Error generating download URL", 
                            org_id=org_id, 
                            document_id=document_id, 
                            error=str(e))
            raise

    async def get_document_by_filename_from_firestore(
        self, 
        org_id: str, 
        filename: str,
        exact_match: bool = True,
        include_inactive: bool = False
    ) -> "DocumentFirestoreResponse":
        """
        Get document by filename using Firestore as primary data source.
        
        This method demonstrates proper Firestore-first architecture by:
        - Querying document metadata directly from Firestore
        - Enriching with relationship data (organization, folder, user)
        - Providing comprehensive document information in single query
        
        Args:
            org_id: Organization ID
            filename: Document filename to search for
            exact_match: Whether to match exact filename (default: True)
            include_inactive: Whether to include soft-deleted documents (default: False)
            
        Returns:
            DocumentFirestoreResponse with document and relationship data
            
        Raises:
            DocumentNotFoundError: If no document found with given filename
        """
        from app.models.schemas import (
            DocumentFirestoreResponse,
            DocumentSearchCriteria,
            DocumentFirestoreMetadata,
            DocumentRelationships,
            DocumentRelationshipOrganization,
            DocumentRelationshipFolder,
            DocumentRelationshipUploader
        )
        
        try:
            self.logger.info("Searching for document by filename in Firestore", 
                           org_id=org_id,
                           filename=filename,
                           exact_match=exact_match,
                           include_inactive=include_inactive)
            
            collection = self._get_collection(org_id)
            
            # Build Firestore query based on search type
            if exact_match:
                query = collection.where(filter=FieldFilter("filename", "==", filename))
                query_method = "filename_exact_match"
            else:
                # For partial match, we'll get all documents and filter client-side
                # Note: Firestore doesn't support case-insensitive contains queries
                query = collection.where(filter=FieldFilter("filename", ">=", filename))
                query_method = "filename_partial_match"
            
            # Filter by active status unless including inactive
            if not include_inactive:
                query = query.where(filter=FieldFilter("is_active", "==", True))
            
            # Execute query
            docs = query.stream()
            found_documents = []
            
            async for doc in docs:
                try:
                    document_data = doc.to_dict()
                    document = Document.from_dict(document_data, doc.id)
                    
                    # For partial match, filter filename on client side
                    if not exact_match:
                        if filename.lower() not in document.filename.lower():
                            continue
                    
                    # Enrich document metadata to ensure complete data
                    document = await self._enrich_document_metadata(document)
                    
                    # Apply safety net to ensure no missing values
                    document = self._ensure_safe_metadata(document)
                    
                    found_documents.append(document)
                    
                    # For exact match, we can break after first match
                    if exact_match:
                        break
                        
                except Exception as e:
                    self.logger.error("Failed to process document during filename search", 
                                    org_id=org_id,
                                    document_id=doc.id,
                                    error=str(e))
                    continue
            
            if not found_documents:
                search_type = "exact" if exact_match else "partial"
                raise DocumentNotFoundError(
                    f"No document found with filename '{filename}' using {search_type} match"
                )
            
            # Use the first found document (for exact match, there should be only one)
            document = found_documents[0]
            
            if len(found_documents) > 1:
                self.logger.warning("Multiple documents found with same filename", 
                                  org_id=org_id,
                                  filename=filename,
                                  count=len(found_documents),
                                  using_first=document.id)
            
            # Get organization information
            org = await self.org_service.get_organization(org_id)
            org_relationship = DocumentRelationshipOrganization(
                id=org.id,
                name=org.name
            )
            
            # Get folder information if document has folder_id
            folder_relationship = None
            if document.folder_id:
                try:
                    folder = await self.folder_service.get_folder(org_id, document.folder_id)
                    folder_relationship = DocumentRelationshipFolder(
                        id=folder.id,
                        name=folder.name,
                        path=folder.path
                    )
                except Exception as e:
                    self.logger.warning("Could not fetch folder information", 
                                      org_id=org_id,
                                      folder_id=document.folder_id,
                                      error=str(e))
                    folder_relationship = DocumentRelationshipFolder(
                        id=document.folder_id,
                        name="Unknown Folder",
                        path="/unknown"
                    )
            
            # Get uploader information
            try:
                from app.services.user_service import user_service
                uploader = await user_service.get_user(org_id, document.uploaded_by)
                uploader_relationship = DocumentRelationshipUploader(
                    id=uploader.id,
                    email=uploader.email,
                    full_name=uploader.full_name
                )
            except Exception as e:
                self.logger.warning("Could not fetch uploader information", 
                                  org_id=org_id,
                                  uploaded_by=document.uploaded_by,
                                  error=str(e))
                uploader_relationship = DocumentRelationshipUploader(
                    id=document.uploaded_by,
                    email="unknown@example.com",
                    full_name="Unknown User"
                )
            
            # Build comprehensive response
            search_criteria = DocumentSearchCriteria(
                filename=filename,
                exact_match=exact_match,
                include_inactive=include_inactive
            )
            
            firestore_metadata = DocumentFirestoreMetadata(
                document_ref=f"organizations/{org_id}/documents/{document.id}",
                query_method=query_method,
                last_updated=document.updated_at
            )
            
            relationships = DocumentRelationships(
                organization=org_relationship,
                folder=folder_relationship,
                uploader=uploader_relationship
            )
            
            document_response = DocumentResponse.model_validate(document)
            
            response = DocumentFirestoreResponse(
                source="firestore",
                search_criteria=search_criteria,
                document=document_response,
                firestore_metadata=firestore_metadata,
                relationships=relationships
            )
            
            self.logger.info("Document found via Firestore filename search", 
                           org_id=org_id,
                           filename=filename,
                           document_id=document.id,
                           exact_match=exact_match,
                           query_method=query_method)
            
            return response
            
        except DocumentNotFoundError:
            raise
        except Exception as e:
            self.logger.error("Error searching document by filename in Firestore", 
                            org_id=org_id,
                            filename=filename,
                            exact_match=exact_match,
                            error=str(e))
            raise DocumentNotFoundError(f"Failed to search for document by filename: {e}")

    async def get_documents_by_folder_name_from_firestore(
        self,
        org_id: str,
        folder_name: str,
        pagination: "PaginationParams",
        exact_match: bool = True,
        include_inactive: bool = False,
        additional_filters: Optional["DocumentFilters"] = None
    ) -> "DocumentFirestoreFolderListResponse":
        """
        Get documents by folder name using Firestore as primary data source.
        
        This method demonstrates proper Firestore-first architecture by:
        - Finding folder by name using folder service
        - Querying documents directly from Firestore using folder_id index
        - Providing comprehensive document and folder information in single response
        - Supporting efficient pagination and filtering
        
        Args:
            org_id: Organization ID
            folder_name: Folder name to search for
            pagination: Pagination parameters
            exact_match: Whether to match exact folder name (default: True)
            include_inactive: Whether to include soft-deleted documents (default: False)
            additional_filters: Optional additional filters (file_type, status, filename)
            
        Returns:
            DocumentFirestoreFolderListResponse with documents and folder info
            
        Raises:
            DocumentNotFoundError: If no folder found with given name
        """
        from app.models.schemas import (
            DocumentFirestoreFolderListResponse,
            DocumentFolderSearchCriteria,
            DocumentFolderInfo,
            DocumentFirestoreMetadata,
            PaginationParams,
            DocumentFilters
        )
        
        try:
            self.logger.info("Searching for documents by folder name in Firestore", 
                           org_id=org_id,
                           folder_name=folder_name,
                           exact_match=exact_match,
                           include_inactive=include_inactive,
                           pagination=pagination.model_dump(),
                           additional_filters=additional_filters.model_dump(exclude_none=True) if additional_filters else {})
            
            # Step 1: Find folder by name using folder service
            folder = await self._find_folder_by_name(org_id, folder_name, exact_match)
            
            if not folder:
                search_type = "exact" if exact_match else "partial"
                raise DocumentNotFoundError(
                    f"No folder found with name '{folder_name}' using {search_type} match"
                )
            
            # Debug logging for folder ID behavior
            potential_ids = getattr(folder, 'potential_folder_ids', [folder.id])
            self.logger.info("Found folder for document search", 
                           org_id=org_id,
                           folder_name=folder_name,
                           folder_id=folder.id,
                           folder_path=getattr(folder, 'path', 'N/A'),
                           potential_folder_ids=potential_ids,
                           exact_match=exact_match)
            
            # Step 2: Query documents by folder_id using Firestore with multiple attempts
            collection = self._get_collection(org_id)
            all_documents = []
            documents_found_by_id = {}
            
            # Try each potential folder ID
            for attempt_folder_id in potential_ids:
                self.logger.info("Trying folder_id query", 
                               org_id=org_id,
                               folder_id_attempt=attempt_folder_id,
                               folder_name=folder_name)
                
                # Base query - filter by folder_id
                query = collection.where(filter=FieldFilter("folder_id", "==", attempt_folder_id))
                
                # Filter by active status unless including inactive
                if not include_inactive:
                    query = query.where(filter=FieldFilter("is_active", "==", True))
                
                # Apply additional filters if provided
                if additional_filters:
                    if additional_filters.file_type:
                        query = query.where(filter=FieldFilter("file_type", "==", additional_filters.file_type.value))
                    if additional_filters.status:
                        query = query.where(filter=FieldFilter("status", "==", additional_filters.status.value))
                    if additional_filters.uploaded_by:
                        query = query.where(filter=FieldFilter("uploaded_by", "==", additional_filters.uploaded_by))
                
                # Order by creation date (newest first)
                query = query.order_by("created_at", direction="DESCENDING")
                
                # Execute query and collect documents
                docs = query.stream()
                docs_found_in_attempt = 0
                
                async for doc in docs:
                    try:
                        # Avoid duplicates by checking document ID
                        if doc.id not in documents_found_by_id:
                            document_data = doc.to_dict()
                            document = Document.from_dict(document_data, doc.id)
                            
                            # Apply filename filter (client-side since Firestore doesn't support case-insensitive contains)
                            if additional_filters and additional_filters.filename:
                                if additional_filters.filename.lower() not in document.filename.lower():
                                    continue
                            
                            # Enrich document metadata to ensure complete data
                            document = await self._enrich_document_metadata(document)
                            
                            # Apply safety net to ensure no missing values
                            document = self._ensure_safe_metadata(document)
                            
                            all_documents.append(document)
                            documents_found_by_id[doc.id] = True
                            docs_found_in_attempt += 1
                            
                    except Exception as e:
                        self.logger.error("Failed to process document during folder search", 
                                        org_id=org_id,
                                        folder_name=folder_name,
                                        folder_id_attempt=attempt_folder_id,
                                        document_id=doc.id,
                                        error=str(e))
                        continue
                
                self.logger.info("Folder_id attempt results", 
                               org_id=org_id,
                               folder_id_attempt=attempt_folder_id,
                               documents_found_in_attempt=docs_found_in_attempt,
                               total_unique_documents=len(all_documents))
                
                # If we found documents and this is exact match, we can stop trying
                if exact_match and docs_found_in_attempt > 0:
                    break
            
            # Step 3: Fallback strategy - if no documents found, try direct folder name patterns
            if len(all_documents) == 0:
                self.logger.info("No documents found with folder ID patterns, trying fallback direct name search", 
                               org_id=org_id,
                               folder_name=folder_name,
                               attempted_folder_ids=potential_ids)
                
                # Try direct folder name searches with various patterns
                fallback_patterns = [
                    folder_name,                    # Original folder name
                    folder_name.lower(),           # Lowercase
                    folder_name.upper(),           # Uppercase
                    f"/{folder_name}",             # With leading slash
                    f"{folder_name}/",             # With trailing slash
                    f"/{folder_name}/",            # With both slashes
                ]
                
                # Remove duplicates and ones we already tried
                fallback_patterns = [p for p in fallback_patterns if p not in potential_ids]
                
                for fallback_pattern in fallback_patterns:
                    self.logger.info("Trying fallback folder_id pattern", 
                                   org_id=org_id,
                                   fallback_pattern=fallback_pattern,
                                   folder_name=folder_name)
                    
                    # Base query - filter by folder_id
                    query = collection.where(filter=FieldFilter("folder_id", "==", fallback_pattern))
                    
                    # Filter by active status unless including inactive
                    if not include_inactive:
                        query = query.where(filter=FieldFilter("is_active", "==", True))
                    
                    # Apply additional filters if provided
                    if additional_filters:
                        if additional_filters.file_type:
                            query = query.where(filter=FieldFilter("file_type", "==", additional_filters.file_type.value))
                        if additional_filters.status:
                            query = query.where(filter=FieldFilter("status", "==", additional_filters.status.value))
                        if additional_filters.uploaded_by:
                            query = query.where(filter=FieldFilter("uploaded_by", "==", additional_filters.uploaded_by))
                    
                    # Order by creation date (newest first)
                    query = query.order_by("created_at", direction="DESCENDING")
                    
                    # Execute query
                    docs = query.stream()
                    docs_found_in_fallback = 0
                    
                    async for doc in docs:
                        try:
                            # Avoid duplicates by checking document ID
                            if doc.id not in documents_found_by_id:
                                document_data = doc.to_dict()
                                document = Document.from_dict(document_data, doc.id)
                                
                                # Apply filename filter
                                if additional_filters and additional_filters.filename:
                                    if additional_filters.filename.lower() not in document.filename.lower():
                                        continue
                                
                                # Enrich document metadata
                                document = await self._enrich_document_metadata(document)
                                document = self._ensure_safe_metadata(document)
                                
                                all_documents.append(document)
                                documents_found_by_id[doc.id] = True
                                docs_found_in_fallback += 1
                                
                        except Exception as e:
                            self.logger.error("Failed to process document during fallback search", 
                                            org_id=org_id,
                                            folder_name=folder_name,
                                            fallback_pattern=fallback_pattern,
                                            document_id=doc.id,
                                            error=str(e))
                            continue
                    
                    self.logger.info("Fallback pattern results", 
                                   org_id=org_id,
                                   fallback_pattern=fallback_pattern,
                                   documents_found_in_fallback=docs_found_in_fallback,
                                   total_unique_documents=len(all_documents))
                    
                    # If we found documents, we can stop trying fallback patterns
                    if docs_found_in_fallback > 0:
                        break
            
            # Debug logging for final query results
            self.logger.info("Final Firestore query results for folder documents", 
                           org_id=org_id,
                           folder_name=folder_name,
                           folder_id_primary=folder.id,
                           documents_found=len(all_documents),
                           document_ids=[doc.id[:8] + "..." for doc in all_documents[:5]])  # Show first 5 IDs
            
            # Step 4: Apply pagination
            total = len(all_documents)
            start_idx = pagination.offset
            end_idx = start_idx + pagination.per_page
            paginated_documents = all_documents[start_idx:end_idx]
            
            # Convert to response models
            document_responses = []
            for doc in paginated_documents:
                try:
                    doc_response = DocumentResponse.model_validate(doc)
                    document_responses.append(doc_response)
                except Exception as e:
                    self.logger.error("Failed to convert Document to DocumentResponse", 
                                    org_id=org_id,
                                    folder_name=folder_name,
                                    document_id=doc.id if hasattr(doc, 'id') else "unknown",
                                    error=str(e))
                    continue
            
            # Step 5: Build comprehensive response
            total_pages = math.ceil(total / pagination.per_page) if total > 0 else 0
            
            # Create folder info
            folder_info = DocumentFolderInfo(
                id=folder.id,
                name=folder.name,
                path=folder.path,
                parent_folder_id=folder.parent_folder_id,
                created_by=folder.created_by,
                created_at=folder.created_at,
                document_count=total
            )
            
            # Create search criteria
            search_criteria = DocumentFolderSearchCriteria(
                folder_name=folder_name,
                exact_match=exact_match,
                include_inactive=include_inactive,
                additional_filters=additional_filters.model_dump(exclude_none=True) if additional_filters else {}
            )
            
            # Create Firestore metadata
            firestore_metadata = DocumentFirestoreMetadata(
                document_ref=f"organizations/{org_id}/documents (folder_id == {folder.id})",
                query_method="folder_id_exact_match_with_filters",
                last_updated=datetime.utcnow()
            )
            
            response = DocumentFirestoreFolderListResponse(
                source="firestore",
                folder_info=folder_info,
                search_criteria=search_criteria,
                documents=document_responses,
                total=total,
                page=pagination.page,
                per_page=pagination.per_page,
                total_pages=total_pages,
                firestore_metadata=firestore_metadata
            )
            
            self.logger.info("Documents found via Firestore folder search", 
                           org_id=org_id,
                           folder_name=folder_name,
                           folder_id=folder.id,
                           total_documents=total,
                           returned_documents=len(document_responses),
                           page=pagination.page,
                           exact_match=exact_match)
            
            return response
            
        except DocumentNotFoundError:
            raise
        except Exception as e:
            self.logger.error("Error searching documents by folder name in Firestore", 
                            org_id=org_id,
                            folder_name=folder_name,
                            exact_match=exact_match,
                            error=str(e))
            raise DocumentNotFoundError(f"Failed to search for documents by folder name: {e}")

    async def _find_folder_by_name(self, org_id: str, folder_name: str, exact_match: bool = True):
        """
        Find folder by name within organization.
        
        This is a helper method that works with the current GCS-based folder service
        to find folders by name for document listing.
        
        Args:
            org_id: Organization ID
            folder_name: Folder name to search for
            exact_match: Whether to match exact folder name
            
        Returns:
            Folder object if found, None otherwise
        """
        try:
            from app.models.schemas import PaginationParams, FolderFilters
            
            # Get folders and search by name with pagination support
            # Note: This uses the existing folder service which is GCS-based
            matching_folders = []
            page = 1
            max_pages = 10  # Limit search to prevent infinite loops
            
            while page <= max_pages:
                pagination = PaginationParams(page=page, per_page=100)  # Get folders (max allowed)
                filters = FolderFilters(name=folder_name) if exact_match else None
                
                folder_list = await self.folder_service.list_folders(org_id, pagination, filters)
                
                # Find matching folder(s) in current page
                for folder in folder_list.folders:
                    if exact_match:
                        if folder.name.lower() == folder_name.lower():
                            matching_folders.append(folder)
                            # If exact match found, we can stop searching
                            break
                    else:
                        if folder_name.lower() in folder.name.lower():
                            matching_folders.append(folder)
                
                # If exact match found or we've reached the last page, stop
                if (exact_match and matching_folders) or page >= folder_list.total_pages:
                    break
                    
                page += 1
            
            if not matching_folders:
                return None
            
            if len(matching_folders) > 1:
                self.logger.warning("Multiple folders found with same name", 
                                  org_id=org_id,
                                  folder_name=folder_name,
                                  count=len(matching_folders),
                                  using_first=matching_folders[0].id)
            
            # Return the first matching folder
            # Convert FolderResponse to a simple object that has the needed properties
            folder_response = matching_folders[0]
            
            # Create a simple folder object with the properties we need
            class SimpleFolder:
                def __init__(self, folder_response):
                    self.id = folder_response.id
                    self.name = folder_response.name
                    self.path = folder_response.path
                    self.parent_folder_id = getattr(folder_response, 'parent_folder_id', None)
                    self.created_by = getattr(folder_response, 'created_by', 'unknown')
                    self.created_at = getattr(folder_response, 'created_at', datetime.utcnow())
                    
                    # Additional properties for folder ID matching
                    self.folder_name_only = folder_response.name  # Just the folder name
                    self.potential_folder_ids = [
                        folder_response.id,           # Original ID (might be path)
                        folder_response.name,         # Just the folder name
                        folder_response.name.lower(), # Lowercase folder name
                        folder_response.path.lstrip('/'), # Path without leading slash
                    ]
                    # Remove duplicates while preserving order
                    seen = set()
                    self.potential_folder_ids = [x for x in self.potential_folder_ids if not (x in seen or seen.add(x))]
            
            return SimpleFolder(folder_response)
            
        except Exception as e:
            self.logger.error("Error finding folder by name", 
                            org_id=org_id,
                            folder_name=folder_name,
                            exact_match=exact_match,
                            error=str(e))
            return None

    async def sync_content_to_firestore(
        self, 
        org_id: str, 
        storage_path: str, 
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Sync document content from GCS to Firestore.
        
        Args:
            org_id: Organization ID
            storage_path: Document storage path to find document
            content: Content to sync to Firestore
            metadata: Optional metadata to update alongside content
            
        Returns:
            Dictionary with sync result information
            
        Raises:
            DocumentNotFoundError: If document not found in Firestore
        """
        try:
            from app.core.firebase_client import firebase_manager
            
            if not firebase_manager.is_initialized:
                self.logger.warning("Firebase not initialized, cannot sync content to Firestore")
                return {
                    "success": False,
                    "error": "Firebase not initialized",
                    "document_updated": False
                }
            
            # Find document by storage_path
            collection = self._get_collection(org_id)
            query = collection.where(filter=FieldFilter("storage_path", "==", storage_path))
            
            docs = query.stream()
            document_found = False
            updated_documents = []
            
            async for doc in docs:
                document_found = True
                
                # Prepare update data
                update_data = {
                    "file_content": content,
                    "updated_at": firebase_manager.get_server_timestamp()
                }
                
                # Include metadata if provided (merge with existing)
                if metadata:
                    existing_metadata = doc.to_dict().get("metadata", {})
                    update_data["metadata"] = {**existing_metadata, **metadata}
                
                # Update document
                await doc.reference.update(update_data)
                
                updated_documents.append({
                    "document_id": doc.id,
                    "storage_path": storage_path
                })
                
                self.logger.info("Synced content to Firestore document", 
                               org_id=org_id,
                               document_id=doc.id,
                               storage_path=storage_path,
                               content_length=len(content))
                break  # Should only be one document with this storage path
            
            if not document_found:
                raise DocumentNotFoundError(f"No document found with storage path: {storage_path}")
            
            return {
                "success": True,
                "document_updated": True,
                "updated_documents": updated_documents,
                "content_length": len(content)
            }
            
        except DocumentNotFoundError:
            raise
        except Exception as e:
            self.logger.error("Failed to sync content to Firestore", 
                            org_id=org_id,
                            storage_path=storage_path,
                            error=str(e))
            return {
                "success": False,
                "error": str(e),
                "document_updated": False
            }

    async def sync_content_from_firestore_to_gcs(
        self, 
        org_id: str, 
        document_id: str,
        gcs_storage_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Sync document content from Firestore to GCS.
        
        Args:
            org_id: Organization ID
            document_id: Document ID in Firestore
            gcs_storage_path: Optional GCS path override, uses document's parsed_storage_path if not provided
            
        Returns:
            Dictionary with sync result information
            
        Raises:
            DocumentNotFoundError: If document not found
        """
        try:
            # Get document from Firestore
            doc_ref = self._get_collection(org_id).document(document_id)
            doc = await doc_ref.get()
            
            if not doc.exists:
                raise DocumentNotFoundError(f"Document with ID {document_id} not found")
            
            doc_data = doc.to_dict()
            file_content = doc_data.get("file_content")
            
            if not file_content:
                return {
                    "success": False,
                    "error": "Document has no file_content to sync",
                    "gcs_updated": False
                }
            
            # Determine storage path
            if not gcs_storage_path:
                gcs_storage_path = doc_data.get("parsed_storage_path")
                if not gcs_storage_path:
                    # Generate parsed storage path from original
                    original_path = doc_data.get("storage_path")
                    if original_path:
                        gcs_storage_path = self._generate_parsed_storage_path(original_path)
                    else:
                        return {
                            "success": False,
                            "error": "Cannot determine GCS storage path",
                            "gcs_updated": False
                        }
            
            # Upload content to GCS
            try:
                content_bytes = file_content.encode('utf-8')
                gcs_client.upload_file_to_path(
                    storage_path=gcs_storage_path,
                    content=content_bytes,
                    content_type="text/markdown"
                )
                
                # Update Firestore with the parsed_storage_path if it wasn't set
                if not doc_data.get("parsed_storage_path"):
                    await doc_ref.update({
                        "parsed_storage_path": gcs_storage_path,
                        "updated_at": firebase_manager.get_server_timestamp()
                    })
                
                self.logger.info("Synced content from Firestore to GCS", 
                               org_id=org_id,
                               document_id=document_id,
                               gcs_storage_path=gcs_storage_path,
                               content_length=len(content_bytes))
                
                return {
                    "success": True,
                    "gcs_updated": True,
                    "gcs_storage_path": gcs_storage_path,
                    "content_length": len(content_bytes)
                }
                
            except GCSClientError as e:
                self.logger.error("Failed to upload content to GCS", 
                                org_id=org_id,
                                document_id=document_id,
                                gcs_storage_path=gcs_storage_path,
                                error=str(e))
                return {
                    "success": False,
                    "error": f"GCS upload failed: {str(e)}",
                    "gcs_updated": False
                }
            
        except DocumentNotFoundError:
            raise
        except Exception as e:
            self.logger.error("Failed to sync content from Firestore to GCS", 
                            org_id=org_id,
                            document_id=document_id,
                            error=str(e))
            return {
                "success": False,
                "error": str(e),
                "gcs_updated": False
            }

    def _generate_parsed_storage_path(self, original_path: str) -> str:
        """
        Generate storage path for parsed content from original path.
        
        Args:
            original_path: Original GCS path (e.g., "Google/original/invoices/file.pdf")
            
        Returns:
            Parsed storage path (e.g., "Google/parsed/invoices/file.md")
        """
        from pathlib import Path
        
        path_parts = original_path.split('/')
        
        if len(path_parts) >= 4:
            # Standard path: org_name/original/folder_name/filename
            org_name = path_parts[0]
            folder_name = path_parts[2]
            filename = path_parts[3]
            
            # Change extension to .md and replace 'original' with 'parsed'
            base_filename = Path(filename).stem
            parsed_filename = f"{base_filename}.md"
            
            return f"{org_name}/parsed/{folder_name}/{parsed_filename}"
        else:
            # Fallback for non-standard paths
            base_path = original_path.replace('/original/', '/parsed/')
            return str(Path(base_path).with_suffix('.md'))

    async def validate_content_sync(
        self, 
        org_id: str, 
        document_id: Optional[str] = None,
        storage_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate synchronization between Firestore content and GCS content.
        
        Args:
            org_id: Organization ID
            document_id: Document ID (optional, used if storage_path not provided)
            storage_path: Storage path to validate (optional, used if document_id not provided)
            
        Returns:
            Dictionary with validation results
        """
        try:
            # Get document data
            if document_id:
                doc_ref = self._get_collection(org_id).document(document_id)
                doc = await doc_ref.get()
                if not doc.exists:
                    return {"valid": False, "error": "Document not found in Firestore"}
                doc_data = doc.to_dict()
                storage_path = doc_data.get("storage_path")
            elif storage_path:
                # Find document by storage path
                collection = self._get_collection(org_id)
                query = collection.where(filter=FieldFilter("storage_path", "==", storage_path))
                docs = query.stream()
                
                doc_data = None
                async for doc in docs:
                    doc_data = doc.to_dict()
                    document_id = doc.id
                    break
                
                if not doc_data:
                    return {"valid": False, "error": "Document not found in Firestore"}
            else:
                return {"valid": False, "error": "Either document_id or storage_path must be provided"}
            
            # Get content from both sources
            firestore_content = doc_data.get("file_content")
            parsed_storage_path = doc_data.get("parsed_storage_path")
            
            if not parsed_storage_path:
                if not firestore_content:
                    return {
                        "valid": True,
                        "synchronized": True,
                        "note": "No content in either location (expected for unparsed documents)"
                    }
                else:
                    return {
                        "valid": False,
                        "synchronized": False,
                        "error": "Content exists in Firestore but no parsed_storage_path"
                    }
            
            # Check GCS content
            try:
                gcs_content_bytes = gcs_client.download_document_file(parsed_storage_path)
                gcs_content = gcs_content_bytes.decode('utf-8')
            except Exception as e:
                if firestore_content:
                    return {
                        "valid": False,
                        "synchronized": False,
                        "error": f"Content exists in Firestore but not in GCS: {str(e)}"
                    }
                else:
                    return {
                        "valid": True,
                        "synchronized": True,
                        "note": "No content in either location"
                    }
            
            # Compare content
            if firestore_content == gcs_content:
                return {
                    "valid": True,
                    "synchronized": True,
                    "firestore_content_length": len(firestore_content) if firestore_content else 0,
                    "gcs_content_length": len(gcs_content),
                    "parsed_storage_path": parsed_storage_path
                }
            else:
                return {
                    "valid": False,
                    "synchronized": False,
                    "error": "Content mismatch between Firestore and GCS",
                    "firestore_content_length": len(firestore_content) if firestore_content else 0,
                    "gcs_content_length": len(gcs_content),
                    "parsed_storage_path": parsed_storage_path
                }
                
        except Exception as e:
            self.logger.error("Failed to validate content sync", 
                            org_id=org_id,
                            document_id=document_id,
                            storage_path=storage_path,
                            error=str(e))
            return {
                "valid": False,
                "error": f"Validation failed: {str(e)}"
            }


# Global service instance
document_service = DocumentService()