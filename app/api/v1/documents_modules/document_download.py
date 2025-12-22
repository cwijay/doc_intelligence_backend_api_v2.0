"""
Document download endpoints.

This module handles document download operations, focusing on:
- Generating signed download URLs for secure access
- Direct download redirects for browser compatibility
- Expiration time management
- Proper error handling for missing documents
"""

from typing import Dict
from fastapi import APIRouter, Query, Depends
from fastapi.responses import RedirectResponse

from app.models.schemas import DocumentDownloadResponse
from app.services.document_service import DocumentNotFoundError, DocumentValidationError
from .common import (
    get_document_dependencies,
    get_user_context,
    handle_document_not_found_error,
    handle_document_validation_error,
    handle_generic_error,
    log_operation_start,
    log_operation_success,
)

router = APIRouter()


@router.get(
    "/{document_id}/download",
    response_model=DocumentDownloadResponse,
    summary="🔗 Get Download URL",
    operation_id="getDownloadUrl",
    description="""Generate a signed download URL for secure document access.

**Authentication Required:** Session token in `Authorization: Bearer <token>` header

**Path Parameters:**
- `document_id`: Document unique identifier

**Query Parameters:**
- `expiration_minutes`: URL expiration time in minutes (default: 60, max: 1440/24 hours)

**Response Format:**
```json
{
  "success": true,
  "document_id": "78258b82-db53-41a3-848a-ce45a32f99c7",
  "filename": "invoice-2025-001.pdf",
  "download_url": "https://storage.googleapis.com/bucket/path?X-Goog-Algorithm=...",
  "expires_at": "2025-08-15T11:12:36.993659",
  "file_size": 1024567,
  "content_type": "application/pdf"
}
```

**Example Request:**
```bash
curl -X GET "http://localhost:8000/api/v1/documents/123/download?expiration_minutes=120" \\
  -H "Authorization: Bearer <token>"
```

**Use Cases:**
- Generate temporary download links for client applications
- Provide secure access without exposing permanent URLs
- Control access duration with expiration times
- Support both programmatic and browser-based downloads

**Security Features:**
- Signed URLs prevent unauthorized access
- Time-limited access (1 minute to 24 hours)
- Organization-scoped access control
- Audit logging of download requests""",
    responses={
        200: {
            "description": "Download URL generated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "document_id": "78258b82-db53-41a3-848a-ce45a32f99c7",
                        "filename": "document.pdf",
                        "download_url": "https://storage.googleapis.com/bucket/path?signed-url-params",
                        "expires_at": "2025-08-15T11:12:36.993659",
                        "file_size": 1024567,
                        "content_type": "application/pdf",
                    }
                }
            },
        },
        400: {
            "description": "Invalid expiration time",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Expiration time must be between 1 and 1440 minutes"
                    }
                }
            },
        },
        404: {
            "description": "Document not found",
            "content": {
                "application/json": {"example": {"detail": "Document not found"}}
            },
        },
        500: {
            "description": "URL generation error",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "An error occurred while generating download URL"
                    }
                }
            },
        },
    },
)
async def get_download_url(
    document_id: str,
    expiration_minutes: int = Query(
        60, ge=1, le=1440, description="URL expiration in minutes"
    ),
    user_context: Dict[str, str] = Depends(get_user_context),
    deps=Depends(get_document_dependencies),
):
    """
    Generate a signed download URL for secure document access.

    Creates a time-limited, signed URL that allows secure downloading
    of documents without exposing permanent storage paths.
    """
    document_service = deps["document_service"]
    org_id = user_context["org_id"]

    try:
        log_operation_start(
            "Download URL generation",
            document_id=document_id,
            expiration_minutes=expiration_minutes,
            **user_context,
        )

        result = await document_service.download_document(
            org_id=org_id,
            document_id=document_id,
            expiration_minutes=expiration_minutes,
        )

        log_operation_success(
            "Download URL generation",
            document_id=document_id,
            filename=result.filename,
            **user_context,
        )

        return result

    except DocumentNotFoundError as e:
        raise handle_document_not_found_error(
            e, "download URL generation", **user_context
        )
    except DocumentValidationError as e:
        raise handle_document_validation_error(
            e, "download URL generation", **user_context
        )
    except Exception as e:
        raise handle_generic_error(e, "download URL generation", **user_context)


@router.get(
    "/{document_id}/download/redirect",
    summary="↪️ Direct Download Redirect",
    operation_id="downloadDocumentRedirect",
    description="""Direct browser redirect to document download URL.

**Authentication Required:** Session token in `Authorization: Bearer <token>` header

**Path Parameters:**
- `document_id`: Document unique identifier

**Query Parameters:**
- `expiration_minutes`: URL expiration time in minutes (default: 60, max: 1440/24 hours)

**Behavior:**
- Returns HTTP 302 redirect to the signed download URL
- Browser will automatically start the download
- No JSON response - direct file download

**Example Request:**
```bash
# Browser will automatically download the file
curl -L "http://localhost:8000/api/v1/documents/123/download/redirect" \\
  -H "Authorization: Bearer <token>"
```

**Use Cases:**
- Direct browser downloads (e.g., "Download" button in web UI)
- Simple integration without handling JSON responses
- Automatic file downloads in client applications
- One-click download functionality

**Example HTML Usage:**
```html
<a href="/api/v1/documents/123/download/redirect?expiration_minutes=30" 
   target="_blank">
  Download Document
</a>
```

**Response Codes:**
- **302 Found**: Successful redirect to download URL
- **404 Not Found**: Document doesn't exist
- **401 Unauthorized**: Invalid or expired session token""",
    responses={
        302: {
            "description": "Redirect to download URL",
            "headers": {
                "Location": {
                    "description": "The signed download URL",
                    "schema": {"type": "string"},
                }
            },
        },
        404: {
            "description": "Document not found",
            "content": {
                "application/json": {"example": {"detail": "Document not found"}}
            },
        },
        500: {
            "description": "Redirect generation error",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "An error occurred while generating download redirect"
                    }
                }
            },
        },
    },
)
async def download_document_redirect(
    document_id: str,
    expiration_minutes: int = Query(
        60, ge=1, le=1440, description="URL expiration in minutes"
    ),
    user_context: Dict[str, str] = Depends(get_user_context),
    deps=Depends(get_document_dependencies),
):
    """
    Direct download redirect for document.

    Generates a signed download URL and returns an HTTP redirect response,
    allowing browsers to automatically initiate the download.
    """
    document_service = deps["document_service"]
    org_id = user_context["org_id"]

    try:
        log_operation_start(
            "Direct download redirect",
            document_id=document_id,
            expiration_minutes=expiration_minutes,
            **user_context,
        )

        result = await document_service.download_document(
            org_id=org_id,
            document_id=document_id,
            expiration_minutes=expiration_minutes,
        )

        log_operation_success(
            "Direct download redirect",
            document_id=document_id,
            filename=result.filename,
            **user_context,
        )

        return RedirectResponse(url=result.download_url, status_code=302)

    except DocumentNotFoundError as e:
        raise handle_document_not_found_error(e, "download redirect", **user_context)
    except Exception as e:
        raise handle_generic_error(e, "download redirect", **user_context)
