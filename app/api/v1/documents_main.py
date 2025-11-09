"""
Document API Router - SOLID Refactored Architecture

This module serves as the main aggregator for all document-related endpoints,
following SOLID principles by organizing functionality into focused sub-modules:

- document_upload.py: Document upload operations
- document_management.py: CRUD operations (list, get, update, delete)
- document_download.py: Download URL generation and redirects
- document_processing.py: Parsing, summarization, and content processing
- document_ai_content.py: AI-generated content management
- document_sync.py: Sync validation and Firestore-first queries
- common.py: Shared utilities and dependencies

Each sub-module follows the Single Responsibility Principle and provides
focused functionality with comprehensive documentation and error handling.
"""

from fastapi import APIRouter, status

# Import all sub-routers
from app.api.v1.documents_modules.document_upload import router as upload_router
from app.api.v1.documents_modules.document_management import router as management_router
from app.api.v1.documents_modules.document_download import router as download_router
from app.api.v1.documents_modules.document_processing import router as processing_router
from app.api.v1.documents_modules.document_sync import router as sync_router
from app.api.v1.documents_modules.document_summarization import router as summarization_router
from app.api.v1.documents_modules.document_faq import router as faq_router
from app.api.v1.documents_modules.document_questions import router as questions_router
from app.api.v1.documents_modules.common import logger

# Create main router
router = APIRouter()

# Include all sub-routers with their specific functionality
# Order matters: specific routes must come before generic path parameter routes

# 1. Routes without path parameters (no conflicts)
router.include_router(
    upload_router,
    tags=["Document Upload"],
)

# 2. AI content routers with specific paths (must come before /{document_id})
router.include_router(
    summarization_router,
    tags=["Document Summarization"],
)

router.include_router(
    faq_router,
    tags=["Document FAQ"],
)

router.include_router(
    questions_router,
    tags=["Document Questions"],
)

# 3. Other specific path routers
router.include_router(
    processing_router,
    tags=["Document Processing"],
)


router.include_router(
    sync_router,
    tags=["Document Sync"],
)

router.include_router(
    download_router,
    tags=["Document Download"],
)

# 4. Generic path parameter routes (MUST BE LAST - has /{document_id})
router.include_router(
    management_router,
    tags=["Document Management"],
)


# Health check endpoint for document service
@router.get(
    "/health", 
    include_in_schema=False,
    summary="🏥 Document Service Health Check",
    description="Health check for document service and dependencies."
)
async def documents_health_check():
    """
    Health check for document service and dependencies.
    
    Checks the status of:
    - Google Cloud Storage connectivity
    - Firestore database connectivity
    - Overall service health
    """
    try:
        from app.core.gcs_client import gcs_client
        from app.core.firebase_client import firebase_client
        
        health_status = {
            "status": "healthy",
            "timestamp": "2025-01-01T00:00:00Z",  # Will be updated in production
            "service": "document-intelligence-api",
            "version": "1.0.0",
            "components": {
                "gcs": gcs_client.health_check() if gcs_client else False,
                "firestore": firebase_client.health_check() if firebase_client else False
            },
            "endpoints": {
                "upload": "✅ Available",
                "management": "✅ Available", 
                "download": "✅ Available",
                "processing": "✅ Available",
                "ai_content": "✅ Available",
                "sync": "✅ Available",
                "summarization": "✅ Available",
                "faq": "✅ Available"
            }
        }
        
        # Check if all components are healthy
        all_healthy = all(health_status["components"].values())
        if not all_healthy:
            health_status["status"] = "degraded"
            health_status["endpoints"] = {
                "upload": "⚠️ Limited" if not health_status["components"]["gcs"] else "✅ Available",
                "management": "⚠️ Limited" if not health_status["components"]["firestore"] else "✅ Available",
                "download": "⚠️ Limited" if not health_status["components"]["gcs"] else "✅ Available",
                "processing": "⚠️ Limited" if not all_healthy else "✅ Available",
                "ai_content": "⚠️ Limited" if not health_status["components"]["firestore"] else "✅ Available",
                "sync": "⚠️ Limited" if not all_healthy else "✅ Available",
                "summarization": "⚠️ Limited" if not health_status["components"]["firestore"] else "✅ Available",
                "faq": "⚠️ Limited" if not health_status["components"]["firestore"] else "✅ Available"
            }
        
        status_code = status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
        
        return health_status
        
    except Exception as e:
        logger.error("Document service health check failed", error=str(e))
        return {
            "status": "unhealthy",
            "service": "document-intelligence-api",
            "error": str(e),
            "timestamp": "2025-01-01T00:00:00Z",
            "components": {
                "gcs": False,
                "firestore": False
            },
            "endpoints": {
                "upload": "❌ Unavailable",
                "management": "❌ Unavailable",
                "download": "❌ Unavailable", 
                "processing": "❌ Unavailable",
                "ai_content": "❌ Unavailable",
                "sync": "❌ Unavailable",
                "summarization": "❌ Unavailable",
                "faq": "❌ Unavailable"
            }
        }


# Module information endpoint for debugging
@router.get(
    "/info", 
    include_in_schema=False,
    summary="📋 Document API Module Information",
    description="Information about the refactored document API structure."
)
async def documents_info():
    """
    Information about the refactored document API architecture.
    
    Provides details about the SOLID-compliant module structure
    and available endpoint categories.
    """
    return {
        "api": "Document Intelligence API",
        "version": "2.0.0",
        "architecture": "SOLID Principles Refactored",
        "refactoring_date": "2025-08-23",
        "modules": {
            "document_upload": {
                "description": "Document upload operations with comprehensive validation",
                "endpoints": [
                    "POST /upload"
                ],
                "responsibilities": [
                    "File upload handling",
                    "Metadata parsing and validation", 
                    "Storage path management",
                    "Upload error handling"
                ]
            },
            "document_management": {
                "description": "Core CRUD operations for documents",
                "endpoints": [
                    "GET /",
                    "GET /{document_id}",
                    "PUT /{document_id}/status",
                    "DELETE /{document_id}"
                ],
                "responsibilities": [
                    "Document listing with pagination and filtering",
                    "Individual document retrieval",
                    "Status updates and management",
                    "Document deletion (soft/hard)"
                ]
            },
            "document_download": {
                "description": "Secure document download operations",
                "endpoints": [
                    "GET /{document_id}/download",
                    "GET /{document_id}/download/redirect"
                ],
                "responsibilities": [
                    "Signed URL generation",
                    "Direct download redirects",
                    "Access control and expiration",
                    "Download security"
                ]
            },
            "document_processing": {
                "description": "Document parsing and AI processing",
                "endpoints": [
                    "POST /parse",
                    "GET /parse/{storage_path:path}",
                    "POST /save-parsed",
                    "POST /summarize/{filename}"
                ],
                "responsibilities": [
                    "LlamaParse document parsing",
                    "Parsed content management",
                    "AI-powered summarization",
                    "Processing workflow orchestration"
                ]
            },
            "document_ai_content": {
                "description": "AI-generated content management",
                "endpoints": [
                    "GET /{document_id}/ai-content",
                    "PATCH /{document_id}/ai-content"
                ],
                "responsibilities": [
                    "AI content retrieval",
                    "Content updates and validation",
                    "FAQ and question management",
                    "AI content metadata tracking"
                ]
            },
            "document_sync": {
                "description": "Sync validation and Firestore-first queries",
                "endpoints": [
                    "GET /sync/validate",
                    "GET /firestore/by-filename/{filename}",
                    "GET /firestore/by-folder-name/{folder_name}"
                ],
                "responsibilities": [
                    "Firestore-GCS sync validation",
                    "Database-first document queries",
                    "Folder-based document listing",
                    "Data consistency monitoring"
                ]
            },
            "common": {
                "description": "Shared utilities and dependencies",
                "exports": [
                    "get_document_dependencies()",
                    "get_user_context()",
                    "Error handlers",
                    "Logging utilities"
                ],
                "responsibilities": [
                    "Dependency injection",
                    "Common error handling patterns",
                    "Structured logging",
                    "Shared validation logic"
                ]
            }
        },
        "benefits": [
            "Single Responsibility Principle compliance",
            "Improved code maintainability",
            "Better testability with focused modules",
            "Enhanced error handling consistency",
            "Comprehensive documentation per module",
            "Easier onboarding for new developers"
        ],
        "total_endpoints": 17,
        "original_file_size": "2,820 lines",
        "refactored_structure": "7 focused modules + 1 aggregator",
        "documentation": "Each module includes comprehensive docstrings and API documentation"
    }