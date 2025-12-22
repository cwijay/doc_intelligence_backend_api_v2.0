"""
Document API Router - SOLID Refactored Architecture

This module serves as the main aggregator for all document-related endpoints,
following SOLID principles by organizing functionality into focused sub-modules:

- document_upload.py: Document upload operations
- document_management.py: CRUD operations (list, get, update, delete)
- document_download.py: Download URL generation and redirects
- common.py: Shared utilities and dependencies

Each sub-module follows the Single Responsibility Principle and provides
focused functionality with comprehensive documentation and error handling.
"""

from fastapi import APIRouter

# Import all sub-routers
from app.api.v1.documents_modules.document_upload import router as upload_router
from app.api.v1.documents_modules.document_management import router as management_router
from app.api.v1.documents_modules.document_download import router as download_router
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

# 2. Download router with specific paths (must come before /{document_id})
router.include_router(
    download_router,
    tags=["Document Download"],
)

# 3. Generic path parameter routes (MUST BE LAST - has /{document_id})
router.include_router(
    management_router,
    tags=["Document Management"],
)


# Health check endpoint for document service
@router.get(
    "/health",
    include_in_schema=False,
    summary="Document Service Health Check",
    description="Health check for document service and dependencies.",
)
async def documents_health_check():
    """
    Health check for document service and dependencies.

    Checks the status of:
    - Google Cloud Storage connectivity
    - PostgreSQL database connectivity
    - Overall service health
    """
    try:
        from app.core.gcs_client import gcs_client
        from biz2bricks_core import db

        # Check database connection
        db_healthy = await db.test_connection(timeout=5.0)

        health_status = {
            "status": "healthy",
            "service": "document-intelligence-api",
            "version": "1.0.0",
            "components": {
                "gcs": gcs_client.health_check() if gcs_client else False,
                "postgresql": db_healthy,
            },
            "endpoints": {
                "upload": "Available",
                "management": "Available",
                "download": "Available",
            },
        }

        # Check if all components are healthy
        all_healthy = all(health_status["components"].values())
        if not all_healthy:
            health_status["status"] = "degraded"
            health_status["endpoints"] = {
                "upload": (
                    "Limited" if not health_status["components"]["gcs"] else "Available"
                ),
                "management": (
                    "Limited"
                    if not health_status["components"]["postgresql"]
                    else "Available"
                ),
                "download": (
                    "Limited" if not health_status["components"]["gcs"] else "Available"
                ),
            }

        return health_status

    except Exception as e:
        logger.error("Document service health check failed", error=str(e))
        return {
            "status": "unhealthy",
            "service": "document-intelligence-api",
            "error": str(e),
            "components": {"gcs": False, "postgresql": False},
            "endpoints": {
                "upload": "Unavailable",
                "management": "Unavailable",
                "download": "Unavailable",
            },
        }


# Module information endpoint for debugging
@router.get(
    "/info",
    include_in_schema=False,
    summary="📋 Document API Module Information",
    description="Information about the refactored document API structure.",
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
                "endpoints": ["POST /upload"],
                "responsibilities": [
                    "File upload handling",
                    "Metadata parsing and validation",
                    "Storage path management",
                    "Upload error handling",
                ],
            },
            "document_management": {
                "description": "Core CRUD operations for documents",
                "endpoints": [
                    "GET /",
                    "GET /{document_id}",
                    "PUT /{document_id}/status",
                    "DELETE /{document_id}",
                ],
                "responsibilities": [
                    "Document listing with pagination and filtering",
                    "Individual document retrieval",
                    "Status updates and management",
                    "Document deletion (soft/hard)",
                ],
            },
            "document_download": {
                "description": "Secure document download operations",
                "endpoints": [
                    "GET /{document_id}/download",
                    "GET /{document_id}/download/redirect",
                ],
                "responsibilities": [
                    "Signed URL generation",
                    "Direct download redirects",
                    "Access control and expiration",
                    "Download security",
                ],
            },
            "common": {
                "description": "Shared utilities and dependencies",
                "exports": [
                    "get_document_dependencies()",
                    "get_user_context()",
                    "Error handlers",
                    "Logging utilities",
                ],
                "responsibilities": [
                    "Dependency injection",
                    "Common error handling patterns",
                    "Structured logging",
                    "Shared validation logic",
                ],
            },
        },
        "benefits": [
            "Single Responsibility Principle compliance",
            "Improved code maintainability",
            "Better testability with focused modules",
            "Enhanced error handling consistency",
            "Comprehensive documentation per module",
            "Easier onboarding for new developers",
        ],
        "total_endpoints": 7,
        "original_file_size": "2,820 lines",
        "refactored_structure": "4 focused modules + 1 aggregator",
        "documentation": "Each module includes comprehensive docstrings and API documentation",
    }
