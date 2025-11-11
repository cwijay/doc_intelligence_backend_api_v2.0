import math
from typing import List, Optional, Dict, Any
from datetime import datetime

from google.cloud.firestore_v1 import FieldFilter

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
from app.core.firebase_client import get_collection
from app.core.gcs_client import gcs_client, GCSClientError
from app.core.logging import get_service_logger

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
        # Import here to avoid circular imports
        from app.services.org_service import organization_service

        self.org_service = organization_service

    def _get_collection(self, org_id: str):
        """Get the folders collection for an organization."""
        return get_collection(f"organizations/{org_id}/folders")

    async def _get_organization_name(self, org_id: str) -> str:
        """
        Get organization name from organization ID.

        Args:
            org_id: Organization ID

        Returns:
            Organization name

        Raises:
            FolderValidationError: If organization not found
        """
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
        self, org_id: str, folder_data: FolderCreate, user_id: str
    ) -> FolderResponse:
        """
        Create a new folder.

        Args:
            org_id: Organization ID
            folder_data: Folder creation data
            user_id: ID of user creating the folder

        Returns:
            Created folder response

        Raises:
            FolderAlreadyExistsError: If folder name already exists in parent
            FolderValidationError: If validation fails
        """
        try:
            # Validate parent folder if specified
            parent_folder = None
            parent_path = None

            if folder_data.parent_folder_id:
                parent_folder = await self._get_folder_by_id(
                    org_id, folder_data.parent_folder_id
                )
                if not parent_folder:
                    raise FolderValidationError(
                        f"Parent folder {folder_data.parent_folder_id} not found"
                    )

                parent_path = parent_folder.path

                # Check depth limit
                if parent_folder.depth >= self.max_depth:
                    raise FolderValidationError(
                        f"Maximum folder depth ({self.max_depth}) exceeded"
                    )

            # Calculate folder path
            if parent_path:
                full_path = f"{parent_path}/{folder_data.name}"
            else:
                full_path = f"/{folder_data.name}"

            # Check if folder already exists in GCS
            if gcs_client.is_initialized:
                org_name = await self._get_organization_name(org_id)
                folder_path = full_path.lstrip("/")

                # Check if any folder structure already exists
                try:
                    existing_files = gcs_client.list_folder_contents(
                        org_name, folder_path, "original"
                    )
                    if existing_files or self._gcs_folder_exists(org_name, folder_path):
                        raise FolderAlreadyExistsError(
                            f"Folder with name '{folder_data.name}' already exists in this location"
                        )
                except Exception as e:
                    # If we can't check, proceed (folder might not exist)
                    self.logger.debug(
                        "Could not check for existing folder in GCS",
                        org_id=org_id,
                        folder_path=folder_path,
                        error=str(e),
                    )

            # Ensure GCS is available
            if not gcs_client.is_initialized:
                error_msg = "GCS client not initialized"
                if gcs_client.initialization_error:
                    error_msg += f": {gcs_client.initialization_error}"
                raise FolderValidationError(error_msg)

            # Get organization name for GCS path
            org_name = await self._get_organization_name(org_id)
            folder_path = full_path.lstrip("/")  # Remove leading slash for GCS

            # Create folder structure in GCS
            try:
                gcs_result = gcs_client.create_folder_structure(org_name, folder_path)
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
                raise FolderValidationError(f"Failed to create folder in GCS: {e}")

            # Create folder model for response (no Firestore storage)
            folder = Folder(
                id=folder_path,  # Use folder path as ID for GCS-only approach
                org_id=org_id,
                name=folder_data.name,
                parent_folder_id=folder_data.parent_folder_id,
                path=full_path,
                created_by=user_id,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )

            self.logger.info(
                "Folder created in GCS only",
                org_id=org_id,
                org_name=org_name,
                name=folder.name,
                path=folder.path,
            )

            return FolderResponse.model_validate(folder)

        except (FolderAlreadyExistsError, FolderValidationError):
            raise
        except Exception as e:
            self.logger.error("Error creating folder", org_id=org_id, error=str(e))
            raise

    async def get_folder(self, org_id: str, folder_id: str) -> FolderResponse:
        """
        Get folder by path (using folder_id as folder path).
        Since we're GCS-only, folder_id is treated as the folder path.

        Args:
            org_id: Organization ID
            folder_id: Folder path (e.g., "quality_control_docs")

        Returns:
            Folder response

        Raises:
            FolderNotFoundError: If folder not found in GCS
        """
        try:
            if not gcs_client.is_initialized:
                raise FolderValidationError("GCS client not initialized")

            org_name = await self._get_organization_name(org_id)
            folder_path = folder_id  # Use folder_id as path

            # Check if folder exists in GCS
            if not self._gcs_folder_exists(org_name, folder_path):
                raise FolderNotFoundError(f"Folder '{folder_path}' not found in GCS")

            # Create folder model from GCS path
            folder = Folder(
                id=folder_path,  # Use path as ID
                org_id=org_id,
                name=folder_path.split("/")[-1],  # Last part of path
                parent_folder_id=None,  # Simplified for GCS-only
                path=f"/{folder_path}",
                created_by="unknown",  # Not tracked in GCS
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )

            self.logger.debug(
                "Folder retrieved from GCS", org_id=org_id, folder_path=folder_path
            )

            return FolderResponse.model_validate(folder)

        except FolderNotFoundError:
            raise
        except Exception as e:
            self.logger.error(
                "Error retrieving folder from GCS",
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
        List folders from GCS bucket structure.

        Args:
            org_id: Organization ID
            pagination: Pagination parameters
            filters: Optional filters (limited support)

        Returns:
            Paginated folder list from GCS
        """
        try:
            if not gcs_client.is_initialized:
                raise FolderValidationError("GCS client not initialized")

            org_name = await self._get_organization_name(org_id)
            all_folders = []

            # List all marker files from both original and parsed folders to get complete folder list
            try:
                folder_paths = set()

                # Check original folders (.keep files)
                original_blobs = gcs_client.bucket.list_blobs(
                    prefix=f"{org_name}/original/"
                )
                for blob in original_blobs:
                    if blob.name.endswith(".keep"):
                        # Extract folder path from: org_name/original/folder_path/.keep
                        parts = blob.name.split("/")
                        if len(parts) >= 3:
                            folder_path = "/".join(
                                parts[2:-1]
                            )  # Remove org/type and marker
                            if folder_path:  # Skip empty paths
                                folder_paths.add(folder_path)

                # Also check parsed folders (.folder_placeholder files) for any additional folders
                parsed_blobs = gcs_client.bucket.list_blobs(
                    prefix=f"{org_name}/parsed/"
                )
                for blob in parsed_blobs:
                    if blob.name.endswith(".folder_placeholder"):
                        # Extract folder path from: org_name/parsed/folder_path/.folder_placeholder
                        parts = blob.name.split("/")
                        if len(parts) >= 3:
                            folder_path = "/".join(
                                parts[2:-1]
                            )  # Remove org/type and placeholder
                            if folder_path:  # Skip empty paths
                                folder_paths.add(folder_path)

                # Convert folder paths to Folder objects
                for folder_path in sorted(folder_paths):
                    folder_name = folder_path.split("/")[-1]  # Last part of path

                    # Apply name filter if specified
                    if filters and filters.name:
                        if filters.name.lower() not in folder_name.lower():
                            continue

                    folder = Folder(
                        id=folder_path,  # Use path as ID
                        org_id=org_id,
                        name=folder_name,
                        parent_folder_id=None,  # Simplified for GCS-only
                        path=f"/{folder_path}",
                        created_by="unknown",  # Not tracked in GCS
                        is_active=True,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                    all_folders.append(folder)

            except Exception as e:
                self.logger.error(
                    "Error listing GCS folders",
                    org_id=org_id,
                    org_name=org_name,
                    error=str(e),
                )
                raise FolderValidationError(f"Failed to list folders from GCS: {e}")

            # Get total count
            total = len(all_folders)

            # Apply pagination
            start_idx = pagination.offset
            end_idx = start_idx + pagination.per_page
            paginated_folders = all_folders[start_idx:end_idx]

            # Convert to response models
            folder_responses = [
                FolderResponse.model_validate(folder) for folder in paginated_folders
            ]

            # Calculate pagination info
            total_pages = math.ceil(total / pagination.per_page) if total > 0 else 0

            self.logger.debug(
                "GCS folders listed",
                org_id=org_id,
                org_name=org_name,
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
            self.logger.error(
                "Error listing folders from GCS", org_id=org_id, error=str(e)
            )
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
            # Get all active folders
            collection = self._get_collection(org_id)
            query = collection.where(filter=FieldFilter("is_active", "==", True))
            query = query.order_by("path")

            docs = query.stream()
            all_folders = []

            async for doc in docs:
                folder_data = doc.to_dict()
                folder = Folder.from_dict(folder_data, doc.id)
                all_folders.append(folder)

            # Build tree structure
            folder_tree = self._build_folder_tree(all_folders)

            self.logger.debug(
                "Folder tree retrieved", org_id=org_id, total_folders=len(all_folders)
            )

            return FolderTree(folders=folder_tree, total_folders=len(all_folders))

        except Exception as e:
            self.logger.error(
                "Error retrieving folder tree", org_id=org_id, error=str(e)
            )
            raise

    async def move_folder(
        self, org_id: str, folder_id: str, new_parent_folder_id: Optional[str]
    ) -> FolderResponse:
        """
        Move folder to new parent.

        Args:
            org_id: Organization ID
            folder_id: Folder ID to move
            new_parent_folder_id: New parent folder ID (None for root)

        Returns:
            Updated folder response

        Raises:
            FolderNotFoundError: If folder not found
            FolderValidationError: If move is invalid
        """
        try:
            # Get folder to move
            folder = await self._get_folder_by_id(org_id, folder_id)
            if not folder or not folder.is_active:
                raise FolderNotFoundError(f"Folder with ID {folder_id} not found")

            # Validate new parent
            new_parent_folder = None
            new_parent_path = None

            if new_parent_folder_id:
                new_parent_folder = await self._get_folder_by_id(
                    org_id, new_parent_folder_id
                )
                if not new_parent_folder or not new_parent_folder.is_active:
                    raise FolderValidationError(
                        f"New parent folder {new_parent_folder_id} not found"
                    )

                new_parent_path = new_parent_folder.path

                # Check if moving to descendant (circular reference)
                if new_parent_path.startswith(folder.path):
                    raise FolderValidationError(
                        "Cannot move folder to its own descendant"
                    )

                # Check depth limit
                new_depth = new_parent_folder.depth + 1
                if new_depth > self.max_depth:
                    raise FolderValidationError(
                        f"Move would exceed maximum depth ({self.max_depth})"
                    )

            # Check if folder with same name exists in new parent
            existing_folder = await self._get_folder_by_name_and_parent(
                org_id, folder.name, new_parent_folder_id
            )
            if existing_folder and existing_folder.id != folder_id:
                raise FolderValidationError(
                    f"Folder with name '{folder.name}' already exists in target location"
                )

            # Calculate new path
            old_path = folder.path
            if new_parent_path:
                new_path = f"{new_parent_path}/{folder.name}"
            else:
                new_path = f"/{folder.name}"

            # Update folder
            folder.parent_folder_id = new_parent_folder_id
            folder.path = new_path
            folder.update_timestamp()

            # Update in Firestore
            doc_ref = self._get_collection(org_id).document(folder_id)
            await doc_ref.update(folder.to_dict())

            # Move in GCS (if available)
            if gcs_client.is_initialized:
                try:
                    # Get organization name for GCS path
                    org_name = await self._get_organization_name(org_id)
                    old_gcs_path = old_path.lstrip("/")
                    new_gcs_path = new_path.lstrip("/")
                    gcs_result = gcs_client.move_folder_structure(
                        org_name, old_gcs_path, new_gcs_path
                    )
                    self.logger.info(
                        "Moved GCS folder structure",
                        org_id=org_id,
                        org_name=org_name,
                        folder_id=folder_id,
                        old_path=old_gcs_path,
                        new_path=new_gcs_path,
                        gcs_result=gcs_result,
                    )
                except GCSClientError as e:
                    self.logger.warning(
                        "Failed to move GCS folder structure",
                        org_id=org_id,
                        folder_id=folder_id,
                        error=str(e),
                    )
                except FolderValidationError as e:
                    self.logger.warning(
                        "Failed to get organization name for GCS move",
                        org_id=org_id,
                        folder_id=folder_id,
                        error=str(e),
                    )
            else:
                self.logger.debug(
                    "GCS not configured, skipping folder structure move",
                    org_id=org_id,
                    folder_id=folder_id,
                )

            # Update paths of all descendant folders
            await self._update_descendant_paths(org_id, folder_id, old_path, new_path)

            self.logger.info(
                "Folder moved",
                org_id=org_id,
                folder_id=folder_id,
                old_path=old_path,
                new_path=new_path,
            )

            return FolderResponse.model_validate(folder)

        except (FolderNotFoundError, FolderValidationError):
            raise
        except Exception as e:
            self.logger.error(
                "Error moving folder", org_id=org_id, folder_id=folder_id, error=str(e)
            )
            raise

    async def delete_folder(self, org_id: str, folder_id: str) -> Dict[str, Any]:
        """
        Delete folder from GCS (folder_id is treated as folder path).

        Args:
            org_id: Organization ID
            folder_id: Folder path to delete

        Returns:
            Dictionary with deletion statistics

        Raises:
            FolderNotFoundError: If folder not found in GCS
        """
        try:
            if not gcs_client.is_initialized:
                raise FolderValidationError("GCS client not initialized")

            org_name = await self._get_organization_name(org_id)
            folder_path = folder_id  # Use folder_id as path

            # Check if folder exists in GCS
            if not self._gcs_folder_exists(org_name, folder_path):
                raise FolderNotFoundError(f"Folder '{folder_path}' not found in GCS")

            # Delete from GCS
            try:
                gcs_result = gcs_client.delete_folder_structure(org_name, folder_path)
                self.logger.info(
                    "Deleted GCS folder structure",
                    org_id=org_id,
                    org_name=org_name,
                    folder_path=folder_path,
                    gcs_result=gcs_result,
                )

                deleted_folders = 1  # Only counting the main folder
                deleted_documents = 0  # TODO: Count actual files if needed

            except GCSClientError as e:
                self.logger.error(
                    "Failed to delete GCS folder structure",
                    org_id=org_id,
                    folder_path=folder_path,
                    error=str(e),
                )
                raise FolderValidationError(f"Failed to delete folder from GCS: {e}")

            self.logger.info(
                "Folder deleted from GCS",
                org_id=org_id,
                org_name=org_name,
                folder_path=folder_path,
            )

            return {
                "success": True,
                "message": f"Folder '{folder_path}' deleted successfully from GCS",
                "deleted_folders": deleted_folders,
                "deleted_documents": deleted_documents,
            }

        except FolderNotFoundError:
            raise
        except Exception as e:
            self.logger.error(
                "Error deleting folder from GCS",
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
            folder = await self._get_folder_by_id(org_id, folder_id)
            if not folder or not folder.is_active:
                raise FolderNotFoundError(f"Folder with ID {folder_id} not found")

            return folder.path

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

    # Private helper methods
    async def _get_folder_by_id(self, org_id: str, folder_id: str) -> Optional[Folder]:
        """Get folder by ID (internal method)."""
        try:
            doc_ref = self._get_collection(org_id).document(folder_id)
            doc = await doc_ref.get()

            if not doc.exists:
                return None

            folder_data = doc.to_dict()
            return Folder.from_dict(folder_data, doc.id)
        except Exception as e:
            self.logger.error(
                "Error getting folder by ID",
                org_id=org_id,
                folder_id=folder_id,
                error=str(e),
            )
            return None

    async def _get_folder_by_name_and_parent(
        self, org_id: str, name: str, parent_folder_id: Optional[str]
    ) -> Optional[Folder]:
        """Get folder by name and parent (internal method)."""
        try:
            collection = self._get_collection(org_id)
            query = collection.where(filter=FieldFilter("name", "==", name))
            query = query.where(
                filter=FieldFilter("parent_folder_id", "==", parent_folder_id)
            )
            query = query.where(filter=FieldFilter("is_active", "==", True))

            docs = query.stream()
            async for doc in docs:
                folder_data = doc.to_dict()
                return Folder.from_dict(folder_data, doc.id)

            return None
        except Exception as e:
            self.logger.error(
                "Error getting folder by name and parent",
                org_id=org_id,
                name=name,
                parent_folder_id=parent_folder_id,
                error=str(e),
            )
            return None

    async def _get_descendant_folders(
        self, org_id: str, folder_path: str
    ) -> List[Folder]:
        """Get all descendant folders of a given path."""
        try:
            collection = self._get_collection(org_id)
            query = collection.where(filter=FieldFilter("is_active", "==", True))

            docs = query.stream()
            descendants = []

            async for doc in docs:
                folder_data = doc.to_dict()
                folder = Folder.from_dict(folder_data, doc.id)

                # Check if this folder is a descendant
                if folder.path.startswith(folder_path + "/"):
                    descendants.append(folder)

            return descendants
        except Exception as e:
            self.logger.error(
                "Error getting descendant folders",
                org_id=org_id,
                folder_path=folder_path,
                error=str(e),
            )
            return []

    async def _update_descendant_paths(
        self, org_id: str, moved_folder_id: str, old_path: str, new_path: str
    ) -> None:
        """Update paths of all descendant folders after a move."""
        try:
            descendant_folders = await self._get_descendant_folders(org_id, old_path)

            collection = self._get_collection(org_id)

            for descendant in descendant_folders:
                # Calculate new path for descendant
                relative_path = descendant.path[
                    len(old_path) :
                ]  # Remove old parent path
                descendant_new_path = new_path + relative_path

                # Update descendant
                doc_ref = collection.document(descendant.id)
                await doc_ref.update(
                    {
                        "path": descendant_new_path,
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                )

                self.logger.debug(
                    "Updated descendant folder path",
                    org_id=org_id,
                    folder_id=descendant.id,
                    old_path=descendant.path,
                    new_path=descendant_new_path,
                )
        except Exception as e:
            self.logger.error(
                "Error updating descendant paths",
                org_id=org_id,
                moved_folder_id=moved_folder_id,
                error=str(e),
            )

    def _gcs_folder_exists(self, org_name: str, folder_path: str) -> bool:
        """Check if a folder exists in GCS by looking for marker files in all folder types."""
        try:
            # Check for different marker files in each folder type
            folder_markers = {
                "original": ".keep",
                "parsed": ".folder_placeholder",
                "bm-25": ".folder_placeholder",
            }

            for folder_type, marker_file in folder_markers.items():
                blob_name = f"{org_name}/{folder_type}/{folder_path}/{marker_file}"
                blob = gcs_client.bucket.blob(blob_name)
                if blob.exists():
                    return True
            return False
        except Exception:
            return False

    def _build_folder_tree(self, folders: List[Folder]) -> List[FolderWithChildren]:
        """Build hierarchical folder tree from flat list."""
        # Create lookup dictionary
        folder_dict = {folder.id: folder for folder in folders if folder.id}

        # Create response objects
        folder_responses = {
            folder.id: FolderWithChildren.model_validate(folder)
            for folder in folders
            if folder.id
        }

        # Build hierarchy
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
