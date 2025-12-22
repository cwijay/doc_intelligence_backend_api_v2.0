from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Path, status

from app.core.logging import get_service_logger
from app.core.simple_auth import get_current_user_dict
from app.services.folder_service import (
    folder_service,
    FolderNotFoundError,
    FolderAlreadyExistsError,
    FolderValidationError,
)
from app.models.schemas import (
    FolderCreateRequest,
    FolderUpdateRequest,
    FolderMoveRequest,
    FolderResponse,
    FolderList,
    FolderTree,
    FolderDeleteResponse,
    PaginationParams,
    FolderFilters,
    FolderStatsResponse,
    NotFoundErrorResponse,
    ConflictErrorResponse,
    ValidationErrorResponse,
    ForbiddenErrorResponse,
    InternalServerErrorResponse,
)

logger = get_service_logger("folder_api")

router = APIRouter()


@router.post(
    "/organizations/{org_id}/folders",
    response_model=FolderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Folder",
    operation_id="createFolder",
    description="""Create a new folder in the specified organization.

**Authentication Required:** Yes

Folder names must be unique within the parent folder. Use `parent_folder_id: null` to create a root folder.

**Example Request:**
```json
{
  "name": "invoices",
  "parent_folder_id": null
}
```""",
    responses={
        201: {"description": "Folder created successfully"},
        400: {"model": ValidationErrorResponse, "description": "Validation error"},
        403: {"model": ForbiddenErrorResponse, "description": "Access denied to organization"},
        409: {"model": ConflictErrorResponse, "description": "Folder name already exists"},
        500: {"model": InternalServerErrorResponse, "description": "Internal server error"},
    },
)
async def create_folder(
    folder: FolderCreateRequest,
    org_id: str = Path(..., description="Organization ID"),
    current_user: Dict[str, Any] = Depends(get_current_user_dict),
) -> FolderResponse:
    """
    Create a new folder.

    - **name**: Folder name (required, unique within parent)
    - **parent_folder_id**: Parent folder ID (optional, null for root folder)
    - **org_id**: Organization ID (required)

    User ID is automatically extracted from the authentication token.
    """
    try:
        user_id = current_user["user_id"]

        # Verify the user belongs to the organization
        if current_user["org_id"] != org_id:
            logger.warning(
                "User attempted to create folder in different organization",
                user_id=user_id,
                user_org_id=current_user["org_id"],
                requested_org_id=org_id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this organization",
            )

        logger.info(
            "Creating folder",
            org_id=org_id,
            name=folder.name,
            parent_id=folder.parent_folder_id,
            user_id=user_id,
        )

        result = await folder_service.create_folder(org_id, folder, user_id)

        logger.info(
            "Folder created successfully",
            org_id=org_id,
            folder_id=result.id,
            name=result.name,
            path=result.path,
        )

        return result

    except FolderAlreadyExistsError as e:
        logger.warning(
            "Folder creation failed - name exists",
            org_id=org_id,
            name=folder.name,
            error=str(e),
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except FolderValidationError as e:
        logger.warning(
            "Folder creation failed - validation error",
            org_id=org_id,
            name=folder.name,
            error=str(e),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(
            "Failed to create folder", org_id=org_id, name=folder.name, error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while creating folder",
        )


@router.get(
    "/organizations/{org_id}/folders/{folder_id}",
    response_model=FolderResponse,
    summary="Get Folder",
    operation_id="getFolder",
    description="""Retrieve a specific folder by its unique identifier.

**Authentication Required:** Yes""",
    responses={
        200: {"description": "Folder retrieved successfully"},
        404: {"model": NotFoundErrorResponse, "description": "Folder not found"},
        500: {"model": InternalServerErrorResponse, "description": "Internal server error"},
    },
)
async def get_folder(
    org_id: str = Path(..., description="Organization ID"),
    folder_id: str = Path(..., description="Folder ID"),
) -> FolderResponse:
    """
    Get folder by ID.

    - **folder_id**: ID of the folder to retrieve
    - **org_id**: Organization ID
    """
    try:
        logger.debug("Retrieving folder", org_id=org_id, folder_id=folder_id)

        result = await folder_service.get_folder(org_id, folder_id)

        return result

    except FolderNotFoundError:
        logger.warning("Folder not found", org_id=org_id, folder_id=folder_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Folder with ID {folder_id} not found",
        )
    except Exception as e:
        logger.error(
            "Failed to retrieve folder",
            org_id=org_id,
            folder_id=folder_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving folder",
        )


@router.get(
    "/organizations/{org_id}/folders",
    response_model=FolderList,
    summary="List Folders",
    operation_id="listFolders",
    description="""Retrieve a paginated list of folders with optional filtering.

**Authentication Required:** Yes

**Query Parameters:**
- `page`: Page number (starts from 1)
- `per_page`: Items per page (max 100)
- `name`: Filter by folder name (partial match)
- `parent_folder_id`: Filter by parent (null for root folders)
- `created_by`: Filter by creator user ID
- `is_active`: Filter by active status""",
    responses={
        200: {"description": "Folders retrieved successfully"},
        500: {"model": InternalServerErrorResponse, "description": "Internal server error"},
    },
)
async def list_folders(
    org_id: str = Path(..., description="Organization ID"),
    page: int = Query(default=1, ge=1, description="Page number (starts from 1)"),
    per_page: int = Query(
        default=20, ge=1, le=100, description="Items per page (max 100)"
    ),
    name: Optional[str] = Query(
        default=None, description="Filter by folder name (partial match)"
    ),
    parent_folder_id: Optional[str] = Query(
        default=None, description="Filter by parent folder ID"
    ),
    created_by: Optional[str] = Query(
        default=None, description="Filter by creator user ID"
    ),
    is_active: Optional[bool] = Query(
        default=None, description="Filter by active status"
    ),
) -> FolderList:
    """
    List folders with pagination and filtering.

    Query Parameters:
    - **org_id**: Organization ID (required)
    - **page**: Page number (default: 1)
    - **per_page**: Items per page (default: 20, max: 100)
    - **name**: Filter by folder name (partial match)
    - **parent_folder_id**: Filter by parent folder ID (null for root folders)
    - **created_by**: Filter by creator user ID
    - **is_active**: Filter by active status (true/false)
    """
    try:
        # Create pagination parameters
        pagination = PaginationParams(page=page, per_page=per_page)

        # Create filters (only include non-None values)
        filters = FolderFilters(
            name=name,
            parent_folder_id=parent_folder_id,
            created_by=created_by,
            is_active=is_active,
        )

        logger.debug(
            "Listing folders",
            org_id=org_id,
            page=page,
            per_page=per_page,
            filters=filters.model_dump(exclude_none=True),
        )

        result = await folder_service.list_folders(org_id, pagination, filters)

        logger.debug(
            "Folders listed successfully",
            org_id=org_id,
            count=len(result.folders),
            total=result.total,
        )

        return result

    except Exception as e:
        logger.error("Failed to list folders", org_id=org_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while listing folders",
        )


@router.get(
    "/organizations/{org_id}/folders/tree",
    response_model=FolderTree,
    summary="Get Folder Tree",
    operation_id="getFolderTree",
    description="""Retrieve the complete folder hierarchy as a tree structure.

**Authentication Required:** Yes

Returns nested folders with children arrays for building hierarchical UI.""",
    responses={
        200: {"description": "Folder tree retrieved successfully"},
        500: {"model": InternalServerErrorResponse, "description": "Internal server error"},
    },
)
async def get_folder_tree(
    org_id: str = Path(..., description="Organization ID")
) -> FolderTree:
    """
    Get folder tree structure.

    Returns the complete folder hierarchy for the organization as a nested tree structure.

    - **org_id**: Organization ID
    """
    try:
        logger.debug("Retrieving folder tree", org_id=org_id)

        result = await folder_service.get_folder_tree(org_id)

        logger.debug(
            "Folder tree retrieved successfully",
            org_id=org_id,
            total_folders=result.total_folders,
        )

        return result

    except Exception as e:
        logger.error("Failed to retrieve folder tree", org_id=org_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving folder tree",
        )


@router.put(
    "/organizations/{org_id}/folders/{folder_id}",
    response_model=FolderResponse,
    summary="Update Folder",
    operation_id="updateFolder",
    description="""Update an existing folder's details.

**Authentication Required:** Yes

Only the name field can be updated. Note: Folder renames require path recalculation.""",
    responses={
        200: {"description": "Folder updated successfully"},
        400: {"model": ValidationErrorResponse, "description": "Validation error"},
        404: {"model": NotFoundErrorResponse, "description": "Folder not found"},
        500: {"model": InternalServerErrorResponse, "description": "Internal server error"},
    },
)
async def update_folder(
    folder: FolderUpdateRequest,
    org_id: str = Path(..., description="Organization ID"),
    folder_id: str = Path(..., description="Folder ID"),
) -> FolderResponse:
    """
    Update folder by ID.

    - **folder_id**: ID of the folder to update
    - **name**: New folder name (optional)
    - **org_id**: Organization ID
    """
    try:
        logger.info("Updating folder", org_id=org_id, folder_id=folder_id)

        # Currently only name field is supported for updates.
        # Folder rename requires path recalculation for all descendants,
        # which is handled in the folder_service.rename_folder method.
        if folder.name is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one field must be provided for update",
            )

        # Get current folder
        current_folder = await folder_service.get_folder(org_id, folder_id)

        if folder.name and folder.name != current_folder.name:
            # Name update not implemented yet as it requires path recalculation
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Folder name updates are not yet implemented",
            )

        # Return current folder for now
        return current_folder

    except FolderNotFoundError:
        logger.warning(
            "Folder update failed - not found", org_id=org_id, folder_id=folder_id
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Folder with ID {folder_id} not found",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to update folder", org_id=org_id, folder_id=folder_id, error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while updating folder",
        )


@router.put(
    "/organizations/{org_id}/folders/{folder_id}/move",
    response_model=FolderResponse,
    summary="Move Folder",
    operation_id="moveFolder",
    description="""Move a folder to a new parent folder or to the root level.

**Authentication Required:** Yes

Set `new_parent_folder_id: null` to move to root. All descendant paths are automatically updated.""",
    responses={
        200: {"description": "Folder moved successfully"},
        400: {"model": ValidationErrorResponse, "description": "Invalid move (circular reference)"},
        404: {"model": NotFoundErrorResponse, "description": "Folder not found"},
        500: {"model": InternalServerErrorResponse, "description": "Internal server error"},
    },
)
async def move_folder(
    move_request: FolderMoveRequest,
    org_id: str = Path(..., description="Organization ID"),
    folder_id: str = Path(..., description="Folder ID"),
) -> FolderResponse:
    """
    Move folder to new parent.

    - **folder_id**: ID of the folder to move
    - **new_parent_folder_id**: New parent folder ID (null to move to root)
    - **org_id**: Organization ID
    """
    try:
        logger.info(
            "Moving folder",
            org_id=org_id,
            folder_id=folder_id,
            new_parent_id=move_request.new_parent_folder_id,
        )

        result = await folder_service.move_folder(
            org_id, folder_id, move_request.new_parent_folder_id
        )

        logger.info(
            "Folder moved successfully",
            org_id=org_id,
            folder_id=folder_id,
            new_path=result.path,
        )

        return result

    except FolderNotFoundError:
        logger.warning(
            "Folder move failed - not found", org_id=org_id, folder_id=folder_id
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Folder with ID {folder_id} not found",
        )
    except FolderValidationError as e:
        logger.warning(
            "Folder move failed - validation error",
            org_id=org_id,
            folder_id=folder_id,
            error=str(e),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(
            "Failed to move folder", org_id=org_id, folder_id=folder_id, error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while moving folder",
        )


@router.delete(
    "/organizations/{org_id}/folders/{folder_id}",
    response_model=FolderDeleteResponse,
    summary="Delete Folder",
    operation_id="deleteFolder",
    description="""Delete a folder and all its contents recursively.

**Authentication Required:** Yes

**Warning:** This deletes all subfolders and documents. This operation cannot be undone.""",
    responses={
        200: {"description": "Folder deleted successfully"},
        404: {"model": NotFoundErrorResponse, "description": "Folder not found"},
        500: {"model": InternalServerErrorResponse, "description": "Internal server error"},
    },
)
async def delete_folder(
    org_id: str = Path(..., description="Organization ID"),
    folder_id: str = Path(..., description="Folder ID"),
) -> FolderDeleteResponse:
    """
    Delete folder by ID.

    - **folder_id**: ID of the folder to delete
    - **org_id**: Organization ID

    Note: This performs a recursive delete of the folder and all its subfolders and documents.
    The operation cannot be undone.
    """
    try:
        logger.info("Deleting folder", org_id=org_id, folder_id=folder_id)

        result = await folder_service.delete_folder(org_id, folder_id)

        logger.info(
            "Folder deleted successfully",
            org_id=org_id,
            folder_id=folder_id,
            deleted_folders=result.get("deleted_folders", 0),
        )

        return FolderDeleteResponse(
            success=result["success"],
            message=result["message"],
            deleted_folders=result.get("deleted_folders", 0),
            deleted_documents=result.get("deleted_documents", 0),
        )

    except FolderNotFoundError:
        logger.warning(
            "Folder deletion failed - not found", org_id=org_id, folder_id=folder_id
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Folder with ID {folder_id} not found",
        )
    except Exception as e:
        logger.error(
            "Failed to delete folder", org_id=org_id, folder_id=folder_id, error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while deleting folder",
        )


@router.get(
    "/organizations/{org_id}/folders/{folder_id}/path",
    response_model=Dict[str, str],
    summary="Get Folder Path",
    operation_id="getFolderPath",
    description="""Get the full path of a folder.

**Authentication Required:** Yes

Returns the complete path from root (e.g., "/invoices/2025/q1").""",
    responses={
        200: {"description": "Folder path retrieved successfully"},
        404: {"model": NotFoundErrorResponse, "description": "Folder not found"},
        500: {"model": InternalServerErrorResponse, "description": "Internal server error"},
    },
)
async def get_folder_path(
    org_id: str = Path(..., description="Organization ID"),
    folder_id: str = Path(..., description="Folder ID"),
) -> Dict[str, str]:
    """
    Get folder path by ID.

    - **folder_id**: ID of the folder
    - **org_id**: Organization ID
    """
    try:
        logger.debug("Retrieving folder path", org_id=org_id, folder_id=folder_id)

        path = await folder_service.get_folder_path(org_id, folder_id)

        return {"path": path}

    except FolderNotFoundError:
        logger.warning(
            "Folder path retrieval failed - not found",
            org_id=org_id,
            folder_id=folder_id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Folder with ID {folder_id} not found",
        )
    except Exception as e:
        logger.error(
            "Failed to retrieve folder path",
            org_id=org_id,
            folder_id=folder_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving folder path",
        )


@router.get(
    "/organizations/{org_id}/folders/stats/summary",
    response_model=FolderStatsResponse,
    summary="Get Folder Statistics",
    operation_id="getFolderStats",
    description="""Get summary statistics about folders in the organization.

**Authentication Required:** Yes

Returns counts by depth, root folder count, and active/inactive metrics.""",
    responses={
        200: {"description": "Statistics retrieved successfully"},
        500: {"model": InternalServerErrorResponse, "description": "Internal server error"},
    },
)
async def get_folder_stats(
    org_id: str = Path(..., description="Organization ID")
) -> FolderStatsResponse:
    """
    Get folder statistics and summary information.

    Returns counts of folders by depth, total folders, and other metrics.

    - **org_id**: Organization ID
    """
    try:
        logger.debug("Retrieving folder statistics", org_id=org_id)

        # Get all folders to calculate stats
        all_folders = await folder_service.list_folders(
            org_id,
            PaginationParams(page=1, per_page=1000),
            FolderFilters(is_active=None),  # Include inactive
        )

        # Calculate statistics
        total_count = all_folders.total
        active_count = sum(1 for folder in all_folders.folders if folder.is_active)
        inactive_count = total_count - active_count

        # Count by depth
        depth_counts = {}
        root_count = 0

        for folder in all_folders.folders:
            if folder.is_active:
                if folder.is_root:
                    root_count += 1

                depth = folder.depth
                depth_counts[depth] = depth_counts.get(depth, 0) + 1

        # Convert depth_counts keys to strings for the response model
        depth_distribution = {str(k): v for k, v in depth_counts.items()}

        stats = FolderStatsResponse(
            total_folders=total_count,
            active_folders=active_count,
            inactive_folders=inactive_count,
            root_folders=root_count,
            depth_distribution=depth_distribution,
            max_depth=max(depth_counts.keys()) if depth_counts else 0,
        )

        logger.debug("Folder statistics retrieved", org_id=org_id, stats=stats.model_dump())

        return stats

    except Exception as e:
        logger.error(
            "Failed to retrieve folder statistics", org_id=org_id, error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving statistics",
        )
