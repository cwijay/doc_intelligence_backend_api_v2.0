"""
Debug endpoints for troubleshooting authentication and database issues.
These endpoints should only be enabled in development/staging environments.
"""

import os
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, status, Query, Depends
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.firebase_client import firebase_manager, get_collection
from app.core.logging import get_service_logger
from app.services.user_service import user_service
from app.services.org_service import organization_service
from google.cloud.firestore import FieldFilter

logger = get_service_logger("debug")

router = APIRouter(
    prefix="/debug",
    tags=["🔧 Debug"],
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


class FirestoreStatusResponse(BaseModel):
    """Response for Firestore status check."""
    initialized: bool = Field(..., description="Whether Firebase is initialized")
    can_connect: bool = Field(..., description="Whether we can connect to Firestore")
    organizations_count: Optional[int] = Field(None, description="Number of organizations")
    users_count: Optional[int] = Field(None, description="Total number of users")
    error: Optional[str] = Field(None, description="Error message if any")


def check_debug_access():
    """Check if debug endpoints are accessible."""
    if settings.ENVIRONMENT == "production":
        # Allow debug in production only if explicitly enabled
        if not os.environ.get("ENABLE_DEBUG_ENDPOINTS", "").lower() == "true":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Debug endpoints not available in production"
            )


@router.get(
    "/firestore-status",
    response_model=FirestoreStatusResponse,
    summary="🔍 Check Firestore Connection Status",
    description="Check if Firebase/Firestore is properly initialized and accessible."
)
async def check_firestore_status(
    _: None = Depends(check_debug_access)
) -> FirestoreStatusResponse:
    """Check Firestore connection and basic functionality."""
    try:
        logger.info("Checking Firestore status")
        
        # Check initialization
        initialized = firebase_manager.is_initialized
        
        if not initialized:
            return FirestoreStatusResponse(
                initialized=False,
                can_connect=False,
                error="Firebase not initialized"
            )
        
        # Try to connect and count organizations
        try:
            orgs_collection = get_collection("organizations")
            orgs_query = orgs_collection.where(filter=FieldFilter("is_active", "==", True))
            orgs_docs = orgs_query.stream()
            
            org_count = 0
            total_users = 0
            
            async for org_doc in orgs_docs:
                org_count += 1
                org_id = org_doc.id
                
                # Count users in this organization
                try:
                    users_collection = get_collection("users") 
                    users_query = users_collection.where(filter=FieldFilter("org_id", "==", org_id))
                    users_docs = users_query.stream()
                    
                    async for user_doc in users_docs:
                        total_users += 1
                except Exception as user_error:
                    logger.warning(f"Error counting users in org {org_id}: {user_error}")
            
            return FirestoreStatusResponse(
                initialized=True,
                can_connect=True,
                organizations_count=org_count,
                users_count=total_users
            )
            
        except Exception as e:
            return FirestoreStatusResponse(
                initialized=True,
                can_connect=False,
                error=f"Connection failed: {str(e)}"
            )
    
    except Exception as e:
        logger.error(f"Error checking Firestore status: {str(e)}")
        return FirestoreStatusResponse(
            initialized=False,
            can_connect=False,
            error=str(e)
        )


@router.get(
    "/user-exists/{email}",
    response_model=UserExistsResponse,
    summary="👤 Check User Existence",
    description="Check if a user exists in the database across all organizations."
)
async def check_user_exists(
    email: str,
    _: None = Depends(check_debug_access)
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
                is_active=user.is_active
            )
        else:
            return UserExistsResponse(
                email=email,
                exists=False
            )
    
    except Exception as e:
        logger.error(f"Error checking user existence: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error checking user: {str(e)}"
        )


@router.get(
    "/organizations",
    response_model=DebugResponse,
    summary="🏢 List Organizations",
    description="List all organizations in the database for debugging."
)
async def list_organizations_debug(
    _: None = Depends(check_debug_access)
) -> DebugResponse:
    """List all organizations for debugging."""
    try:
        logger.info("Listing organizations for debug")
        
        from app.models.schemas import PaginationParams
        pagination = PaginationParams(page=1, per_page=50)
        
        result = await organization_service.list_organizations(pagination)
        
        org_data = []
        for org in result.organizations:
            org_data.append({
                "id": org.id,
                "name": org.name,
                "domain": org.domain,
                "plan_type": org.plan_type,
                "is_active": org.is_active,
                "created_at": org.created_at.isoformat() if org.created_at else None
            })
        
        return DebugResponse(
            success=True,
            message=f"Found {len(org_data)} organizations",
            data={
                "organizations": org_data,
                "total": result.total
            }
        )
    
    except Exception as e:
        logger.error(f"Error listing organizations: {str(e)}")
        return DebugResponse(
            success=False,
            message=f"Error: {str(e)}"
        )


@router.get(
    "/users",
    response_model=DebugResponse,
    summary="👥 List Users",
    description="List users from a specific organization for debugging."
)
async def list_users_debug(
    org_id: str = Query(..., description="Organization ID"),
    limit: int = Query(10, description="Maximum number of users to return"),
    _: None = Depends(check_debug_access)
) -> DebugResponse:
    """List users from an organization for debugging."""
    try:
        logger.info(f"Listing users for debug: org_id={org_id}")
        
        from app.models.schemas import PaginationParams
        pagination = PaginationParams(page=1, per_page=limit)
        
        result = await user_service.list_users(org_id, pagination)
        
        user_data = []
        for user in result.users:
            user_data.append({
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "username": user.username,
                "role": user.role,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat() if user.created_at else None
            })
        
        return DebugResponse(
            success=True,
            message=f"Found {len(user_data)} users in organization {org_id}",
            data={
                "users": user_data,
                "total": result.total
            }
        )
    
    except Exception as e:
        logger.error(f"Error listing users: {str(e)}")
        return DebugResponse(
            success=False,
            message=f"Error: {str(e)}"
        )


@router.post(
    "/test-password",
    response_model=DebugResponse,
    summary="🔐 Test Password Verification",
    description="Test password verification for debugging authentication issues."
)
async def test_password_verification(
    email: str = Query(..., description="User email"),
    password: str = Query(..., description="Password to test"),
    _: None = Depends(check_debug_access)
) -> DebugResponse:
    """Test password verification for a user."""
    try:
        logger.info(f"Testing password verification for: {email}")
        
        # Find user
        user = await user_service._get_user_by_email_simple(email.lower())
        
        if not user:
            return DebugResponse(
                success=False,
                message="User not found",
                data={"email": email}
            )
        
        # Test password
        password_valid = await user_service.verify_password(password, user.password_hash)
        
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
                "hash_length": len(user.password_hash) if user.password_hash else 0
            }
        )
    
    except Exception as e:
        logger.error(f"Error testing password: {str(e)}")
        return DebugResponse(
            success=False,
            message=f"Error: {str(e)}"
        )


@router.get(
    "/environment",
    response_model=DebugResponse,
    summary="🌍 Environment Information",
    description="Get environment and configuration information."
)
async def get_environment_info(
    _: None = Depends(check_debug_access)
) -> DebugResponse:
    """Get environment information for debugging."""
    try:
        env_info = {
            "environment": settings.ENVIRONMENT,
            "debug": settings.DEBUG,
            "firebase_project_id": settings.FIREBASE_PROJECT_ID,
            "gcp_project_id": settings.GCP_PROJECT_ID,
            "cors_origins": settings.resolved_cors_origins,
            "log_level": settings.LOG_LEVEL,
            "jwt_algorithm": settings.JWT_ALGORITHM,
            "access_token_expire_minutes": settings.access_token_expire_minutes,
            "python_version": os.sys.version,
            "firebase_initialized": firebase_manager.is_initialized
        }
        
        return DebugResponse(
            success=True,
            message="Environment information retrieved",
            data=env_info
        )
    
    except Exception as e:
        logger.error(f"Error getting environment info: {str(e)}")
        return DebugResponse(
            success=False,
            message=f"Error: {str(e)}"
        )