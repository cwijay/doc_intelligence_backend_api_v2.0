from typing import Optional, Dict, Any
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    UploadFile,
    File,
    Form,
    Query,
)
from fastapi.responses import RedirectResponse

from app.models.schemas import (
    DocumentResponse,
    DocumentList,
    DocumentUploadResponse,
    DocumentDownloadResponse,
    DocumentDeleteResponse,
    DocumentStatusUpdate,
    DocumentFilters,
    DocumentSyncValidationResponse,
    PaginationParams,
    DocumentParseRequest,
    DocumentParseResponse,
    ExistingDocumentParseResponse,
)
from app.models.document import DocumentStatus, FileType
from app.services.document_service import (
    document_service,
    DocumentNotFoundError,
    DocumentValidationError,
    DocumentUploadError,
)
from app.services.document.document_parsing_service import (
    document_parsing_service,
    DocumentParsingError,
    UnsupportedFileTypeError,
)

# AI service imports moved to document_summarization.py
from app.core.simple_auth import get_current_user_dict
from app.core.logging import get_api_logger

logger = get_api_logger()
router = APIRouter()


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    summary="📤 Upload Document",
    description="""Upload a document file (PDF or XLSX) with precise storage path control.

**Authentication Required:** Session token in `Authorization: Bearer <token>` header

**Supported File Types:**
- **PDF**: `application/pdf` (documents, invoices, reports)
- **XLSX**: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` (spreadsheets)

**File Constraints:**
- Maximum file size: 50MB
- Files are stored in Google Cloud Storage
- Metadata is saved in Firestore

**🎯 Storage Path Control (target_path parameter):**
The `target_path` parameter gives you **complete control** over where your document is stored in the GCS bucket.

**Format:** `{org_name}/original/{folder_name}/{document_name}`

**Examples:**
- `"Google/original/invoices/invoice-2025-001.pdf"`
- `"TechCorp/original/contracts/service-agreement.pdf"`  
- `"Startup/original/reports/quarterly-report.xlsx"`
- `"MyOrg/original/root/general-document.pdf"` (for root folder)

**Path Requirements:**
- Must contain exactly 4 segments separated by "/"
- Second segment must be "original" (file type indicator)
- Folder name required (use "root" for root folder)
- Document name must be valid filename (automatically sanitized)
- Total path length < 1024 characters
- No directory traversal characters (../, ./, etc.)

**Parameter Priority:**
- When `target_path` is provided: **Uses exact client-specified path**
- When `target_path` is omitted: Falls back to `folder_id` + auto-generated path

**Example cURL with target_path:**
```bash
curl -X POST http://localhost:8000/api/v1/documents/upload \\
  -H "Authorization: Bearer <token>" \\
  -F "file=@invoice.pdf" \\
  -F "target_path=Google/original/invoices/invoice-2025-001.pdf" \\
  -F "metadata={\\"source\\":\\"web_upload\\",\\"category\\":\\"invoice\\"}"
```

**Example cURL with folder_id (legacy):**
```bash  
curl -X POST http://localhost:8000/api/v1/documents/upload \\
  -H "Authorization: Bearer <token>" \\
  -F "file=@document.pdf" \\
  -F "folder_id=folder_123" \\
  -F "metadata={\\"source\\":\\"web_upload\\"}"
```

**Response Example:**
```json
{
  "success": true,
  "message": "Document uploaded successfully",
  "document": {
    "id": "78258b82-db53-41a3-848a-ce45a32f99c7",
    "filename": "invoice-2025-001.pdf",
    "file_type": "pdf",
    "file_size": 1024567,
    "storage_path": "Google/original/invoices/invoice-2025-001.pdf",
    "status": "uploaded",
    "org_id": "oJIChgDgktkF30dAPy2c",
    "uploaded_by": "jhYXgm0s4avwacnBSXH9",
    "created_at": "2025-08-15T10:12:36.993659"
  }
}
```
""",
    responses={
        200: {
            "description": "Document uploaded successfully",
            "content": {
                "application/json": {
                    "examples": {
                        "target_path_upload": {
                            "summary": "Upload with target_path (recommended)",
                            "value": {
                                "success": True,
                                "message": "Document uploaded successfully",
                                "document": {
                                    "id": "78258b82-db53-41a3-848a-ce45a32f99c7",
                                    "filename": "invoice-2025-001.pdf",
                                    "original_filename": "invoice-2025-001.pdf",
                                    "folder_id": None,
                                    "metadata": {
                                        "source": "web_upload",
                                        "category": "invoice",
                                    },
                                    "org_id": "oJIChgDgktkF30dAPy2c",
                                    "file_type": "pdf",
                                    "file_size": 1024567,
                                    "storage_path": "Google/original/invoices/invoice-2025-001.pdf",
                                    "status": "uploaded",
                                    "uploaded_by": "jhYXgm0s4avwacnBSXH9",
                                    "is_active": True,
                                    "created_at": "2025-08-15T10:12:36.993659",
                                    "updated_at": "2025-08-15T10:12:36.993662",
                                },
                            },
                        },
                        "folder_id_upload": {
                            "summary": "Upload with folder_id (legacy)",
                            "value": {
                                "success": True,
                                "message": "Document uploaded successfully",
                                "document": {
                                    "id": "12345678-abcd-4567-890e-123456789abc",
                                    "filename": "document.pdf",
                                    "original_filename": "document.pdf",
                                    "folder_id": "folder_123",
                                    "metadata": {"source": "web_upload"},
                                    "org_id": "oJIChgDgktkF30dAPy2c",
                                    "file_type": "pdf",
                                    "file_size": 2048000,
                                    "storage_path": "Google/original/contracts/document.pdf",
                                    "status": "uploaded",
                                    "uploaded_by": "jhYXgm0s4avwacnBSXH9",
                                    "is_active": True,
                                    "created_at": "2025-08-15T10:12:36.993659",
                                    "updated_at": "2025-08-15T10:12:36.993662",
                                },
                            },
                        },
                    }
                }
            },
        },
        400: {
            "description": "Validation error",
            "content": {
                "application/json": {
                    "examples": {
                        "invalid_file_type": {
                            "summary": "Invalid file type",
                            "value": {"detail": "Only PDF and XLSX files are allowed"},
                        },
                        "file_too_large": {
                            "summary": "File too large",
                            "value": {"detail": "File size must be less than 50MB"},
                        },
                        "invalid_metadata": {
                            "summary": "Invalid metadata JSON",
                            "value": {"detail": "Invalid metadata JSON format"},
                        },
                        "invalid_target_path": {
                            "summary": "Invalid target_path format",
                            "value": {
                                "detail": "Invalid target_path format. Must be: {org_name}/original/{folder_name}/{document_name}"
                            },
                        },
                        "unsafe_target_path": {
                            "summary": "Unsafe target_path with directory traversal",
                            "value": {
                                "detail": "Target path contains unsafe characters. Directory traversal not allowed."
                            },
                        },
                    }
                }
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
        500: {
            "description": "Upload failed",
            "content": {
                "application/json": {
                    "example": {"detail": "An unexpected error occurred during upload"}
                }
            },
        },
    },
)
async def upload_document(
    file: UploadFile = File(..., description="Document file (PDF or XLSX, max 50MB)"),
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
    current_user: Dict[str, Any] = Depends(
        get_current_user_dict
    ),  # TEMPORARY: Mock auth for testing
):
    """
    Upload a new document with precise storage path control.

    **Primary Parameters:**
    - **file**: Document file (PDF or XLSX, max 50MB)
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
    """
    # IMMEDIATE DEBUG LOGGING - This should appear in logs if endpoint is reached
    logger.info(
        "🚀 UPLOAD ENDPOINT CALLED",
        filename=file.filename if file else "NO_FILE",
        folder_id=folder_id,
        target_path=target_path,
        metadata=metadata,
        file_size=file.size if file else "UNKNOWN",
        content_type=file.content_type if file else "UNKNOWN",
    )

    # Log session authentication info
    logger.info(
        "🔐 SESSION AUTHENTICATION INFO",
        org_id=current_user.get("org_id"),
        user_id=current_user.get("user_id"),
        session_id=current_user.get("session_id", "")[:8] + "...",
        email=current_user.get("email"),
    )

    try:
        # Parse metadata JSON
        import json

        try:
            parsed_metadata = json.loads(metadata) if metadata else {}
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid metadata JSON format",
            )

        if not isinstance(parsed_metadata, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Metadata must be a JSON object",
            )

        # Get user/org info from session
        org_id = current_user["org_id"]
        user_id = current_user["user_id"]

        logger.info(
            "Document upload started",
            org_id=org_id,
            user_id=user_id,
            filename=file.filename,
            folder_id=folder_id,
        )

        result = await document_service.create_document(
            org_id=org_id,
            file=file,
            user_id=user_id,
            folder_id=folder_id,
            target_path=target_path,
            metadata=parsed_metadata,
        )

        logger.info(
            "Document uploaded successfully",
            org_id=org_id,
            user_id=user_id,
            document_id=result.document.id if result.document else None,
            filename=file.filename,
        )

        return result

    except DocumentValidationError as e:
        logger.warning(
            "Document upload validation failed",
            org_id=org_id,
            filename=file.filename,
            error=str(e),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except DocumentUploadError as e:
        logger.error(
            "Document upload failed",
            org_id=org_id,
            filename=file.filename,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
    except Exception as e:
        logger.error(
            "Unexpected error during document upload",
            org_id=org_id,
            filename=file.filename,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during upload",
        )


@router.get(
    "",
    response_model=DocumentList,
    summary="📋 List Documents",
    description="List documents with pagination and filtering - redirects to main route.",
    include_in_schema=False,
)
async def list_documents_no_slash(
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
    """Handle requests to /api/v1/documents (without trailing slash) - delegates to main route."""
    return await list_documents(
        page=page,
        per_page=per_page,
        filename=filename,
        file_type=file_type,
        document_status=document_status,
        folder_id=folder_id,
        folder_path=folder_path,
        uploaded_by=uploaded_by,
        current_user=current_user,
    )


@router.get(
    "/",
    response_model=DocumentList,
    summary="📋 List Documents",
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
```
""",
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
                                    },
                                    {
                                        "id": "abc12345-def6-789a-bcde-123456789abc",
                                        "filename": "invoice-2025-002.pdf",
                                        "original_filename": "invoice-2025-002.pdf",
                                        "folder_id": None,
                                        "metadata": {"category": "invoice"},
                                        "org_id": "oJIChgDgktkF30dAPy2c",
                                        "file_type": "pdf",
                                        "file_size": 2048000,
                                        "storage_path": "Google/original/invoices/invoice-2025-002.pdf",
                                        "status": "processed",
                                        "uploaded_by": "jhYXgm0s4avwacnBSXH9",
                                        "is_active": True,
                                        "created_at": "2025-08-15T11:30:15.123456",
                                        "updated_at": "2025-08-15T11:35:22.987654",
                                    },
                                ],
                                "total": 15,
                                "page": 1,
                                "per_page": 10,
                                "total_pages": 2,
                            },
                        },
                        "folder_id_filter": {
                            "summary": "Documents filtered by folder_id (legacy)",
                            "value": {
                                "documents": [
                                    {
                                        "id": "legacy123-456a-789b-cdef-987654321fed",
                                        "filename": "contract.pdf",
                                        "original_filename": "contract.pdf",
                                        "folder_id": "folder_123",
                                        "metadata": {},
                                        "org_id": "oJIChgDgktkF30dAPy2c",
                                        "file_type": "pdf",
                                        "file_size": 1536000,
                                        "storage_path": "Google/original/contracts/contract.pdf",
                                        "status": "uploaded",
                                        "uploaded_by": "jhYXgm0s4avwacnBSXH9",
                                        "is_active": True,
                                        "created_at": "2025-08-14T14:20:10.111222",
                                        "updated_at": "2025-08-14T14:20:10.111222",
                                    }
                                ],
                                "total": 7,
                                "page": 1,
                                "per_page": 10,
                                "total_pages": 1,
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
    uploaded_by: Optional[str] = Query(None, description="Filter by uploader user ID"),
    current_user: Dict[str, Any] = Depends(
        get_current_user_dict
    ),  # TEMPORARY: Mock auth for testing
):
    """
    List documents with pagination and filtering.

    **Parameters:**
    - **page**: Page number (starts from 1)
    - **per_page**: Items per page (max 100)
    - **filename**: Filter by filename (partial match, case-insensitive)
    - **file_type**: Filter by file type (`pdf` or `xlsx`)
    - **document_status**: Filter by processing status

    **Folder Filtering (choose one):**
    - **folder_id**: Filter by folder ID (for legacy uploads with folder_id)
    - **folder_path**: Filter by folder path (for target_path uploads, e.g. `invoices`, `contracts`)

    **Other Filters:**
    - **uploaded_by**: Filter by uploader user ID

    **Folder Filtering Examples:**
    - `GET /api/v1/documents/?folder_path=invoices` - Documents in invoices folder
    - `GET /api/v1/documents/?folder_id=folder_123` - Documents in legacy folder
    - `GET /api/v1/documents/?folder_path=contracts&file_type=pdf` - PDF contracts
    """
    try:
        # Get user/org info from session
        org_id = current_user["org_id"]

        pagination = PaginationParams(page=page, per_page=per_page)
        filters = DocumentFilters(
            filename=filename,
            file_type=file_type,
            status=document_status,
            folder_id=folder_id,
            folder_path=folder_path,
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
        logger.error("Error listing documents", org_id=org_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while listing documents",
        )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    current_user: Dict[str, Any] = Depends(
        get_current_user_dict
    ),  # TEMPORARY: Mock auth for testing
):
    """
    Get document details by ID.

    - **document_id**: Document unique identifier
    """
    try:
        # Get user/org info from session
        org_id = current_user["org_id"]

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
        logger.warning(
            "Document not found", org_id=org_id, document_id=document_id, error=str(e)
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(
            "Error retrieving document",
            org_id=org_id,
            document_id=document_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving the document",
        )


@router.get("/{document_id}/download", response_model=DocumentDownloadResponse)
async def get_download_url(
    document_id: str,
    expiration_minutes: int = Query(
        60, ge=1, le=1440, description="URL expiration in minutes"
    ),
    current_user: Dict[str, Any] = Depends(
        get_current_user_dict
    ),  # TEMPORARY: Mock auth for testing
):
    """
    Get signed download URL for document.

    - **document_id**: Document unique identifier
    - **expiration_minutes**: URL expiration time in minutes (max 24 hours)
    """
    try:
        # Get user/org info from session
        org_id = current_user["org_id"]

        logger.info(
            "Generating download URL",
            org_id=org_id,
            document_id=document_id,
            expiration_minutes=expiration_minutes,
        )

        result = await document_service.download_document(
            org_id=org_id,
            document_id=document_id,
            expiration_minutes=expiration_minutes,
        )

        logger.info(
            "Download URL generated successfully",
            org_id=org_id,
            document_id=document_id,
            filename=result.filename,
        )

        return result

    except DocumentNotFoundError as e:
        logger.warning(
            "Document not found for download",
            org_id=org_id,
            document_id=document_id,
            error=str(e),
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DocumentValidationError as e:
        logger.warning(
            "Document download validation failed",
            org_id=org_id,
            document_id=document_id,
            error=str(e),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(
            "Error generating download URL",
            org_id=org_id,
            document_id=document_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while generating download URL",
        )


@router.get("/{document_id}/download/redirect")
async def download_document_redirect(
    document_id: str,
    expiration_minutes: int = Query(
        60, ge=1, le=1440, description="URL expiration in minutes"
    ),
    current_user: Dict[str, Any] = Depends(
        get_current_user_dict
    ),  # TEMPORARY: Mock auth for testing
):
    """
    Direct download redirect for document.

    - **document_id**: Document unique identifier
    - **expiration_minutes**: URL expiration time in minutes (max 24 hours)

    Returns a redirect response to the signed download URL.
    """
    try:
        # Get user/org info from session
        org_id = current_user["org_id"]

        logger.info(
            "Generating direct download redirect",
            org_id=org_id,
            document_id=document_id,
        )

        result = await document_service.download_document(
            org_id=org_id,
            document_id=document_id,
            expiration_minutes=expiration_minutes,
        )

        logger.info(
            "Redirecting to download URL",
            org_id=org_id,
            document_id=document_id,
            filename=result.filename,
        )

        return RedirectResponse(url=result.download_url, status_code=302)

    except DocumentNotFoundError as e:
        logger.warning(
            "Document not found for download redirect",
            org_id=org_id,
            document_id=document_id,
            error=str(e),
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(
            "Error generating download redirect",
            org_id=org_id,
            document_id=document_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while generating download redirect",
        )


@router.put("/{document_id}/status", response_model=DocumentResponse)
async def update_document_status(
    document_id: str,
    status_update: DocumentStatusUpdate,
    current_user: Dict[str, Any] = Depends(
        get_current_user_dict
    ),  # TEMPORARY: Mock auth for testing
):
    """
    Update document processing status.

    - **document_id**: Document unique identifier
    - **status**: New processing status
    - **metadata**: Additional metadata (optional)
    """
    try:
        # Get user/org info from session
        org_id = current_user["org_id"]
        user_id = current_user["user_id"]

        logger.info(
            "Updating document status",
            org_id=org_id,
            user_id=user_id,
            document_id=document_id,
            new_status=status_update.status.value,
        )

        result = await document_service.update_document_status(
            org_id=org_id,
            document_id=document_id,
            new_status=status_update.status,
            metadata=status_update.metadata,
        )

        logger.info(
            "Document status updated successfully",
            org_id=org_id,
            document_id=document_id,
            new_status=status_update.status.value,
        )

        return result

    except DocumentNotFoundError as e:
        logger.warning(
            "Document not found for status update",
            org_id=org_id,
            document_id=document_id,
            error=str(e),
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DocumentValidationError as e:
        logger.warning(
            "Document status update validation failed",
            org_id=org_id,
            document_id=document_id,
            error=str(e),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(
            "Error updating document status",
            org_id=org_id,
            document_id=document_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating document status",
        )


@router.delete("/{document_id}", response_model=DocumentDeleteResponse)
async def delete_document(
    document_id: str,
    current_user: Dict[str, Any] = Depends(
        get_current_user_dict
    ),  # TEMPORARY: Mock auth for testing
):
    """
    Delete document.

    - **document_id**: Document unique identifier

    This performs a soft delete in Firestore and hard delete from GCS.
    """
    try:
        # Get user/org info from session
        org_id = current_user["org_id"]
        user_id = current_user["user_id"]

        logger.info(
            "Deleting document", org_id=org_id, user_id=user_id, document_id=document_id
        )

        result = await document_service.delete_document(
            org_id=org_id, document_id=document_id
        )

        logger.info(
            "Document deleted successfully", org_id=org_id, document_id=document_id
        )

        return DocumentDeleteResponse(
            success=result["success"], message=result["message"]
        )

    except DocumentNotFoundError as e:
        logger.warning(
            "Document not found for deletion",
            org_id=org_id,
            document_id=document_id,
            error=str(e),
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(
            "Error deleting document",
            org_id=org_id,
            document_id=document_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting the document",
        )


@router.get("/sync/validate", response_model=DocumentSyncValidationResponse)
async def validate_document_sync(
    folder_id: Optional[str] = Query(
        None, description="Filter by folder ID (optional)"
    ),
    current_user: Dict[str, Any] = Depends(
        get_current_user_dict
    ),  # TEMPORARY: Mock auth for testing
):
    """
    Validate sync between Firestore documents and GCS files.

    This endpoint performs a comprehensive check to ensure that:
    - All Firestore documents have corresponding GCS files
    - No duplicate storage paths exist in Firestore
    - No orphaned GCS files exist without metadata
    - No documents are stuck in UPLOADING status

    **Parameters:**
    - **folder_id**: Optional folder ID to filter validation scope

    **Response includes:**
    - **sync_status**: Overall health ('healthy', 'minor_issues', 'issues', 'error')
    - **summary**: Counts of documents, files, and issues
    - **issues**: Detailed list of any sync problems found
    - **recommendations**: Suggested actions to fix issues

    **Use Cases:**
    - Manual health checks before important operations
    - Troubleshooting document listing discrepancies
    - Periodic maintenance validation
    - Post-cleanup verification
    """
    try:
        # Get user/org info from session
        org_id = current_user["org_id"]

        logger.info("Validating document sync", org_id=org_id, folder_id=folder_id)

        result = await document_service.validate_sync(
            org_id=org_id, folder_id=folder_id
        )

        logger.info(
            "Document sync validation completed",
            org_id=org_id,
            folder_id=folder_id,
            sync_status=result["sync_status"],
            issues_count=result["summary"].get("issues_found", 0),
        )

        return DocumentSyncValidationResponse(**result)

    except Exception as e:
        logger.error(
            "Error during sync validation",
            org_id=org_id,
            folder_id=folder_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during sync validation",
        )


@router.get(
    "/firestore/by-filename/{filename}",
    response_model=None,  # We'll import the response model in the function
    summary="🔍 Get Document by Filename (Firestore)",
    description="""Get document information using filename from Firestore metadata store.

**Authentication Required:** Session token in `Authorization: Bearer <token>` header

**Key Features:**
- **Firestore-First Architecture**: Queries document metadata directly from Firestore instead of GCS
- **Rich Relationships**: Returns organization, folder, and uploader information in single response
- **Fast Queries**: Uses indexed Firestore queries instead of iterating GCS objects
- **Flexible Search**: Supports both exact and partial filename matching
- **Status Tracking**: Shows real-time processing pipeline status from database

**Path Parameters:**
- `filename`: Document filename to search for (e.g., "invoice-2025-001.pdf")

**Query Parameters:**
- `exact_match`: Boolean (default: true) - Whether to match exact filename or partial
- `include_inactive`: Boolean (default: false) - Whether to include soft-deleted documents

**Comparison with Regular Document API:**
- **Current API**: `/api/v1/documents/{document_id}` - Requires document ID, may use GCS metadata
- **This API**: `/api/v1/documents/firestore/by-filename/{filename}` - Search by filename, pure Firestore
- **Performance**: Firestore queries vs GCS API calls
- **Data Richness**: Includes related entity information vs basic document data

**Example Requests:**
```bash
# Exact filename match (default)
GET /api/v1/documents/firestore/by-filename/invoice-2025-001.pdf

# Partial filename match
GET /api/v1/documents/firestore/by-filename/invoice?exact_match=false

# Include soft-deleted documents
GET /api/v1/documents/firestore/by-filename/contract.pdf?include_inactive=true
```

**Response Example:**
```json
{
  "source": "firestore",
  "search_criteria": {
    "filename": "invoice-2025-001.pdf",
    "exact_match": true,
    "include_inactive": false
  },
  "document": {
    "id": "78258b82-db53-41a3-848a-ce45a32f99c7",
    "filename": "invoice-2025-001.pdf",
    "file_type": "pdf",
    "file_size": 1024567,
    "status": "processed",
    "metadata": {
      "category": "invoice",
      "processing_results": {...}
    },
    "org_id": "oJIChgDgktkF30dAPy2c",
    "created_at": "2025-08-15T10:12:36.993659"
  },
  "firestore_metadata": {
    "document_ref": "organizations/{org_id}/documents/{doc_id}",
    "query_method": "filename_exact_match",
    "last_updated": "2025-08-15T11:35:22.987654"
  },
  "relationships": {
    "organization": {
      "id": "oJIChgDgktkF30dAPy2c",
      "name": "Google"
    },
    "folder": {
      "id": "folder_123",
      "name": "Invoices", 
      "path": "/invoices"
    },
    "uploader": {
      "id": "jhYXgm0s4avwacnBSXH9",
      "email": "user@example.com",
      "full_name": "John Doe"
    }
  }
}
```

**Use Cases:**
- **File Upload Verification**: Check if filename already exists before upload
- **Document Search**: Find documents by partial filename match  
- **Processing Status Check**: Get current status of uploaded file
- **Relationship Exploration**: See which folder/user owns a document
- **Debugging**: Verify Firestore vs GCS consistency
- **Performance Testing**: Compare Firestore vs GCS metadata performance
""",
    responses={
        200: {
            "description": "Document found successfully",
            "content": {
                "application/json": {
                    "examples": {
                        "exact_match": {
                            "summary": "Exact filename match (default)",
                            "value": {
                                "source": "firestore",
                                "search_criteria": {
                                    "filename": "invoice-2025-001.pdf",
                                    "exact_match": True,
                                    "include_inactive": False,
                                },
                                "document": {
                                    "id": "78258b82-db53-41a3-848a-ce45a32f99c7",
                                    "filename": "invoice-2025-001.pdf",
                                    "original_filename": "invoice-2025-001.pdf",
                                    "file_type": "pdf",
                                    "file_size": 1024567,
                                    "storage_path": "Google/original/invoices/invoice-2025-001.pdf",
                                    "status": "processed",
                                    "metadata": {
                                        "category": "invoice",
                                        "source": "web_upload",
                                    },
                                    "org_id": "oJIChgDgktkF30dAPy2c",
                                    "folder_id": "folder_123",
                                    "uploaded_by": "jhYXgm0s4avwacnBSXH9",
                                    "is_active": True,
                                    "created_at": "2025-08-15T10:12:36.993659",
                                    "updated_at": "2025-08-15T11:35:22.987654",
                                },
                                "firestore_metadata": {
                                    "document_ref": "organizations/oJIChgDgktkF30dAPy2c/documents/78258b82-db53-41a3-848a-ce45a32f99c7",
                                    "query_method": "filename_exact_match",
                                    "last_updated": "2025-08-15T11:35:22.987654",
                                },
                                "relationships": {
                                    "organization": {
                                        "id": "oJIChgDgktkF30dAPy2c",
                                        "name": "Google",
                                    },
                                    "folder": {
                                        "id": "folder_123",
                                        "name": "Invoices",
                                        "path": "/invoices",
                                    },
                                    "uploader": {
                                        "id": "jhYXgm0s4avwacnBSXH9",
                                        "email": "user@example.com",
                                        "full_name": "John Doe",
                                    },
                                },
                            },
                        },
                        "partial_match": {
                            "summary": "Partial filename match",
                            "value": {
                                "source": "firestore",
                                "search_criteria": {
                                    "filename": "invoice",
                                    "exact_match": False,
                                    "include_inactive": False,
                                },
                                "document": {
                                    "id": "abc12345-def6-789a-bcde-123456789abc",
                                    "filename": "invoice-2025-002.pdf",
                                    "original_filename": "invoice-2025-002.pdf",
                                    "file_type": "pdf",
                                    "file_size": 2048000,
                                    "storage_path": "Google/original/invoices/invoice-2025-002.pdf",
                                    "status": "uploaded",
                                    "metadata": {"category": "invoice"},
                                    "org_id": "oJIChgDgktkF30dAPy2c",
                                    "folder_id": None,
                                    "uploaded_by": "jhYXgm0s4avwacnBSXH9",
                                    "is_active": True,
                                    "created_at": "2025-08-15T11:30:15.123456",
                                    "updated_at": "2025-08-15T11:30:15.123456",
                                },
                                "firestore_metadata": {
                                    "document_ref": "organizations/oJIChgDgktkF30dAPy2c/documents/abc12345-def6-789a-bcde-123456789abc",
                                    "query_method": "filename_partial_match",
                                    "last_updated": "2025-08-15T11:30:15.123456",
                                },
                                "relationships": {
                                    "organization": {
                                        "id": "oJIChgDgktkF30dAPy2c",
                                        "name": "Google",
                                    },
                                    "folder": None,
                                    "uploader": {
                                        "id": "jhYXgm0s4avwacnBSXH9",
                                        "email": "user@example.com",
                                        "full_name": "John Doe",
                                    },
                                },
                            },
                        },
                    }
                }
            },
        },
        404: {
            "description": "Document not found",
            "content": {
                "application/json": {
                    "examples": {
                        "not_found_exact": {
                            "summary": "Document not found with exact match",
                            "value": {
                                "detail": "No document found with filename 'nonexistent.pdf' using exact match"
                            },
                        },
                        "not_found_partial": {
                            "summary": "Document not found with partial match",
                            "value": {
                                "detail": "No document found with filename 'xyz' using partial match"
                            },
                        },
                    }
                }
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
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "An error occurred while searching for document"
                    }
                }
            },
        },
    },
)
async def get_document_by_filename_firestore(
    filename: str,
    exact_match: bool = Query(
        True, description="Whether to match exact filename (true) or partial (false)"
    ),
    include_inactive: bool = Query(
        False, description="Whether to include soft-deleted documents"
    ),
    current_user: Dict[str, Any] = Depends(
        get_current_user_dict
    ),  # TEMPORARY: Mock auth for testing
):
    """
    Get document by filename using Firestore as the primary data source.

    This endpoint demonstrates proper Firestore-first architecture by:
    - Querying document metadata directly from Firestore (not GCS)
    - Using indexed Firestore queries for fast filename search
    - Enriching response with relationship data (organization, folder, user)
    - Providing comprehensive document information in single API call
    - Showing processing pipeline status from database

    **Parameters:**
    - **filename**: Document filename to search for (URL path parameter)
    - **exact_match**: Whether to match exact filename (default: true) or partial
    - **include_inactive**: Whether to include soft-deleted documents (default: false)

    **Key Benefits over GCS-based approach:**
    - **Performance**: Direct Firestore queries vs iterating GCS objects
    - **Rich Data**: Complete metadata and relationships vs basic file info
    - **Real-time Status**: Processing pipeline status from database
    - **Flexible Search**: Both exact and partial filename matching
    - **Organization Isolation**: Automatic org-scoped queries
    """
    # Import here to avoid circular imports

    try:
        # Get user/org info from session
        org_id = current_user["org_id"]

        logger.info(
            "Firestore filename search requested",
            org_id=org_id,
            filename=filename,
            exact_match=exact_match,
            include_inactive=include_inactive,
            user_id=current_user.get("user_id"),
        )

        result = await document_service.get_document_by_filename_from_firestore(
            org_id=org_id,
            filename=filename,
            exact_match=exact_match,
            include_inactive=include_inactive,
        )

        logger.info(
            "Firestore filename search completed successfully",
            org_id=org_id,
            filename=filename,
            document_id=result.document.id,
            exact_match=exact_match,
            query_method=result.firestore_metadata.query_method,
        )

        return result

    except DocumentNotFoundError as e:
        logger.warning(
            "Document not found in Firestore filename search",
            org_id=org_id,
            filename=filename,
            exact_match=exact_match,
            error=str(e),
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(
            "Error in Firestore filename search",
            org_id=org_id,
            filename=filename,
            exact_match=exact_match,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while searching for document",
        )


@router.get(
    "/firestore/by-folder-name/{folder_name}",
    response_model=None,  # We'll import the response model in the function
    summary="📁 List Documents by Folder Name (Firestore)",
    description="""List all documents in a folder using folder name with Firestore-first architecture.

**Authentication Required:** Session token in `Authorization: Bearer <token>` header

**Key Features:**
- **Firestore-First Architecture**: Queries documents directly from Firestore using indexed folder_id
- **Natural Search**: Search by human-readable folder name instead of folder ID
- **Rich Folder Context**: Returns complete folder information along with documents
- **Fast Queries**: Uses indexed Firestore queries instead of GCS bucket iteration
- **Comprehensive Filtering**: Support file type, status, filename filters within folder
- **Efficient Pagination**: Database-level pagination for large folders

**Path Parameters:**
- `folder_name`: Folder name to search for (e.g., "invoices", "contracts", "reports")

**Query Parameters:**
- `page`: Page number (default: 1, min: 1)
- `per_page`: Items per page (default: 20, min: 1, max: 100)
- `exact_match`: Boolean (default: true) - Whether to match exact folder name or partial
- `include_inactive`: Boolean (default: false) - Whether to include soft-deleted documents
- `file_type`: Filter by file type (pdf, xlsx)
- `status`: Filter by document processing status (uploaded, parsing, parsed, failed)
- `filename`: Filter by filename within folder (partial match, case-insensitive)

**Architecture Benefits over GCS iteration:**
- **Performance**: Direct Firestore indexed queries vs expensive GCS bucket listing
- **Rich Data**: Complete document metadata + folder context vs basic file info
- **Real-time**: Processing status from database vs static file information
- **Scalable**: Indexed queries scale better than bucket iteration
- **Flexible**: Multiple filter combinations within folder context

**Example Requests:**
```bash
# List all documents in "invoices" folder
GET /api/v1/documents/firestore/by-folder-name/invoices

# Paginated PDF documents in "contracts" folder  
GET /api/v1/documents/firestore/by-folder-name/contracts?file_type=pdf&page=2&per_page=10

# Partial folder name match with filename filter
GET /api/v1/documents/firestore/by-folder-name/invoice?exact_match=false&filename=2025

# Include inactive documents in "archive" folder
GET /api/v1/documents/firestore/by-folder-name/archive?include_inactive=true

# Filter by processing status
GET /api/v1/documents/firestore/by-folder-name/pending?status=parsing
```

**Response Example:**
```json
{
  "source": "firestore",
  "folder_info": {
    "id": "invoices",
    "name": "invoices", 
    "path": "/invoices",
    "parent_folder_id": null,
    "created_by": "user123",
    "created_at": "2025-08-01T10:00:00Z",
    "document_count": 25
  },
  "search_criteria": {
    "folder_name": "invoices",
    "exact_match": true,
    "include_inactive": false,
    "additional_filters": {
      "file_type": "pdf"
    }
  },
  "documents": [
    {
      "id": "doc123",
      "filename": "invoice-2025-001.pdf",
      "file_type": "pdf",
      "file_size": 1024567,
      "status": "parsed",
      "folder_id": "invoices",
      "created_at": "2025-08-15T10:12:36Z"
    }
  ],
  "total": 25,
  "page": 1,
  "per_page": 20,
  "total_pages": 2,
  "firestore_metadata": {
    "document_ref": "organizations/{org_id}/documents (folder_id == invoices)",
    "query_method": "folder_id_exact_match_with_filters",
    "last_updated": "2025-08-17T16:30:00Z"
  }
}
```

**Use Cases:**
- **Folder Organization**: List all documents in specific business folders
- **Content Management**: Browse documents by logical folder structure  
- **Batch Operations**: Select documents within folder for bulk processing
- **Audit & Compliance**: Review documents organized by department/project
- **Search & Discovery**: Find documents within specific folder contexts
- **Performance Monitoring**: Compare Firestore vs GCS listing performance
""",
    responses={
        200: {
            "description": "Documents listed successfully",
            "content": {
                "application/json": {
                    "examples": {
                        "folder_with_documents": {
                            "summary": "Folder with multiple documents",
                            "value": {
                                "source": "firestore",
                                "folder_info": {
                                    "id": "invoices",
                                    "name": "invoices",
                                    "path": "/invoices",
                                    "parent_folder_id": None,
                                    "created_by": "user123",
                                    "created_at": "2025-08-01T10:00:00Z",
                                    "document_count": 15,
                                },
                                "search_criteria": {
                                    "folder_name": "invoices",
                                    "exact_match": True,
                                    "include_inactive": False,
                                    "additional_filters": {},
                                },
                                "documents": [
                                    {
                                        "id": "78258b82-db53-41a3-848a-ce45a32f99c7",
                                        "filename": "invoice-2025-001.pdf",
                                        "original_filename": "invoice-2025-001.pdf",
                                        "file_type": "pdf",
                                        "file_size": 1024567,
                                        "storage_path": "Google/original/invoices/invoice-2025-001.pdf",
                                        "status": "parsed",
                                        "metadata": {"category": "invoice"},
                                        "org_id": "oJIChgDgktkF30dAPy2c",
                                        "folder_id": "invoices",
                                        "uploaded_by": "jhYXgm0s4avwacnBSXH9",
                                        "is_active": True,
                                        "created_at": "2025-08-15T10:12:36.993659",
                                        "updated_at": "2025-08-15T11:35:22.987654",
                                    },
                                    {
                                        "id": "abc12345-def6-789a-bcde-123456789abc",
                                        "filename": "invoice-2025-002.pdf",
                                        "original_filename": "invoice-2025-002.pdf",
                                        "file_type": "pdf",
                                        "file_size": 2048000,
                                        "storage_path": "Google/original/invoices/invoice-2025-002.pdf",
                                        "status": "uploaded",
                                        "metadata": {"category": "invoice"},
                                        "org_id": "oJIChgDgktkF30dAPy2c",
                                        "folder_id": "invoices",
                                        "uploaded_by": "jhYXgm0s4avwacnBSXH9",
                                        "is_active": True,
                                        "created_at": "2025-08-15T11:30:15.123456",
                                        "updated_at": "2025-08-15T11:30:15.123456",
                                    },
                                ],
                                "total": 15,
                                "page": 1,
                                "per_page": 20,
                                "total_pages": 1,
                                "firestore_metadata": {
                                    "document_ref": "organizations/oJIChgDgktkF30dAPy2c/documents (folder_id == invoices)",
                                    "query_method": "folder_id_exact_match_with_filters",
                                    "last_updated": "2025-08-17T16:30:00Z",
                                },
                            },
                        },
                        "empty_folder": {
                            "summary": "Empty folder (no documents)",
                            "value": {
                                "source": "firestore",
                                "folder_info": {
                                    "id": "empty_folder",
                                    "name": "empty_folder",
                                    "path": "/empty_folder",
                                    "parent_folder_id": None,
                                    "created_by": "user123",
                                    "created_at": "2025-08-10T14:00:00Z",
                                    "document_count": 0,
                                },
                                "search_criteria": {
                                    "folder_name": "empty_folder",
                                    "exact_match": True,
                                    "include_inactive": False,
                                    "additional_filters": {},
                                },
                                "documents": [],
                                "total": 0,
                                "page": 1,
                                "per_page": 20,
                                "total_pages": 0,
                                "firestore_metadata": {
                                    "document_ref": "organizations/oJIChgDgktkF30dAPy2c/documents (folder_id == empty_folder)",
                                    "query_method": "folder_id_exact_match_with_filters",
                                    "last_updated": "2025-08-17T16:30:00Z",
                                },
                            },
                        },
                        "filtered_results": {
                            "summary": "Folder with filtered results (PDF only)",
                            "value": {
                                "source": "firestore",
                                "folder_info": {
                                    "id": "mixed_docs",
                                    "name": "mixed_docs",
                                    "path": "/mixed_docs",
                                    "parent_folder_id": None,
                                    "created_by": "user123",
                                    "created_at": "2025-08-05T09:00:00Z",
                                    "document_count": 3,
                                },
                                "search_criteria": {
                                    "folder_name": "mixed_docs",
                                    "exact_match": True,
                                    "include_inactive": False,
                                    "additional_filters": {"file_type": "pdf"},
                                },
                                "documents": [
                                    {
                                        "id": "pdf-doc-123",
                                        "filename": "report.pdf",
                                        "original_filename": "report.pdf",
                                        "file_type": "pdf",
                                        "file_size": 3048000,
                                        "storage_path": "Google/original/mixed_docs/report.pdf",
                                        "status": "parsed",
                                        "folder_id": "mixed_docs",
                                        "org_id": "oJIChgDgktkF30dAPy2c",
                                        "uploaded_by": "jhYXgm0s4avwacnBSXH9",
                                        "is_active": True,
                                        "created_at": "2025-08-16T15:20:00Z",
                                        "updated_at": "2025-08-16T15:25:00Z",
                                    }
                                ],
                                "total": 3,
                                "page": 1,
                                "per_page": 20,
                                "total_pages": 1,
                                "firestore_metadata": {
                                    "document_ref": "organizations/oJIChgDgktkF30dAPy2c/documents (folder_id == mixed_docs)",
                                    "query_method": "folder_id_exact_match_with_filters",
                                    "last_updated": "2025-08-17T16:30:00Z",
                                },
                            },
                        },
                    }
                }
            },
        },
        404: {
            "description": "Folder not found",
            "content": {
                "application/json": {
                    "examples": {
                        "folder_not_found_exact": {
                            "summary": "Folder not found with exact match",
                            "value": {
                                "detail": "No folder found with name 'nonexistent_folder' using exact match"
                            },
                        },
                        "folder_not_found_partial": {
                            "summary": "Folder not found with partial match",
                            "value": {
                                "detail": "No folder found with name 'xyz' using partial match"
                            },
                        },
                    }
                }
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
        400: {
            "description": "Invalid query parameters",
            "content": {
                "application/json": {
                    "examples": {
                        "invalid_pagination": {
                            "summary": "Invalid pagination parameters",
                            "value": {
                                "detail": "Page must be >= 1 and per_page must be between 1 and 100"
                            },
                        },
                        "invalid_filters": {
                            "summary": "Invalid filter parameters",
                            "value": {
                                "detail": "Invalid file_type. Must be 'pdf' or 'xlsx'"
                            },
                        },
                    }
                }
            },
        },
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "An error occurred while searching for documents in folder"
                    }
                }
            },
        },
    },
)
async def list_documents_by_folder_name_firestore(
    folder_name: str,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    exact_match: bool = Query(
        True, description="Whether to match exact folder name (true) or partial (false)"
    ),
    include_inactive: bool = Query(
        False, description="Whether to include soft-deleted documents"
    ),
    file_type: Optional[FileType] = Query(
        None, description="Filter by file type (pdf or xlsx)"
    ),
    document_status: Optional[DocumentStatus] = Query(
        None, description="Filter by processing status"
    ),
    filename: Optional[str] = Query(
        None, description="Filter by filename within folder (partial match)"
    ),
    current_user: Dict[str, Any] = Depends(
        get_current_user_dict
    ),  # TEMPORARY: Mock auth for testing
):
    """
    List documents in a folder by folder name using Firestore as the primary data source.

    This endpoint demonstrates proper Firestore-first architecture by:
    - Finding folder by human-readable name instead of requiring folder ID
    - Querying documents directly from Firestore using indexed folder_id
    - Providing comprehensive folder and document information in single response
    - Supporting efficient pagination and multiple filtering options
    - Using database queries instead of expensive GCS bucket iteration

    **Parameters:**
    - **folder_name**: Human-readable folder name to search for (URL path parameter)
    - **page**: Page number for pagination (default: 1)
    - **per_page**: Items per page (default: 20, max: 100)
    - **exact_match**: Whether to match exact folder name (default: true) or partial
    - **include_inactive**: Whether to include soft-deleted documents (default: false)
    - **file_type**: Filter by file type (pdf, xlsx) within folder
    - **document_status**: Filter by processing status within folder
    - **filename**: Filter by filename within folder (case-insensitive partial match)

    **Key Benefits over GCS bucket iteration:**
    - **Performance**: Indexed Firestore queries vs expensive bucket listing
    - **Rich Data**: Complete metadata and folder context vs basic file info
    - **Real-time Status**: Processing pipeline status from database
    - **Flexible Filtering**: Multiple filter combinations within folder
    - **Natural Search**: Use folder names instead of folder IDs
    - **Efficient Pagination**: Database-level pagination for large folders
    """
    # Import here to avoid circular imports
    from app.models.schemas import (
        PaginationParams,
        DocumentFilters,
    )

    try:
        # Get user/org info from session
        org_id = current_user["org_id"]

        logger.info(
            "Firestore folder document listing requested",
            org_id=org_id,
            folder_name=folder_name,
            page=page,
            per_page=per_page,
            exact_match=exact_match,
            include_inactive=include_inactive,
            file_type=file_type.value if file_type else None,
            document_status=document_status.value if document_status else None,
            filename=filename,
            user_id=current_user.get("user_id"),
        )

        # Build pagination parameters
        pagination = PaginationParams(page=page, per_page=per_page)

        # Build additional filters
        additional_filters = DocumentFilters(
            file_type=file_type, status=document_status, filename=filename
        )

        result = await document_service.get_documents_by_folder_name_from_firestore(
            org_id=org_id,
            folder_name=folder_name,
            pagination=pagination,
            exact_match=exact_match,
            include_inactive=include_inactive,
            additional_filters=additional_filters,
        )

        logger.info(
            "Firestore folder document listing completed successfully",
            org_id=org_id,
            folder_name=folder_name,
            folder_id=result.folder_info.id,
            total_documents=result.total,
            returned_documents=len(result.documents),
            page=page,
            exact_match=exact_match,
            query_method=result.firestore_metadata.query_method,
        )

        return result

    except DocumentNotFoundError as e:
        logger.warning(
            "Folder not found in Firestore folder search",
            org_id=org_id,
            folder_name=folder_name,
            exact_match=exact_match,
            error=str(e),
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(
            "Error in Firestore folder document listing",
            org_id=org_id,
            folder_name=folder_name,
            exact_match=exact_match,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while searching for documents in folder",
        )


@router.post(
    "/parse",
    response_model=DocumentParseResponse,
    summary="🔍 Parse Document from GCS",
    description="""Parse a document file stored in GCS and convert to markdown format.

**Authentication Required:** Session token in `Authorization: Bearer <token>` header

**Key Features:**
- **File Type Support**: PDF, XLSX, XLS, CSV documents
- **LlamaParse Integration**: Advanced document parsing with AI
- **Markdown Output**: Structured markdown format with headers, tables, and metadata
- **GCS Integration**: Downloads from and stores results in Google Cloud Storage
- **Automatic Storage**: Parsed content stored in `{org_name}/parsed/{folder_name}/{filename}.md`
- **Metadata Extraction**: Document structure, page count, headers/footers
- **Organization Isolation**: Only access files within user's organization
- **Status Tracking**: Updates document status in Firestore

**Request Body:**
- `storage_path`: Complete GCS storage path of the document to parse
  - Format: `"Google/original/invoices/invoice-2025-001.pdf"`
  - Must be a valid path within your organization's GCS bucket

**Parsing Process:**
1. **Validate**: Check file exists and type is supported
2. **Download**: Retrieve file content from GCS
3. **Parse**: Use LlamaParse to extract content and structure
4. **Store**: Save markdown result to parsed folder in GCS
5. **Update**: Mark document as parsed in Firestore metadata

**Supported File Types:**
- **PDF**: `application/pdf` (documents, invoices, reports, forms)
- **XLSX**: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- **XLS**: `application/vnd.ms-excel` (legacy Excel files)
- **CSV**: `text/csv` (comma-separated values)

**Example Request:**
```bash
curl -X POST "http://localhost:8000/api/v1/documents/parse" \\
  -H "Authorization: Bearer <session_token>" \\
  -H "Content-Type: application/json" \\
  -d '{"storage_path": "Google/original/invoices/invoice-2025-001.pdf"}'
```

**Use Cases:**
- **Document Digitization**: Convert PDFs to searchable text
- **Data Extraction**: Extract structured data from invoices, forms
- **Content Analysis**: Prepare documents for AI processing
- **Search Indexing**: Create text versions for search engines
- **Workflow Automation**: Automate document processing pipelines
- **Compliance**: Extract text for legal/regulatory review
""",
    responses={
        200: {
            "description": "Document parsed successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "storage_path": "Google/original/invoices/invoice-2025-001.pdf",
                        "parsed_storage_path": "Google/parsed/invoices/invoice-2025-001.md",
                        "parsed_content": "# Invoice 2025-001\n\n**Date:** January 15, 2025...",
                        "parsing_metadata": {
                            "total_pages": 2,
                            "has_headers": True,
                            "has_footers": True,
                            "content_length": 2450,
                            "pages_with_content": 2,
                        },
                        "gcs_metadata": {
                            "size": 1024567,
                            "content_type": "application/pdf",
                            "created": "2025-08-15T10:12:36Z",
                        },
                        "file_info": {
                            "original_size": 1024567,
                            "parsed_size": 2450,
                            "file_type": ".pdf",
                            "content_type": "application/pdf",
                        },
                        "timestamp": "2025-08-20T14:30:00Z",
                    }
                }
            },
        },
        400: {
            "description": "Validation error or unsupported file type",
            "content": {
                "application/json": {
                    "examples": {
                        "invalid_storage_path": {
                            "summary": "Invalid storage path format",
                            "value": {
                                "detail": "Storage path must have at least 3 parts: org/type/folder or org/type/file"
                            },
                        },
                        "unsupported_file_type": {
                            "summary": "Unsupported file type",
                            "value": {
                                "detail": "File type '.txt' is not supported for parsing"
                            },
                        },
                    }
                }
            },
        },
        401: {"description": "Authentication required"},
        404: {"description": "Document not found"},
        500: {"description": "Parsing failed"},
    },
)
async def parse_document(
    parse_request: DocumentParseRequest,
    current_user: Dict[str, Any] = Depends(get_current_user_dict),
):
    """
    Parse a document from GCS storage and convert to markdown format.

    This endpoint provides comprehensive document parsing capabilities using
    LlamaParse for advanced AI-powered content extraction.
    """
    try:
        # Get user/org info from session
        org_id = current_user["org_id"]
        user_id = current_user["user_id"]

        logger.info(
            "Document parsing requested",
            org_id=org_id,
            user_id=user_id,
            storage_path=parse_request.storage_path,
        )

        # Call parsing service
        result = await document_parsing_service.parse_document_from_gcs(
            org_id=org_id, storage_path=parse_request.storage_path, user_id=user_id
        )

        # Create response model
        response = DocumentParseResponse(
            success=result["success"],
            storage_path=result["storage_path"],
            parsed_storage_path=result["parsed_storage_path"],
            parsed_content=result["parsed_content"],
            parsing_metadata=result["parsing_metadata"],
            gcs_metadata=result["gcs_metadata"],
            file_info=result["file_info"],
        )

        logger.info(
            "Document parsing completed successfully",
            org_id=org_id,
            user_id=user_id,
            storage_path=parse_request.storage_path,
            parsed_content_length=len(result["parsed_content"]),
        )

        return response

    except UnsupportedFileTypeError as e:
        logger.warning(
            "Unsupported file type for parsing",
            org_id=org_id,
            storage_path=parse_request.storage_path,
            error=str(e),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except DocumentNotFoundError as e:
        logger.warning(
            "Document not found for parsing",
            org_id=org_id,
            storage_path=parse_request.storage_path,
            error=str(e),
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DocumentParsingError as e:
        logger.error(
            "Document parsing failed",
            org_id=org_id,
            storage_path=parse_request.storage_path,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse document: {str(e)}",
        )
    except Exception as e:
        logger.error(
            "Unexpected error during document parsing",
            org_id=org_id,
            storage_path=parse_request.storage_path,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during document parsing",
        )


@router.get(
    "/parse/{storage_path:path}",
    response_model=ExistingDocumentParseResponse,
    summary="📄 Get Existing Parsed Document",
    description="""Retrieve existing parsed document content if it exists in the parsed folder.

**Authentication Required:** Session token in `Authorization: Bearer <token>` header

**Path Parameters:**
- `storage_path`: Original GCS storage path (e.g., "Google/original/invoices/file.pdf")

**Response:**
- If parsed version exists: Returns parsed content and metadata
- If not parsed yet: Returns exists=false with suggested action

**Example Request:**
```bash
GET /api/v1/documents/parse/Google/original/invoices/invoice-2025-001.pdf
```

**Use Cases:**
- Check if document has already been parsed
- Retrieve parsed content without re-processing
- Verify parsing status before requesting new parse
""",
    responses={
        200: {
            "description": "Parsed document status retrieved",
            "content": {
                "application/json": {
                    "examples": {
                        "exists": {
                            "summary": "Parsed document exists",
                            "value": {
                                "exists": True,
                                "storage_path": "Google/original/invoices/invoice-2025-001.pdf",
                                "parsed_storage_path": "Google/parsed/invoices/invoice-2025-001.md",
                                "parsed_content": "# Invoice 2025-001\n\n**Date:** January 15, 2025...",
                                "parsed_metadata": {
                                    "size": 2450,
                                    "content_type": "text/markdown",
                                    "created": "2025-08-20T14:30:15Z",
                                },
                            },
                        },
                        "not_exists": {
                            "summary": "Parsed document does not exist",
                            "value": {
                                "exists": False,
                                "storage_path": "Google/original/invoices/invoice-2025-002.pdf",
                                "parsed_storage_path": "Google/parsed/invoices/invoice-2025-002.md",
                                "message": "Parsed version does not exist",
                            },
                        },
                    }
                }
            },
        },
        401: {"description": "Authentication required"},
        500: {"description": "Server error"},
    },
)
async def get_parsed_document(
    storage_path: str, current_user: Dict[str, Any] = Depends(get_current_user_dict)
):
    """
    Get existing parsed document content if available.

    This endpoint allows clients to check if a document has already been
    parsed and retrieve the existing content without re-processing.
    """
    try:
        # Get user/org info from session
        org_id = current_user["org_id"]

        logger.debug(
            "Checking for existing parsed document",
            org_id=org_id,
            storage_path=storage_path,
        )

        result = await document_parsing_service.get_parsed_document(
            org_id=org_id, storage_path=storage_path
        )

        response = ExistingDocumentParseResponse(**result)

        logger.debug(
            "Parsed document check completed",
            org_id=org_id,
            storage_path=storage_path,
            exists=result["exists"],
        )

        return response

    except Exception as e:
        logger.error(
            "Error checking parsed document",
            org_id=org_id,
            storage_path=storage_path,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while checking parsed document",
        )


# Summarization endpoints moved to /app/api/v1/documents/document_summarization.py
# for better organization within the SOLID-refactored architecture


# Health check endpoint for document service
@router.get("/health", include_in_schema=False)
async def documents_health_check():
    """Health check for document service and dependencies."""
    try:
        from app.core.gcs_client import gcs_client
        from app.core.firebase_client import firebase_client

        health_status = {
            "status": "healthy",
            "timestamp": "2024-01-01T00:00:00Z",  # Will be updated in production
            "components": {
                "gcs": gcs_client.health_check() if gcs_client else False,
                "firestore": (
                    firebase_client.health_check() if firebase_client else False
                ),
            },
        }

        # Check if all components are healthy
        all_healthy = all(health_status["components"].values())
        if not all_healthy:
            health_status["status"] = "degraded"

        status_code = (
            status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
        )

        return health_status

    except Exception as e:
        logger.error("Document service health check failed", error=str(e))
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": "2024-01-01T00:00:00Z",
        }
