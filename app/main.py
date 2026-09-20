"""FastAPI Application Entry Point.

Document management platform built with FastAPI, featuring:
- File upload and storage (Google Cloud Storage)
- Multi-tenant organization support
- Session-based JWT authentication
"""

import time
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional

from fastapi import FastAPI, Request, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

# Import models for the direct route handler
from app.models.schemas import DocumentList, PaginationParams, DocumentFilters
from app.models.document import DocumentStatus, FileType
from app.core.simple_auth import get_current_user_dict

from app.core.config import settings
from app.core.logging import configure_logging, setup_request_logging, get_logger
from app.core.exceptions import setup_exception_handlers
from app.core.db_client import db
from app.core.cache import init_cache, close_cache
from app.core.openapi import create_custom_openapi
from app.core.middleware import setup_cors_middleware, setup_trusted_host_middleware

# Import SessionModel to register with SQLAlchemy Base for table creation
from biz2bricks_core import SessionModel  # noqa: F401

# Configure logging first
configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    # Startup
    logger.info(
        "Starting application",
        project_name=settings.PROJECT_NAME,
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        debug=settings.DEBUG,
    )

    startup_tasks = []

    # Initialize database connection
    try:
        engine = await db.get_engine_async()
        if engine:
            # The schema is owned by Alembic and applied by the deploy-time
            # migration step. Creating tables here ran on every start of the
            # dev service (ENVIRONMENT=dev satisfies is_development), which
            # silently diverged the database from the migrations -- and could
            # only ever add tables, never alter one. For a local database, run:
            #     alembic upgrade head        # from the biz2bricks_core repo

            # Test connection
            if await db.test_connection():
                startup_tasks.append("PostgreSQL connected")

                # Load persisted sessions from database
                from app.core.simple_auth import simple_auth_manager

                try:
                    session_count = await simple_auth_manager.load_sessions_from_db()
                    startup_tasks.append(f"Sessions restored ({session_count})")
                except Exception as e:
                    logger.warning("Failed to load sessions from DB", error=str(e))
            else:
                logger.warning("Database connection test failed")
        else:
            logger.warning("Database engine not initialized")
    except Exception as e:
        logger.error("Failed to initialize database", error=str(e))
        if settings.ENVIRONMENT.lower() == "production":
            raise

    # Initialize cache
    try:
        await init_cache()
        startup_tasks.append(f"Cache initialized ({settings.CACHE_BACKEND})")
    except Exception as e:
        logger.warning("Cache initialization failed", error=str(e))

    logger.info("Application startup completed", tasks=startup_tasks)

    yield

    # Shutdown
    logger.info("Shutting down application")

    shutdown_tasks = []

    # Close cache connections
    try:
        await close_cache()
        shutdown_tasks.append("Cache closed")
    except Exception as e:
        logger.error("Error closing cache", error=str(e))

    # Close database connections
    try:
        await db.close_all()
        shutdown_tasks.append("Database connections closed")
    except Exception as e:
        logger.error("Error closing database", error=str(e))

    logger.info("Application shutdown completed", tasks=shutdown_tasks)


# API Description
API_DESCRIPTION = """# Document Intelligence API

## Overview
FastAPI-based document management API. Supports PDF/XLSX upload, storage, and organization with multi-tenant support.

## Authentication
**Session-based JWT** with automatic refresh:
- **Header**: `Authorization: Bearer <session_token>`
- **Session**: 2 hours, **Refresh**: 7 days

**Key Endpoints:**
- `POST /api/v1/auth/login` - Get session + refresh tokens
- `POST /api/v1/auth/refresh-session` - Refresh tokens
- `GET /api/v1/auth/validate` - Check token validity

## Documents
**File Support:** PDF, XLSX (max 50MB)
**Storage:** Google Cloud Storage + PostgreSQL metadata

## Getting Started
1. **Get Organizations**: `GET /api/v1/auth/organizations`
2. **Register**: `POST /api/v1/auth/register`
3. **Upload Documents**: `POST /api/v1/documents/upload`
4. **List Documents**: `GET /api/v1/documents/`
"""

# Create FastAPI application
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    redirect_slashes=True,
    description=API_DESCRIPTION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json" if settings.DEBUG else None,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
    contact={
        "name": "Document Intelligence API",
        "email": "support@example.com",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    servers=[
        {"url": "http://localhost:8000", "description": "Development server"},
        {"url": "https://your-domain.com", "description": "Production server"},
    ],
)

# Custom OpenAPI schema
app.openapi = lambda: create_custom_openapi(app)

# Setup middleware (CORS first, then trusted hosts)
setup_cors_middleware(app)
setup_trusted_host_middleware(app)

# Setup exception handlers AFTER CORS middleware
setup_exception_handlers(app)

# Setup request logging
setup_request_logging(app)


# Middleware for timing requests
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Add processing time header to responses."""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(round(process_time, 4))
    return response


# Include health router (root level endpoints)
from app.api.health import router as health_router

app.include_router(health_router, tags=["Health"])

# Include API routers
from app.api.v1.auth import router as auth_router
from app.api.v1.organizations import router as organizations_router
from app.api.v1.users import router as users_router
from app.api.v1.password import router as password_router
from app.api.v1.folders import router as folders_router
from app.api.v1.audit import router as audit_router

# Import from documents_main.py file (modular structure with save-parsed endpoint)
from app.api.v1.documents_main import router as documents_router
from app.api.v1.debug import router as debug_router

# Authentication router
app.include_router(
    auth_router, prefix=f"{settings.API_V1_STR}/auth", tags=["Authentication"]
)

# Organization management router
app.include_router(
    organizations_router, prefix=settings.API_V1_STR, tags=["Organizations"]
)

# User management router
app.include_router(users_router, prefix=settings.API_V1_STR, tags=["Users"])

# Password utilities router
app.include_router(password_router, prefix=settings.API_V1_STR, tags=["Password"])

# Folder management router
app.include_router(folders_router, prefix=settings.API_V1_STR, tags=["Folders"])

# Audit log router
app.include_router(audit_router, prefix=f"{settings.API_V1_STR}/audit", tags=["Audit"])


# Direct route handler to bypass redirect issues for /api/v1/documents (no trailing slash)
# MUST BE DEFINED BEFORE including the router to take precedence
@app.get(
    f"{settings.API_V1_STR}/documents",
    response_model=DocumentList,
    include_in_schema=False,
)
async def documents_no_slash_direct(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    filename: Optional[str] = Query(
        None, description="Filter by filename (partial match)"
    ),
    file_type: Optional[FileType] = Query(
        None, description="Filter by file type (pdf or xlsx)"
    ),
    document_status: Optional[DocumentStatus] = Query(
        None, description="Filter by processing status"
    ),
    folder_id: Optional[str] = Query(
        None, description="Filter by folder ID (legacy uploads)"
    ),
    folder_path: Optional[str] = Query(
        None, description="Filter by folder path (target_path uploads, e.g. 'invoices')"
    ),
    folder_name: Optional[str] = Query(
        None, description="Filter by folder name (exact match lookup)"
    ),
    uploaded_by: Optional[str] = Query(None, description="Filter by uploader user ID"),
    current_user: Dict[str, Any] = Depends(get_current_user_dict),
):
    """Direct handler for /api/v1/documents (no trailing slash) to bypass FastAPI redirect behavior."""
    from app.services.document_service import document_service

    try:
        pagination = PaginationParams(page=page, per_page=per_page)
        filters = DocumentFilters(
            filename=filename,
            file_type=file_type,
            status=document_status,
            folder_id=folder_id,
            folder_path=folder_path,
            folder_name=folder_name,
            uploaded_by=uploaded_by,
        )

        documents = await document_service.list_documents(
            org_id=current_user["org_id"], pagination=pagination, filters=filters
        )
        return documents
    except Exception as e:
        logger.error(
            "Failed to list documents", error=str(e), org_id=current_user["org_id"]
        )
        raise HTTPException(status_code=500, detail="Failed to retrieve documents")


# Document management router - AFTER the direct route handler
app.include_router(
    documents_router, prefix=f"{settings.API_V1_STR}/documents", tags=["Documents"]
)

# Debug router (development/staging only)
app.include_router(debug_router, prefix=settings.API_V1_STR, tags=["Debug"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
        access_log=True,
    )
