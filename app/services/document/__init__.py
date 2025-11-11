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
- document_ai_service: AI content management
- document_sync_service: Firestore-GCS synchronization
- document_download_service: Download URL generation and file access
- document_parsing_service: Document parsing with LlamaParse integration
- document_summarization_service: AI-powered document summarization
- document_service: Orchestration facade (main interface)
"""

# Export parsing service and its exceptions for backward compatibility
from .document_parsing_service import (
    DocumentParsingService,
    document_parsing_service,
    DocumentParsingError,
    UnsupportedFileTypeError,
)

# Export summarization service and its exceptions for backward compatibility
from .document_summarization_service import (
    DocumentSummarizationService,
    document_summarization_service,
    DocumentSummarizationError,
    ContentNotFoundError,
    SummarizationError,
)

# Make services available at package level
__all__ = [
    # Parsing service exports
    "DocumentParsingService",
    "document_parsing_service",
    "DocumentParsingError",
    "UnsupportedFileTypeError",
    # Summarization service exports
    "DocumentSummarizationService",
    "document_summarization_service",
    "DocumentSummarizationError",
    "ContentNotFoundError",
    "SummarizationError",
]
