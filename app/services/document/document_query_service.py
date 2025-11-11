"""
Document Query Service - Complex queries, filtering, and search operations.

This service handles advanced document search and retrieval operations:
- Paginated document listing with complex filters
- Filename-based document search with relationship data
- Folder-based document queries with metadata enrichment
- GCS-based document listing for direct storage queries
- Advanced search criteria and result compilation
"""

import math
from datetime import datetime
from typing import Optional, Any
from google.cloud.firestore_v1 import FieldFilter

from app.models.document import Document, DocumentStatus, FileType
from app.models.schemas import (
    DocumentList,
    DocumentResponse,
    DocumentFilters,
    PaginationParams,
)
from app.core.gcs_client import gcs_client
from .document_base_service import DocumentBaseService, DocumentNotFoundError


class DocumentQueryService(DocumentBaseService):
    """Service for complex document queries and search operations."""

    def __init__(self):
        """Initialize the query service with dependencies."""
        super().__init__()

        # Import here to avoid circular imports
        from app.services.org_service import organization_service
        from app.services.folder_service import folder_service

        self.org_service = organization_service
        self.folder_service = folder_service

    async def list_documents(
        self,
        org_id: str,
        pagination: PaginationParams,
        filters: Optional[DocumentFilters] = None,
        storage_service=None,
        validation_service=None,
    ) -> DocumentList:
        """
        List documents with pagination and advanced filtering.

        Args:
            org_id: Organization ID
            pagination: Pagination parameters
            filters: Optional filters for document search
            storage_service: Storage service dependency
            validation_service: Validation service dependency

        Returns:
            Paginated document list with filtering applied
        """
        try:
            # CHECK FOR GCS DIRECT LISTING: If folder_path contains "/original/", list files directly from GCS
            if filters and filters.folder_path and "/original/" in filters.folder_path:
                self.logger.info(
                    "Detected GCS path in folder_path, using direct GCS listing",
                    org_id=org_id,
                    folder_path=filters.folder_path,
                )
                return await self._list_documents_from_gcs(
                    org_id,
                    filters.folder_path,
                    pagination,
                    filters,
                    storage_service,
                    validation_service,
                )

            # EXISTING FIRESTORE LOGIC for backward compatibility
            collection = self._get_collection(org_id)
            query = collection.where(filter=FieldFilter("is_active", "==", True))

            # Apply filters
            if filters:
                if filters.file_type:
                    query = query.where(
                        filter=FieldFilter("file_type", "==", filters.file_type.value)
                    )
                if filters.status:
                    query = query.where(
                        filter=FieldFilter("status", "==", filters.status.value)
                    )
                if filters.folder_id:
                    query = query.where(
                        filter=FieldFilter("folder_id", "==", filters.folder_id)
                    )
                if filters.uploaded_by:
                    query = query.where(
                        filter=FieldFilter("uploaded_by", "==", filters.uploaded_by)
                    )

            # Order by creation date (newest first)
            query = query.order_by("created_at", direction="DESCENDING")

            # Get total count (Note: This is simplified - in production, use a separate count query)
            all_docs = query.stream()
            all_documents = []

            async for doc in all_docs:
                try:
                    document_data = doc.to_dict()
                    document = Document.from_dict(document_data, doc.id)

                    # Enrich document metadata to ensure complete data
                    document = await storage_service._enrich_document_metadata(document)

                    # NUCLEAR SAFETY NET: Final validation to guarantee no "Unknown" values
                    document = validation_service._ensure_safe_metadata(document)

                    # Apply name filter (Firestore doesn't support case-insensitive contains)
                    if filters and filters.filename:
                        if filters.filename.lower() not in document.filename.lower():
                            continue

                    # Apply folder_path filter (storage_path-based filtering for target_path uploads)
                    if filters and filters.folder_path:
                        document_folder = (
                            validation_service._extract_folder_from_storage_path(
                                document.storage_path
                            )
                        )
                        if (
                            not document_folder
                            or document_folder.lower() != filters.folder_path.lower()
                        ):
                            continue

                    all_documents.append(document)

                except Exception as e:
                    self.logger.error(
                        "Failed to process document from Firestore",
                        org_id=org_id,
                        document_id=doc.id,
                        document_data=(
                            document_data if "document_data" in locals() else "unknown"
                        ),
                        error=str(e),
                    )
                    # Skip this document and continue with others
                    continue

            # Get total count
            total = len(all_documents)

            # Apply pagination
            start_idx = pagination.offset
            end_idx = start_idx + pagination.per_page
            paginated_documents = all_documents[start_idx:end_idx]

            # Convert to response models with error handling
            document_responses = []
            for doc in paginated_documents:
                try:
                    doc_response = DocumentResponse.model_validate(doc)
                    document_responses.append(doc_response)
                except Exception as e:
                    self.logger.error(
                        "Failed to convert Document to DocumentResponse",
                        org_id=org_id,
                        document_id=doc.id if hasattr(doc, "id") else "unknown",
                        document_data=(
                            doc.model_dump() if hasattr(doc, "model_dump") else str(doc)
                        ),
                        error=str(e),
                    )
                    # Skip this document and continue with others
                    continue

            # Calculate pagination info
            total_pages = math.ceil(total / pagination.per_page) if total > 0 else 0

            # Enhanced logging for folder filtering
            filter_info = {}
            if filters:
                if filters.folder_id:
                    filter_info["folder_id"] = filters.folder_id
                if filters.folder_path:
                    filter_info["folder_path"] = filters.folder_path
                if filters.filename:
                    filter_info["filename"] = filters.filename
                if filters.file_type:
                    filter_info["file_type"] = filters.file_type.value
                if filters.status:
                    filter_info["status"] = filters.status.value

            self.logger.debug(
                "Documents listed with enhanced folder filtering",
                org_id=org_id,
                count=len(document_responses),
                total=total,
                page=pagination.page,
                filters=filter_info,
                folder_filtering_used=bool(
                    filters and (filters.folder_id or filters.folder_path)
                ),
            )

            return DocumentList(
                documents=document_responses,
                total=total,
                page=pagination.page,
                per_page=pagination.per_page,
                total_pages=total_pages,
            )

        except Exception as e:
            self.logger.error("Error listing documents", org_id=org_id, error=str(e))
            raise

    async def _list_documents_from_gcs(
        self,
        org_id: str,
        folder_path: str,
        pagination: PaginationParams,
        filters: Optional[DocumentFilters] = None,
        storage_service=None,
        validation_service=None,
    ) -> DocumentList:
        """
        List documents directly from GCS for immediate access to uploaded files.

        This method provides direct GCS listing capability for scenarios where
        Firestore sync may be delayed or when browsing GCS bucket structure directly.

        Args:
            org_id: Organization ID
            folder_path: GCS folder path (e.g., "Google/original/invoices/")
            pagination: Pagination parameters
            filters: Optional filters
            storage_service: Storage service dependency
            validation_service: Validation service dependency

        Returns:
            Document list from GCS with minimal metadata
        """
        try:
            self.logger.info(
                "Listing documents from GCS",
                org_id=org_id,
                folder_path=folder_path,
                pagination=pagination.model_dump(),
            )

            if not gcs_client.is_initialized:
                error_msg = "GCS client not initialized"
                if gcs_client.initialization_error:
                    error_msg += f": {gcs_client.initialization_error}"
                raise RuntimeError(error_msg)

            # Get file list from GCS
            try:
                gcs_files = gcs_client.list_files_in_path(folder_path)
                self.logger.info(
                    "Retrieved GCS file list",
                    org_id=org_id,
                    folder_path=folder_path,
                    file_count=len(gcs_files),
                )
            except Exception as e:
                self.logger.error(
                    "Failed to list files from GCS",
                    org_id=org_id,
                    folder_path=folder_path,
                    error=str(e),
                )
                # Return empty list instead of failing
                return DocumentList(
                    documents=[],
                    total=0,
                    page=pagination.page,
                    per_page=pagination.per_page,
                    total_pages=0,
                )

            # Convert GCS files to Document objects
            documents = []
            for gcs_file in gcs_files:
                try:
                    # Create minimal document from GCS metadata
                    file_type = Document.extract_file_type(
                        gcs_file.get("name", "unknown.pdf")
                    )
                    if not file_type:
                        file_type = FileType.PDF  # Default fallback

                    document = Document(
                        id=Document.generate_id(),  # Generate temporary ID for GCS files
                        org_id=org_id,
                        filename=gcs_file.get("name", "unknown_file"),
                        original_filename=gcs_file.get("name", "unknown_file"),
                        file_type=file_type,
                        file_size=gcs_file.get("size", 0),
                        storage_path=gcs_file.get(
                            "path", folder_path + gcs_file.get("name", "")
                        ),
                        status=DocumentStatus.UPLOADED,  # Assume uploaded if in GCS
                        uploaded_by="gcs_direct",  # Indicate this is from GCS listing
                        folder_id=None,  # No folder ID for GCS direct listing
                        metadata={
                            "source": "gcs_direct",
                            "content_type": gcs_file.get("content_type"),
                            "updated": gcs_file.get("updated"),
                            "etag": gcs_file.get("etag"),
                        },
                    )

                    # Apply filters if specified
                    if filters:
                        if (
                            filters.file_type
                            and document.file_type != filters.file_type
                        ):
                            continue
                        if (
                            filters.filename
                            and filters.filename.lower()
                            not in document.filename.lower()
                        ):
                            continue

                    # Enrich metadata if services available
                    if storage_service:
                        document = await storage_service._enrich_document_metadata(
                            document
                        )

                    if validation_service:
                        document = validation_service._ensure_safe_metadata(document)

                    documents.append(document)

                except Exception as e:
                    self.logger.error(
                        "Failed to process GCS file", gcs_file=gcs_file, error=str(e)
                    )
                    continue

            # Apply pagination
            total = len(documents)
            start_idx = pagination.offset
            end_idx = start_idx + pagination.per_page
            paginated_documents = documents[start_idx:end_idx]

            # Convert to response models
            document_responses = []
            for doc in paginated_documents:
                try:
                    doc_response = DocumentResponse.model_validate(doc)
                    document_responses.append(doc_response)
                except Exception as e:
                    self.logger.error(
                        "Failed to convert GCS Document to DocumentResponse",
                        document_id=doc.id,
                        error=str(e),
                    )
                    continue

            # Calculate pagination info
            total_pages = math.ceil(total / pagination.per_page) if total > 0 else 0

            self.logger.info(
                "GCS document listing completed",
                org_id=org_id,
                folder_path=folder_path,
                total_files=total,
                returned_count=len(document_responses),
                page=pagination.page,
                total_pages=total_pages,
            )

            return DocumentList(
                documents=document_responses,
                total=total,
                page=pagination.page,
                per_page=pagination.per_page,
                total_pages=total_pages,
            )

        except Exception as e:
            self.logger.error(
                "Error listing documents from GCS",
                org_id=org_id,
                folder_path=folder_path,
                error=str(e),
            )
            # Return empty result instead of failing
            return DocumentList(
                documents=[],
                total=0,
                page=pagination.page,
                per_page=pagination.per_page,
                total_pages=0,
            )

    async def get_document_by_filename_from_firestore(
        self,
        org_id: str,
        filename: str,
        exact_match: bool = True,
        include_inactive: bool = False,
        storage_service=None,
        validation_service=None,
    ) -> Any:
        """
        Get document by filename using Firestore with relationship data.

        Args:
            org_id: Organization ID
            filename: Document filename to search for
            exact_match: Whether to match exact filename
            include_inactive: Whether to include soft-deleted documents
            storage_service: Storage service dependency
            validation_service: Validation service dependency

        Returns:
            DocumentFirestoreResponse with document and relationship data

        Raises:
            DocumentNotFoundError: If no document found with given filename
        """
        from app.models.schemas import (
            DocumentFirestoreResponse,
            DocumentSearchCriteria,
            DocumentFirestoreMetadata,
            DocumentRelationships,
            DocumentRelationshipOrganization,
            DocumentRelationshipFolder,
            DocumentRelationshipUploader,
        )

        try:
            self.logger.info(
                "Searching for document by filename in Firestore",
                org_id=org_id,
                filename=filename,
                exact_match=exact_match,
                include_inactive=include_inactive,
            )

            collection = self._get_collection(org_id)

            # Build Firestore query based on search type
            if exact_match:
                query = collection.where(filter=FieldFilter("filename", "==", filename))
                query_method = "filename_exact_match"
            else:
                # For partial match, we'll get all documents and filter client-side
                # Note: Firestore doesn't support case-insensitive contains queries
                query = collection.where(filter=FieldFilter("filename", ">=", filename))
                query_method = "filename_partial_match"

            # Filter by active status unless including inactive
            if not include_inactive:
                query = query.where(filter=FieldFilter("is_active", "==", True))

            # Execute query
            docs = query.stream()
            found_documents = []

            async for doc in docs:
                try:
                    document_data = doc.to_dict()
                    document = Document.from_dict(document_data, doc.id)

                    # For partial match, filter filename on client side
                    if not exact_match:
                        if filename.lower() not in document.filename.lower():
                            continue

                    # Enrich document metadata to ensure complete data
                    if storage_service:
                        document = await storage_service._enrich_document_metadata(
                            document
                        )

                    # Apply safety net to ensure no missing values
                    if validation_service:
                        document = validation_service._ensure_safe_metadata(document)

                    found_documents.append(document)

                    # For exact match, we can break after first match
                    if exact_match:
                        break

                except Exception as e:
                    self.logger.error(
                        "Failed to process document during filename search",
                        org_id=org_id,
                        document_id=doc.id,
                        error=str(e),
                    )
                    continue

            if not found_documents:
                search_type = "exact" if exact_match else "partial"
                raise DocumentNotFoundError(
                    f"No document found with filename '{filename}' using {search_type} match"
                )

            # Use the first found document (for exact match, there should be only one)
            document = found_documents[0]

            if len(found_documents) > 1:
                self.logger.warning(
                    "Multiple documents found with same filename",
                    org_id=org_id,
                    filename=filename,
                    count=len(found_documents),
                    using_first=document.id,
                )

            # Get organization information
            org = await self.org_service.get_organization(org_id)
            org_relationship = DocumentRelationshipOrganization(
                id=org.id, name=org.name
            )

            # Get folder information if document has folder_id
            folder_relationship = None
            if document.folder_id:
                try:
                    folder = await self.folder_service.get_folder(
                        org_id, document.folder_id
                    )
                    folder_relationship = DocumentRelationshipFolder(
                        id=folder.id, name=folder.name, path=folder.path
                    )
                except Exception as e:
                    self.logger.warning(
                        "Could not fetch folder information",
                        org_id=org_id,
                        folder_id=document.folder_id,
                        error=str(e),
                    )
                    folder_relationship = DocumentRelationshipFolder(
                        id=document.folder_id, name="Unknown Folder", path="/unknown"
                    )

            # Get uploader information
            try:
                from app.services.user_service import user_service

                uploader = await user_service.get_user(org_id, document.uploaded_by)
                uploader_relationship = DocumentRelationshipUploader(
                    id=uploader.id, email=uploader.email, full_name=uploader.full_name
                )
            except Exception as e:
                self.logger.warning(
                    "Could not fetch uploader information",
                    org_id=org_id,
                    uploaded_by=document.uploaded_by,
                    error=str(e),
                )
                uploader_relationship = DocumentRelationshipUploader(
                    id=document.uploaded_by,
                    email="unknown@example.com",
                    full_name="Unknown User",
                )

            # Build comprehensive response
            search_criteria = DocumentSearchCriteria(
                filename=filename,
                exact_match=exact_match,
                include_inactive=include_inactive,
            )

            firestore_metadata = DocumentFirestoreMetadata(
                document_ref=f"organizations/{org_id}/documents/{document.id}",
                query_method=query_method,
                last_updated=document.updated_at,
            )

            relationships = DocumentRelationships(
                organization=org_relationship,
                folder=folder_relationship,
                uploader=uploader_relationship,
            )

            document_response = DocumentResponse.model_validate(document)

            response = DocumentFirestoreResponse(
                source="firestore",
                search_criteria=search_criteria,
                document=document_response,
                firestore_metadata=firestore_metadata,
                relationships=relationships,
            )

            self.logger.info(
                "Document found via Firestore filename search",
                org_id=org_id,
                filename=filename,
                document_id=document.id,
                exact_match=exact_match,
                query_method=query_method,
            )

            return response

        except DocumentNotFoundError:
            raise
        except Exception as e:
            self.logger.error(
                "Error searching document by filename in Firestore",
                org_id=org_id,
                filename=filename,
                exact_match=exact_match,
                error=str(e),
            )
            raise DocumentNotFoundError(
                f"Failed to search for document by filename: {e}"
            )

    async def get_documents_by_folder_name_from_firestore(
        self,
        org_id: str,
        folder_name: str,
        pagination: PaginationParams,
        exact_match: bool = True,
        include_inactive: bool = False,
        additional_filters: Optional[DocumentFilters] = None,
    ) -> Any:
        """
        Get documents by folder name using Firestore with comprehensive filtering.

        Args:
            org_id: Organization ID
            folder_name: Folder name to search for
            pagination: Pagination parameters
            exact_match: Whether to match exact folder name
            include_inactive: Whether to include soft-deleted documents
            additional_filters: Optional additional filters

        Returns:
            DocumentFirestoreFolderListResponse with documents and folder info

        Raises:
            DocumentNotFoundError: If no folder found with given name
        """
        from app.models.schemas import (
            DocumentFirestoreFolderListResponse,
            DocumentFolderSearchCriteria,
            DocumentFolderInfo,
            DocumentFirestoreMetadata,
        )

        try:
            self.logger.info(
                "Searching for documents by folder name in Firestore",
                org_id=org_id,
                folder_name=folder_name,
                exact_match=exact_match,
                include_inactive=include_inactive,
                pagination=pagination.model_dump(),
                additional_filters=(
                    additional_filters.model_dump(exclude_none=True)
                    if additional_filters
                    else {}
                ),
            )

            # Step 1: Find folder by name using folder service
            folder = await self._find_folder_by_name(org_id, folder_name, exact_match)

            if not folder:
                search_type = "exact" if exact_match else "partial"
                raise DocumentNotFoundError(
                    f"No folder found with name '{folder_name}' using {search_type} match"
                )

            # Step 2: Get documents in the folder using Firestore query
            collection = self._get_collection(org_id)

            # Build query to find documents in this folder
            query = collection.where(filter=FieldFilter("folder_id", "==", folder.id))

            # Filter by active status unless including inactive
            if not include_inactive:
                query = query.where(filter=FieldFilter("is_active", "==", True))

            # Apply additional filters if provided
            if additional_filters:
                if additional_filters.file_type:
                    query = query.where(
                        filter=FieldFilter(
                            "file_type", "==", additional_filters.file_type.value
                        )
                    )
                if additional_filters.status:
                    query = query.where(
                        filter=FieldFilter(
                            "status", "==", additional_filters.status.value
                        )
                    )

            # Get all matching documents
            docs = query.stream()
            found_documents = []

            async for doc in docs:
                try:
                    document_data = doc.to_dict()
                    document = Document.from_dict(document_data, doc.id)

                    # Apply filename filter if specified
                    if additional_filters and additional_filters.filename:
                        if (
                            additional_filters.filename.lower()
                            not in document.filename.lower()
                        ):
                            continue

                    found_documents.append(document)

                except Exception as e:
                    self.logger.warning(
                        "Error processing document in folder query",
                        document_id=doc.id,
                        error=str(e),
                    )
                    continue

            # Apply pagination to the results
            total = len(found_documents)
            start_idx = pagination.offset
            end_idx = start_idx + pagination.per_page
            paginated_documents = found_documents[start_idx:end_idx]

            # Build response models
            document_responses = [
                DocumentResponse.model_validate(doc) for doc in paginated_documents
            ]

            # Build folder info
            folder_info = DocumentFolderInfo(
                id=folder.id,
                name=folder.name,
                path=f"/{folder.name}",  # Simplified path
                parent_folder_id=folder.parent_folder_id,
                created_by=folder.created_by,
                created_at=folder.created_at,
                document_count=total,
            )

            # Build search criteria
            search_criteria = DocumentFolderSearchCriteria(
                folder_name=folder_name,
                exact_match=exact_match,
                include_inactive=include_inactive,
                additional_filters=(
                    additional_filters.model_dump(exclude_none=True)
                    if additional_filters
                    else {}
                ),
            )

            # Build Firestore metadata
            firestore_metadata = DocumentFirestoreMetadata(
                document_ref=f"organizations/{org_id}/documents (folder_id == {folder.id})",
                query_method="folder_id_exact_match_with_filters",
                last_updated=datetime.now(),
            )

            # Calculate total pages
            total_pages = math.ceil(total / pagination.per_page) if total > 0 else 0

            return DocumentFirestoreFolderListResponse(
                source="firestore",
                folder_info=folder_info,
                search_criteria=search_criteria,
                documents=document_responses,
                total=total,
                page=pagination.page,
                per_page=pagination.per_page,
                total_pages=total_pages,
                firestore_metadata=firestore_metadata,
            )

        except DocumentNotFoundError:
            raise
        except Exception as e:
            self.logger.error(
                "Error searching documents by folder name in Firestore",
                org_id=org_id,
                folder_name=folder_name,
                error=str(e),
            )
            raise DocumentNotFoundError(
                f"Failed to search for documents by folder name: {e}"
            )

    async def _find_folder_by_name(
        self, org_id: str, folder_name: str, exact_match: bool = True
    ):
        """
        Find folder by name for document queries.

        Args:
            org_id: Organization ID
            folder_name: Folder name to search for
            exact_match: Whether to match exact folder name

        Returns:
            Folder object or None if not found
        """
        try:
            # Use folder service to find folder by name
            # Fetch folders in batches to handle large folder counts
            page = 1
            per_page = 100  # Maximum allowed by PaginationParams

            while True:
                pagination = PaginationParams(page=page, per_page=per_page)
                folders = await self.folder_service.list_folders(org_id, pagination)

                # Search through current page of folders
                for folder in folders.folders:
                    if exact_match:
                        if folder.name == folder_name:
                            return folder
                    else:
                        if folder_name.lower() in folder.name.lower():
                            return folder

                # Check if we have more pages to fetch
                if page >= folders.total_pages:
                    break

                page += 1

            return None

        except Exception as e:
            self.logger.error(
                "Error finding folder by name",
                org_id=org_id,
                folder_name=folder_name,
                exact_match=exact_match,
                error=str(e),
            )
            return None
