"""
Document processing endpoints.

This module handles document processing operations, focusing on:
- Document parsing with LlamaParse integration
- Getting existing parsed documents
- Saving parsed content directly to GCS
- AI-powered document summarization
"""

from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, status

from app.models.schemas import (
    DocumentParseRequest,
    DocumentParseResponse,
    ExistingDocumentParseResponse,
    SaveParsedDocumentRequest,
    SaveParsedDocumentResponse,
)
from app.services.document_service import DocumentNotFoundError
from app.services.document.document_parsing_service import (
    document_parsing_service,
    UnsupportedFileTypeError,
    DocumentParsingError,
)
from app.services.vector_indexing_service import (
    vector_indexing_service,
    VectorIndexingError,
)

# Summarization now handled in documents.py - imports removed
from .common import (
    get_document_dependencies,
    get_user_context,
    handle_document_not_found_error,
    handle_generic_error,
    log_operation_start,
    log_operation_success,
    log_operation_error,
    logger,
)

router = APIRouter()


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
- **Compliance**: Extract text for legal/regulatory review""",
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
    user_context: Dict[str, str] = Depends(get_user_context),
    deps=Depends(get_document_dependencies),
):
    """
    Parse a document from GCS storage and convert to markdown format.

    This endpoint provides comprehensive document parsing capabilities using
    LlamaParse for advanced AI-powered content extraction.
    """
    org_id = user_context["org_id"]
    user_id = user_context["user_id"]

    try:
        log_operation_start(
            "Document parsing", storage_path=parse_request.storage_path, **user_context
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

        log_operation_success(
            "Document parsing",
            storage_path=parse_request.storage_path,
            parsed_content_length=len(result["parsed_content"]),
            **user_context,
        )

        return response

    except UnsupportedFileTypeError as e:
        log_operation_error("Document parsing", str(e), **user_context)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except DocumentNotFoundError as e:
        raise handle_document_not_found_error(e, "parsing", **user_context)
    except DocumentParsingError as e:
        log_operation_error("Document parsing", str(e), **user_context)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse document: {str(e)}",
        )
    except Exception as e:
        raise handle_generic_error(e, "document parsing", **user_context)


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
- Verify parsing status before requesting new parse""",
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
    storage_path: str, user_context: Dict[str, str] = Depends(get_user_context)
):
    """
    Get existing parsed document content if available.

    This endpoint allows clients to check if a document has already been
    parsed and retrieve the existing content without re-processing.
    """
    org_id = user_context["org_id"]

    try:
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
        raise handle_generic_error(e, "checking parsed document", **user_context)


@router.post(
    "/save-parsed",
    response_model=SaveParsedDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="💾 Save Parsed Document Content",
    description="""Save parsed document content to GCS with vector and keyword indexing.

**Authentication Required:** Session token in `Authorization: Bearer <token>` header

**🚀 Enhanced Features:**
- **GCS Storage**: Saves content to Google Cloud Storage
- **Vector Indexing**: Indexes content in Pinecone for semantic search
- **Keyword Indexing**: Creates BM25 index for keyword-based search
- **Metadata Enrichment**: Comprehensive metadata for search operations
- **Error Resilience**: GCS save succeeds even if indexing fails

**Path Construction:**
The system constructs the full GCS path using:
- **Bucket**: From `GCS_BUCKET_NAME` setting (e.g., `biz-to-bricks-document-store`)
- **Target Path**: `{org_name}/parsed/{folder_name}` (provided in request)
- **Filename**: `{original_filename}.md` (auto-converted to markdown extension)

**Vector Indexing Process:**
1. **Embedding Generation**: Creates vector embedding using OpenAI text-embedding-ada-002
2. **Pinecone Storage**: Stores vector with metadata in organization-scoped index
3. **BM25 Indexing**: Creates keyword index for traditional search
4. **Metadata Enrichment**: Adds searchable metadata (filename, folder, organization)

**Example Request:**
```json
{
    "target_path": "Tech Innovations Corp/parsed/control-docs",
    "content": "# Sample Document\\n\\nThis is the parsed content...",
    "original_filename": "Sample2.pdf",
    "metadata": {
        "parser": "manual",
        "version": "1.0",
        "category": "compliance"
    }
}
```

**Enhanced Response:**
```json
{
    "success": true,
    "gcs_path": "Tech Innovations Corp/parsed/control-docs/Sample2.md",
    "gcs_url": "https://storage.googleapis.com/bucket/path/Sample2.md",
    "file_size": 1250,
    "overwritten": false,
    "indexing": {
        "enabled": true,
        "pinecone_indexed": true,
        "bm25_indexed": true,
        "embedding_dimension": 1536,
        "token_count": 234,
        "indexed_at": "2025-08-20T14:30:00Z"
    }
}
```

**Indexing Benefits:**
- **Semantic Search**: Find similar documents by meaning
- **Keyword Search**: Traditional search by specific terms
- **Organization Scoped**: Search limited to user's organization
- **Rich Metadata**: Search by filename, folder, content type
- **Real-time**: Documents immediately available for search

**Error Handling:**
- GCS save always attempted first
- Indexing failures don't prevent GCS save
- Detailed error reporting in response
- Graceful degradation if vector services unavailable

**Security:**
- User must belong to the organization specified in target_path
- Path validation prevents directory traversal attacks
- Content size limits apply (based on system settings)
- Organization-scoped vector indexing

**Next.js Client Example:**
```typescript
const response = await fetch('/api/v1/documents/save-parsed', {
    method: 'POST',
    headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
    },
    body: JSON.stringify({
        target_path: 'Tech Innovations Corp/parsed/control-docs',
        content: '# Sample Document\\n\\nThis is the parsed content...',
        original_filename: 'Sample2.pdf',
        metadata: { category: 'compliance' }
    })
});

const result = await response.json();
console.log('Document saved:', result.gcs_path);
console.log('Indexed for search:', result.indexing.pinecone_indexed);
```""",
    responses={
        201: {
            "description": "Parsed content saved and indexed successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "gcs_path": "Tech Innovations Corp/parsed/control-docs/Sample2.md",
                        "gcs_url": "https://storage.googleapis.com/bucket/path/Sample2.md",
                        "target_path": "Tech Innovations Corp/parsed/control-docs",
                        "final_filename": "Sample2.md",
                        "file_size": 1250,
                        "overwritten": False,
                        "timestamp": "2025-08-20T14:30:00Z",
                        "metadata": {"category": "compliance", "parser": "manual"},
                        "indexing": {
                            "enabled": True,
                            "pinecone_indexed": True,
                            "bm25_indexed": True,
                            "embedding_dimension": 1536,
                            "token_count": 234,
                            "indexed_at": "2025-08-20T14:30:00Z",
                        },
                    }
                }
            },
        },
        400: {
            "description": "Invalid request or path validation error",
            "content": {
                "application/json": {
                    "example": {"detail": "Invalid target path format"}
                }
            },
        },
        403: {
            "description": "Organization access denied",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "User does not belong to specified organization"
                    }
                }
            },
        },
        500: {
            "description": "Storage error",
            "content": {
                "application/json": {
                    "example": {"detail": "Failed to save parsed content to GCS"}
                }
            },
        },
    },
)
async def save_parsed_document(
    request: SaveParsedDocumentRequest,
    user_context: Dict[str, str] = Depends(get_user_context),
) -> SaveParsedDocumentResponse:
    """
    Save parsed document content directly to GCS with vector indexing.

    This endpoint provides comprehensive document processing with:
    - Organization validation and isolation
    - Automatic path construction with .md extension
    - Override detection and reporting
    - Firestore document updating when original exists
    - Vector indexing in Pinecone for semantic search
    - BM25 indexing for keyword search
    - Complete metadata tracking
    """
    try:
        log_operation_start(
            "Save parsed content with indexing",
            target_path=request.target_path,
            original_filename=request.original_filename,
            content_size=len(request.content),
            **user_context,
        )

        # Step 1: Clean target path and parse organization
        cleaned_target_path = document_parsing_service._clean_storage_path(
            request.target_path
        )

        path_parts = cleaned_target_path.split("/")
        org_name = path_parts[0]
        folder_path = "/".join(path_parts[2:])  # Skip 'parsed' part

        # Step 2: Validate user belongs to organization
        # This should be validated by the service layer

        # Step 3: Save to GCS
        result = await document_parsing_service.save_parsed_content_to_gcs(
            target_path=request.target_path,
            content=request.content,
            original_filename=request.original_filename,
            metadata=request.metadata or {},
            org_id=user_context["org_id"],
        )

        # Step 4: Index the document content for search
        indexing_results = {"indexed": False}
        try:
            # Generate a document ID for indexing (use filename without extension)
            import os

            base_filename = os.path.splitext(request.original_filename)[0]
            document_id = f"{org_name}_{folder_path}_{base_filename}".replace(
                "/", "_"
            ).replace(" ", "_")

            # Create indexing metadata
            indexing_metadata = {
                "filename": request.original_filename,
                "folder_path": folder_path,
                "org_name": org_name,
                "gcs_path": result["gcs_path"],
                "created_by": user_context["user_id"],
                "content_type": "parsed_markdown",
                **(request.metadata or {}),
            }

            # Index in both Pinecone and BM25
            indexing_results = await vector_indexing_service.index_document(
                org_id=user_context["org_id"],
                document_id=document_id,
                storage_path=result["storage_path"],
                content=request.content,
                metadata=indexing_metadata,
            )

            logger.info(
                "Document indexing completed",
                document_id=document_id,
                pinecone_indexed=indexing_results.get("pinecone_indexed", False),
                bm25_indexed=indexing_results.get("bm25_indexed", False),
                **user_context,
            )

        except VectorIndexingError as e:
            # Log indexing error but don't fail the entire operation
            logger.warning(
                "Document indexing failed but GCS save succeeded",
                error=str(e),
                gcs_path=result["gcs_path"],
                **user_context,
            )
            indexing_results = {
                "indexed": False,
                "error": str(e),
                "pinecone_indexed": False,
                "bm25_indexed": False,
            }
        except Exception as e:
            # Log unexpected indexing error
            logger.error(
                "Unexpected error during document indexing",
                error=str(e),
                error_type=type(e).__name__,
                **user_context,
            )
            indexing_results = {
                "indexed": False,
                "error": f"Unexpected error: {str(e)}",
                "pinecone_indexed": False,
                "bm25_indexed": False,
            }

        # Step 5: Prepare enhanced response
        enhanced_result = {
            **result,  # Original GCS save results
            "indexing": {
                "enabled": True,
                "pinecone_indexed": indexing_results.get("pinecone_indexed", False),
                "bm25_indexed": indexing_results.get("bm25_indexed", False),
                "embedding_dimension": indexing_results.get("embedding_dimension"),
                "token_count": indexing_results.get("token_count"),
                "indexed_at": indexing_results.get("metadata", {}).get("indexed_at"),
            },
        }

        # Add indexing error info if present
        if "error" in indexing_results:
            enhanced_result["indexing"]["error"] = indexing_results["error"]

        log_operation_success(
            "Save parsed content with indexing",
            gcs_path=result["gcs_path"],
            file_size=result["file_size"],
            overwritten=result["overwritten"],
            pinecone_indexed=enhanced_result["indexing"]["pinecone_indexed"],
            bm25_indexed=enhanced_result["indexing"]["bm25_indexed"],
            **user_context,
        )

        return SaveParsedDocumentResponse(**enhanced_result)

    except Exception as e:
        raise handle_generic_error(
            e, "saving parsed content with indexing", **user_context
        )


# Summarization endpoint removed - now handled by the simplified DocumentAIService
# in /app/api/v1/documents.py for better maintainability and focused implementation
