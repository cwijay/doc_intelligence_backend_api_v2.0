"""
Document upload endpoints.

This module handles document upload operations, focusing on:
- File upload with comprehensive validation
- Storage path management (target_path vs folder_id)
- Metadata parsing and validation
- Error handling and logging
"""

from typing import Dict, Any, Optional
import json
from fastapi import APIRouter, File, Form, UploadFile, Depends, HTTPException, status

from app.models.schemas import DocumentUploadResponse
from app.services.document_service import (
    DocumentValidationError,
    DocumentUploadError,
    DocumentDuplicateError,
)
from app.services.usage_enforcement import check_storage_before_upload
from .common import (
    get_document_dependencies,
    get_user_context,
    handle_document_validation_error,
    handle_document_upload_error,
    handle_generic_error,
    log_operation_start,
    log_operation_success,
    logger,
)

router = APIRouter()


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    summary="📤 Upload Document",
    operation_id="uploadDocument",
    description="""Upload a new document with precise storage path control.
    
**Primary Parameters:**
- **file**: Document file (PDF, XLSX, CSV, JPEG, PNG, DOCX, DOC, PPTX, PPT, TXT, GIF, WEBP, TIFF - max 50MB)
- **target_path**: Complete GCS storage path (recommended)
    - Format: `{org_name}/original/{folder_name}/{document_name}`
    - Example: `"Google/original/invoices/invoice-2025-001.pdf"`
    - When provided, gives you complete control over storage location

**Legacy Parameters:**
- **folder_id**: Target folder ID (only used if target_path not provided)
- **metadata**: Additional metadata as JSON string (optional, default: "{}")

**Path Priority:**
1. If `target_path` provided: Uses exact client-specified path
2. If `folder_id` provided: Auto-generates path with folder structure  
3. Neither provided: Uses root folder with auto-generated path

**Authentication Required:** Session token in `Authorization: Bearer <token>` header

**Example Request:**
```bash
curl -X POST "http://localhost:8000/api/v1/documents/upload" \\
  -H "Authorization: Bearer <token>" \\
  -F "file=@invoice.pdf" \\
  -F "target_path=Google/original/invoices/invoice-2025-001.pdf" \\
  -F "metadata={\\"category\\": \\"invoice\\"}"
```

**Response Format:**
```json
{
  "success": true,
  "message": "Document uploaded successfully",
  "document": {
    "id": "78258b82-db53-41a3-848a-ce45a32f99c7",
    "filename": "invoice-2025-001.pdf",
    "file_type": "pdf",
    "file_size": 1024567,
    "status": "uploading",
    "storage_path": "Google/original/invoices/invoice-2025-001.pdf",
    "org_id": "oJIChgDgktkF30dAPy2c",
    "uploaded_by": "jhYXgm0s4avwacnBSXH9",
    "created_at": "2025-08-15T10:12:36.993659"
  },
  "upload_time_ms": 234
}
```

**Error Responses:**
- **400 Bad Request**: Invalid file, metadata, or validation error
- **409 Conflict**: Document with same name already exists in folder (use force_override=true to replace)
- **413 Payload Too Large**: File exceeds 50MB limit
- **422 Unprocessable Entity**: Invalid file type
- **500 Internal Server Error**: Upload processing error""",
    responses={
        200: {
            "description": "Document uploaded successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Document uploaded successfully",
                        "document": {
                            "id": "78258b82-db53-41a3-848a-ce45a32f99c7",
                            "filename": "document.pdf",
                            "file_type": "pdf",
                            "file_size": 1024567,
                            "status": "uploading",
                            "storage_path": "Google/original/invoices/document.pdf",
                            "org_id": "oJIChgDgktkF30dAPy2c",
                            "uploaded_by": "jhYXgm0s4avwacnBSXH9",
                            "created_at": "2025-08-15T10:12:36.993659",
                        },
                        "upload_time_ms": 234,
                    }
                }
            },
        },
        400: {
            "description": "Validation error",
            "content": {
                "application/json": {
                    "examples": {
                        "invalid_metadata": {
                            "summary": "Invalid metadata JSON",
                            "value": {"detail": "Invalid metadata JSON format"},
                        },
                        "file_validation": {
                            "summary": "File validation error",
                            "value": {
                                "detail": "File size exceeds maximum limit of 50MB"
                            },
                        },
                    }
                }
            },
        },
        409: {
            "description": "Document with same name already exists",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Document with same name already exists in folder",
                        "existing_document": {
                            "id": "abc123",
                            "filename": "invoice.pdf",
                            "created_at": "2025-01-15T10:00:00",
                            "uploaded_by": "user123",
                        },
                        "hint": "Use force_override=true to replace the existing document",
                    }
                }
            },
        },
        413: {
            "description": "File too large",
            "content": {
                "application/json": {
                    "example": {"detail": "File size exceeds maximum limit of 50MB"}
                }
            },
        },
        422: {
            "description": "Unsupported file type",
            "content": {
                "application/json": {"example": {"detail": "Unsupported file type"}}
            },
        },
        500: {
            "description": "Upload processing error",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "An error occurred while processing the document"
                    }
                }
            },
        },
    },
)
async def upload_document(
    file: UploadFile = File(..., description="Document file (max 50MB)"),
    target_path: Optional[str] = Form(
        None,
        description="Complete storage path: {org_name}/original/{folder_name}/{document_name}",
    ),
    folder_id: Optional[str] = Form(
        None, description="Target folder ID (legacy, ignored if target_path provided)"
    ),
    metadata: Optional[str] = Form(
        "{}", description="Additional metadata as JSON string"
    ),
    force_override: bool = Form(
        False,
        description="Force override existing document with same name in folder",
    ),
    user_context: Dict[str, str] = Depends(get_user_context),
    deps=Depends(get_document_dependencies),
):
    """
    Upload a new document with precise storage path control.

    This endpoint provides flexible document upload with comprehensive validation,
    detailed logging, and proper error handling following SOLID principles.
    """
    document_service = deps["document_service"]

    # Log upload operation start with detailed context
    log_operation_start(
        "Document upload",
        filename=file.filename if file else "NO_FILE",
        folder_id=folder_id,
        target_path=target_path,
        metadata=metadata,
        force_override=force_override,
        file_size=file.size if file else "UNKNOWN",
        content_type=file.content_type if file else "UNKNOWN",
        **user_context,
    )

    try:
        # Parse and validate metadata JSON
        parsed_metadata = _parse_metadata(metadata)

        # Extract user context
        org_id = user_context["org_id"]
        user_id = user_context["user_id"]

        # Check storage limit before upload
        file_size = file.size if file.size else 0
        if file_size == 0:
            # Read file content to determine size, then reset
            content = await file.read()
            file_size = len(content)
            await file.seek(0)

        await check_storage_before_upload(org_id, file_size)

        # Call document service to handle upload
        result = await document_service.create_document(
            org_id=org_id,
            file=file,
            user_id=user_id,
            folder_id=folder_id,
            target_path=target_path,
            metadata=parsed_metadata,
            force_override=force_override,
        )

        # Log successful upload
        log_operation_success(
            "Document upload",
            document_id=result.document.id if result.document else None,
            filename=file.filename,
            **user_context,
        )

        return result

    except DocumentDuplicateError as e:
        logger.warning(
            "Duplicate document detected",
            filename=file.filename,
            existing_document=e.existing_document,
            **user_context,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "detail": str(e),
                "existing_document": e.existing_document,
                "hint": "Use force_override=true to replace the existing document",
            },
        )
    except DocumentValidationError as e:
        raise handle_document_validation_error(e, "document upload", **user_context)
    except DocumentUploadError as e:
        raise handle_document_upload_error(e, "document upload", **user_context)
    except Exception as e:
        raise handle_generic_error(e, "document upload", **user_context)


def _parse_metadata(metadata: Optional[str]) -> Dict[str, Any]:
    """
    Parse and validate metadata JSON string.

    Args:
        metadata: JSON string containing metadata

    Returns:
        Dict containing parsed metadata

    Raises:
        HTTPException: If metadata JSON is invalid or not an object
    """
    try:
        parsed_metadata = json.loads(metadata) if metadata else {}
    except json.JSONDecodeError:
        logger.warning("Invalid metadata JSON format", metadata=metadata)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid metadata JSON format",
        )

    if not isinstance(parsed_metadata, dict):
        logger.warning(
            "Metadata must be JSON object", metadata_type=type(parsed_metadata).__name__
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Metadata must be a JSON object",
        )

    return parsed_metadata
