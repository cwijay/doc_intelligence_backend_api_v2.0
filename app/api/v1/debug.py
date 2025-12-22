"""
Debug endpoints for troubleshooting authentication and database issues.
These endpoints should only be enabled in development/staging environments.
"""

import sys
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, status, Query, Depends
from pydantic import BaseModel, Field

from sqlalchemy import select, func

from app.core.config import settings
from biz2bricks_core import db, OrganizationModel, UserModel
from app.core.logging import get_service_logger
from app.services.user_service import user_service
from app.services.org_service import organization_service

logger = get_service_logger("debug")

router = APIRouter(
    prefix="/debug",
    tags=["Debug"],
    responses={404: {"description": "Not found"}},
)


class DebugResponse(BaseModel):
    """Base debug response model."""

    success: bool = Field(..., description="Whether the operation was successful")
    message: str = Field(..., description="Response message")
    data: Optional[Dict[str, Any]] = Field(None, description="Response data")


class UserExistsResponse(BaseModel):
    """Response for user existence check."""

    email: str = Field(..., description="Email checked")
    exists: bool = Field(..., description="Whether user exists")
    user_id: Optional[str] = Field(None, description="User ID if found")
    org_id: Optional[str] = Field(None, description="Organization ID if found")
    org_name: Optional[str] = Field(None, description="Organization name if found")
    is_active: Optional[bool] = Field(None, description="Whether user is active")


class DatabaseStatusResponse(BaseModel):
    """Response for database status check."""

    initialized: bool = Field(..., description="Whether database is initialized")
    can_connect: bool = Field(..., description="Whether we can connect to database")
    organizations_count: Optional[int] = Field(
        None, description="Number of organizations"
    )
    users_count: Optional[int] = Field(None, description="Total number of users")
    error: Optional[str] = Field(None, description="Error message if any")


def check_debug_access():
    """Check if debug endpoints are accessible.

    SECURITY: Debug endpoints are ONLY available in development mode.
    No override is allowed to prevent accidental exposure in production.
    """
    if not settings.is_development:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )


@router.get(
    "/database-status",
    response_model=DatabaseStatusResponse,
    summary="Check Database Connection Status",
    description="Check if PostgreSQL is properly initialized and accessible.",
)
async def check_database_status(
    _: None = Depends(check_debug_access),
) -> DatabaseStatusResponse:
    """Check database connection and basic functionality."""
    try:
        logger.info("Checking database status")

        # Check connection
        can_connect = await db.test_connection()

        if not can_connect:
            return DatabaseStatusResponse(
                initialized=False, can_connect=False, error="Database connection failed"
            )

        # Count organizations and users
        try:
            async with db.session() as session:
                # Count organizations
                org_count_result = await session.execute(
                    select(func.count(OrganizationModel.id)).where(
                        OrganizationModel.is_active == True
                    )
                )
                org_count = org_count_result.scalar() or 0

                # Count users
                user_count_result = await session.execute(
                    select(func.count(UserModel.id)).where(UserModel.is_active == True)
                )
                user_count = user_count_result.scalar() or 0

                return DatabaseStatusResponse(
                    initialized=True,
                    can_connect=True,
                    organizations_count=org_count,
                    users_count=user_count,
                )

        except Exception as e:
            return DatabaseStatusResponse(
                initialized=True,
                can_connect=False,
                error=f"Query failed: {str(e)}",
            )

    except Exception as e:
        logger.error(f"Error checking database status: {str(e)}")
        return DatabaseStatusResponse(
            initialized=False, can_connect=False, error=str(e)
        )


@router.get(
    "/user-exists/{email}",
    response_model=UserExistsResponse,
    summary="Check User Existence",
    description="Check if a user exists in the database across all organizations.",
)
async def check_user_exists(
    email: str, _: None = Depends(check_debug_access)
) -> UserExistsResponse:
    """Check if a user exists in the database."""
    try:
        logger.info(f"Checking if user exists: {email}")

        # Use the same method as authentication
        user = await user_service._get_user_by_email_simple(email.lower())

        if user:
            # Get organization name
            org_name = "unknown"
            try:
                org = await organization_service.get_organization(user.org_id)
                org_name = org.name
            except Exception:
                pass

            return UserExistsResponse(
                email=email,
                exists=True,
                user_id=user.id,
                org_id=user.org_id,
                org_name=org_name,
                is_active=user.is_active,
            )
        else:
            return UserExistsResponse(email=email, exists=False)

    except Exception as e:
        logger.error(f"Error checking user existence: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error checking user: {str(e)}",
        )


@router.get(
    "/organizations",
    response_model=DebugResponse,
    summary="List Organizations",
    description="List all organizations in the database for debugging.",
)
async def list_organizations_debug(
    _: None = Depends(check_debug_access),
) -> DebugResponse:
    """List all organizations for debugging."""
    try:
        logger.info("Listing organizations for debug")

        from app.models.schemas import PaginationParams

        pagination = PaginationParams(page=1, per_page=50)

        result = await organization_service.list_organizations(pagination)

        org_data = []
        for org in result.organizations:
            org_data.append(
                {
                    "id": org.id,
                    "name": org.name,
                    "domain": org.domain,
                    "plan_type": org.plan_type,
                    "is_active": org.is_active,
                    "created_at": (
                        org.created_at.isoformat() if org.created_at else None
                    ),
                }
            )

        return DebugResponse(
            success=True,
            message=f"Found {len(org_data)} organizations",
            data={"organizations": org_data, "total": result.total},
        )

    except Exception as e:
        logger.error(f"Error listing organizations: {str(e)}")
        return DebugResponse(success=False, message=f"Error: {str(e)}")


@router.get(
    "/users",
    response_model=DebugResponse,
    summary="List Users",
    description="List users from a specific organization for debugging.",
)
async def list_users_debug(
    org_id: str = Query(..., description="Organization ID"),
    limit: int = Query(10, description="Maximum number of users to return"),
    _: None = Depends(check_debug_access),
) -> DebugResponse:
    """List users from an organization for debugging."""
    try:
        logger.info(f"Listing users for debug: org_id={org_id}")

        from app.models.schemas import PaginationParams

        pagination = PaginationParams(page=1, per_page=limit)

        result = await user_service.list_users(org_id, pagination)

        user_data = []
        for user in result.users:
            user_data.append(
                {
                    "id": user.id,
                    "email": user.email,
                    "full_name": user.full_name,
                    "username": user.username,
                    "role": user.role,
                    "is_active": user.is_active,
                    "created_at": (
                        user.created_at.isoformat() if user.created_at else None
                    ),
                }
            )

        return DebugResponse(
            success=True,
            message=f"Found {len(user_data)} users in organization {org_id}",
            data={"users": user_data, "total": result.total},
        )

    except Exception as e:
        logger.error(f"Error listing users: {str(e)}")
        return DebugResponse(success=False, message=f"Error: {str(e)}")


@router.post(
    "/test-password",
    response_model=DebugResponse,
    summary="Test Password Verification",
    description="Test password verification for debugging authentication issues.",
)
async def test_password_verification(
    email: str = Query(..., description="User email"),
    password: str = Query(..., description="Password to test"),
    _: None = Depends(check_debug_access),
) -> DebugResponse:
    """Test password verification for a user."""
    try:
        logger.info(f"Testing password verification for: {email}")

        # Find user
        user = await user_service._get_user_by_email_simple(email.lower())

        if not user:
            return DebugResponse(
                success=False, message="User not found", data={"email": email}
            )

        # Test password
        password_valid = await user_service.verify_password(
            password, user.password_hash
        )

        return DebugResponse(
            success=True,
            message=f"Password verification result: {'valid' if password_valid else 'invalid'}",
            data={
                "email": email,
                "user_id": user.id,
                "org_id": user.org_id,
                "password_valid": password_valid,
                "user_active": user.is_active,
                "has_password_hash": bool(user.password_hash),
                "hash_length": len(user.password_hash) if user.password_hash else 0,
            },
        )

    except Exception as e:
        logger.error(f"Error testing password: {str(e)}")
        return DebugResponse(success=False, message=f"Error: {str(e)}")


@router.get(
    "/environment",
    response_model=DebugResponse,
    summary="Environment Information",
    description="Get environment and configuration information.",
)
async def get_environment_info(_: None = Depends(check_debug_access)) -> DebugResponse:
    """Get environment information for debugging."""
    try:
        db_connected = await db.test_connection()

        env_info = {
            "environment": settings.ENVIRONMENT,
            "debug": settings.DEBUG,
            "gcp_project_id": settings.GCP_PROJECT_ID,
            "database_connected": db_connected,
            "use_cloud_sql_connector": settings.USE_CLOUD_SQL_CONNECTOR,
            "cors_origins": settings.resolved_cors_origins,
            "log_level": settings.LOG_LEVEL,
            "jwt_algorithm": settings.JWT_ALGORITHM,
            "access_token_expire_minutes": settings.access_token_expire_minutes,
            "python_version": sys.version,
        }

        return DebugResponse(
            success=True, message="Environment information retrieved", data=env_info
        )

    except Exception as e:
        logger.error(f"Error getting environment info: {str(e)}")
        return DebugResponse(success=False, message=f"Error: {str(e)}")
