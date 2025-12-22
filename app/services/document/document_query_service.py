"""
Document Query Service - Complex queries, filtering, and search operations.

This service handles document search and retrieval operations:
- Paginated document listing with complex filters
- GCS-based document listing for direct storage queries
"""

import math
from typing import Optional

from sqlalchemy import select, func, or_

from app.models.document import Document, DocumentStatus, FileType
from app.models.schemas import (
    DocumentList,
    DocumentResponse,
    DocumentFilters,
    PaginationParams,
)
from app.core.gcs_client import gcs_client
from biz2bricks_core import DocumentModel, FolderModel
from .document_base_service import DocumentBaseService


class DocumentQueryService(DocumentBaseService):
    """Service for complex document queries and search operations."""

    def __init__(self):
        """Initialize the query service."""
        super().__init__()

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
                    DocumentModel.is_active == True,
                )

                # Apply ALL filters in SQL (not in application)
                if filters:
                    # INFO log to trace filter values
                    self.logger.info(
                        "Document list query - filters received",
                        org_id=org_id,
                        folder_name=filters.folder_name,
                        folder_id=filters.folder_id,
                        folder_path=filters.folder_path,
                    )

                    if filters.file_type:
                        file_type_value = (
                            filters.file_type.value
                            if hasattr(filters.file_type, "value")
                            else filters.file_type
                        )
                        stmt = stmt.where(DocumentModel.file_type == file_type_value)

                    if filters.status:
                        status_value = (
                            filters.status.value
                            if hasattr(filters.status, "value")
                            else filters.status
                        )
                        stmt = stmt.where(DocumentModel.status == status_value)

                    if filters.folder_id:
                        stmt = stmt.where(DocumentModel.folder_id == filters.folder_id)

                    # Filter by folder_name (hybrid: folder_id OR storage_path pattern)
                    if filters.folder_name:
                        conditions = []

                        # Condition 1: Match by folder_id (legacy uploads)
                        folder_lookup = await session.execute(
                            select(FolderModel.id).where(
                                FolderModel.org_id == org_id,
                                FolderModel.name == filters.folder_name,
                                FolderModel.is_active == True,
                            )
                        )
                        folder_id_result = folder_lookup.scalar_one_or_none()

                        # Condition 2: Match by storage_path pattern (target_path uploads)
                        # Pattern: {org}/original/{folder_name}/{file}
                        storage_pattern = f"%/original/{filters.folder_name}/%"

                        # INFO log to trace filter application
                        self.logger.info(
                            "Applying folder_name filter",
                            folder_name=filters.folder_name,
                            folder_id_found=folder_id_result,
                            storage_pattern=storage_pattern,
                        )

                        if folder_id_result:
                            conditions.append(
                                DocumentModel.folder_id == folder_id_result
                            )

                        conditions.append(
                            DocumentModel.storage_path.ilike(storage_pattern)
                        )

                        # Apply OR of all conditions
                        self.logger.info(
                            "Folder filter conditions",
                            conditions_count=len(conditions),
                        )
                        stmt = stmt.where(or_(*conditions))

                    if filters.uploaded_by:
                        stmt = stmt.where(
                            DocumentModel.uploaded_by == filters.uploaded_by
                        )

                    # Apply filename filter in SQL using ILIKE for case-insensitive search
                    if filters.filename:
                        stmt = stmt.where(
                            DocumentModel.filename.ilike(f"%{filters.filename}%")
                        )

                    # Apply storage_path/folder_path filter in SQL if provided
                    if filters.folder_path:
                        stmt = stmt.where(
                            DocumentModel.storage_path.ilike(f"%{filters.folder_path}%")
                        )

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

                # Log returned documents for folder_name filter
                if filters and filters.folder_name:
                    self.logger.info(
                        "Documents returned for folder_name filter",
                        folder_name=filters.folder_name,
                        count=len(doc_models),
                        storage_paths=[dm.storage_path for dm in doc_models],
                    )

                # Convert and enrich ONLY the paginated documents (not all)
                document_responses = []
                for doc_model in doc_models:
                    try:
                        document = self._model_to_pydantic(doc_model)

                        # Enrich document metadata (only for paginated results)
                        if storage_service:
                            document = await storage_service._enrich_document_metadata(
                                document
                            )

                        # Safety validation
                        if validation_service:
                            document = validation_service._ensure_safe_metadata(
                                document
                            )

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
                    file_type = Document.extract_file_type(
                        gcs_file.get("name", "unknown.pdf")
                    )
                    if not file_type:
                        file_type = FileType.PDF

                    document = Document(
                        id=Document.generate_id(),
                        org_id=org_id,
                        filename=gcs_file.get("name", "unknown_file"),
                        original_filename=gcs_file.get("name", "unknown_file"),
                        file_type=file_type,
                        file_size=gcs_file.get("size", 0),
                        storage_path=gcs_file.get(
                            "path", folder_path + gcs_file.get("name", "")
                        ),
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

                    if storage_service:
                        document = await storage_service._enrich_document_metadata(
                            document
                        )

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
