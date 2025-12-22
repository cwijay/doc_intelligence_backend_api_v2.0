from typing import Dict, Any, Optional
import asyncio

from fastapi import APIRouter, HTTPException, status, Depends, Request
from pydantic import BaseModel, Field, field_validator

from app.core.logging import get_service_logger
from biz2bricks_core import AuditAction, AuditEntityType
from app.services.audit_service import audit_service
from app.core.simple_auth import (
    get_current_user_dict,
    validate_user_session,
    refresh_user_session,
)
from app.core.exceptions import (
    TokenExpiredError,
    TokenInvalidError,
    RefreshTokenExpiredError,
    RefreshTokenInvalidError,
)
from fastapi.security import HTTPBearer
from datetime import datetime, timezone
from app.services.auth_service import (
    auth_service,
    InvalidCredentialsError,
    UserInactiveError,
    OrganizationInactiveError,
    RegistrationError,
    InvitationError,
    AuthenticationError,
)
from app.services.org_service import organization_service
from app.models.organization import PlanType
from app.models.user import UserRole
from app.models.schemas import (
    OrganizationResponse,
    PaginationParams,
    OrganizationFilters,
)
from fastapi import Query, Path
from typing import List

logger = get_service_logger("auth_api")

router = APIRouter()


# Request/Response Models


class LoginRequest(BaseModel):
    """Request model for user login."""

    email: str = Field(..., description="User email address")
    password: str = Field(..., description="User password")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Validate email format."""
        v = v.strip().lower()
        if not v:
            raise ValueError("Email cannot be empty")
        return v


class RegisterRequest(BaseModel):
    """Request model for MVP user registration with organization selection."""

    email: str = Field(..., description="User email address")
    password: str = Field(..., description="User password (min 8 chars)")
    full_name: str = Field(..., description="User's full name")
    username: str = Field(..., description="Username")
    organization_id: str = Field(..., description="ID of the organization to join")

    # Legacy fields - kept for backwards compatibility but deprecated
    organization_name: Optional[str] = Field(
        None, description="Deprecated: use organization_id instead"
    )
    domain: Optional[str] = Field(None, description="Deprecated: not used in MVP")
    plan_type: Optional[PlanType] = Field(
        None, description="Deprecated: not used in MVP"
    )

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Validate email format."""
        v = v.strip().lower()
        if not v:
            raise ValueError("Email cannot be empty")
        return v

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username."""
        v = v.strip().lower()
        if not v:
            raise ValueError("Username cannot be empty")
        return v

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        """Validate full name."""
        v = v.strip()
        if not v:
            raise ValueError("Full name cannot be empty")
        return v

    @field_validator("organization_id")
    @classmethod
    def validate_organization_id(cls, v: str) -> str:
        """Validate organization ID."""
        v = v.strip()
        if not v:
            raise ValueError("Organization ID cannot be empty")
        return v


class InviteRegisterRequest(BaseModel):
    """Request model for user registration with invitation token."""

    invitation_token: str = Field(..., description="Valid invitation token")
    password: str = Field(..., description="User password (min 8 chars)")
    full_name: str = Field(..., description="User's full name")
    username: str = Field(..., description="Username")

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username."""
        v = v.strip().lower()
        if not v:
            raise ValueError("Username cannot be empty")
        return v

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        """Validate full name."""
        v = v.strip()
        if not v:
            raise ValueError("Full name cannot be empty")
        return v


class RefreshTokenRequest(BaseModel):
    """Request model for token refresh."""

    refresh_token: str = Field(..., description="Valid refresh token")


class AuthResponse(BaseModel):
    """Response model for authentication operations."""

    access_token: str = Field(..., description="Session access token")
    refresh_token: str = Field(..., description="Session refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Access token expiration in seconds")
    refresh_expires_in: int = Field(
        ..., description="Refresh token expiration in seconds"
    )
    access_token_expires_at: str = Field(
        ..., description="Access token expiration timestamp (ISO format)"
    )
    refresh_token_expires_at: str = Field(
        ..., description="Refresh token expiration timestamp (ISO format)"
    )
    user: Dict[str, Any] = Field(..., description="User information")


class AccessTokenResponse(BaseModel):
    """Response model for access token refresh."""

    access_token: str = Field(..., description="New session access token")
    refresh_token: Optional[str] = Field(
        None, description="New refresh token if rotation is enabled"
    )
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Access token expiration in seconds")
    access_token_expires_at: str = Field(
        ..., description="Access token expiration timestamp (ISO format)"
    )
    refresh_token_expires_at: Optional[str] = Field(
        None, description="Refresh token expiration timestamp if rotated"
    )
    refresh_token_expires_in: Optional[int] = Field(
        None, description="Refresh token expiration in seconds if rotated"
    )
    rotation_enabled: bool = Field(..., description="Whether token rotation is enabled")
    refresh_token_rotated: bool = Field(
        ..., description="Whether refresh token was rotated"
    )


class InvitationTokenResponse(BaseModel):
    """Response model for invitation token creation."""

    invitation_token: str = Field(..., description="Invitation token")
    expires_in_hours: int = Field(..., description="Token expiration in hours")


class LogoutResponse(BaseModel):
    """Response model for logout operation."""

    message: str = Field(..., description="Logout confirmation message")
    logged_out_at: str = Field(..., description="Logout timestamp")


class LogoutAllResponse(BaseModel):
    """Response model for logout-all operation."""

    message: str = Field(..., description="Logout confirmation message")
    sessions_invalidated: int = Field(..., description="Number of sessions invalidated")
    logged_out_at: str = Field(..., description="Logout timestamp")


# Authentication Endpoints


@router.post(
    "/login",
    response_model=AuthResponse,
    status_code=status.HTTP_200_OK,
    summary="🔐 User Login",
    operation_id="login",
    description="""Authenticate user with email and password using simple session-based authentication.
    
**Authentication Flow:**
1. Send email and password
2. Receive session token (UUID format)
3. Use token in `Authorization: Bearer <token>` header
4. Token expires after 24 hours

**Example Request:**
```json
{
  "email": "user@example.com",
  "password": "Password123!"
}
```

**Example Response:**
```json
{
  "access_token": "b9a85c75-15de-4a7b-b278-651eaf42383f",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": {
    "email": "user@example.com",
    "full_name": "John Doe",
    "role": "user",
    "org_name": "Google"
  }
}
```""",
    responses={
        200: {
            "description": "Login successful",
            "content": {
                "application/json": {
                    "examples": {
                        "successful_login": {
                            "summary": "Successful login",
                            "value": {
                                "access_token": "b9a85c75-15de-4a7b-b278-651eaf42383f",
                                "refresh_token": "b9a85c75-15de-4a7b-b278-651eaf42383f",
                                "token_type": "bearer",
                                "expires_in": 86400,
                                "refresh_expires_in": 86400,
                                "access_token_expires_at": "2025-08-16T10:12:27.931957",
                                "refresh_token_expires_at": "2025-08-16T10:12:27.931957",
                                "user": {
                                    "user_id": "jhYXgm0s4avwacnBSXH9",
                                    "email": "user@example.com",
                                    "full_name": "John Doe",
                                    "username": "johndoe",
                                    "role": "user",
                                    "org_id": "oJIChgDgktkF30dAPy2c",
                                    "org_name": "Google",
                                    "session_id": "b9a85c75-15de-4a7b-b278-651eaf42383f",
                                },
                            },
                        }
                    }
                }
            },
        },
        401: {
            "description": "Invalid credentials",
            "content": {
                "application/json": {"example": {"detail": "Invalid email or password"}}
            },
        },
        403: {
            "description": "User or organization inactive",
            "content": {
                "application/json": {
                    "examples": {
                        "user_inactive": {
                            "summary": "User account inactive",
                            "value": {"detail": "User account is inactive"},
                        },
                        "org_inactive": {
                            "summary": "Organization inactive",
                            "value": {"detail": "Organization is inactive"},
                        },
                    }
                }
            },
        },
    },
)
async def login(login_request: LoginRequest, request: Request) -> AuthResponse:
    """
    Authenticate user and return session token (MVP).

    Args:
        login_request: Login credentials
        request: FastAPI request object for audit context

    Returns:
        Authentication response with session token and user data

    Raises:
        HTTPException: If authentication fails
    """
    try:
        logger.info("Session-based login attempt", email=login_request.email)

        # Authenticate user and get user info
        access_token, refresh_token, user_data = await auth_service.authenticate_user(
            email=login_request.email, password=login_request.password
        )

        # For session-based auth, we'll create a simple session instead of using JWT
        from app.core.simple_auth import create_user_session

        session = create_user_session(
            user_id=user_data["user_id"],
            org_id=user_data["org_id"],
            email=user_data["email"],
            full_name=user_data["full_name"],
            username=user_data.get("username", user_data["email"].split("@")[0]),
            role=user_data["role"],
        )

        logger.info(
            "Session-based login successful",
            email=login_request.email,
            user_id=user_data["user_id"],
            session_id=session.session_id[:8] + "...",
        )

        # Audit logging for successful login (non-blocking)
        client_ip = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        asyncio.create_task(
            audit_service.log_event(
                org_id=user_data["org_id"],
                action=AuditAction.LOGIN,
                entity_type=AuditEntityType.USER,
                entity_id=user_data["user_id"],
                user_id=user_data["user_id"],
                details={
                    "email": user_data["email"],
                    "session_id": session.session_id,
                    "operation": "login",
                },
                ip_address=client_ip,
                session_id=session.session_id,
                user_agent=user_agent,
            )
        )

        # Return session tokens in AuthResponse format
        return AuthResponse(
            access_token=session.session_id,  # Session ID as access token
            refresh_token=session.refresh_token
            or session.session_id,  # Refresh token or fallback
            expires_in=session.time_until_expiry(),
            refresh_expires_in=(
                int(
                    (
                        session.refresh_expires_at - datetime.now(timezone.utc)
                    ).total_seconds()
                )
                if session.refresh_expires_at
                else session.time_until_expiry()
            ),
            access_token_expires_at=session.expires_at.isoformat(),
            refresh_token_expires_at=(
                session.refresh_expires_at.isoformat()
                if session.refresh_expires_at
                else session.expires_at.isoformat()
            ),
            user={
                "user_id": user_data["user_id"],
                "email": user_data["email"],
                "full_name": user_data["full_name"],
                "username": user_data.get("username", user_data["email"].split("@")[0]),
                "role": user_data["role"],
                "org_id": user_data["org_id"],
                "org_name": user_data.get("org_name", ""),
                "session_id": session.session_id,
            },
        )

    except InvalidCredentialsError:
        logger.warning("Login failed - invalid credentials", email=login_request.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    except UserInactiveError:
        logger.warning("Login failed - user inactive", email=login_request.email)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive"
        )
    except OrganizationInactiveError:
        logger.warning(
            "Login failed - organization inactive", email=login_request.email
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Organization is inactive"
        )
    except Exception as e:
        logger.error("Login error", email=login_request.email, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed due to server error",
        )


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="📝 User Registration",
    operation_id="register",
    description="""Register a new user by selecting an existing organization (MVP flow).
    
**Registration Flow:**
1. Get available organizations from `GET /api/v1/auth/organizations`
2. Select an organization ID
3. Submit registration with all required fields
4. Receive session token for immediate login

**Validation Rules:**
- Email must be valid and unique within organization
- Password minimum 8 characters
- Username must be unique within organization
- Organization ID must exist and be active

**Example Request:**
```json
{
  "email": "user@example.com",
  "password": "Password123!",
  "full_name": "John Doe",
  "username": "johndoe",
  "organization_id": "oJIChgDgktkF30dAPy2c"
}
```

**Example Response:**
```json
{
  "access_token": "d3098d62-e2e9-40e9-ae6c-70ba481ccaac",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": {
    "email": "user@example.com",
    "full_name": "John Doe",
    "username": "johndoe",
    "role": "user",
    "org_name": "Google"
  }
}
```""",
    responses={
        201: {
            "description": "Registration successful",
            "content": {
                "application/json": {
                    "examples": {
                        "successful_registration": {
                            "summary": "Successful registration",
                            "value": {
                                "access_token": "d3098d62-e2e9-40e9-ae6c-70ba481ccaac",
                                "refresh_token": "d3098d62-e2e9-40e9-ae6c-70ba481ccaac",
                                "token_type": "bearer",
                                "expires_in": 86400,
                                "refresh_expires_in": 86400,
                                "access_token_expires_at": "2025-08-16T10:12:18.775296",
                                "refresh_token_expires_at": "2025-08-16T10:12:18.775296",
                                "user": {
                                    "user_id": "jhYXgm0s4avwacnBSXH9",
                                    "email": "user@example.com",
                                    "full_name": "John Doe",
                                    "username": "johndoe",
                                    "role": "user",
                                    "org_id": "oJIChgDgktkF30dAPy2c",
                                    "org_name": "Google",
                                    "session_id": "d3098d62-e2e9-40e9-ae6c-70ba481ccaac",
                                },
                            },
                        }
                    }
                }
            },
        },
        400: {
            "description": "Validation error or user already exists",
            "content": {
                "application/json": {
                    "examples": {
                        "validation_error": {
                            "summary": "Validation failed",
                            "value": {"detail": "Invalid email format"},
                        },
                        "user_exists": {
                            "summary": "User already exists",
                            "value": {
                                "detail": "User with this email or username already exists in this organization"
                            },
                        },
                        "invalid_org": {
                            "summary": "Invalid organization",
                            "value": {"detail": "Invalid organization selected"},
                        },
                    }
                }
            },
        },
    },
)
async def register(request: RegisterRequest) -> AuthResponse:
    """
    Register a new user with organization selection (MVP).

    This is the simplified MVP registration flow where users select
    from existing organizations instead of creating new ones.

    Args:
        request: Registration details including organization_id

    Returns:
        Authentication response with session token and user data

    Raises:
        HTTPException: If registration fails
    """
    try:
        logger.info(
            "MVP registration attempt",
            email=request.email,
            org_id=request.organization_id,
        )

        # Use the new MVP registration method
        session_token, user_data = await auth_service.register_user_simple(
            email=request.email,
            password=request.password,
            full_name=request.full_name,
            username=request.username,
            organization_id=request.organization_id,
        )

        logger.info(
            "MVP registration successful",
            email=request.email,
            user_id=user_data["user_id"],
            org_id=user_data["org_id"],
        )

        # MVP uses session tokens - map to AuthResponse format for compatibility
        return AuthResponse(
            access_token=session_token,  # Session token instead of JWT
            refresh_token=session_token,  # Use same session token for both (MVP simplification)
            expires_in=86400,  # 24 hours in seconds
            refresh_expires_in=86400,  # Same as access for MVP
            access_token_expires_at=user_data["expires_at"],
            refresh_token_expires_at=user_data["expires_at"],
            user=user_data,
        )

    except RegistrationError as e:
        logger.warning("Registration failed", email=request.email, error=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Registration error", email=request.email, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed due to server error",
        )


@router.post(
    "/register/invite",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register user with invitation token",
    operation_id="registerWithInvitation",
    description="Register a new user using an invitation token. This allows team members to join existing organizations.",
)
async def register_with_invitation(request: InviteRegisterRequest) -> AuthResponse:
    """
    Register a new user using an invitation token.

    This allows team members to join existing organizations after
    receiving an invitation from an admin or user with permissions.

    Args:
        request: Invitation registration details

    Returns:
        Authentication response with tokens and user data

    Raises:
        HTTPException: If registration fails
    """
    try:
        logger.info(
            "Invitation registration attempt",
            token=request.invitation_token[:10] + "...",
        )

        access_token, refresh_token, user_data = (
            await auth_service.register_user_with_invitation(
                invitation_token=request.invitation_token,
                password=request.password,
                full_name=request.full_name,
                username=request.username,
            )
        )

        logger.info(
            "Invitation registration successful",
            email=user_data["email"],
            user_id=user_data["user_id"],
            org_id=user_data["org_id"],
        )

        return AuthResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=user_data["access_token_expires_in"],
            refresh_expires_in=user_data["refresh_token_expires_in"],
            access_token_expires_at=user_data["access_token_expires_at"],
            refresh_token_expires_at=user_data["refresh_token_expires_at"],
            user=user_data,
        )

    except InvitationError as e:
        logger.warning("Invitation registration failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except RegistrationError as e:
        logger.warning("Invitation registration failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Invitation registration error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed due to server error",
        )


@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh access token",
    operation_id="refreshAccessToken",
    description="Get a new access token using a valid refresh token.",
)
async def refresh_access_token(request: RefreshTokenRequest) -> AccessTokenResponse:
    """
    Refresh access token using a refresh token.

    Args:
        request: Refresh token request

    Returns:
        New access token response

    Raises:
        HTTPException: If refresh fails
    """
    try:
        logger.debug("Enterprise token refresh attempt")

        access_token, new_refresh_token, token_info = (
            await auth_service.refresh_access_token(request.refresh_token)
        )

        logger.debug(
            "Enterprise token refresh successful",
            rotation_enabled=token_info["rotation_enabled"],
            refresh_token_rotated=token_info["refresh_token_rotated"],
        )

        return AccessTokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            expires_in=token_info["access_token_expires_in"],
            access_token_expires_at=token_info["access_token_expires_at"],
            refresh_token_expires_at=token_info.get("refresh_token_expires_at"),
            refresh_token_expires_in=token_info.get("refresh_token_expires_in"),
            rotation_enabled=token_info["rotation_enabled"],
            refresh_token_rotated=token_info["refresh_token_rotated"],
        )

    except AuthenticationError as e:
        logger.warning("Enterprise token refresh failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    except Exception as e:
        logger.error("Enterprise token refresh error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed due to server error",
        )


# Bearer token security scheme for logout
security = HTTPBearer()


@router.post(
    "/logout",
    response_model=LogoutResponse,
    status_code=status.HTTP_200_OK,
    summary="Logout user",
    operation_id="logout",
    description="Logout user by invalidating their session token. Session will be invalid for future requests.",
)
async def logout(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user_dict),
) -> LogoutResponse:
    """
    Logout user by invalidating their session token.

    This endpoint invalidates the provided session token, making it invalid
    for future authenticated requests. The user will need to login again
    to get a new valid session.

    Args:
        request: FastAPI request object for audit context
        current_user: Current user info from session validation

    Returns:
        Logout confirmation message

    Raises:
        HTTPException: If logout fails or session is invalid
    """
    try:
        session_id = current_user.get("session_id")
        user_id = current_user.get("user_id")
        org_id = current_user.get("org_id")

        logger.info(
            "Logout request received",
            user_id=user_id,
            org_id=org_id,
            session_id=session_id[:8] + "..." if session_id else "unknown",
        )

        # Invalidate the session using simple auth
        from app.core.simple_auth import invalidate_user_session

        success = invalidate_user_session(session_id)
        if not success:
            logger.warning(
                "Failed to invalidate session - session not found",
                user_id=user_id,
                session_id=session_id[:8] + "..." if session_id else "unknown",
            )
            # Still return success since the goal (session invalid) is achieved

        logout_time = datetime.now(timezone.utc).isoformat()

        logger.info(
            "User logged out successfully",
            user_id=user_id,
            org_id=org_id,
            logged_out_at=logout_time,
        )

        # Audit logging for logout (non-blocking)
        client_ip = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        asyncio.create_task(
            audit_service.log_event(
                org_id=org_id,
                action=AuditAction.LOGOUT,
                entity_type=AuditEntityType.USER,
                entity_id=user_id,
                user_id=user_id,
                details={
                    "email": current_user.get("email"),
                    "session_id": session_id,
                    "operation": "logout",
                },
                ip_address=client_ip,
                session_id=session_id,
                user_agent=user_agent,
            )
        )

        return LogoutResponse(
            message="Successfully logged out", logged_out_at=logout_time
        )

    except Exception as e:
        logger.error("Logout error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed due to server error",
        )


@router.post(
    "/logout-all",
    response_model=LogoutAllResponse,
    status_code=status.HTTP_200_OK,
    summary="Logout from all devices",
    operation_id="logoutAllSessions",
    description="Security feature: Logout user from all devices by invalidating all their active sessions. Useful for security incidents.",
)
async def logout_all_sessions(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user_dict),
) -> LogoutAllResponse:
    """
    Logout user from all devices by invalidating all active sessions.

    This is a security feature that allows users to immediately
    invalidate all their active sessions across all devices. Useful when:
    - User suspects account compromise
    - Lost device with active session
    - Security policy requires session reset

    Args:
        request: FastAPI request object for audit context
        current_user: Current user info from session validation

    Returns:
        Logout confirmation with count of invalidated sessions

    Raises:
        HTTPException: If logout fails or session is invalid
    """
    try:
        user_id = current_user.get("user_id")
        org_id = current_user.get("org_id")
        session_id = current_user.get("session_id")

        logger.info(
            "🔒 LOGOUT-ALL request received - Security action",
            user_id=user_id,
            org_id=org_id,
        )

        if not all([user_id, org_id]):
            logger.error(
                "Invalid user data for logout-all",
                user_id=bool(user_id),
                org_id=bool(org_id),
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session data"
            )

        # Invalidate ALL user sessions (including current one)
        from app.core.simple_auth import invalidate_all_user_sessions

        invalidated_count = invalidate_all_user_sessions(user_id, org_id)

        logout_time = datetime.now(timezone.utc).isoformat()

        logger.info(
            "🔒 LOGOUT-ALL completed successfully",
            user_id=user_id,
            org_id=org_id,
            sessions_invalidated=invalidated_count,
            logged_out_at=logout_time,
        )

        # Audit logging for logout-all (non-blocking)
        client_ip = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        asyncio.create_task(
            audit_service.log_event(
                org_id=org_id,
                action=AuditAction.LOGOUT,
                entity_type=AuditEntityType.USER,
                entity_id=user_id,
                user_id=user_id,
                details={
                    "email": current_user.get("email"),
                    "session_id": session_id,
                    "sessions_invalidated": invalidated_count,
                    "operation": "logout_all",
                    "security_action": True,
                },
                ip_address=client_ip,
                session_id=session_id,
                user_agent=user_agent,
            )
        )

        return LogoutAllResponse(
            message=f"Successfully logged out from all devices. {invalidated_count} sessions invalidated.",
            sessions_invalidated=invalidated_count,
            logged_out_at=logout_time,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Logout-all error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout-all failed due to server error",
        )


@router.post(
    "/invite",
    response_model=InvitationTokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create invitation token",
    operation_id="createInvitation",
    description="Create an invitation token for a new user to join the organization. Requires admin or user permissions.",
)
async def create_invitation(
    org_id: str,
    email: str,
    role: UserRole = UserRole.USER,
    expires_hours: int = 168,  # 7 days default
) -> InvitationTokenResponse:
    """
    Create an invitation token for a new user.

    Note: This endpoint will need authentication middleware added later.
    For now, it's a basic implementation.

    Args:
        org_id: Organization ID
        email: Email address to invite
        role: Role to assign to the invited user
        expires_hours: Token expiration in hours

    Returns:
        Invitation token response

    Raises:
        HTTPException: If invitation creation fails
    """
    try:
        logger.info("Creating invitation", org_id=org_id, email=email, role=role.value)

        invitation_token = await auth_service.create_invitation_token(
            org_id=org_id, email=email, role=role, expires_hours=expires_hours
        )

        logger.info("Invitation created successfully", org_id=org_id, email=email)

        return InvitationTokenResponse(
            invitation_token=invitation_token, expires_in_hours=expires_hours
        )

    except InvitationError as e:
        logger.warning(
            "Invitation creation failed", org_id=org_id, email=email, error=str(e)
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(
            "Invitation creation error", org_id=org_id, email=email, error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invitation creation failed due to server error",
        )


@router.get(
    "/organizations",
    response_model=List[OrganizationResponse],
    status_code=status.HTTP_200_OK,
    summary="🏢 List Organizations for Registration",
    operation_id="listOrganizationsForRegistration",
    description="""List all available organizations for user registration selection.

**Usage:**
This endpoint is used during the registration flow to show users
which organizations they can join. No authentication required.

**Response:**
Returns a list of all active organizations with their details.

**Example Response:**
```json
[
  {
    "id": "oJIChgDgktkF30dAPy2c",
    "name": "Google",
    "domain": "google.com",
    "plan_type": "free",
    "is_active": true,
    "created_at": "2025-08-15T05:31:35.921520"
  },
  {
    "id": "GUbmPT49OSDO3eFDU2r5",
    "name": "Tech Innovations Corp", 
    "domain": "techinnovations.com",
    "plan_type": "pro",
    "is_active": true,
    "created_at": "2025-08-11T14:08:19.233046"
  }
]
```

**Organization Plan Types:**
- `free`: Free tier with basic features
- `starter`: Starter tier with additional features
- `pro`: Professional tier with all features
""",
    responses={
        200: {
            "description": "List of active organizations",
            "content": {
                "application/json": {
                    "examples": {
                        "organizations_list": {
                            "summary": "Available organizations",
                            "value": [
                                {
                                    "id": "oJIChgDgktkF30dAPy2c",
                                    "name": "Google",
                                    "domain": "google.com",
                                    "settings": {},
                                    "plan_type": "free",
                                    "is_active": True,
                                    "created_at": "2025-08-15T05:31:35.921520",
                                    "updated_at": "2025-08-15T05:31:35.921523",
                                },
                                {
                                    "id": "GUbmPT49OSDO3eFDU2r5",
                                    "name": "Tech Innovations Corp",
                                    "domain": "techinnovations.com",
                                    "settings": {},
                                    "plan_type": "pro",
                                    "is_active": True,
                                    "created_at": "2025-08-11T14:08:19.233046",
                                    "updated_at": "2025-08-11T14:08:19.233057",
                                },
                            ],
                        }
                    }
                }
            },
        },
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {"example": {"detail": "Internal server error"}}
            },
        },
    },
)
async def list_organizations_for_registration() -> List[OrganizationResponse]:
    """
    List all available organizations for registration.

    This endpoint is used during the registration flow to allow users
    to select which organization they want to join.

    Returns:
        List of all active organizations

    Raises:
        HTTPException: If listing fails
    """
    try:
        logger.info("Listing organizations for registration")

        # Get all active organizations with basic pagination
        pagination = PaginationParams(
            page=1, per_page=100
        )  # Get up to 100 orgs for selection
        filters = OrganizationFilters(is_active=True)

        result = await organization_service.list_organizations(pagination, filters)

        logger.info("Organizations listed for registration", count=len(result.items))

        return result.items

    except Exception as e:
        logger.error("Failed to list organizations for registration", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list organizations",
        )


@router.get(
    "/organizations/lookup",
    response_model=List[OrganizationResponse],
    status_code=status.HTTP_200_OK,
    summary="Lookup organizations",
    operation_id="lookupOrganizations",
    description="Search for organizations by name. Used during login to help users find their organization.",
)
async def lookup_organizations(
    query: str = Query(
        "",
        description="Search query for organization name (empty string returns all active organizations)",
    )
) -> List[OrganizationResponse]:
    """
    Lookup organizations by name query.

    This endpoint is used during the authentication flow to help users
    find their organization. It searches for organizations where the name
    contains the query string (case-insensitive partial match).

    Args:
        query: Search query string

    Returns:
        List of matching organizations

    Raises:
        HTTPException: If lookup fails
    """
    try:
        logger.debug("Organization lookup", query=query)

        # Use the organization service to search with name filter
        filters = OrganizationFilters(name=query, is_active=True)
        pagination = PaginationParams(page=1, per_page=20)  # Limit results for lookup

        result = await organization_service.list_organizations(pagination, filters)

        logger.debug(
            "Organization lookup completed", query=query, count=len(result.items)
        )

        return result.items

    except Exception as e:
        logger.error("Organization lookup failed", query=query, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Organization lookup failed due to server error",
        )


@router.get(
    "/organizations/check-availability/{name}",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Check organization name availability",
    operation_id="checkOrganizationAvailability",
    description="Check if an organization name is available for registration.",
)
async def check_organization_availability(
    name: str = Path(..., description="Organization name to check")
) -> Dict[str, Any]:
    """
    Check if an organization name is available for registration.

    This endpoint helps users validate organization names before attempting
    to register, providing better user experience.

    Args:
        name: Organization name to check

    Returns:
        Dictionary with availability status and suggestions

    Raises:
        HTTPException: If check fails
    """
    try:
        logger.debug("Checking organization name availability", name=name)

        # Check if organization exists
        existing_org = await organization_service.get_organization_by_name(name)

        if existing_org:
            # Organization exists - not available
            result = {
                "available": False,
                "name": name,
                "message": f"Organization '{name}' already exists",
                "suggestions": [
                    "Contact an admin of this organization for an invitation",
                    "Choose a different organization name",
                    f"Try variations like '{name} LLC', '{name} Inc', etc.",
                ],
            }
        else:
            # Organization name is available
            result = {
                "available": True,
                "name": name,
                "message": f"Organization name '{name}' is available",
            }

        logger.debug(
            "Organization availability check completed",
            name=name,
            available=result["available"],
        )

        return result

    except Exception as e:
        logger.error("Organization availability check failed", name=name, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Availability check failed due to server error",
        )


@router.get(
    "/validate",
    response_model=Dict[str, Any],
    summary="Validate access token",
    operation_id="validateToken",
    description="Validate the current session token and return expiration information for the frontend.",
)
async def validate_token(
    current_user: Dict[str, Any] = Depends(get_current_user_dict),
) -> Dict[str, Any]:
    """
    Validate session token and return validation info.

    This endpoint allows the frontend to check if the current session is valid
    and get information about when it expires.

    Args:
        current_user: Current user info from session validation

    Returns:
        Token validation information including expiry details

    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        session_id = current_user.get("session_id")
        if not session_id:
            raise TokenInvalidError("Session ID not found in token")

        validation_info = validate_user_session(session_id)
        if not validation_info:
            raise TokenInvalidError("Session validation failed")

        logger.debug(
            "Token validation successful",
            user_id=current_user.get("user_id"),
            session_id=session_id[:8] + "...",
        )

        return {
            "valid": validation_info["valid"],
            "expires_at": validation_info["expires_at"],
            "time_remaining": validation_info["time_remaining"],
            "in_grace_period": validation_info["in_grace_period"],
            "can_refresh": validation_info["can_refresh"],
            "user": {
                "user_id": current_user["user_id"],
                "email": current_user["email"],
                "full_name": current_user["full_name"],
                "role": current_user["role"],
                "org_id": current_user["org_id"],
            },
        }

    except (TokenExpiredError, TokenInvalidError):
        raise
    except Exception as e:
        logger.error("Token validation error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token validation failed",
        )


@router.post(
    "/refresh-session",
    response_model=AuthResponse,
    summary="Refresh session token",
    operation_id="refreshSession",
    description="Refresh the session using a refresh token to get new access and refresh tokens.",
)
async def refresh_session_token(request: RefreshTokenRequest) -> AuthResponse:
    """
    Refresh session using refresh token.

    This endpoint allows the frontend to get a new session token when
    the current one is expired or about to expire.

    Args:
        request: Refresh token request containing the refresh token

    Returns:
        New authentication response with fresh tokens

    Raises:
        HTTPException: If refresh token is invalid or expired
    """
    try:
        logger.info(
            "Session refresh attempt", refresh_token=request.refresh_token[:8] + "..."
        )

        new_session = refresh_user_session(request.refresh_token)
        if not new_session:
            raise RefreshTokenInvalidError("Invalid or expired refresh token")

        # Calculate expiration times
        expires_in = new_session.time_until_expiry()
        refresh_expires_in = (
            int(
                (
                    new_session.refresh_expires_at - datetime.now(timezone.utc)
                ).total_seconds()
            )
            if new_session.refresh_expires_at
            else 0
        )

        logger.info(
            "Session refresh successful",
            user_id=new_session.user_id,
            new_session_id=new_session.session_id[:8] + "...",
        )

        return AuthResponse(
            access_token=new_session.session_id,
            refresh_token=new_session.refresh_token or "",
            token_type="bearer",
            expires_in=expires_in,
            refresh_expires_in=refresh_expires_in,
            access_token_expires_at=new_session.expires_at.isoformat(),
            refresh_token_expires_at=(
                new_session.refresh_expires_at.isoformat()
                if new_session.refresh_expires_at
                else ""
            ),
            user={
                "user_id": new_session.user_id,
                "email": new_session.email,
                "full_name": new_session.full_name,
                "username": new_session.username,
                "role": new_session.role,
                "org_id": new_session.org_id,
                "session_id": new_session.session_id,
            },
        )

    except (RefreshTokenExpiredError, RefreshTokenInvalidError):
        raise
    except Exception as e:
        logger.error("Session refresh error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session refresh failed",
        )


@router.get(
    "/debug/session-info",
    summary="Session diagnostics",
    description="Debugging endpoint for session validation issues. Use for troubleshooting authentication problems.",
    include_in_schema=False,  # Hide from public API docs for security
)
async def debug_session_info(
    current_user: Dict[str, Any] = Depends(get_current_user_dict),
) -> Dict[str, Any]:
    """
    Session diagnostics endpoint for debugging authentication issues.

    This endpoint provides detailed information about session validation
    without performing actual operations. Useful for troubleshooting.

    Args:
        current_user: Current user info from session validation

    Returns:
        Detailed session diagnostic information

    Raises:
        HTTPException: If session cannot be analyzed
    """
    try:
        from app.core.simple_auth import validate_user_session, simple_auth_manager

        logger.info("🔍 SESSION DIAGNOSTICS requested")

        session_id = current_user.get("session_id")
        user_id = current_user.get("user_id")
        org_id = current_user.get("org_id")

        diagnostic_info = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id_length": len(session_id) if session_id else 0,
            "session_id_prefix": session_id[:20] + "..." if session_id else "N/A",
            "validation_steps": {},
        }

        # Step 1: Session structure validation
        if session_id:
            try:
                # Check if it's a valid UUID format
                import uuid

                uuid.UUID(session_id)
                diagnostic_info["validation_steps"]["session_structure"] = {
                    "status": "valid",
                    "format": "UUID",
                    "session_id": session_id[:8] + "..." if session_id else "N/A",
                }
            except ValueError:
                diagnostic_info["validation_steps"]["session_structure"] = {
                    "status": "invalid",
                    "format": "non-UUID",
                    "error": "Session ID is not a valid UUID",
                }
        else:
            diagnostic_info["validation_steps"]["session_structure"] = {
                "status": "missing",
                "error": "No session ID found",
            }

        # Step 2: Session validation
        if session_id:
            try:
                validation_info = validate_user_session(session_id)
                if validation_info:
                    diagnostic_info["validation_steps"]["session_validation"] = {
                        "status": "valid",
                        "expires_at": validation_info["expires_at"],
                        "time_remaining": validation_info["time_remaining"],
                        "in_grace_period": validation_info["in_grace_period"],
                        "can_refresh": validation_info["can_refresh"],
                    }
                else:
                    diagnostic_info["validation_steps"]["session_validation"] = {
                        "status": "invalid",
                        "reason": "session_not_found_or_expired",
                    }
            except Exception as e:
                diagnostic_info["validation_steps"]["session_validation"] = {
                    "status": "error",
                    "error": str(e),
                }

        # Step 3: Session registry check
        try:
            with simple_auth_manager._lock:
                session_exists = (
                    session_id in simple_auth_manager._sessions if session_id else False
                )
                active_session_count = simple_auth_manager.get_active_session_count()
                user_session_count = (
                    simple_auth_manager.get_user_session_count(user_id, org_id)
                    if user_id and org_id
                    else 0
                )

                diagnostic_info["validation_steps"]["session_registry"] = {
                    "status": "tracked" if session_exists else "not_tracked",
                    "session_in_registry": session_exists,
                    "total_active_sessions": active_session_count,
                    "user_active_sessions": user_session_count,
                }

                if session_exists and session_id:
                    session = simple_auth_manager._sessions[session_id]
                    diagnostic_info["session_details"] = {
                        "user_id": session.user_id,
                        "org_id": session.org_id,
                        "email": session.email,
                        "role": session.role,
                        "created_at": session.created_at.isoformat(),
                        "last_used": session.last_used.isoformat(),
                        "expires_at": session.expires_at.isoformat(),
                        "has_refresh_token": session.refresh_token is not None,
                        "refresh_expires_at": (
                            session.refresh_expires_at.isoformat()
                            if session.refresh_expires_at
                            else None
                        ),
                    }

        except Exception as e:
            diagnostic_info["validation_steps"]["session_registry"] = {
                "status": "error",
                "error": str(e),
            }

        # Step 4: Configuration info
        diagnostic_info["system_configuration"] = {
            "session_duration_hours": settings.SESSION_DURATION_HOURS,
            "refresh_session_duration_days": settings.REFRESH_SESSION_DURATION_DAYS,
            "token_grace_period_minutes": settings.TOKEN_GRACE_PERIOD_MINUTES,
            "max_concurrent_sessions": settings.MAX_CONCURRENT_SESSIONS,
            "environment": settings.ENVIRONMENT,
        }

        logger.info(
            "🔍 SESSION DIAGNOSTICS completed",
            session_id=session_id[:8] + "..." if session_id else "N/A",
            user_id=user_id,
            validation_status=all(
                step.get("status") in ["valid", "tracked", "not_tracked"]
                for step in diagnostic_info["validation_steps"].values()
            ),
        )

        return diagnostic_info

    except Exception as e:
        logger.error("Session diagnostics error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session diagnostics failed",
        )
