"""
Document Service - Backward compatibility facade for the refactored document services.

This module maintains backward compatibility by re-exporting the DocumentService
and related classes from the refactored services/document/ package.

The original monolithic DocumentService (2,805 lines) has been refactored following
SOLID principles into focused services:

- DocumentBaseService: Common utilities and shared functionality
- DocumentValidationService: File validation and security checks
- DocumentStorageService: GCS operations and storage management
- DocumentService: Main orchestration facade (this file)

Additional services:
- DocumentCrudService: Basic CRUD operations
- DocumentQueryService: Complex queries and filtering
- DocumentSyncService: PostgreSQL-GCS synchronization
- DocumentDownloadService: Download URL generation

This facade ensures all existing imports continue to work while the underlying
implementation is properly organized following SOLID principles.
"""

# Export the main service and exception classes for backward compatibility
from .document.document_service import document_service, DocumentService
from .document.document_base_service import (
    DocumentNotFoundError,
    DocumentValidationError,
    DocumentUploadError,
    DocumentDuplicateError,
)

# Make sure the global service instance is available at module level
__all__ = [
    "document_service",
    "DocumentService",
    "DocumentNotFoundError",
    "DocumentValidationError",
    "DocumentUploadError",
    "DocumentDuplicateError",
]
