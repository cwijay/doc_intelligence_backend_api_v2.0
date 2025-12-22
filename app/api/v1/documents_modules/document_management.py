"""
Document management endpoints.

This module handles core document management operations, focusing on:
- Listing documents with filtering and pagination
- Retrieving individual documents
- Updating document status
- Deleting documents (soft delete)
"""

from typing import Dict, Optional
from fastapi import APIRouter, Query, Depends

from app.models.schemas import (
    DocumentList,
    DocumentResponse,
    DocumentDeleteResponse,
    DocumentStatusUpdate,
    PaginationParams,
    DocumentFilters,
    FileType,
    DocumentStatus,
)
from app.services.document_service import DocumentNotFoundError, DocumentValidationError
from .common import (
    get_document_dependencies,
    get_user_context,
    handle_document_not_found_error,
    handle_document_validation_error,
    handle_generic_error,
    log_operation_start,
    log_operation_success,
    logger,
)

router = APIRouter()


@router.get(
    "/",
    response_model=DocumentList,
    summary="📋 List Documents",
    operation_id="listDocuments",
    description="""List documents with pagination and filtering capabilities.

**Authentication Required:** Session token in `Authorization: Bearer <token>` header

**Query Parameters:**
- `page`: Page number (starts from 1)
- `per_page`: Items per page (max 100)
- `filename`: Filter by filename (partial match, case-insensitive)
- `file_type`: Filter by file type (`pdf` or `xlsx`)
- `status`: Filter by processing status

**🗂️ Folder Filtering (choose one):**
- `folder_id`: Filter by folder ID (for legacy uploads with folder_id)
- `folder_path`: Filter by folder path (for target_path uploads, e.g., `invoices`, `contracts`, `reports`)

**Other Filters:**
- `uploaded_by`: Filter by uploader user ID

**Example Requests:**
```bash
# List documents in "invoices" folder (target_path uploads)
GET /api/v1/documents/?folder_path=invoices

# List documents in legacy folder
GET /api/v1/documents/?folder_id=folder_123

# Combine filters: PDF invoices
GET /api/v1/documents/?folder_path=invoices&file_type=pdf

# Paginated results
GET /api/v1/documents/?page=1&per_page=10&file_type=pdf&status=uploaded
```

**Response Example:**
```json
{
  "documents": [
    {
      "id": "78258b82-db53-41a3-848a-ce45a32f99c7",
      "filename": "document.pdf",
      "file_type": "pdf",
      "file_size": 1024567,
      "status": "uploaded",
      "org_id": "oJIChgDgktkF30dAPy2c",
      "uploaded_by": "jhYXgm0s4avwacnBSXH9",
      "created_at": "2025-08-15T10:12:36.993659"
    }
  ],
  "total": 45,
  "page": 1,
  "per_page": 10,
  "total_pages": 5
}
```""",
    responses={
        200: {
            "description": "Documents listed successfully",
            "content": {
                "application/json": {
                    "examples": {
                        "folder_path_filter": {
                            "summary": "Documents filtered by folder_path (recommended)",
                            "value": {
                                "documents": [
                                    {
                                        "id": "78258b82-db53-41a3-848a-ce45a32f99c7",
                                        "filename": "invoice-2025-001.pdf",
                                        "original_filename": "invoice-2025-001.pdf",
                                        "folder_id": None,
                                        "metadata": {"category": "invoice"},
                                        "org_id": "oJIChgDgktkF30dAPy2c",
                                        "file_type": "pdf",
                                        "file_size": 1024567,
                                        "storage_path": "Google/original/invoices/invoice-2025-001.pdf",
                                        "status": "uploaded",
                                        "uploaded_by": "jhYXgm0s4avwacnBSXH9",
                                        "is_active": True,
                                        "created_at": "2025-08-15T10:12:36.993659",
                                        "updated_at": "2025-08-15T10:12:36.993662",
                                    }
                                ],
                                "total": 15,
                                "page": 1,
                                "per_page": 10,
                                "total_pages": 2,
                            },
                        },
                        "all_documents": {
                            "summary": "All documents (no folder filter)",
                            "value": {
                                "documents": [
                                    {
                                        "id": "78258b82-db53-41a3-848a-ce45a32f99c7",
                                        "filename": "document.pdf",
                                        "original_filename": "document.pdf",
                                        "folder_id": None,
                                        "metadata": {},
                                        "org_id": "oJIChgDgktkF30dAPy2c",
                                        "file_type": "pdf",
                                        "file_size": 1024567,
                                        "storage_path": "Google/original/root/document.pdf",
                                        "status": "uploaded",
                                        "uploaded_by": "jhYXgm0s4avwacnBSXH9",
                                        "is_active": True,
                                        "created_at": "2025-08-15T10:12:36.993659",
                                        "updated_at": "2025-08-15T10:12:36.993662",
                                    }
                                ],
                                "total": 45,
                                "page": 1,
                                "per_page": 10,
                                "total_pages": 5,
                            },
                        },
                    }
                }
            },
        },
        400: {
            "description": "Invalid query parameters",
            "content": {
                "application/json": {"example": {"detail": "Invalid query parameters"}}
            },
        },
        401: {
            "description": "Authentication required",
            "content": {
                "application/json": {
                    "example": {"detail": "Invalid or expired session token"}
                }
            },
        },
    },
)
async def list_documents(
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
    user_context: Dict[str, str] = Depends(get_user_context),
    deps=Depends(get_document_dependencies),
):
    """
    List documents with pagination and filtering.

    Provides comprehensive document listing with folder-based filtering,
    pagination, and multiple search criteria for efficient document discovery.
    """
    document_service = deps["document_service"]
    org_id = user_context["org_id"]

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

        logger.debug(
            "Listing documents",
            org_id=org_id,
            page=page,
            per_page=per_page,
            filters=filters.model_dump(exclude_none=True),
        )

        result = await document_service.list_documents(
            org_id=org_id, pagination=pagination, filters=filters
        )

        logger.debug(
            "Documents listed successfully",
            org_id=org_id,
            count=len(result.documents),
            total=result.total,
        )

        return result

    except Exception as e:
        raise handle_generic_error(e, "listing documents", **user_context)


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="📄 Get Document Details",
    operation_id="getDocument",
    description="""Retrieve detailed information about a specific document.

**Authentication Required:** Session token in `Authorization: Bearer <token>` header

**Path Parameters:**
- `document_id`: Document unique identifier

**Response includes:**
- Basic document metadata (filename, size, type, status)
- Storage information (path, folder)
- Processing information (status, metadata)
- Timestamps and user information

**Example Response:**
```json
{
  "id": "78258b82-db53-41a3-848a-ce45a32f99c7",
  "filename": "invoice-2025-001.pdf",
  "original_filename": "invoice-2025-001.pdf",
  "file_type": "pdf",
  "file_size": 1024567,
  "storage_path": "Google/original/invoices/invoice-2025-001.pdf",
  "status": "uploaded",
  "metadata": {"category": "invoice", "quarter": "Q4"},
  "org_id": "oJIChgDgktkF30dAPy2c",
  "uploaded_by": "jhYXgm0s4avwacnBSXH9",
  "created_at": "2025-08-15T10:12:36.993659",
  "updated_at": "2025-08-15T10:12:36.993662"
}
```""",
    responses={
        200: {
            "description": "Document retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": "78258b82-db53-41a3-848a-ce45a32f99c7",
                        "filename": "document.pdf",
                        "file_type": "pdf",
                        "file_size": 1024567,
                        "status": "uploaded",
                        "org_id": "oJIChgDgktkF30dAPy2c",
                        "uploaded_by": "jhYXgm0s4avwacnBSXH9",
                        "created_at": "2025-08-15T10:12:36.993659",
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
    },
)
async def get_document(
    document_id: str,
    user_context: Dict[str, str] = Depends(get_user_context),
    deps=Depends(get_document_dependencies),
):
    """
    Retrieve detailed information about a specific document.

    Returns comprehensive document information including metadata,
    processing status, and AI-generated content if available.
    """
    document_service = deps["document_service"]
    org_id = user_context["org_id"]

    try:
        logger.debug("Getting document", org_id=org_id, document_id=document_id)

        result = await document_service.get_document(
            org_id=org_id, document_id=document_id
        )

        logger.debug(
            "Document retrieved successfully",
            org_id=org_id,
            document_id=document_id,
            filename=result.filename,
        )

        return result

    except DocumentNotFoundError as e:
        raise handle_document_not_found_error(e, "retrieving document", **user_context)
    except Exception as e:
        raise handle_generic_error(e, "retrieving document", **user_context)


@router.put(
    "/{document_id}/status",
    response_model=DocumentResponse,
    summary="🔄 Update Document Status",
    operation_id="updateDocumentStatus",
    description="""Update the processing status of a document.

**Authentication Required:** Session token in `Authorization: Bearer <token>` header

**Path Parameters:**
- `document_id`: Document unique identifier

**Request Body:**
```json
{
  "status": "parsing",
  "metadata": {
    "updated_by": "system",
    "started_at": "2025-08-15T10:30:00Z"
  }
}
```

**Available Status Values:**
- `uploading`: File is being uploaded
- `uploaded`: File uploaded successfully
- `parsing`: Document is being parsed
- `parsed`: Document parsing completed
- `failed`: Processing failed

**Use Cases:**
- Mark document as parsing when processing starts
- Update to parsed when processing completes
- Set to failed if processing encounters errors
- Include relevant metadata about processing steps

**Example Request:**
```bash
curl -X PUT "http://localhost:8000/api/v1/documents/123/status" \\
  -H "Authorization: Bearer <token>" \\
  -H "Content-Type: application/json" \\
  -d '{
    "status": "parsed",
    "metadata": {
      "pages_processed": 15,
      "content_length": 45000
    }
  }'
```""",
    responses={
        200: {
            "description": "Status updated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": "78258b82-db53-41a3-848a-ce45a32f99c7",
                        "status": "parsed",
                        "updated_at": "2025-08-15T10:35:00.123456",
                    }
                }
            },
        },
        400: {
            "description": "Invalid status or validation error",
            "content": {
                "application/json": {"example": {"detail": "Invalid status transition"}}
            },
        },
        404: {
            "description": "Document not found",
            "content": {
                "application/json": {"example": {"detail": "Document not found"}}
            },
        },
    },
)
async def update_document_status(
    document_id: str,
    status_update: DocumentStatusUpdate,
    user_context: Dict[str, str] = Depends(get_user_context),
    deps=Depends(get_document_dependencies),
):
    """
    Update document processing status.

    Allows updating the processing status and associated metadata
    for tracking document processing workflows.
    """
    document_service = deps["document_service"]
    org_id = user_context["org_id"]
    user_id = user_context["user_id"]

    try:
        log_operation_start(
            "Document status update",
            document_id=document_id,
            new_status=status_update.status.value,
            **user_context,
        )

        result = await document_service.update_document_status(
            org_id=org_id,
            document_id=document_id,
            new_status=status_update.status,
            metadata=status_update.metadata,
        )

        log_operation_success(
            "Document status update",
            document_id=document_id,
            new_status=status_update.status.value,
            **user_context,
        )

        return result

    except DocumentNotFoundError as e:
        raise handle_document_not_found_error(e, "status update", **user_context)
    except DocumentValidationError as e:
        raise handle_document_validation_error(e, "status update", **user_context)
    except Exception as e:
        raise handle_generic_error(e, "document status update", **user_context)


@router.delete(
    "/{document_id}",
    response_model=DocumentDeleteResponse,
    summary="🗑️ Delete Document",
    operation_id="deleteDocument",
    description="""Delete a document from the system.

**Authentication Required:** Session token in `Authorization: Bearer <token>` header

**Path Parameters:**
- `document_id`: Document unique identifier

**Deletion Behavior:**
- **PostgreSQL**: Soft delete (sets `is_active: false`)
- **Google Cloud Storage**: Hard delete (file permanently removed)

**Response Format:**
```json
{
  "success": true,
  "message": "Document deleted successfully"
}
```

**Example Request:**
```bash
curl -X DELETE "http://localhost:8000/api/v1/documents/123" \\
  -H "Authorization: Bearer <token>"
```

**Important Notes:**
- This operation cannot be undone
- Original files are removed from GCS
- Document metadata remains in PostgreSQL for audit purposes""",
    responses={
        200: {
            "description": "Document deleted successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Document deleted successfully",
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
            "description": "Deletion error",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "An error occurred while deleting the document"
                    }
                }
            },
        },
    },
)
async def delete_document(
    document_id: str,
    user_context: Dict[str, str] = Depends(get_user_context),
    deps=Depends(get_document_dependencies),
):
    """
    Delete a document from the system.

    Performs soft delete in PostgreSQL and hard delete from GCS storage.
    This operation cannot be undone.
    """
    document_service = deps["document_service"]
    org_id = user_context["org_id"]

    try:
        log_operation_start(
            "Document deletion", document_id=document_id, **user_context
        )

        result = await document_service.delete_document(
            org_id=org_id, document_id=document_id
        )

        log_operation_success(
            "Document deletion", document_id=document_id, **user_context
        )

        return DocumentDeleteResponse(
            success=result["success"], message=result["message"]
        )

    except DocumentNotFoundError as e:
        raise handle_document_not_found_error(e, "deletion", **user_context)
    except Exception as e:
        raise handle_generic_error(e, "document deletion", **user_context)
