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

from sqlalchemy import select, func

from app.models.document import Document, DocumentStatus, FileType
from app.models.schemas import (
    DocumentList,
    DocumentResponse,
    DocumentFilters,
    PaginationParams,
)
from app.core.gcs_client import gcs_client
from app.core.db_models import DocumentModel
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

    def _model_to_pydantic(self, model: DocumentModel) -> Document:
        """Convert SQLAlchemy model to Pydantic model."""
        return Document(
            id=model.id,
            org_id=model.organization_id,
            folder_id=model.folder_id,
            filename=model.filename,
            original_filename=model.original_filename,
            file_type=model.file_type,
            file_size=model.file_size,
            storage_path=model.storage_path,
            status=model.status,
            uploaded_by=model.uploaded_by,
            is_active=model.is_active,
            metadata=model.doc_metadata or {},
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

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
            # CHECK FOR GCS DIRECT LISTING
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

            async with self.db.session() as session:
                # Build base query with ALL filters in SQL for performance
                stmt = select(DocumentModel).where(
                    DocumentModel.organization_id == org_id,
                    DocumentModel.is_active == True
                )

                # Apply ALL filters in SQL (not in application)
                if filters:
                    if filters.file_type:
                        file_type_value = filters.file_type.value if hasattr(filters.file_type, 'value') else filters.file_type
                        stmt = stmt.where(DocumentModel.file_type == file_type_value)

                    if filters.status:
                        status_value = filters.status.value if hasattr(filters.status, 'value') else filters.status
                        stmt = stmt.where(DocumentModel.status == status_value)

                    if filters.folder_id:
                        stmt = stmt.where(DocumentModel.folder_id == filters.folder_id)

                    if filters.uploaded_by:
                        stmt = stmt.where(DocumentModel.uploaded_by == filters.uploaded_by)

                    # Apply filename filter in SQL using ILIKE for case-insensitive search
                    if filters.filename:
                        stmt = stmt.where(DocumentModel.filename.ilike(f"%{filters.filename}%"))

                    # Apply storage_path/folder_path filter in SQL if provided
                    if filters.folder_path:
                        stmt = stmt.where(DocumentModel.storage_path.ilike(f"%{filters.folder_path}%"))

                # Get total count with all filters applied
                count_stmt = select(func.count()).select_from(stmt.subquery())
                count_result = await session.execute(count_stmt)
                total = count_result.scalar() or 0

                # Apply ordering and SQL-level pagination (LIMIT/OFFSET)
                stmt = stmt.order_by(DocumentModel.created_at.desc())
                stmt = stmt.offset(pagination.offset).limit(pagination.per_page)

                # Execute query - only fetches paginated results
                result = await session.execute(stmt)
                doc_models = result.scalars().all()

                # Convert and enrich ONLY the paginated documents (not all)
                document_responses = []
                for doc_model in doc_models:
                    try:
                        document = self._model_to_pydantic(doc_model)

                        # Enrich document metadata (only for paginated results)
                        if storage_service:
                            document = await storage_service._enrich_document_metadata(document)

                        # Safety validation
                        if validation_service:
                            document = validation_service._ensure_safe_metadata(document)

                        doc_response = DocumentResponse.model_validate(document)
                        document_responses.append(doc_response)

                    except Exception as e:
                        self.logger.error(
                            "Failed to process document",
                            org_id=org_id,
                            document_id=doc_model.id,
                            error=str(e),
                        )
                        continue

                # Calculate pagination info
                total_pages = math.ceil(total / pagination.per_page) if total > 0 else 0

                self.logger.debug(
                    "Documents listed",
                    org_id=org_id,
                    count=len(document_responses),
                    total=total,
                    page=pagination.page,
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
        """
        try:
            self.logger.info(
                "Listing documents from GCS",
                org_id=org_id,
                folder_path=folder_path,
            )

            if not gcs_client.is_initialized:
                error_msg = "GCS client not initialized"
                if gcs_client.initialization_error:
                    error_msg += f": {gcs_client.initialization_error}"
                raise RuntimeError(error_msg)

            # Get file list from GCS
            try:
                gcs_files = gcs_client.list_files_in_path(folder_path)
            except Exception as e:
                self.logger.error(
                    "Failed to list files from GCS",
                    org_id=org_id,
                    folder_path=folder_path,
                    error=str(e),
                )
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
                    file_type = Document.extract_file_type(gcs_file.get("name", "unknown.pdf"))
                    if not file_type:
                        file_type = FileType.PDF

                    document = Document(
                        id=Document.generate_id(),
                        org_id=org_id,
                        filename=gcs_file.get("name", "unknown_file"),
                        original_filename=gcs_file.get("name", "unknown_file"),
                        file_type=file_type,
                        file_size=gcs_file.get("size", 0),
                        storage_path=gcs_file.get("path", folder_path + gcs_file.get("name", "")),
                        status=DocumentStatus.UPLOADED,
                        uploaded_by="gcs_direct",
                        folder_id=None,
                        metadata={
                            "source": "gcs_direct",
                            "content_type": gcs_file.get("content_type"),
                            "updated": gcs_file.get("updated"),
                        },
                    )

                    # Apply filters
                    if filters:
                        if filters.file_type and document.file_type != filters.file_type:
                            continue
                        if filters.filename and filters.filename.lower() not in document.filename.lower():
                            continue

                    if storage_service:
                        document = await storage_service._enrich_document_metadata(document)

                    if validation_service:
                        document = validation_service._ensure_safe_metadata(document)

                    documents.append(document)

                except Exception as e:
                    self.logger.error("Failed to process GCS file", error=str(e))
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
                    self.logger.error("Failed to convert GCS Document", error=str(e))
                    continue

            total_pages = math.ceil(total / pagination.per_page) if total > 0 else 0

            return DocumentList(
                documents=document_responses,
                total=total,
                page=pagination.page,
                per_page=pagination.per_page,
                total_pages=total_pages,
            )

        except Exception as e:
            self.logger.error("Error listing documents from GCS", error=str(e))
            return DocumentList(
                documents=[],
                total=0,
                page=pagination.page,
                per_page=pagination.per_page,
                total_pages=0,
            )

    async def get_document_by_filename(
        self,
        org_id: str,
        filename: str,
        exact_match: bool = True,
        include_inactive: bool = False,
        storage_service=None,
        validation_service=None,
    ) -> Any:
        """
        Get document by filename using PostgreSQL with relationship data.
        """
        from app.models.schemas import (
            DocumentDatabaseResponse,
            DocumentSearchCriteria,
            DocumentDatabaseMetadata,
            DocumentRelationships,
            DocumentRelationshipOrganization,
            DocumentRelationshipFolder,
            DocumentRelationshipUploader,
        )

        try:
            async with self.db.session() as session:
                # Build query
                stmt = select(DocumentModel).where(DocumentModel.organization_id == org_id)

                if not include_inactive:
                    stmt = stmt.where(DocumentModel.is_active == True)

                if exact_match:
                    stmt = stmt.where(DocumentModel.filename == filename)
                else:
                    stmt = stmt.where(DocumentModel.filename.ilike(f"%{filename}%"))

                result = await session.execute(stmt)
                doc_models = result.scalars().all()

                found_documents = []
                for doc_model in doc_models:
                    document = self._model_to_pydantic(doc_model)

                    if storage_service:
                        document = await storage_service._enrich_document_metadata(document)

                    if validation_service:
                        document = validation_service._ensure_safe_metadata(document)

                    found_documents.append(document)

                    if exact_match:
                        break

                if not found_documents:
                    search_type = "exact" if exact_match else "partial"
                    raise DocumentNotFoundError(
                        f"No document found with filename '{filename}' using {search_type} match"
                    )

                document = found_documents[0]

                # Get organization info
                org = await self.org_service.get_organization(org_id)
                org_relationship = DocumentRelationshipOrganization(
                    id=org.id, name=org.name
                )

                # Get folder info
                folder_relationship = None
                if document.folder_id:
                    try:
                        folder = await self.folder_service.get_folder(org_id, document.folder_id)
                        folder_relationship = DocumentRelationshipFolder(
                            id=folder.id, name=folder.name, path=folder.path
                        )
                    except Exception:
                        folder_relationship = DocumentRelationshipFolder(
                            id=document.folder_id, name="Unknown Folder", path="/unknown"
                        )

                # Get uploader info
                try:
                    from app.services.user_service import user_service
                    uploader = await user_service.get_user(org_id, document.uploaded_by)
                    uploader_relationship = DocumentRelationshipUploader(
                        id=uploader.id, email=uploader.email, full_name=uploader.full_name
                    )
                except Exception:
                    uploader_relationship = DocumentRelationshipUploader(
                        id=document.uploaded_by,
                        email="unknown@example.com",
                        full_name="Unknown User",
                    )

                search_criteria = DocumentSearchCriteria(
                    filename=filename,
                    exact_match=exact_match,
                    include_inactive=include_inactive,
                )

                database_metadata = DocumentDatabaseMetadata(
                    document_ref=f"documents/{document.id}",
                    query_method="filename_exact_match" if exact_match else "filename_partial_match",
                    last_updated=document.updated_at,
                )

                relationships = DocumentRelationships(
                    organization=org_relationship,
                    folder=folder_relationship,
                    uploader=uploader_relationship,
                )

                return DocumentDatabaseResponse(
                    source="postgresql",
                    search_criteria=search_criteria,
                    document=DocumentResponse.model_validate(document),
                    database_metadata=database_metadata,
                    relationships=relationships,
                )

        except DocumentNotFoundError:
            raise
        except Exception as e:
            self.logger.error("Error searching document by filename", error=str(e))
            raise DocumentNotFoundError(f"Failed to search for document: {e}")

    async def get_documents_by_folder_name(
        self,
        org_id: str,
        folder_name: str,
        pagination: PaginationParams,
        exact_match: bool = True,
        include_inactive: bool = False,
        additional_filters: Optional[DocumentFilters] = None,
    ) -> Any:
        """
        Get documents by folder name using PostgreSQL.
        """
        from app.models.schemas import (
            DocumentDatabaseFolderListResponse,
            DocumentFolderSearchCriteria,
            DocumentFolderInfo,
            DocumentDatabaseMetadata,
        )

        try:
            # Find folder by name
            folder = await self._find_folder_by_name(org_id, folder_name, exact_match)

            if not folder:
                search_type = "exact" if exact_match else "partial"
                raise DocumentNotFoundError(
                    f"No folder found with name '{folder_name}' using {search_type} match"
                )

            async with self.db.session() as session:
                # Build query
                stmt = select(DocumentModel).where(
                    DocumentModel.organization_id == org_id,
                    DocumentModel.folder_id == folder.id
                )

                if not include_inactive:
                    stmt = stmt.where(DocumentModel.is_active == True)

                if additional_filters:
                    if additional_filters.file_type:
                        file_type_value = additional_filters.file_type.value if hasattr(additional_filters.file_type, 'value') else additional_filters.file_type
                        stmt = stmt.where(DocumentModel.file_type == file_type_value)

                    if additional_filters.status:
                        status_value = additional_filters.status.value if hasattr(additional_filters.status, 'value') else additional_filters.status
                        stmt = stmt.where(DocumentModel.status == status_value)

                result = await session.execute(stmt)
                doc_models = result.scalars().all()

                found_documents = []
                for doc_model in doc_models:
                    document = self._model_to_pydantic(doc_model)

                    if additional_filters and additional_filters.filename:
                        if additional_filters.filename.lower() not in document.filename.lower():
                            continue

                    found_documents.append(document)

                # Apply pagination
                total = len(found_documents)
                start_idx = pagination.offset
                end_idx = start_idx + pagination.per_page
                paginated_documents = found_documents[start_idx:end_idx]

                document_responses = [
                    DocumentResponse.model_validate(doc) for doc in paginated_documents
                ]

                folder_info = DocumentFolderInfo(
                    id=folder.id,
                    name=folder.name,
                    path=f"/{folder.name}",
                    parent_folder_id=folder.parent_folder_id,
                    created_by=folder.created_by,
                    created_at=folder.created_at,
                    document_count=total,
                )

                search_criteria = DocumentFolderSearchCriteria(
                    folder_name=folder_name,
                    exact_match=exact_match,
                    include_inactive=include_inactive,
                    additional_filters=(
                        additional_filters.model_dump(exclude_none=True)
                        if additional_filters else {}
                    ),
                )

                database_metadata = DocumentDatabaseMetadata(
                    document_ref=f"documents (folder_id == {folder.id})",
                    query_method="folder_id_exact_match_with_filters",
                    last_updated=datetime.now(),
                )

                total_pages = math.ceil(total / pagination.per_page) if total > 0 else 0

                return DocumentDatabaseFolderListResponse(
                    source="postgresql",
                    folder_info=folder_info,
                    search_criteria=search_criteria,
                    documents=document_responses,
                    total=total,
                    page=pagination.page,
                    per_page=pagination.per_page,
                    total_pages=total_pages,
                    database_metadata=database_metadata,
                )

        except DocumentNotFoundError:
            raise
        except Exception as e:
            self.logger.error("Error searching documents by folder name", error=str(e))
            raise DocumentNotFoundError(f"Failed to search documents: {e}")

    async def _find_folder_by_name(
        self, org_id: str, folder_name: str, exact_match: bool = True
    ):
        """Find folder by name using direct SQL query for performance."""
        from app.core.db_models import FolderModel

        try:
            async with self.db.session() as session:
                stmt = select(FolderModel).where(
                    FolderModel.organization_id == org_id,
                    FolderModel.is_active == True
                )

                if exact_match:
                    stmt = stmt.where(FolderModel.name == folder_name)
                else:
                    stmt = stmt.where(FolderModel.name.ilike(f"%{folder_name}%"))

                stmt = stmt.limit(1)
                result = await session.execute(stmt)
                folder_model = result.scalar_one_or_none()

                if folder_model:
                    # Convert to Folder pydantic model
                    from app.models.folder import Folder
                    return Folder(
                        id=folder_model.id,
                        org_id=folder_model.organization_id,
                        name=folder_model.name,
                        path=folder_model.path,
                        parent_folder_id=folder_model.parent_folder_id,
                        created_by=folder_model.created_by,
                        is_active=folder_model.is_active,
                        created_at=folder_model.created_at,
                        updated_at=folder_model.updated_at,
                    )

                return None

        except Exception as e:
            self.logger.error("Error finding folder by name", error=str(e))
            return None
