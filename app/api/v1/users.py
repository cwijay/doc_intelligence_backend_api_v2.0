from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Query, Path, status
from app.core.logging import get_service_logger
from app.services.user_service import (
    user_service,
    UserNotFoundError,
    UserAlreadyExistsError,
    OrganizationNotFoundError,
)
from app.models.schemas import (
    UserCreateRequest,
    UserUpdateRequest,
    UserResponse,
    UserList,
    UserDeleteResponse,
    PaginationParams,
    UserFilters,
    UserRole,
    UserStatsResponse,
    NotFoundErrorResponse,
    ConflictErrorResponse,
    ValidationErrorResponse,
    InternalServerErrorResponse,
)

logger = get_service_logger("user_api")

router = APIRouter()


@router.post(
    "/organizations/{org_id}/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create User",
    operation_id="createUser",
    description="""Create a new user within the specified organization.

**Authentication Required:** Yes (Admin role recommended)

**Validation Rules:**
- Email must be valid and unique within the organization
- Username must be unique within organization (3-50 chars, alphanumeric + underscore/hyphen)
- Password minimum 8 characters with complexity requirements
- Full name 2-100 characters

**Example Request:**
```json
{
  "email": "john.doe@example.com",
  "password": "SecureP@ss123!",
  "username": "johndoe",
  "full_name": "John Doe",
  "role": "user"
}
```""",
    responses={
        201: {"description": "User created successfully"},
        404: {"model": NotFoundErrorResponse, "description": "Organization not found"},
        409: {"model": ConflictErrorResponse, "description": "User with email or username already exists"},
        422: {"model": ValidationErrorResponse, "description": "Validation error"},
        500: {"model": InternalServerErrorResponse, "description": "Internal server error"},
    },
)
async def create_user(
    org_id: str = Path(..., description="Organization ID"),
    user: UserCreateRequest = ...,
) -> UserResponse:
    """
    Create a new user in the organization.

    - **org_id**: Organization ID where user will be created
    - **email**: User email (unique within organization)
    - **username**: Username (unique within organization)
    - **password**: Password (min 8 chars with complexity requirements)
    - **full_name**: User's full name
    - **role**: User role (admin/user/viewer)
    """
    try:
        logger.info(
            "Creating user", org_id=org_id, email=user.email, username=user.username
        )

        result = await user_service.create_user(org_id, user)

        logger.info(
            "User created successfully",
            org_id=org_id,
            user_id=str(result.id),
            email=result.email,
        )

        return result

    except OrganizationNotFoundError as e:
        logger.warning(
            "User creation failed - organization not found", org_id=org_id, error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization with ID {org_id} not found",
        )
    except UserAlreadyExistsError as e:
        logger.warning(
            "User creation failed - user exists",
            org_id=org_id,
            email=user.email,
            username=user.username,
            error=str(e),
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logger.error(
            "Failed to create user", org_id=org_id, email=user.email, error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while creating user",
        )


@router.get(
    "/organizations/{org_id}/users/{user_id}",
    response_model=UserResponse,
    summary="Get User",
    operation_id="getUser",
    description="""Retrieve a specific user by their ID within the organization.

**Authentication Required:** Yes

Returns the user's profile information including email, username, full name, role, and timestamps.""",
    responses={
        200: {"description": "User retrieved successfully"},
        404: {"model": NotFoundErrorResponse, "description": "Organization or user not found"},
        500: {"model": InternalServerErrorResponse, "description": "Internal server error"},
    },
)
async def get_user(
    org_id: str = Path(..., description="Organization ID"),
    user_id: str = Path(..., description="User ID"),
) -> UserResponse:
    """
    Get user by ID within organization.

    - **org_id**: Organization ID
    - **user_id**: ID of the user to retrieve
    """
    try:
        logger.debug("Retrieving user", org_id=org_id, user_id=user_id)

        result = await user_service.get_user(org_id, user_id)

        return result

    except OrganizationNotFoundError:
        logger.warning(
            "User retrieval failed - organization not found",
            org_id=org_id,
            user_id=user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization with ID {org_id} not found",
        )
    except UserNotFoundError:
        logger.warning("User not found", org_id=org_id, user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found in organization {org_id}",
        )
    except Exception as e:
        logger.error(
            "Failed to retrieve user", org_id=org_id, user_id=user_id, error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving user",
        )


@router.put(
    "/organizations/{org_id}/users/{user_id}",
    response_model=UserResponse,
    summary="Update User",
    operation_id="updateUser",
    description="""Update an existing user's details within the organization.

**Authentication Required:** Yes (Admin role or self-update)

Only provided fields will be updated. All fields are optional.

**Example Request:**
```json
{
  "full_name": "John D. Doe",
  "role": "admin"
}
```""",
    responses={
        200: {"description": "User updated successfully"},
        404: {"model": NotFoundErrorResponse, "description": "Organization or user not found"},
        409: {"model": ConflictErrorResponse, "description": "Email or username already taken"},
        422: {"model": ValidationErrorResponse, "description": "Validation error"},
        500: {"model": InternalServerErrorResponse, "description": "Internal server error"},
    },
)
async def update_user(
    org_id: str = Path(..., description="Organization ID"),
    user_id: str = Path(..., description="User ID"),
    user: UserUpdateRequest = ...,
) -> UserResponse:
    """
    Update user within organization.

    - **org_id**: Organization ID
    - **user_id**: ID of the user to update
    - **email**: New email (optional, unique within org)
    - **username**: New username (optional, unique within org)
    - **password**: New password (optional)
    - **full_name**: New full name (optional)
    - **role**: New role (optional)
    """
    try:
        logger.info("Updating user", org_id=org_id, user_id=user_id)

        result = await user_service.update_user(org_id, user_id, user)

        logger.info(
            "User updated successfully",
            org_id=org_id,
            user_id=user_id,
            email=result.email,
        )

        return result

    except OrganizationNotFoundError:
        logger.warning(
            "User update failed - organization not found",
            org_id=org_id,
            user_id=user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization with ID {org_id} not found",
        )
    except UserNotFoundError:
        logger.warning(
            "User update failed - user not found", org_id=org_id, user_id=user_id
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found in organization {org_id}",
        )
    except UserAlreadyExistsError as e:
        logger.warning(
            "User update failed - conflict",
            org_id=org_id,
            user_id=user_id,
            error=str(e),
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logger.error(
            "Failed to update user", org_id=org_id, user_id=user_id, error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while updating user",
        )


@router.get(
    "/organizations/{org_id}/users",
    response_model=UserList,
    summary="List Users",
    operation_id="listUsers",
    description="""Retrieve a paginated list of users within the organization with optional filtering.

**Authentication Required:** Yes

**Query Parameters:**
- `page`: Page number (starts from 1)
- `per_page`: Items per page (max 100)
- `email`: Filter by email (partial match)
- `username`: Filter by username (partial match)
- `full_name`: Filter by full name (partial match)
- `role`: Filter by role (admin/user/viewer)
- `is_active`: Filter by active status (true/false)

**Example:** `/organizations/org_123/users?page=1&per_page=20&role=user`""",
    responses={
        200: {"description": "Users retrieved successfully"},
        404: {"model": NotFoundErrorResponse, "description": "Organization not found"},
        500: {"model": InternalServerErrorResponse, "description": "Internal server error"},
    },
)
async def list_users(
    org_id: str = Path(..., description="Organization ID"),
    page: int = Query(default=1, ge=1, description="Page number (starts from 1)"),
    per_page: int = Query(
        default=20, ge=1, le=100, description="Items per page (max 100)"
    ),
    email: str = Query(default=None, description="Filter by email (partial match)"),
    username: str = Query(
        default=None, description="Filter by username (partial match)"
    ),
    full_name: str = Query(
        default=None, description="Filter by full name (partial match)"
    ),
    role: UserRole = Query(default=None, description="Filter by role"),
    is_active: bool = Query(default=None, description="Filter by active status"),
) -> UserList:
    """
    List users in organization with pagination and filtering.

    Query Parameters:
    - **org_id**: Organization ID
    - **page**: Page number (default: 1)
    - **per_page**: Items per page (default: 20, max: 100)
    - **email**: Filter by email (partial match)
    - **username**: Filter by username (partial match)
    - **full_name**: Filter by full name (partial match)
    - **role**: Filter by role (admin/user/viewer)
    - **is_active**: Filter by active status (true/false)
    """
    try:
        # Create pagination parameters
        pagination = PaginationParams(page=page, per_page=per_page)

        # Create filters (only include non-None values)
        filters = UserFilters(
            email=email,
            username=username,
            full_name=full_name,
            role=role,
            is_active=is_active,
        )

        logger.debug(
            "Listing users",
            org_id=org_id,
            page=page,
            per_page=per_page,
            filters=filters.model_dump(exclude_none=True),
        )

        result = await user_service.list_users(org_id, pagination, filters)

        logger.debug(
            "Users listed successfully",
            org_id=org_id,
            count=len(result.users),
            total=result.total,
        )

        return result

    except OrganizationNotFoundError:
        logger.warning("User list failed - organization not found", org_id=org_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization with ID {org_id} not found",
        )
    except Exception as e:
        logger.error("Failed to list users", org_id=org_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while listing users",
        )


@router.delete(
    "/organizations/{org_id}/users/{user_id}",
    response_model=UserDeleteResponse,
    summary="Delete User",
    operation_id="deleteUser",
    description="""Soft delete a user by setting them as inactive within the organization.

**Authentication Required:** Yes (Admin role)

**Important:** This performs a soft delete by marking the user as inactive.
The user data is preserved but will not appear in normal queries.
This operation cannot be undone via API.""",
    responses={
        200: {"description": "User deleted successfully"},
        404: {"model": NotFoundErrorResponse, "description": "Organization or user not found"},
        500: {"model": InternalServerErrorResponse, "description": "Internal server error"},
    },
)
async def delete_user(
    org_id: str = Path(..., description="Organization ID"),
    user_id: str = Path(..., description="User ID"),
) -> UserDeleteResponse:
    """
    Soft delete user within organization.

    - **org_id**: Organization ID
    - **user_id**: ID of the user to delete

    Note: This performs a soft delete by marking the user as inactive.
    The user data is preserved but will not appear in normal queries.
    """
    try:
        logger.info("Deleting user", org_id=org_id, user_id=user_id)

        success = await user_service.delete_user(org_id, user_id)

        if success:
            logger.info("User deleted successfully", org_id=org_id, user_id=user_id)
            return UserDeleteResponse(
                success=True, message=f"User {user_id} has been deleted successfully"
            )
        else:
            logger.error(
                "User deletion failed unexpectedly", org_id=org_id, user_id=user_id
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete user",
            )

    except OrganizationNotFoundError:
        logger.warning(
            "User deletion failed - organization not found",
            org_id=org_id,
            user_id=user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization with ID {org_id} not found",
        )
    except UserNotFoundError:
        logger.warning(
            "User deletion failed - user not found", org_id=org_id, user_id=user_id
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found in organization {org_id}",
        )
    except Exception as e:
        logger.error(
            "Failed to delete user", org_id=org_id, user_id=user_id, error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while deleting user",
        )


@router.get(
    "/organizations/{org_id}/users/search/by-email/{email}",
    response_model=UserResponse,
    summary="Get User by Email",
    operation_id="getUserByEmail",
    description="""Retrieve a user by their email address within the organization.

**Authentication Required:** Yes

Searches for an exact email match (case-insensitive).""",
    responses={
        200: {"description": "User retrieved successfully"},
        404: {"model": NotFoundErrorResponse, "description": "Organization or user not found"},
        500: {"model": InternalServerErrorResponse, "description": "Internal server error"},
    },
)
async def get_user_by_email(
    org_id: str = Path(..., description="Organization ID"),
    email: str = Path(..., description="User email address"),
) -> UserResponse:
    """
    Get user by email within organization.

    - **org_id**: Organization ID
    - **email**: User email address to search for
    """
    try:
        logger.debug("Retrieving user by email", org_id=org_id, email=email)

        result = await user_service.get_user_by_email(org_id, email)

        if result is None:
            logger.warning("User not found by email", org_id=org_id, email=email)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with email '{email}' not found in organization {org_id}",
            )

        return result

    except HTTPException:
        raise
    except OrganizationNotFoundError:
        logger.warning(
            "User search by email failed - organization not found",
            org_id=org_id,
            email=email,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization with ID {org_id} not found",
        )
    except Exception as e:
        logger.error(
            "Failed to retrieve user by email", org_id=org_id, email=email, error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving user",
        )


@router.get(
    "/organizations/{org_id}/users/search/by-username/{username}",
    response_model=UserResponse,
    summary="Get User by Username",
    operation_id="getUserByUsername",
    description="""Retrieve a user by their username within the organization.

**Authentication Required:** Yes

Searches for an exact username match (case-insensitive).""",
    responses={
        200: {"description": "User retrieved successfully"},
        404: {"model": NotFoundErrorResponse, "description": "Organization or user not found"},
        500: {"model": InternalServerErrorResponse, "description": "Internal server error"},
    },
)
async def get_user_by_username(
    org_id: str = Path(..., description="Organization ID"),
    username: str = Path(..., description="Username"),
) -> UserResponse:
    """
    Get user by username within organization.

    - **org_id**: Organization ID
    - **username**: Username to search for
    """
    try:
        logger.debug("Retrieving user by username", org_id=org_id, username=username)

        result = await user_service.get_user_by_username(org_id, username)

        if result is None:
            logger.warning(
                "User not found by username", org_id=org_id, username=username
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with username '{username}' not found in organization {org_id}",
            )

        return result

    except HTTPException:
        raise
    except OrganizationNotFoundError:
        logger.warning(
            "User search by username failed - organization not found",
            org_id=org_id,
            username=username,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization with ID {org_id} not found",
        )
    except Exception as e:
        logger.error(
            "Failed to retrieve user by username",
            org_id=org_id,
            username=username,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving user",
        )


@router.get(
    "/organizations/{org_id}/users/stats/summary",
    response_model=UserStatsResponse,
    summary="Get User Statistics",
    operation_id="getUserStats",
    description="""Get summary statistics about users in the organization.

**Authentication Required:** Yes (Admin role recommended)

Returns counts by role, active/inactive status, and recent activity metrics.""",
    responses={
        200: {"description": "Statistics retrieved successfully"},
        404: {"model": NotFoundErrorResponse, "description": "Organization not found"},
        500: {"model": InternalServerErrorResponse, "description": "Internal server error"},
    },
)
async def get_user_stats(
    org_id: str = Path(..., description="Organization ID")
) -> UserStatsResponse:
    """
    Get user statistics for organization.

    Returns counts by role, active/inactive status, and other metrics.

    - **org_id**: Organization ID
    """
    try:
        logger.debug("Retrieving user statistics", org_id=org_id)

        # Get all users in organization to calculate stats
        all_users = await user_service.list_users(
            org_id,
            PaginationParams(page=1, per_page=1000),
            UserFilters(is_active=None),  # Include inactive
        )

        # Calculate statistics
        total_count = all_users.total
        active_count = sum(1 for user in all_users.users if user.is_active)
        inactive_count = total_count - active_count

        # Count by role
        role_counts = {
            "admin": sum(
                1
                for user in all_users.users
                if user.role == UserRole.ADMIN and user.is_active
            ),
            "user": sum(
                1
                for user in all_users.users
                if user.role == UserRole.USER and user.is_active
            ),
            "viewer": sum(
                1
                for user in all_users.users
                if user.role == UserRole.VIEWER and user.is_active
            ),
        }

        # Count users with recent activity (logged in recently)
        from datetime import datetime, timedelta, timezone

        recent_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        recent_activity_count = 0
        for user in all_users.users:
            if user.is_active and user.last_login is not None:
                # Handle potential string datetime values
                if isinstance(user.last_login, str):
                    try:
                        user_last_login = datetime.fromisoformat(user.last_login)
                    except (ValueError, TypeError):
                        continue  # Skip invalid dates
                else:
                    user_last_login = user.last_login

                if user_last_login > recent_cutoff:
                    recent_activity_count += 1

        stats = UserStatsResponse(
            total_users=total_count,
            active_users=active_count,
            inactive_users=inactive_count,
            users_with_recent_activity=recent_activity_count,
            role_distribution=role_counts,
            privileged_users=role_counts["admin"] + role_counts["user"],
        )

        logger.debug("User statistics retrieved", org_id=org_id, stats=stats.model_dump())

        return stats

    except OrganizationNotFoundError:
        logger.warning("User stats failed - organization not found", org_id=org_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization with ID {org_id} not found",
        )
    except Exception as e:
        logger.error("Failed to retrieve user statistics", org_id=org_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving statistics",
        )
