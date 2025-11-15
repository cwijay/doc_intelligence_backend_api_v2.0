import time
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional

from fastapi import FastAPI, Request, status, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.openapi.utils import get_openapi

# Import models for the direct route handler
from app.models.schemas import DocumentList, PaginationParams, DocumentFilters
from app.models.document import DocumentStatus, FileType
from app.core.simple_auth import get_current_user_dict

from app.core.config import settings
from app.core.logging import configure_logging, setup_request_logging, get_logger
from app.core.exceptions import setup_exception_handlers
from app.core.firebase_client import init_firebase, close_firebase, get_firebase_health

# Configure logging first
configure_logging()
logger = get_logger(__name__)

# Technology Stack:
# - Database: Google Cloud Firestore
# - Caching: Redis (GCP)
# - Vector DB: Pinecone
# - LLM: OpenAI GPT-4o-mini
# - Document Parser: LlamaParse
# - File Storage: Google Cloud Storage
# - Framework: FastAPI with async/await


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

    # Initialize Firebase connection
    try:
        await init_firebase()
        startup_tasks.append("Firebase initialized")
    except Exception as e:
        logger.error("Failed to initialize Firebase", error=str(e))
        if settings.ENVIRONMENT.lower() == "production":
            raise

    # Additional services can be initialized here
    # (Redis, Pinecone, etc. when implemented)

    logger.info("Application startup completed", tasks=startup_tasks)

    yield

    # Shutdown
    logger.info("Shutting down application")

    shutdown_tasks = []

    # Close Firebase connections
    try:
        await close_firebase()
        shutdown_tasks.append("Firebase closed")
    except Exception as e:
        logger.error("Error closing Firebase", error=str(e))

    # Close additional services here when implemented
    # (Redis, Pinecone, etc.)

    logger.info("Application shutdown completed", tasks=shutdown_tasks)


# Create FastAPI application with redirect_slashes enabled for proper routing
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    redirect_slashes=True,
    description="""# 🚀 Document Intelligence API

## Overview
FastAPI-based document processing API with AI features. Supports PDF/XLSX upload, processing, and intelligent content generation with multi-tenant organization support.

## 🤖 AI Features
- Document summarization
- FAQ generation  
- Question extraction
- AI content stored in Firestore

## 💻 For Next.js Developers
- TypeScript-compatible endpoints
- Generate types from OpenAPI spec
- All AI fields are optional for backward compatibility

## 🔐 Authentication
**Session-based JWT** with automatic refresh:
- **Header**: `Authorization: Bearer <session_token>`
- **Session**: 2 hours, **Refresh**: 7 days
- **Format**: UUID v4 tokens

**Key Endpoints:**
- `POST /api/v1/auth/login` - Get session + refresh tokens
- `POST /api/v1/auth/refresh-session` - Refresh tokens  
- `GET /api/v1/auth/validate` - Check token validity

## 📄 Documents
**File Support:** PDF, XLSX (max 50MB)  
**Storage:** Google Cloud Storage + Firestore metadata

**Upload Methods:**
- `target_path` (recommended): Full path control
- `folder_id` (legacy): Folder-based organization

**Filtering:**
- `folder_path`: Filter by path
- `folder_id`: Filter by folder ID
- `file_type`: Filter by type

## 🏢 Multi-Tenant
Organization-based isolation. All endpoints require organization context.

## ⚡ Rate Limits
- Auth: 5/min per IP
- Upload: 10/min per user
- General: 100/min per user

## 🚨 Error Handling
All errors follow consistent JSON format with specific error codes:

### Authentication Error Codes
- **TOKEN_EXPIRED**: Session token has expired → Use refresh token or re-login
- **TOKEN_INVALID**: Session token is invalid/not found → Re-login required
- **REFRESH_TOKEN_EXPIRED**: Refresh token expired → Re-login required  
- **REFRESH_TOKEN_INVALID**: Refresh token invalid → Re-login required

### Error Response Format
```json
{
  "error": {
    "code": "TOKEN_EXPIRED",
    "message": "Access token has expired",
    "error_id": "abc123",
    "details": {
      "expired_at": "2025-08-17T08:00:00Z",
      "action": "refresh_token_or_relogin"
    }
  }
}
```

### Additional Features
- Unique error ID for tracking and debugging
- Field-specific validation errors for forms
- Recommended actions in error details
- HTTP status codes (400, 401, 403, 404, 500)

## 🔄 Getting Started

### Quick Start Guide
1. **Get Organizations**: `GET /api/v1/auth/organizations` - List available organizations
2. **Register**: `POST /api/v1/auth/register` - Register with organization (get session + refresh tokens)
3. **Validate Token**: `GET /api/v1/auth/validate` - Check session status and expiration  
4. **Upload Documents**: `POST /api/v1/documents/upload` - Start uploading files
5. **List Documents**: `GET /api/v1/documents/` - View and manage documents

### Session Management Flow
```javascript
// 1. Login and get tokens
const authResponse = await login(email, password);
const { access_token, refresh_token } = authResponse;

// 2. Use access token for API calls
api.defaults.headers.Authorization = `Bearer ${access_token}`;

// 3. Check token validity periodically  
const validation = await api.get('/api/v1/auth/validate');

// 4. Refresh when needed (automatic rotation)
if (validation.in_grace_period) {
  const newTokens = await api.post('/api/v1/auth/refresh-session', {
    refresh_token
  });
}
```

### Frontend Integration
- **Session Duration**: 2 hours → Plan for automatic refresh
- **Validation Endpoint**: Check token status every 5 minutes
- **Error Handling**: Implement specific error code responses  
- **Refresh Logic**: Use refresh tokens for seamless user experience

For complete Next.js integration examples, see the authentication guide.
""",
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


# Custom OpenAPI schema with authentication
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        servers=app.servers,
        tags=[
            {
                "name": "Authentication",
                "description": "Session-based JWT authentication with refresh tokens",
            },
            {
                "name": "Documents",
                "description": "Document upload, processing, and AI content management",
            },
            {
                "name": "Organizations",
                "description": "Multi-tenant organization management",
            },
            {"name": "Users", "description": "User management and profiles"},
            {
                "name": "Folders",
                "description": "Document organization and folder management",
            },
            {
                "name": "Health",
                "description": "API health checks and status monitoring",
            },
        ],
    )

    # Add security schemes
    openapi_schema["components"]["securitySchemes"] = {
        "SessionAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "UUID",
            "description": "Session-based authentication using UUID tokens. Format: `Bearer <uuid>`. Tokens expire after 24 hours.",
        }
    }

    # Add examples to components
    openapi_schema["components"]["examples"] = {
        "LoginRequest": {
            "summary": "Login request",
            "value": {"email": "user@example.com", "password": "Password123!"},
        },
        "RegisterRequest": {
            "summary": "Registration request",
            "value": {
                "email": "user@example.com",
                "password": "Password123!",
                "full_name": "John Doe",
                "username": "johndoe",
                "organization_id": "oJIChgDgktkF30dAPy2c",
            },
        },
        "AuthResponse": {
            "summary": "Authentication response",
            "value": {
                "access_token": "b9a85c75-15de-4a7b-b278-651eaf42383f",
                "refresh_token": "b9a85c75-15de-4a7b-b278-651eaf42383f",
                "token_type": "bearer",
                "expires_in": 86400,
                "refresh_expires_in": 86400,
                "user": {
                    "user_id": "jhYXgm0s4avwacnBSXH9",
                    "email": "user@example.com",
                    "full_name": "John Doe",
                    "username": "johndoe",
                    "role": "user",
                    "org_id": "oJIChgDgktkF30dAPy2c",
                    "org_name": "Google",
                    "session_id": "b9a85c75-15de-4a7b-b278-651eaf42383f",
                },
            },
        },
        "DocumentUpload": {
            "summary": "Document upload response",
            "value": {
                "success": True,
                "message": "Document uploaded successfully",
                "document": {
                    "id": "doc-123",
                    "filename": "invoice.pdf",
                    "file_type": "pdf",
                    "file_size": 1024567,
                    "status": "uploaded",
                    "created_at": "2025-08-15T10:12:36Z",
                },
            },
        },
        "DocumentList": {
            "summary": "Documents list with pagination",
            "value": {
                "documents": [
                    {
                        "id": "doc-123",
                        "filename": "invoice.pdf",
                        "file_type": "pdf",
                        "file_size": 1024567,
                        "status": "uploaded",
                        "created_at": "2025-08-15T10:12:36Z",
                    }
                ],
                "total": 15,
                "page": 1,
                "per_page": 10,
            },
        },
        "ErrorResponse": {
            "summary": "Error response",
            "value": {
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Invalid email format",
                    "error_id": "unique-error-identifier",
                    "details": {
                        "field_errors": [
                            {
                                "field": "email",
                                "message": "Invalid email format",
                                "type": "format_error",
                            }
                        ]
                    },
                }
            },
        },
        "DocumentResponseWithAI": {
            "summary": "Document with AI content",
            "description": "Example of a document response including AI-generated content",
            "value": {
                "id": "doc-123e4567-e89b-12d3-a456-426614174000",
                "org_id": "oJIChgDgktkF30dAPy2c",
                "filename": "quarterly-report-q4-2024.pdf",
                "original_filename": "Q4 2024 Quarterly Financial Report.pdf",
                "file_type": "pdf",
                "file_size": 2048576,
                "storage_path": "TechCorp/original/reports/quarterly-report-q4-2024.pdf",
                "status": "parsed",
                "folder_id": None,
                "metadata": {"source": "web_upload", "category": "financial"},
                "file_content": "# Q4 2024 Financial Report...",
                "summary": "This quarterly report demonstrates strong performance with 15% revenue growth compared to the previous year...",
                "faq": [
                    {
                        "question": "What was the revenue growth in Q4 2024?",
                        "answer": "The company achieved 15% revenue growth compared to Q4 2023.",
                    },
                    {
                        "question": "Which segments performed best?",
                        "answer": "Cloud services and AI development showed the strongest growth.",
                    },
                ],
                "questions": [
                    "What are the key performance indicators for this quarter?",
                    "How do these results compare to previous quarters?",
                    "What are the growth projections for 2025?",
                ],
                "uploaded_by": "jhYXgm0s4avwacnBSXH9",
                "is_active": True,
                "created_at": "2024-12-15T09:30:00Z",
                "updated_at": "2024-12-15T10:30:00Z",
            },
        },
        "DocumentSummarizeResponseUpdated": {
            "summary": "Updated document summarization response",
            "description": "Response showing summary saved to Firestore instead of GCS",
            "value": {
                "success": True,
                "document_id": "doc-123e4567-e89b-12d3-a456-426614174000",
                "filename": "quarterly-report-q4-2024.pdf",
                "original_storage_path": "TechCorp/original/reports/quarterly-report-q4-2024.pdf",
                "summary_content": "# Q4 2024 Executive Summary\n\n## Financial Performance\n- Revenue growth: 15% YoY\n- Net profit margin: 12.3%\n- EBITDA: $2.4M\n\n## Key Highlights\n- Cloud services expansion accelerated\n- AI initiatives successfully launched\n- Strong customer retention: 94%\n\n## Strategic Outlook\n- Continued investment in AI development\n- Market expansion into new territories\n- Enhanced customer experience initiatives",
                "summary_metadata": {
                    "created_at": "2024-12-15T10:30:00Z",
                    "model": "gpt-4o-mini",
                    "content_length": 15420,
                    "summary_length": 542,
                    "processing_time_ms": 1850,
                },
                "saved_to_firestore": True,
                "timestamp": "2024-12-15T10:30:00Z",
            },
        },
    }

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

# Add CORS middleware FIRST - must be before exception handlers for OPTIONS requests
cors_origins = settings.resolved_cors_origins
logger.info("=" * 80)
logger.info(
    "CORS CONFIGURATION",
    environment=settings.ENVIRONMENT,
    debug_enabled=settings.ENABLE_CORS_DEBUG,
)
logger.info("Allowed CORS Origins:")
for idx, origin in enumerate(cors_origins, 1):
    logger.info(f"  {idx}. {origin}")
logger.info("CORS Credentials Enabled: %s", settings.CORS_CREDENTIALS)
logger.info("CORS Methods: %s", ", ".join(settings.CORS_METHODS))
logger.info("=" * 80)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=settings.CORS_CREDENTIALS,
    allow_methods=settings.CORS_METHODS,
    allow_headers=settings.CORS_HEADERS,
    expose_headers=["*"],  # Allow frontend to read all response headers
)

# Setup exception handlers AFTER CORS middleware
setup_exception_handlers(app)

# Setup request logging
setup_request_logging(app)

# Add security middleware
if settings.ENVIRONMENT.lower() == "production":
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*"],  # Configure this properly for production
    )


# Middleware for timing requests
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Add processing time header to responses."""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(round(process_time, 4))
    return response


# Root endpoint
@app.get("/", tags=["Root"])
async def root() -> Dict[str, Any]:
    """Root endpoint with API information."""
    return {
        "message": f"Welcome to {settings.PROJECT_NAME}",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "status": "running",
        "docs": "/docs" if settings.DEBUG else None,
        "redoc": "/redoc" if settings.DEBUG else None,
        "health": "/health",
        "status_endpoint": "/status",
    }


# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check() -> Dict[str, Any]:
    """Simple health check endpoint."""
    try:
        # Get basic health status
        health_status = {
            "status": "healthy",
            "timestamp": time.time(),
            "version": settings.VERSION,
            "environment": settings.ENVIRONMENT,
        }

        return health_status

    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "timestamp": time.time(),
                "version": settings.VERSION,
                "error": str(e),
            },
        )


# Detailed status endpoint
@app.get("/status", tags=["Health"])
async def detailed_status() -> Dict[str, Any]:
    """Detailed status endpoint with service health checks."""
    try:
        # Get Firebase health
        firebase_health = await get_firebase_health()

        # Overall status
        overall_status = "healthy"
        if not firebase_health.get("firestore_available", False):
            overall_status = "degraded"

        status_response = {
            "application": {
                "name": settings.PROJECT_NAME,
                "version": settings.VERSION,
                "environment": settings.ENVIRONMENT,
                "debug": settings.DEBUG,
                "status": overall_status,
            },
            "services": {
                "firestore": firebase_health,
                "redis": {"status": "not_implemented"},
                "pinecone": {"status": "not_implemented"},
                "openai": {"status": "not_implemented"},
                "llamaparse": {"status": "not_implemented"},
            },
            "configuration": {
                "cors_enabled": True,
                "cors_origins": settings.resolved_cors_origins,
                "api_prefix": settings.API_V1_STR,
                "log_level": settings.LOG_LEVEL,
                "log_format": settings.LOG_FORMAT,
            },
            "system": {
                "timestamp": time.time(),
                "uptime": time.time(),  # This would need to be calculated properly
            },
        }

        return status_response

    except Exception as e:
        logger.error("Status check failed", error=str(e))
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "error", "timestamp": time.time(), "error": str(e)},
        )


# Readiness probe (for Kubernetes)
@app.get("/ready", tags=["Health"])
async def readiness_check() -> Dict[str, Any]:
    """Readiness probe endpoint."""
    try:
        # Check if critical services are ready
        firebase_health = await get_firebase_health()

        if not firebase_health.get("firestore_available", False):
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "ready": False,
                    "reason": "Firestore not ready",
                    "timestamp": time.time(),
                },
            )

        return {"ready": True, "timestamp": time.time()}

    except Exception as e:
        logger.error("Readiness check failed", error=str(e))
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"ready": False, "reason": str(e), "timestamp": time.time()},
        )


# Liveness probe (for Kubernetes)
@app.get("/live", tags=["Health"])
async def liveness_check() -> Dict[str, Any]:
    """Liveness probe endpoint."""
    return {"alive": True, "timestamp": time.time()}


# Metrics endpoint (basic)
@app.get("/metrics", tags=["Health"])
async def metrics() -> Dict[str, Any]:
    """Basic metrics endpoint."""
    try:
        # This is a placeholder - in production, you'd use proper metrics
        return {
            "application": {
                "name": settings.PROJECT_NAME,
                "version": settings.VERSION,
                "uptime": time.time(),
            },
            "requests": {
                "total": "not_implemented",
                "errors": "not_implemented",
                "response_time": "not_implemented",
            },
            "firestore": {
                "connections": "not_implemented",
                "queries": "not_implemented",
            },
            "timestamp": time.time(),
        }
    except Exception as e:
        logger.error("Metrics collection failed", error=str(e))
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "Metrics collection failed", "timestamp": time.time()},
        )


# Include API routers
from app.api.v1.auth import router as auth_router
from app.api.v1.organizations import router as organizations_router
from app.api.v1.users import router as users_router
from app.api.v1.password import router as password_router
from app.api.v1.folders import router as folders_router

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
    uploaded_by: Optional[str] = Query(None, description="Filter by uploader user ID"),
    current_user: Dict[str, Any] = Depends(get_current_user_dict),
):
    """Direct handler for /api/v1/documents (no trailing slash) to bypass FastAPI redirect behavior."""
    # Import the service here to avoid circular imports
    from app.services.document_service import document_service

    try:
        # Create pagination and filter objects matching the service signature
        pagination = PaginationParams(page=page, per_page=per_page)
        filters = DocumentFilters(
            filename=filename,
            file_type=file_type,
            status=document_status,
            folder_id=folder_id,
            folder_path=folder_path,
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

# Other routers (when implemented)
# from app.api.v1 import auth, users, documents, search, ai
#
# app.include_router(
#     auth.router,
#     prefix=f"{settings.API_V1_STR}/auth",
#     tags=["Authentication"]
# )
# app.include_router(
#     users.router,
#     prefix=f"{settings.API_V1_STR}/users",
#     tags=["Users"]
# )
# app.include_router(
#     documents.router,
#     prefix=f"{settings.API_V1_STR}/documents",
#     tags=["Documents"]
# )
# app.include_router(
#     search.router,
#     prefix=f"{settings.API_V1_STR}/search",
#     tags=["Search"]
# )
# app.include_router(
#     ai.router,
#     prefix=f"{settings.API_V1_STR}/ai",
#     tags=["AI Operations"]
# )


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
