"""
Document sync and Firestore-first endpoints.

This module handles document synchronization and validation operations, focusing on:
- Sync validation between Firestore and GCS
- Firestore-first document queries by filename
- Folder-based document listing from Firestore
- Rich relationship data and metadata queries
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, Query, Depends, HTTPException, status

from app.models.schemas import (
    DocumentSyncValidationResponse, DocumentFirestoreResponse,
    DocumentFirestoreFolderListResponse, PaginationParams, DocumentFilters,
    FileType, DocumentStatus
)
from app.services.document_service import DocumentNotFoundError
from .common import (
    get_document_dependencies,
    get_user_context,
    handle_document_not_found_error,
    handle_generic_error,
    log_operation_start,
    log_operation_success,
    logger
)

router = APIRouter()


@router.get(
    "/sync/validate", 
    response_model=DocumentSyncValidationResponse,
    summary="🔄 Validate Document Sync",
    description="""Validate sync between Firestore documents and GCS files.

**Authentication Required:** Session token in `Authorization: Bearer <token>` header

**Validation Checks:**
This endpoint performs a comprehensive health check to ensure data consistency:
- **File Existence**: All Firestore documents have corresponding GCS files
- **Path Uniqueness**: No duplicate storage paths exist in Firestore
- **Orphaned Files**: No GCS files exist without Firestore metadata
- **Status Consistency**: No documents are stuck in UPLOADING status
- **Metadata Integrity**: File sizes and types match between Firestore and GCS

**Query Parameters:**
- `folder_id`: Optional folder ID to filter validation scope (validates all documents if not provided)

**Response Structure:**
- **sync_status**: Overall health indicator
  - `'healthy'`: All checks passed, no issues found
  - `'minor_issues'`: Some non-critical issues detected
  - `'issues'`: Significant problems that may affect functionality
  - `'error'`: Critical errors preventing proper operation
- **summary**: Aggregated counts and statistics
  - `documents_checked`: Total documents validated
  - `files_checked`: Total GCS files validated
  - `issues_found`: Number of sync problems detected
- **issues**: Detailed list of specific problems found
- **recommendations**: Suggested actions to fix detected issues

**Example Request:**
```bash
# Validate all documents in organization
curl -X GET "http://localhost:8000/api/v1/documents/sync/validate" \\
  -H "Authorization: Bearer <session_token>"

# Validate specific folder only
curl -X GET "http://localhost:8000/api/v1/documents/sync/validate?folder_id=folder_123" \\
  -H "Authorization: Bearer <session_token>"
```

**Use Cases:**
- **Maintenance**: Periodic health checks to ensure data integrity
- **Troubleshooting**: Diagnose document listing discrepancies
- **Post-Migration**: Verify data consistency after system changes
- **Pre-Cleanup**: Identify issues before performing bulk operations
- **Monitoring**: Automated health checks in production environments

**Issue Types:**
- `missing_gcs_file`: Firestore document without corresponding GCS file
- `orphaned_gcs_file`: GCS file without Firestore metadata
- `duplicate_storage_path`: Multiple documents with same storage path
- `stuck_upload`: Document in UPLOADING status for too long
- `size_mismatch`: File size differs between Firestore and GCS
- `type_mismatch`: Content type differs between sources""",
    responses={
        200: {
            "description": "Sync validation completed",
            "content": {
                "application/json": {
                    "examples": {
                        "healthy": {
                            "summary": "All systems healthy",
                            "value": {
                                "sync_status": "healthy",
                                "summary": {
                                    "documents_checked": 45,
                                    "files_checked": 45,
                                    "issues_found": 0,
                                    "orphaned_files": 0,
                                    "missing_files": 0,
                                    "duplicate_paths": 0
                                },
                                "issues": [],
                                "recommendations": ["No issues found. System is healthy."],
                                "timestamp": "2025-08-15T10:12:36.993659"
                            }
                        },
                        "issues_found": {
                            "summary": "Issues detected requiring attention",
                            "value": {
                                "sync_status": "issues",
                                "summary": {
                                    "documents_checked": 45,
                                    "files_checked": 43,
                                    "issues_found": 3,
                                    "orphaned_files": 1,
                                    "missing_files": 2,
                                    "duplicate_paths": 0
                                },
                                "issues": [
                                    {
                                        "type": "missing_gcs_file",
                                        "severity": "high",
                                        "description": "Document doc123 references missing GCS file",
                                        "document_id": "doc123",
                                        "storage_path": "Google/original/invoices/missing-file.pdf"
                                    },
                                    {
                                        "type": "orphaned_gcs_file",
                                        "severity": "medium",
                                        "description": "GCS file exists without Firestore metadata",
                                        "storage_path": "Google/original/reports/orphaned.xlsx"
                                    }
                                ],
                                "recommendations": [
                                    "Remove or re-upload missing files",
                                    "Create metadata for orphaned files or delete them"
                                ],
                                "timestamp": "2025-08-15T10:12:36.993659"
                            }
                        }
                    }
                }
            }
        },
        401: {"description": "Authentication required"},
        500: {
            "description": "Validation error",
            "content": {
                "application/json": {
                    "example": {"detail": "An error occurred during sync validation"}
                }
            }
        }
    }
)
async def validate_document_sync(
    folder_id: Optional[str] = Query(None, description="Filter by folder ID (optional)"),
    user_context: Dict[str, str] = Depends(get_user_context),
    deps = Depends(get_document_dependencies)
):
    """
    Validate sync between Firestore documents and GCS files.
    
    Performs comprehensive health checks to ensure data consistency
    between metadata store (Firestore) and file storage (GCS).
    """
    document_service = deps["document_service"]
    org_id = user_context["org_id"]
    
    try:
        log_operation_start("Document sync validation", folder_id=folder_id, **user_context)
        
        result = await document_service.validate_sync(
            org_id=org_id,
            folder_id=folder_id
        )
        
        log_operation_success(
            "Document sync validation",
            folder_id=folder_id,
            sync_status=result["sync_status"],
            issues_count=result["summary"].get("issues_found", 0),
            **user_context
        )
        
        return DocumentSyncValidationResponse(**result)
        
    except Exception as e:
        raise handle_generic_error(e, "sync validation", **user_context)


@router.get(
    "/firestore/by-filename/{filename}",
    response_model=DocumentFirestoreResponse,
    summary="🔍 Get Document by Filename (Firestore)",
    description="""Get document information using filename from Firestore metadata store.

**Authentication Required:** Session token in `Authorization: Bearer <token>` header

**Firestore-First Architecture Benefits:**
- **Performance**: Direct indexed Firestore queries instead of GCS bucket iteration
- **Rich Relationships**: Organization, folder, and uploader information in single response
- **Real-time Status**: Current processing pipeline status from database
- **Flexible Search**: Support for both exact and partial filename matching
- **Comprehensive Metadata**: Complete document information with relationships

**Path Parameters:**
- `filename`: Document filename to search for (e.g., "invoice-2025-001.pdf")

**Query Parameters:**
- `exact_match`: Boolean (default: true) - Whether to match exact filename or partial
- `include_inactive`: Boolean (default: false) - Whether to include soft-deleted documents

**Response Structure:**
The response includes multiple data sections:
- **document**: Complete document metadata and status information
- **firestore_metadata**: Query method and database information
- **relationships**: Related entities (organization, folder, uploader)
- **search_criteria**: The search parameters used

**Comparison with Standard Document API:**
- **Standard API**: `/api/v1/documents/{document_id}` - Requires document ID
- **This API**: Search by human-readable filename
- **Performance**: Indexed database queries vs potential GCS lookups
- **Data Richness**: Includes relationships and context information

**Example Requests:**
```bash
# Exact filename match (default)
curl -X GET "http://localhost:8000/api/v1/documents/firestore/by-filename/invoice-2025-001.pdf" \\
  -H "Authorization: Bearer <session_token>"

# Partial filename match
curl -X GET "http://localhost:8000/api/v1/documents/firestore/by-filename/invoice?exact_match=false" \\
  -H "Authorization: Bearer <session_token>"

# Include soft-deleted documents
curl -X GET "http://localhost:8000/api/v1/documents/firestore/by-filename/contract.pdf?include_inactive=true" \\
  -H "Authorization: Bearer <session_token>"
```

**Use Cases:**
- **Upload Verification**: Check if filename already exists before upload
- **Document Discovery**: Find documents using partial filename search
- **Status Monitoring**: Get real-time processing status
- **Relationship Exploration**: Understand document context and ownership
- **Debugging**: Compare Firestore vs GCS data consistency
- **Performance Testing**: Benchmark database vs storage queries""",
    responses={
        200: {
            "description": "Document found successfully",
            "content": {
                "application/json": {
                    "example": {
                        "source": "firestore",
                        "search_criteria": {
                            "filename": "invoice-2025-001.pdf",
                            "exact_match": True,
                            "include_inactive": False
                        },
                        "document": {
                            "id": "78258b82-db53-41a3-848a-ce45a32f99c7",
                            "filename": "invoice-2025-001.pdf",
                            "file_type": "pdf",
                            "file_size": 1024567,
                            "status": "processed",
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
                            "uploader": {
                                "id": "jhYXgm0s4avwacnBSXH9",
                                "email": "user@example.com"
                            }
                        }
                    }
                }
            }
        },
        404: {
            "description": "Document not found",
            "content": {
                "application/json": {
                    "examples": {
                        "not_found_exact": {
                            "summary": "Exact filename not found",
                            "value": {"detail": "No document found with filename 'nonexistent.pdf' using exact match"}
                        },
                        "not_found_partial": {
                            "summary": "Partial filename not found",
                            "value": {"detail": "No document found with filename 'xyz' using partial match"}
                        }
                    }
                }
            }
        },
        401: {"description": "Authentication required"},
        500: {
            "description": "Search error",
            "content": {
                "application/json": {
                    "example": {"detail": "An error occurred while searching for document"}
                }
            }
        }
    }
)
async def get_document_by_filename_firestore(
    filename: str,
    exact_match: bool = Query(True, description="Whether to match exact filename (true) or partial (false)"),
    include_inactive: bool = Query(False, description="Whether to include soft-deleted documents"),
    user_context: Dict[str, str] = Depends(get_user_context),
    deps = Depends(get_document_dependencies)
):
    """
    Get document by filename using Firestore as the primary data source.
    
    Demonstrates proper Firestore-first architecture with indexed queries,
    rich relationship data, and comprehensive document information.
    """
    document_service = deps["document_service"]
    org_id = user_context["org_id"]
    
    try:
        log_operation_start(
            "Firestore filename search",
            filename=filename,
            exact_match=exact_match,
            include_inactive=include_inactive,
            **user_context
        )
        
        result = await document_service.get_document_by_filename_from_firestore(
            org_id=org_id,
            filename=filename,
            exact_match=exact_match,
            include_inactive=include_inactive
        )
        
        log_operation_success(
            "Firestore filename search",
            filename=filename,
            document_id=result.document.id,
            exact_match=exact_match,
            query_method=result.firestore_metadata.query_method,
            **user_context
        )
        
        return result
        
    except DocumentNotFoundError as e:
        raise handle_document_not_found_error(e, "Firestore filename search", **user_context)
    except Exception as e:
        raise handle_generic_error(e, "Firestore filename search", **user_context)


@router.get(
    "/firestore/by-folder-name/{folder_name}",
    response_model=DocumentFirestoreFolderListResponse,
    summary="📁 List Documents by Folder Name (Firestore)",
    description="""List all documents in a folder using folder name with Firestore-first architecture.

**Authentication Required:** Session token in `Authorization: Bearer <token>` header

**Firestore-First Architecture Benefits:**
- **Natural Search**: Use human-readable folder names instead of folder IDs
- **Indexed Queries**: Fast Firestore queries with proper indexing
- **Rich Context**: Complete folder information along with documents
- **Efficient Pagination**: Database-level pagination for large folders
- **Multiple Filters**: Combine various filtering criteria within folders

**Path Parameters:**
- `folder_name`: Human-readable folder name to search for (e.g., "invoices", "contracts")

**Query Parameters:**
- `page`: Page number for pagination (default: 1)
- `per_page`: Items per page (default: 20, max: 100)
- `exact_match`: Whether to match exact folder name (default: true) or partial
- `include_inactive`: Whether to include soft-deleted documents (default: false)
- `file_type`: Filter by file type (pdf, xlsx) within folder
- `document_status`: Filter by processing status within folder
- `filename`: Filter by filename within folder (case-insensitive partial match)

**Response Structure:**
- **documents**: Paginated list of documents in the folder
- **folder_info**: Complete folder metadata and information
- **pagination**: Page information (current, total pages, counts)
- **firestore_metadata**: Query metadata and database information
- **filters_applied**: Summary of active filters

**Performance Advantages:**
- **Indexed Queries**: Uses Firestore composite indexes for optimal performance
- **Database Pagination**: Efficient pagination without loading all documents
- **Combined Filters**: Multiple filter criteria applied at database level
- **Relationship Joins**: Folder and document data retrieved in optimized queries

**Example Requests:**
```bash
# List all documents in "invoices" folder
curl -X GET "http://localhost:8000/api/v1/documents/firestore/by-folder-name/invoices" \\
  -H "Authorization: Bearer <session_token>"

# Search for folders containing "invoice" with pagination
curl -X GET "http://localhost:8000/api/v1/documents/firestore/by-folder-name/invoice?exact_match=false&page=1&per_page=10" \\
  -H "Authorization: Bearer <session_token>"

# Filter PDF files in contracts folder
curl -X GET "http://localhost:8000/api/v1/documents/firestore/by-folder-name/contracts?file_type=pdf" \\
  -H "Authorization: Bearer <session_token>"

# Find processed documents in reports folder
curl -X GET "http://localhost:8000/api/v1/documents/firestore/by-folder-name/reports?document_status=parsed" \\
  -H "Authorization: Bearer <session_token>"
```

**Use Cases:**
- **Folder Browsing**: Navigate document hierarchy by folder names
- **Bulk Operations**: Select documents within folder for batch processing
- **Content Management**: Organize and filter documents by folder context
- **Reporting**: Generate folder-based document reports and analytics
- **Search Enhancement**: Combine folder context with content search
- **Administrative**: Monitor document distribution across folders""",
    responses={
        200: {
            "description": "Documents listed successfully",
            "content": {
                "application/json": {
                    "example": {
                        "documents": [
                            {
                                "id": "78258b82-db53-41a3-848a-ce45a32f99c7",
                                "filename": "invoice-2025-001.pdf",
                                "file_type": "pdf",
                                "status": "parsed",
                                "created_at": "2025-08-15T10:12:36.993659"
                            }
                        ],
                        "folder_info": {
                            "id": "folder_123",
                            "name": "invoices",
                            "path": "/invoices",
                            "document_count": 15
                        },
                        "total": 15,
                        "page": 1,
                        "per_page": 20,
                        "total_pages": 1,
                        "firestore_metadata": {
                            "query_method": "folder_name_exact_match",
                            "filters_applied": ["file_type", "status"]
                        }
                    }
                }
            }
        },
        404: {
            "description": "Folder not found",
            "content": {
                "application/json": {
                    "example": {"detail": "No folder found with name 'nonexistent-folder' using exact match"}
                }
            }
        },
        401: {"description": "Authentication required"},
        500: {
            "description": "Search error",
            "content": {
                "application/json": {
                    "example": {"detail": "An error occurred while searching for documents in folder"}
                }
            }
        }
    }
)
async def list_documents_by_folder_name_firestore(
    folder_name: str,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    exact_match: bool = Query(True, description="Whether to match exact folder name (true) or partial (false)"),
    include_inactive: bool = Query(False, description="Whether to include soft-deleted documents"),
    file_type: Optional[FileType] = Query(None, description="Filter by file type (pdf or xlsx)"),
    document_status: Optional[DocumentStatus] = Query(None, description="Filter by processing status"),
    filename: Optional[str] = Query(None, description="Filter by filename within folder (partial match)"),
    user_context: Dict[str, str] = Depends(get_user_context),
    deps = Depends(get_document_dependencies)
):
    """
    List documents in a folder by folder name using Firestore as the primary data source.
    
    Demonstrates proper Firestore-first architecture with natural folder name search,
    efficient pagination, and comprehensive filtering capabilities.
    """
    document_service = deps["document_service"]
    org_id = user_context["org_id"]
    
    try:
        log_operation_start(
            "Firestore folder document listing",
            folder_name=folder_name,
            page=page,
            per_page=per_page,
            exact_match=exact_match,
            include_inactive=include_inactive,
            file_type=file_type.value if file_type else None,
            document_status=document_status.value if document_status else None,
            filename=filename,
            **user_context
        )
        
        # Build pagination parameters
        pagination = PaginationParams(page=page, per_page=per_page)
        
        # Build additional filters
        additional_filters = DocumentFilters(
            file_type=file_type,
            status=document_status,
            filename=filename
        )
        
        result = await document_service.get_documents_by_folder_name_from_firestore(
            org_id=org_id,
            folder_name=folder_name,
            pagination=pagination,
            exact_match=exact_match,
            include_inactive=include_inactive,
            additional_filters=additional_filters
        )
        
        log_operation_success(
            "Firestore folder document listing",
            folder_name=folder_name,
            folder_id=result.folder_info.id,
            total_documents=result.total,
            returned_documents=len(result.documents),
            page=page,
            exact_match=exact_match,
            query_method=result.firestore_metadata.query_method,
            **user_context
        )
        
        return result
        
    except DocumentNotFoundError as e:
        raise handle_document_not_found_error(e, "Firestore folder search", **user_context)
    except Exception as e:
        raise handle_generic_error(e, "Firestore folder document listing", **user_context)