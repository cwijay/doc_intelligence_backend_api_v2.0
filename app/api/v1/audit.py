"""
Audit log API endpoints.

Provides endpoints for querying audit logs with role-based access:
- Regular users: Can view their own activity
- Admin users: Can view all audit logs for the organization
"""

from typing import Optional, Dict, Any, List
from datetime import datetime

from fastapi import APIRouter, Query, Depends, HTTPException, status

from app.core.simple_auth import get_current_user_dict
from biz2bricks_core import AuditAction, AuditEntityType
from app.core.logging import get_api_logger
from app.services.audit_service import audit_service
from app.models.schemas import (
    PaginationParams,
    AuditLogListResponse,
    ValidationErrorResponse,
    ForbiddenErrorResponse,
    InternalServerErrorResponse,
)

logger = get_api_logger()
router = APIRouter()


def _is_admin(current_user: Dict[str, Any]) -> bool:
    """Check if the current user has admin role."""
    return current_user.get("role") == "admin"


@router.get(
    "/",
    response_model=AuditLogListResponse,
    summary="List Audit Logs",
    operation_id="listAuditLogs",
    description="""Query audit logs with filtering and pagination.

**Authentication Required:** Yes

**Access Control:**
- Admin users: Can view all audit logs for the organization
- Regular users: Can only view their own activity (logs where they are the actor)

**Filter Options:**
- `entity_type`: ORGANIZATION, USER, FOLDER, DOCUMENT
- `action`: CREATE, UPDATE, DELETE, LOGIN, LOGOUT, UPLOAD, DOWNLOAD, MOVE
- `user_id`: Filter by actor (admin only)
- `start_date`/`end_date`: Date range filter (ISO 8601 format)

**Example:** `/audit?entity_type=DOCUMENT&action=UPLOAD&page=1&per_page=20`""",
    responses={
        200: {"description": "Audit logs retrieved successfully"},
        400: {"model": ValidationErrorResponse, "description": "Invalid filter parameters"},
        403: {"model": ForbiddenErrorResponse, "description": "Non-admin users cannot filter by other users"},
        500: {"model": InternalServerErrorResponse, "description": "Internal server error"},
    },
)
async def list_audit_logs(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=100, description="Items per page"),
    entity_type: Optional[str] = Query(
        None,
        description="Filter by entity type (ORGANIZATION, USER, FOLDER, DOCUMENT)",
    ),
    entity_id: Optional[str] = Query(None, description="Filter by entity ID"),
    user_id: Optional[str] = Query(
        None, description="Filter by user who performed action (admin only)"
    ),
    action: Optional[str] = Query(
        None,
        description="Filter by action type (CREATE, UPDATE, DELETE, LOGIN, LOGOUT, UPLOAD, DOWNLOAD, MOVE)",
    ),
    start_date: Optional[datetime] = Query(
        None, description="Filter from date (ISO format)"
    ),
    end_date: Optional[datetime] = Query(
        None, description="Filter to date (ISO format)"
    ),
    current_user: Dict[str, Any] = Depends(get_current_user_dict),
):
    """
    List audit logs with pagination and filtering.

    Returns audit logs based on user role:
    - Admins see all logs for the organization
    - Regular users only see their own activity
    """
    try:
        pagination = PaginationParams(page=page, per_page=per_page)

        # Convert string params to enums if provided
        entity_type_enum = None
        if entity_type:
            try:
                entity_type_enum = AuditEntityType(entity_type)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid entity_type: {entity_type}. Must be one of: {[e.value for e in AuditEntityType]}",
                )

        action_enum = None
        if action:
            try:
                action_enum = AuditAction(action)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid action: {action}. Must be one of: {[a.value for a in AuditAction]}",
                )

        # Determine access level
        is_admin = _is_admin(current_user)

        # Non-admin users can only see their own activity
        restrict_to_user = None if is_admin else current_user["user_id"]

        # Non-admin users cannot filter by user_id (they can only see their own)
        if not is_admin and user_id and user_id != current_user["user_id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only view your own activity",
            )

        result = await audit_service.get_audit_logs(
            org_id=current_user["org_id"],
            pagination=pagination,
            entity_type=entity_type_enum,
            entity_id=entity_id,
            user_id=user_id if is_admin else None,  # Only admins can filter by user
            action=action_enum,
            start_date=start_date,
            end_date=end_date,
            restrict_to_user=restrict_to_user,
        )

        logger.debug(
            "Audit logs retrieved",
            org_id=current_user["org_id"],
            user_id=current_user["user_id"],
            is_admin=is_admin,
            total=result["total"],
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error listing audit logs",
            org_id=current_user["org_id"],
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve audit logs",
        )


@router.get(
    "/my-activity",
    response_model=AuditLogListResponse,
    summary="Get My Activity",
    operation_id="getMyActivity",
    description="""Get the current user's own activity history.

**Authentication Required:** Yes

A convenience endpoint that filters audit logs to show only the current user's actions.
Useful for users to review their own recent activity.

**Filter Options:**
- `action`: CREATE, UPDATE, DELETE, LOGIN, LOGOUT, UPLOAD, DOWNLOAD, MOVE
- `start_date`/`end_date`: Date range filter (ISO 8601 format)

**Example:** `/audit/my-activity?action=UPLOAD&per_page=10`""",
    responses={
        200: {"description": "User activity retrieved successfully"},
        400: {"model": ValidationErrorResponse, "description": "Invalid filter parameters"},
        500: {"model": InternalServerErrorResponse, "description": "Internal server error"},
    },
)
async def get_my_activity(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=100, description="Items per page"),
    action: Optional[str] = Query(
        None,
        description="Filter by action type (CREATE, UPDATE, DELETE, LOGIN, LOGOUT, UPLOAD, DOWNLOAD, MOVE)",
    ),
    start_date: Optional[datetime] = Query(
        None, description="Filter from date (ISO format)"
    ),
    end_date: Optional[datetime] = Query(
        None, description="Filter to date (ISO format)"
    ),
    current_user: Dict[str, Any] = Depends(get_current_user_dict),
):
    """
    Get the current user's activity history.

    This is a convenience endpoint that filters audit logs
    to show only the current user's actions.
    """
    try:
        pagination = PaginationParams(page=page, per_page=per_page)

        action_enum = None
        if action:
            try:
                action_enum = AuditAction(action)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid action: {action}. Must be one of: {[a.value for a in AuditAction]}",
                )

        result = await audit_service.get_user_activity(
            org_id=current_user["org_id"],
            user_id=current_user["user_id"],
            pagination=pagination,
            action=action_enum,
            start_date=start_date,
            end_date=end_date,
        )

        logger.debug(
            "User activity retrieved",
            org_id=current_user["org_id"],
            user_id=current_user["user_id"],
            total=result["total"],
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error getting user activity",
            org_id=current_user["org_id"],
            user_id=current_user["user_id"],
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve activity",
        )


@router.get(
    "/entity/{entity_type}/{entity_id}",
    response_model=List[Dict[str, Any]],
    summary="Get Entity History",
    operation_id="getEntityHistory",
    description="""Get complete audit history for a specific entity.

**Authentication Required:** Yes (Admin only)

Returns all audit events for a document, user, folder, or organization.

**Use Cases:**
- View all changes to a specific document
- Track user account modifications
- Debug folder operations
- Audit organization-level changes

**Path Parameters:**
- `entity_type`: ORGANIZATION, USER, FOLDER, DOCUMENT
- `entity_id`: The unique identifier of the entity

**Example:** `/audit/entity/DOCUMENT/doc_abc123?limit=100`""",
    responses={
        200: {"description": "Entity history retrieved successfully"},
        400: {"model": ValidationErrorResponse, "description": "Invalid entity_type"},
        403: {"model": ForbiddenErrorResponse, "description": "Admin access required"},
        500: {"model": InternalServerErrorResponse, "description": "Internal server error"},
    },
)
async def get_entity_history(
    entity_type: str,
    entity_id: str,
    limit: int = Query(50, ge=1, le=200, description="Maximum records to return"),
    current_user: Dict[str, Any] = Depends(get_current_user_dict),
):
    """
    Get audit history for a specific entity.

    **Admin only** - Returns all audit events for a document, user, folder, or organization.

    Useful for:
    - Viewing all changes to a document
    - Tracking user modifications
    - Debugging folder operations
    """
    # Admin only check
    if not _is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required to view entity history",
        )

    try:
        # Validate entity type
        try:
            entity_type_enum = AuditEntityType(entity_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid entity_type: {entity_type}. Must be one of: {[e.value for e in AuditEntityType]}",
            )

        result = await audit_service.get_entity_history(
            org_id=current_user["org_id"],
            entity_type=entity_type_enum,
            entity_id=entity_id,
            limit=limit,
        )

        logger.debug(
            "Entity history retrieved",
            org_id=current_user["org_id"],
            entity_type=entity_type,
            entity_id=entity_id,
            count=len(result),
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error getting entity history",
            org_id=current_user["org_id"],
            entity_type=entity_type,
            entity_id=entity_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve entity history",
        )
