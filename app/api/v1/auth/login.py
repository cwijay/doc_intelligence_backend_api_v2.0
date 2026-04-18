"""Login, logout, and registration endpoints.

Provides:
- /login - User authentication
- /logout - Single session logout
- /logout-all - All sessions logout
- /register - User registration
- /register/invite - Registration with invitation token
"""

from typing import Dict, Any
import asyncio

from fastapi import APIRouter, HTTPException, status, Depends, Request
from datetime import datetime, timezone

from app.core.logging import get_service_logger
from biz2bricks_core import AuditAction, AuditEntityType
from app.services.audit_service import audit_service
from app.core.simple_auth import get_current_user_dict
from app.services.auth_service import (
    auth_service,
    InvalidCredentialsError,
    UserInactiveError,
    OrganizationInactiveError,
    RegistrationError,
    InvitationError,
)
from app.models.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    InviteRegisterRequest,
    AuthResponse,
    LogoutResponse,
    LogoutAllResponse,
)

logger = get_service_logger("auth_api")

router = APIRouter()


@router.post(
    "/login",
    response_model=AuthResponse,
    status_code=status.HTTP_200_OK,
    summary="User Login",
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
    summary="User Registration",
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
            plan_type=request.plan_type,
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
            "LOGOUT-ALL request received - Security action",
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
            "LOGOUT-ALL completed successfully",
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
