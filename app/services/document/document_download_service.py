"""
Document Download Service - URL generation and secure file access operations.

This service handles secure document access and download operations:
- Signed URL generation for temporary file access
- Download URL validation and security checks
- Expiration time management and validation
- Access logging and audit trails
- Bulk download operations and batch URL generation
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone

from app.models.schemas import DocumentDownloadResponse
from app.core.gcs_client import gcs_client, GCSClientError
from .document_base_service import (
    DocumentBaseService,
    DocumentNotFoundError,
    DocumentValidationError,
    DocumentUploadError,
)


class DocumentDownloadService(DocumentBaseService):
    """Service for document download operations and URL generation."""

    def __init__(self):
        """Initialize the download service with security configurations."""
        super().__init__()

        # Download security settings
        self.min_expiration_minutes = 5  # Minimum URL expiration
        self.max_expiration_minutes = 1440  # Maximum URL expiration (24 hours)
        self.default_expiration_minutes = 60  # Default URL expiration
        self.max_bulk_downloads = 50  # Maximum documents per bulk operation

    async def download_document(
        self,
        org_id: str,
        document_id: str,
        expiration_minutes: int = None,
        user_id: Optional[str] = None,
        crud_service=None,
    ) -> DocumentDownloadResponse:
        """
        Generate secure signed URL for document download with comprehensive validation.

        Args:
            org_id: Organization ID
            document_id: Document ID
            expiration_minutes: URL expiration time in minutes (optional)
            user_id: User requesting the download (for audit logging)
            crud_service: CRUD service dependency for document retrieval

        Returns:
            Document download response with signed URL and metadata

        Raises:
            DocumentNotFoundError: If document not found
            DocumentValidationError: If download parameters are invalid
        """
        try:
            # Validate expiration time
            if expiration_minutes is None:
                expiration_minutes = self.default_expiration_minutes

            if expiration_minutes < self.min_expiration_minutes:
                raise DocumentValidationError(
                    f"Expiration time too short: {expiration_minutes} minutes (min {self.min_expiration_minutes})"
                )

            if expiration_minutes > self.max_expiration_minutes:
                raise DocumentValidationError(
                    f"Expiration time too long: {expiration_minutes} minutes (max {self.max_expiration_minutes})"
                )

            # Get document using CRUD service
            if crud_service:
                document_response = await crud_service.get_document(org_id, document_id)
            else:
                # Fallback to direct document retrieval
                doc_ref = self._get_collection(org_id).document(document_id)
                doc = await doc_ref.get()

                if not doc.exists:
                    raise DocumentNotFoundError(
                        f"Document with ID {document_id} not found"
                    )

                from app.models.document import Document
                from app.models.schemas import DocumentResponse

                document_data = doc.to_dict()
                document = Document.from_dict(document_data, doc.id)

                if not document.is_active:
                    raise DocumentNotFoundError(
                        f"Document with ID {document_id} not found"
                    )

                document_response = DocumentResponse.model_validate(document)

            # Validate GCS availability
            if not gcs_client.is_initialized:
                error_msg = "GCS client not initialized"
                if gcs_client.initialization_error:
                    error_msg += f": {gcs_client.initialization_error}"
                raise DocumentValidationError(error_msg)

            # Validate storage path exists
            if not document_response.storage_path:
                raise DocumentValidationError("Document has no storage path")

            # Generate signed URL with security validation
            try:
                signed_url, expiration = gcs_client.generate_signed_url(
                    storage_path=document_response.storage_path,
                    expiration_minutes=expiration_minutes,
                )

                # Additional security validation of the generated URL
                if not signed_url or not signed_url.startswith(("https://", "http://")):
                    raise DocumentValidationError("Invalid signed URL generated")

                # Log download access for audit trail
                self.logger.info(
                    "Generated download URL for document",
                    org_id=org_id,
                    document_id=document_id,
                    filename=document_response.filename,
                    original_filename=document_response.original_filename,
                    storage_path=document_response.storage_path,
                    expiration_minutes=expiration_minutes,
                    expires_at=expiration.isoformat(),
                    user_id=user_id,
                    file_size=document_response.file_size,
                )

                return DocumentDownloadResponse(
                    download_url=signed_url,
                    expires_at=expiration,
                    filename=document_response.original_filename,
                    file_size=document_response.file_size,
                    content_type=self._get_content_type_from_file_type(
                        document_response.file_type
                    ),
                )

            except GCSClientError as e:
                self.logger.error(
                    "Failed to generate download URL",
                    org_id=org_id,
                    document_id=document_id,
                    filename=document_response.filename,
                    storage_path=document_response.storage_path,
                    error=str(e),
                )
                raise DocumentValidationError(f"Failed to generate download URL: {e}")

        except (DocumentNotFoundError, DocumentValidationError):
            raise
        except Exception as e:
            self.logger.error(
                "Error generating download URL",
                org_id=org_id,
                document_id=document_id,
                user_id=user_id,
                error=str(e),
            )
            raise DocumentUploadError(
                f"Unexpected error during download URL generation: {e}"
            )

    async def bulk_download_documents(
        self,
        org_id: str,
        document_ids: List[str],
        expiration_minutes: int = None,
        user_id: Optional[str] = None,
        crud_service=None,
    ) -> Dict[str, Any]:
        """
        Generate download URLs for multiple documents in batch operation.

        Args:
            org_id: Organization ID
            document_ids: List of document IDs to generate URLs for
            expiration_minutes: URL expiration time in minutes
            user_id: User requesting the downloads
            crud_service: CRUD service dependency

        Returns:
            Dictionary with successful downloads and errors
        """
        try:
            # Validate input
            if not document_ids:
                raise DocumentValidationError("Document IDs list cannot be empty")

            if len(document_ids) > self.max_bulk_downloads:
                raise DocumentValidationError(
                    f"Too many documents requested: {len(document_ids)} (max {self.max_bulk_downloads})"
                )

            # Remove duplicates while preserving order
            unique_document_ids = list(dict.fromkeys(document_ids))

            if expiration_minutes is None:
                expiration_minutes = self.default_expiration_minutes

            # Process documents in batch
            successful_downloads = []
            failed_downloads = []

            for document_id in unique_document_ids:
                try:
                    download_response = await self.download_document(
                        org_id=org_id,
                        document_id=document_id,
                        expiration_minutes=expiration_minutes,
                        user_id=user_id,
                        crud_service=crud_service,
                    )

                    successful_downloads.append(
                        {
                            "document_id": document_id,
                            "download_url": download_response.download_url,
                            "expires_at": download_response.expires_at,
                            "filename": download_response.filename,
                            "file_size": download_response.file_size,
                        }
                    )

                except Exception as e:
                    failed_downloads.append(
                        {
                            "document_id": document_id,
                            "error": str(e),
                            "error_type": type(e).__name__,
                        }
                    )

                    self.logger.warning(
                        "Failed to generate download URL in bulk operation",
                        org_id=org_id,
                        document_id=document_id,
                        user_id=user_id,
                        error=str(e),
                    )

            self.logger.info(
                "Bulk download URLs generated",
                org_id=org_id,
                requested_count=len(unique_document_ids),
                successful_count=len(successful_downloads),
                failed_count=len(failed_downloads),
                user_id=user_id,
                expiration_minutes=expiration_minutes,
            )

            return {
                "success": True,
                "requested_count": len(unique_document_ids),
                "successful_downloads": successful_downloads,
                "failed_downloads": failed_downloads,
                "success_rate": (
                    len(successful_downloads) / len(unique_document_ids)
                    if unique_document_ids
                    else 0
                ),
                "expiration_minutes": expiration_minutes,
                "generated_at": datetime.now(timezone.utc),
            }

        except DocumentValidationError:
            raise
        except Exception as e:
            self.logger.error(
                "Error in bulk download operation",
                org_id=org_id,
                document_count=len(document_ids) if document_ids else 0,
                user_id=user_id,
                error=str(e),
            )
            raise DocumentUploadError(f"Bulk download operation failed: {e}")

    async def validate_download_access(
        self, org_id: str, document_id: str, user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate if a user has permission to download a document.

        Args:
            org_id: Organization ID
            document_id: Document ID
            user_id: User requesting access validation

        Returns:
            Dictionary with access validation results
        """
        try:
            # Get document metadata
            doc_ref = self._get_collection(org_id).document(document_id)
            doc = await doc_ref.get()

            if not doc.exists:
                return {
                    "access_granted": False,
                    "reason": "document_not_found",
                    "message": f"Document with ID {document_id} not found",
                }

            doc_data = doc.to_dict()

            from app.models.document import Document

            document = Document.from_dict(doc_data, doc.id)

            if not document.is_active:
                return {
                    "access_granted": False,
                    "reason": "document_inactive",
                    "message": "Document is not active",
                }

            # Check if document has a valid storage path
            if not document.storage_path:
                return {
                    "access_granted": False,
                    "reason": "no_storage_path",
                    "message": "Document has no storage path",
                }

            # Validate GCS accessibility
            if not gcs_client.is_initialized:
                return {
                    "access_granted": False,
                    "reason": "storage_unavailable",
                    "message": "Document storage is not available",
                }

            # Additional access checks could be implemented here:
            # - User role verification
            # - Organization membership validation
            # - Document sharing permissions
            # - Time-based access restrictions

            self.logger.debug(
                "Download access validated",
                org_id=org_id,
                document_id=document_id,
                filename=document.filename,
                user_id=user_id,
                access_granted=True,
            )

            return {
                "access_granted": True,
                "document_id": document_id,
                "filename": document.filename,
                "file_size": document.file_size,
                "storage_path": document.storage_path,
                "validated_at": datetime.now(timezone.utc),
            }

        except Exception as e:
            self.logger.error(
                "Error validating download access",
                org_id=org_id,
                document_id=document_id,
                user_id=user_id,
                error=str(e),
            )
            return {
                "access_granted": False,
                "reason": "validation_error",
                "message": f"Access validation failed: {e}",
            }

    def _get_content_type_from_file_type(self, file_type) -> str:
        """
        Get MIME content type from document file type.

        Args:
            file_type: Document file type enum

        Returns:
            MIME content type string
        """
        from app.models.document import FileType

        content_type_mapping = {
            FileType.PDF: "application/pdf",
            FileType.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            # Add more mappings as needed
        }

        return content_type_mapping.get(file_type, "application/octet-stream")

    async def get_download_statistics(
        self,
        org_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Get download statistics for an organization.

        Note: This is a placeholder for download analytics.
        In a full implementation, this would query download logs/metrics.

        Args:
            org_id: Organization ID
            start_date: Start date for statistics (optional)
            end_date: End date for statistics (optional)

        Returns:
            Dictionary with download statistics
        """
        try:
            # Placeholder implementation
            # In a real system, this would query download logs or metrics storage

            if start_date is None:
                start_date = datetime.now(timezone.utc) - timedelta(days=30)

            if end_date is None:
                end_date = datetime.now(timezone.utc)

            # This would be replaced with actual metrics queries
            placeholder_stats = {
                "org_id": org_id,
                "period": {
                    "start_date": start_date,
                    "end_date": end_date,
                    "days": (end_date - start_date).days,
                },
                "download_metrics": {
                    "total_downloads": 0,
                    "unique_documents": 0,
                    "unique_users": 0,
                    "total_bytes_downloaded": 0,
                    "average_file_size": 0,
                },
                "top_downloaded_documents": [],
                "download_patterns": {
                    "peak_hour": "Not available",
                    "peak_day": "Not available",
                    "most_common_file_type": "Not available",
                },
                "note": "Download statistics require implementation of download logging system",
                "generated_at": datetime.now(timezone.utc),
            }

            self.logger.info(
                "Download statistics requested",
                org_id=org_id,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                note="placeholder_implementation",
            )

            return placeholder_stats

        except Exception as e:
            self.logger.error(
                "Error getting download statistics", org_id=org_id, error=str(e)
            )
            return {
                "org_id": org_id,
                "error": str(e),
                "generated_at": datetime.now(timezone.utc),
            }
