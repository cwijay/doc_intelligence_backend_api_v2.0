"""
Document services package.

This package contains the refactored document services following SOLID principles.
Each service has a single responsibility and focused functionality.

Services:
- document_base_service: Common utilities and shared functionality
- document_validation_service: File validation and security checks
- document_storage_service: GCS operations and storage management
- document_crud_service: Basic CRUD operations
- document_query_service: Complex queries and filtering
- document_download_service: Download URL generation and file access
- document_service: Orchestration facade (main interface)
"""

# Export the main document service for backward compatibility
from .document_service import DocumentService, document_service

# Make services available at package level
__all__ = [
    "DocumentService",
    "document_service",
]
