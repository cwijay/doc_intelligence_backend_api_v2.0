import math
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, func

from app.models.folder import Folder
from app.models.schemas import (
    FolderCreate,
    FolderResponse,
    FolderList,
    FolderTree,
    FolderWithChildren,
    PaginationParams,
    FolderFilters,
)
from biz2bricks_core import (
    db,
    FolderModel,
    OrganizationModel,
    AuditAction,
    AuditEntityType,
)
from app.core.gcs_client import gcs_client, GCSClientError
from app.core.logging import get_service_logger
from app.core.cache import cached_folders, invalidate_folders
from app.services.audit_service import audit_service

logger = get_service_logger("folder")


class FolderNotFoundError(Exception):
    """Folder not found error."""

    pass


class FolderAlreadyExistsError(Exception):
    """Folder already exists error."""

    pass


class FolderValidationError(Exception):
    """Folder validation error."""

    pass


class FolderService:
    """Service for managing hierarchical folders with GCS integration."""

    def __init__(self):
        self.logger = logger
        self.max_depth = 5
        from app.services.org_service import organization_service

        self.org_service = organization_service

    def _model_to_pydantic(self, model: FolderModel) -> Folder:
        """Convert SQLAlchemy model to Pydantic model."""
        return Folder(
            id=model.id,
            org_id=model.organization_id,
            name=model.name,
            parent_folder_id=model.parent_folder_id,
            path=model.path,
            created_by=model.created_by,
            is_active=model.is_active,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _ensure_response_model(self, data: FolderResponse | dict) -> FolderResponse:
        """Ensure cached data is converted back to Pydantic model.

        fastapi-cache2 serializes responses to JSON dicts when caching.
        This method ensures we always return a proper Pydantic model.
        """
        if isinstance(data, dict):
            return FolderResponse.model_validate(data)
        return data

    async def _get_organization_name(self, org_id: str) -> str:
        """Get organization name from organization ID."""
        try:
            org_response = await self.org_service.get_organization(org_id)
            return org_response.name
        except Exception as e:
            self.logger.error(
                "Failed to get organization name", org_id=org_id, error=str(e)
            )
            raise FolderValidationError(
                f"Could not fetch organization name for ID {org_id}: {e}"
            )

    async def create_folder(
        self,
        org_id: str,
        folder_data: FolderCreate,
        user_id: str,
        ip_address: Optional[str] = None,
        session_id: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> FolderResponse:
        """
        Create a new folder.

        Args:
            org_id: Organization ID
            folder_data: Folder creation data
            user_id: ID of user creating the folder
            ip_address: Client IP address (for audit)
            session_id: Session ID (for audit)
            user_agent: Client user agent (for audit)

        Returns:
            Created folder response

        Raises:
            FolderAlreadyExistsError: If folder name already exists in parent
            FolderValidationError: If validation fails
        """
        try:
            async with db.session() as session:
                # Verify organization exists
                org_stmt = select(OrganizationModel).where(
                    OrganizationModel.id == org_id, OrganizationModel.is_active == True
                )
                org_result = await session.execute(org_stmt)
                if not org_result.scalar_one_or_none():
                    raise FolderValidationError(f"Organization {org_id} not found")

                # Validate parent folder if specified
                parent_folder = None
                parent_path = ""

                if folder_data.parent_folder_id:
                    parent_stmt = select(FolderModel).where(
                        FolderModel.id == folder_data.parent_folder_id,
                        FolderModel.organization_id == org_id,
                        FolderModel.is_active == True,
                    )
                    parent_result = await session.execute(parent_stmt)
                    parent_folder = parent_result.scalar_one_or_none()

                    if not parent_folder:
                        raise FolderValidationError(
                            f"Parent folder {folder_data.parent_folder_id} not found"
                        )

                    parent_path = parent_folder.path

                    # Check depth limit
                    depth = len([p for p in parent_path.split("/") if p])
                    if depth >= self.max_depth:
                        raise FolderValidationError(
                            f"Maximum folder depth ({self.max_depth}) exceeded"
                        )

                # Calculate folder path
                if parent_path:
                    full_path = f"{parent_path}/{folder_data.name}"
                else:
                    full_path = f"/{folder_data.name}"

                # Check if folder already exists in same parent
                existing_stmt = select(FolderModel).where(
                    FolderModel.organization_id == org_id,
                    FolderModel.name == folder_data.name,
                    FolderModel.parent_folder_id == folder_data.parent_folder_id,
                    FolderModel.is_active == True,
                )
                existing_result = await session.execute(existing_stmt)
                if existing_result.scalar_one_or_none():
                    raise FolderAlreadyExistsError(
                        f"Folder with name '{folder_data.name}' already exists in this location"
                    )

                # Create GCS folder structure if available
                if gcs_client.is_initialized:
                    org_name = await self._get_organization_name(org_id)
                    folder_path = full_path.lstrip("/")

                    try:
                        gcs_result = await gcs_client.create_folder_structure_async(
                            org_name, folder_path
                        )
                        self.logger.info(
                            "Created GCS folder structure",
                            org_id=org_id,
                            org_name=org_name,
                            folder_path=folder_path,
                            gcs_result=gcs_result,
                        )
                    except GCSClientError as e:
                        self.logger.error(
                            "Failed to create GCS folder structure",
                            org_id=org_id,
                            folder_path=folder_path,
                            error=str(e),
                        )
                        raise FolderValidationError(
                            f"Failed to create folder in GCS: {e}"
                        )

                # Create folder in database
                folder_id = str(uuid4())
                now = datetime.now(timezone.utc)

                folder_model = FolderModel(
                    id=folder_id,
                    organization_id=org_id,
                    name=folder_data.name,
                    parent_folder_id=folder_data.parent_folder_id,
                    path=full_path,
                    created_by=user_id,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )

                session.add(folder_model)
                await session.flush()

                folder = self._model_to_pydantic(folder_model)
                self.logger.info(
                    "Folder created",
                    org_id=org_id,
                    folder_id=folder_id,
                    name=folder.name,
                    path=folder.path,
                )

                # Invalidate folder cache
                asyncio.create_task(invalidate_folders(org_id))

                # Audit logging (non-blocking)
                asyncio.create_task(
                    audit_service.log_event(
                        org_id=org_id,
                        action=AuditAction.CREATE,
                        entity_type=AuditEntityType.FOLDER,
                        entity_id=folder_id,
                        user_id=user_id,
                        details={
                            "new_values": {
                                "name": folder.name,
                                "path": folder.path,
                                "parent_folder_id": folder.parent_folder_id,
                            },
                            "operation": "create",
                        },
                        ip_address=ip_address,
                        session_id=session_id,
                        user_agent=user_agent,
                    )
                )

                return FolderResponse.model_validate(folder)

        except (FolderAlreadyExistsError, FolderValidationError):
            raise
        except Exception as e:
            self.logger.error("Error creating folder", org_id=org_id, error=str(e))
            raise

    async def get_folder(self, org_id: str, folder_id: str) -> FolderResponse:
        """
        Get folder by ID.

        Args:
            org_id: Organization ID
            folder_id: Folder ID

        Returns:
            Folder response (cached for 5 minutes)

        Raises:
            FolderNotFoundError: If folder not found
        """
        result = await self._get_folder_cached(org_id, folder_id)
        return self._ensure_response_model(result)

    @cached_folders()
    async def _get_folder_cached(self, org_id: str, folder_id: str) -> FolderResponse:
        """Internal cached method for fetching folder."""
        try:
            async with db.session() as session:
                stmt = select(FolderModel).where(
                    FolderModel.id == folder_id,
                    FolderModel.organization_id == org_id,
                    FolderModel.is_active == True,
                )
                result = await session.execute(stmt)
                folder_model = result.scalar_one_or_none()

                if not folder_model:
                    raise FolderNotFoundError(f"Folder with ID {folder_id} not found")

                folder = self._model_to_pydantic(folder_model)
                self.logger.debug(
                    "Folder retrieved", org_id=org_id, folder_id=folder_id
                )

                return FolderResponse.model_validate(folder)

        except FolderNotFoundError:
            raise
        except Exception as e:
            self.logger.error(
                "Error retrieving folder",
                org_id=org_id,
                folder_id=folder_id,
                error=str(e),
            )
            raise

    async def list_folders(
        self,
        org_id: str,
        pagination: PaginationParams,
        filters: Optional[FolderFilters] = None,
    ) -> FolderList:
        """
        List folders with pagination and filtering.

        Args:
            org_id: Organization ID
            pagination: Pagination parameters
            filters: Optional filters

        Returns:
            Paginated folder list
        """
        try:
            async with db.session() as session:
                # Build base query
                stmt = select(FolderModel).where(
                    FolderModel.organization_id == org_id, FolderModel.is_active == True
                )

                # Apply filters
                if filters:
                    if filters.name:
                        stmt = stmt.where(FolderModel.name.ilike(f"%{filters.name}%"))

                    if filters.parent_folder_id is not None:
                        stmt = stmt.where(
                            FolderModel.parent_folder_id == filters.parent_folder_id
                        )

                # Get total count
                count_stmt = select(func.count()).select_from(stmt.subquery())
                count_result = await session.execute(count_stmt)
                total = count_result.scalar() or 0

                # Apply ordering and pagination
                stmt = stmt.order_by(FolderModel.path)
                stmt = stmt.offset(pagination.offset).limit(pagination.per_page)

                result = await session.execute(stmt)
                folder_models = result.scalars().all()

                # Convert to response models
                folder_responses = [
                    FolderResponse.model_validate(self._model_to_pydantic(m))
                    for m in folder_models
                ]

                # Calculate pagination info
                total_pages = math.ceil(total / pagination.per_page) if total > 0 else 0

                self.logger.debug(
                    "Folders listed",
                    org_id=org_id,
                    count=len(folder_responses),
                    total=total,
                    page=pagination.page,
                )

                return FolderList(
                    folders=folder_responses,
                    total=total,
                    page=pagination.page,
                    per_page=pagination.per_page,
                    total_pages=total_pages,
                )

        except Exception as e:
            self.logger.error("Error listing folders", org_id=org_id, error=str(e))
            raise

    async def get_folder_tree(self, org_id: str) -> FolderTree:
        """
        Get folder tree structure.

        Args:
            org_id: Organization ID

        Returns:
            Folder tree structure
        """
        try:
            async with db.session() as session:
                stmt = (
                    select(FolderModel)
                    .where(
                        FolderModel.organization_id == org_id,
                        FolderModel.is_active == True,
                    )
                    .order_by(FolderModel.path)
                )

                result = await session.execute(stmt)
                folder_models = result.scalars().all()

                all_folders = [self._model_to_pydantic(m) for m in folder_models]
                folder_tree = self._build_folder_tree(all_folders)

                self.logger.debug(
                    "Folder tree retrieved",
                    org_id=org_id,
                    total_folders=len(all_folders),
                )

                return FolderTree(folders=folder_tree, total_folders=len(all_folders))

        except Exception as e:
            self.logger.error(
                "Error retrieving folder tree", org_id=org_id, error=str(e)
            )
            raise

    async def move_folder(
        self,
        org_id: str,
        folder_id: str,
        new_parent_folder_id: Optional[str],
        moved_by_user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        session_id: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> FolderResponse:
        """
        Move folder to new parent.

        Args:
            org_id: Organization ID
            folder_id: Folder ID to move
            new_parent_folder_id: New parent folder ID (None for root)
            moved_by_user_id: ID of user who moved this folder (for audit)
            ip_address: Client IP address (for audit)
            session_id: Session ID (for audit)
            user_agent: Client user agent (for audit)

        Returns:
            Updated folder response

        Raises:
            FolderNotFoundError: If folder not found
            FolderValidationError: If move is invalid
        """
        try:
            async with db.session() as session:
                # Get folder to move
                folder_stmt = select(FolderModel).where(
                    FolderModel.id == folder_id,
                    FolderModel.organization_id == org_id,
                    FolderModel.is_active == True,
                )
                folder_result = await session.execute(folder_stmt)
                folder_model = folder_result.scalar_one_or_none()

                if not folder_model:
                    raise FolderNotFoundError(f"Folder with ID {folder_id} not found")

                old_path = folder_model.path
                old_parent_folder_id = folder_model.parent_folder_id

                # Validate new parent
                new_parent_path = ""
                if new_parent_folder_id:
                    parent_stmt = select(FolderModel).where(
                        FolderModel.id == new_parent_folder_id,
                        FolderModel.organization_id == org_id,
                        FolderModel.is_active == True,
                    )
                    parent_result = await session.execute(parent_stmt)
                    new_parent = parent_result.scalar_one_or_none()

                    if not new_parent:
                        raise FolderValidationError(
                            f"New parent folder {new_parent_folder_id} not found"
                        )

                    new_parent_path = new_parent.path

                    # Check if moving to descendant
                    if new_parent_path.startswith(old_path):
                        raise FolderValidationError(
                            "Cannot move folder to its own descendant"
                        )

                # Calculate new path
                if new_parent_path:
                    new_path = f"{new_parent_path}/{folder_model.name}"
                else:
                    new_path = f"/{folder_model.name}"

                # Check if folder with same name exists in new parent
                existing_stmt = select(FolderModel).where(
                    FolderModel.organization_id == org_id,
                    FolderModel.name == folder_model.name,
                    FolderModel.parent_folder_id == new_parent_folder_id,
                    FolderModel.id != folder_id,
                    FolderModel.is_active == True,
                )
                existing_result = await session.execute(existing_stmt)
                if existing_result.scalar_one_or_none():
                    raise FolderValidationError(
                        f"Folder with name '{folder_model.name}' already exists in target location"
                    )

                # Update folder
                folder_model.parent_folder_id = new_parent_folder_id
                folder_model.path = new_path
                folder_model.updated_at = datetime.now(timezone.utc)

                # Move in GCS if available
                if gcs_client.is_initialized:
                    try:
                        org_name = await self._get_organization_name(org_id)
                        old_gcs_path = old_path.lstrip("/")
                        new_gcs_path = new_path.lstrip("/")
                        await gcs_client.move_folder_structure_async(
                            org_name, old_gcs_path, new_gcs_path
                        )
                        self.logger.info(
                            "Moved GCS folder structure",
                            org_id=org_id,
                            old_path=old_gcs_path,
                            new_path=new_gcs_path,
                        )
                    except Exception as e:
                        self.logger.warning(
                            "Failed to move GCS folder structure",
                            org_id=org_id,
                            error=str(e),
                        )

                # Update paths of all descendant folders
                descendants_stmt = select(FolderModel).where(
                    FolderModel.organization_id == org_id,
                    FolderModel.path.startswith(old_path + "/"),
                    FolderModel.is_active == True,
                )
                descendants_result = await session.execute(descendants_stmt)
                descendants = descendants_result.scalars().all()

                for descendant in descendants:
                    relative_path = descendant.path[len(old_path) :]
                    descendant.path = new_path + relative_path
                    descendant.updated_at = datetime.now(timezone.utc)

                await session.flush()

                folder = self._model_to_pydantic(folder_model)
                self.logger.info(
                    "Folder moved",
                    org_id=org_id,
                    folder_id=folder_id,
                    old_path=old_path,
                    new_path=new_path,
                )

                # Invalidate folder cache
                asyncio.create_task(invalidate_folders(org_id))

                # Audit logging (non-blocking)
                asyncio.create_task(
                    audit_service.log_event(
                        org_id=org_id,
                        action=AuditAction.MOVE,
                        entity_type=AuditEntityType.FOLDER,
                        entity_id=folder_id,
                        user_id=moved_by_user_id,
                        details={
                            "old_path": old_path,
                            "new_path": new_path,
                            "old_parent_id": old_parent_folder_id,
                            "new_parent_id": new_parent_folder_id,
                            "operation": "move",
                        },
                        ip_address=ip_address,
                        session_id=session_id,
                        user_agent=user_agent,
                    )
                )

                return FolderResponse.model_validate(folder)

        except (FolderNotFoundError, FolderValidationError):
            raise
        except Exception as e:
            self.logger.error(
                "Error moving folder", org_id=org_id, folder_id=folder_id, error=str(e)
            )
            raise

    async def delete_folder(
        self,
        org_id: str,
        folder_id: str,
        deleted_by_user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        session_id: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Soft delete folder.

        Args:
            org_id: Organization ID
            folder_id: Folder ID to delete
            deleted_by_user_id: ID of user who deleted this folder (for audit)
            ip_address: Client IP address (for audit)
            session_id: Session ID (for audit)
            user_agent: Client user agent (for audit)

        Returns:
            Dictionary with deletion statistics

        Raises:
            FolderNotFoundError: If folder not found
        """
        try:
            async with db.session() as session:
                stmt = select(FolderModel).where(
                    FolderModel.id == folder_id,
                    FolderModel.organization_id == org_id,
                    FolderModel.is_active == True,
                )
                result = await session.execute(stmt)
                folder_model = result.scalar_one_or_none()

                if not folder_model:
                    raise FolderNotFoundError(f"Folder with ID {folder_id} not found")

                folder_path = folder_model.path
                folder_name = folder_model.name

                # Delete from GCS if available
                deleted_from_gcs = False
                if gcs_client.is_initialized:
                    try:
                        org_name = await self._get_organization_name(org_id)
                        gcs_path = folder_path.lstrip("/")
                        await gcs_client.delete_folder_structure_async(
                            org_name, gcs_path
                        )
                        deleted_from_gcs = True
                        self.logger.info(
                            "Deleted GCS folder structure",
                            org_id=org_id,
                            folder_path=gcs_path,
                        )
                    except Exception as e:
                        self.logger.warning(
                            "Failed to delete GCS folder structure",
                            org_id=org_id,
                            error=str(e),
                        )

                # Soft delete folder and descendants
                folder_model.is_active = False
                folder_model.updated_at = datetime.now(timezone.utc)

                # Also soft delete descendants
                descendants_stmt = select(FolderModel).where(
                    FolderModel.organization_id == org_id,
                    FolderModel.path.startswith(folder_path + "/"),
                    FolderModel.is_active == True,
                )
                descendants_result = await session.execute(descendants_stmt)
                descendants = descendants_result.scalars().all()

                deleted_folders = 1
                for descendant in descendants:
                    descendant.is_active = False
                    descendant.updated_at = datetime.now(timezone.utc)
                    deleted_folders += 1

                await session.flush()

                self.logger.info(
                    "Folder deleted",
                    org_id=org_id,
                    folder_id=folder_id,
                    deleted_folders=deleted_folders,
                )

                # Invalidate folder cache
                asyncio.create_task(invalidate_folders(org_id))

                # Audit logging (non-blocking)
                asyncio.create_task(
                    audit_service.log_event(
                        org_id=org_id,
                        action=AuditAction.DELETE,
                        entity_type=AuditEntityType.FOLDER,
                        entity_id=folder_id,
                        user_id=deleted_by_user_id,
                        details={
                            "deleted_values": {
                                "name": folder_name,
                                "path": folder_path,
                            },
                            "deleted_folders_count": deleted_folders,
                            "deleted_from_gcs": deleted_from_gcs,
                            "operation": "delete",
                        },
                        ip_address=ip_address,
                        session_id=session_id,
                        user_agent=user_agent,
                    )
                )

                return {
                    "success": True,
                    "message": "Folder deleted successfully",
                    "deleted_folders": deleted_folders,
                    "deleted_from_gcs": deleted_from_gcs,
                }

        except FolderNotFoundError:
            raise
        except Exception as e:
            self.logger.error(
                "Error deleting folder",
                org_id=org_id,
                folder_id=folder_id,
                error=str(e),
            )
            raise

    async def get_folder_path(self, org_id: str, folder_id: str) -> str:
        """
        Get full path of a folder.

        Args:
            org_id: Organization ID
            folder_id: Folder ID

        Returns:
            Full folder path

        Raises:
            FolderNotFoundError: If folder not found
        """
        try:
            async with db.session() as session:
                stmt = select(FolderModel).where(
                    FolderModel.id == folder_id,
                    FolderModel.organization_id == org_id,
                    FolderModel.is_active == True,
                )
                result = await session.execute(stmt)
                folder_model = result.scalar_one_or_none()

                if not folder_model:
                    raise FolderNotFoundError(f"Folder with ID {folder_id} not found")

                return folder_model.path

        except FolderNotFoundError:
            raise
        except Exception as e:
            self.logger.error(
                "Error getting folder path",
                org_id=org_id,
                folder_id=folder_id,
                error=str(e),
            )
            raise

    def _build_folder_tree(self, folders: List[Folder]) -> List[FolderWithChildren]:
        """Build hierarchical folder tree from flat list."""
        folder_dict = {folder.id: folder for folder in folders if folder.id}
        folder_responses = {
            folder.id: FolderWithChildren.model_validate(folder)
            for folder in folders
            if folder.id
        }

        root_folders = []

        for folder in folders:
            if folder.is_root:
                root_folders.append(folder_responses[folder.id])
            else:
                parent_id = folder.parent_folder_id
                if parent_id in folder_responses:
                    folder_responses[parent_id].children.append(
                        folder_responses[folder.id]
                    )

        return root_folders


# Global service instance
folder_service = FolderService()
