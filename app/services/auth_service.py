from typing import Optional, Tuple, Dict, Any

from app.core.config import settings
from app.core.simple_auth import create_user_session

from app.core.logging import get_service_logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    create_user_token_data,
    generate_invitation_token,
    verify_invitation_token,
)
from app.services.user_service import (
    user_service,
    UserAlreadyExistsError,
)
from app.services.org_service import (
    organization_service,
)
from app.models.user import UserRole
from app.models.schemas import UserCreate, OrganizationCreate
from app.models.organization import PlanType

logger = get_service_logger("auth")


class AuthenticationError(Exception):
    """Authentication failed error."""

    pass


class InvalidCredentialsError(AuthenticationError):
    """Invalid username/password error."""

    pass


class UserInactiveError(AuthenticationError):
    """User account is inactive."""

    pass


class OrganizationInactiveError(AuthenticationError):
    """Organization is inactive."""

    pass


class RegistrationError(Exception):
    """Registration failed error."""

    pass


class InvitationError(Exception):
    """Invitation token error."""

    pass


class AuthService:
    """Service for handling authentication and registration."""

    def __init__(self):
        self.logger = logger

    async def authenticate_user(
        self, email: str, password: str
    ) -> Tuple[str, str, Dict[str, Any]]:
        """
        Authenticate a user with email and password.

        Args:
            email: User email address
            password: User password

        Returns:
            Tuple of (access_token, refresh_token, user_data)

        Raises:
            InvalidCredentialsError: If credentials are invalid
            UserInactiveError: If user is inactive
            OrganizationInactiveError: If organization is inactive
        """
        try:
            self.logger.info("Simple authentication attempt", email=email)

            # Find user by email - simple global search
            user = await user_service._get_user_by_email_simple(email)

            if not user:
                self.logger.warning(
                    "Authentication failed - user not found", email=email
                )
                raise InvalidCredentialsError("Invalid email or password")

            # Verify password
            self.logger.info("Verifying password", user_id=user.id)
            password_valid = await user_service.verify_password(
                password, user.password_hash
            )

            if not password_valid:
                self.logger.warning(
                    "Authentication failed - invalid password",
                    email=email,
                    user_id=user.id,
                )
                raise InvalidCredentialsError("Invalid email or password")

            # Check if user is active
            if not user.is_active:
                self.logger.warning(
                    "Authentication failed - user inactive",
                    email=email,
                    user_id=user.id,
                )
                raise UserInactiveError("User account is inactive")

            # Check if organization is active
            org = await organization_service.get_organization(user.org_id)
            # Handle both dict (from cache) and Pydantic model responses
            org_is_active = org.get('is_active', False) if isinstance(org, dict) else org.is_active
            if not org_is_active:
                self.logger.warning(
                    "Authentication failed - organization inactive",
                    email=email,
                    org_id=user.org_id,
                )
                raise OrganizationInactiveError("Organization is inactive")

            # Create tokens with enterprise tracking
            self.logger.info("Creating authentication tokens", user_id=user.id)
            token_data = create_user_token_data(
                user.id, user.org_id, user.email, user.role
            )

            # Create access token with enterprise tracking
            access_token, access_token_info = create_access_token(token_data)

            # Invalidate previous tokens if configured
            from app.core.security import invalidate_user_sessions

            if settings.INVALIDATE_TOKENS_ON_LOGIN:
                invalidated_count = invalidate_user_sessions(
                    user.id, user.org_id, access_token_info.token_id
                )
                self.logger.info(
                    "Invalidated previous user sessions",
                    user_id=user.id,
                    invalidated_count=invalidated_count,
                )

            # Create refresh token with enterprise tracking
            refresh_token, refresh_token_info = create_refresh_token(
                user.id, user.org_id
            )

            self.logger.info(
                "Authentication tokens created successfully",
                access_token_id=access_token_info.token_id[:8] + "...",
                refresh_token_id=refresh_token_info.token_id[:8] + "...",
                expires_in_minutes=settings.access_token_expire_minutes,
            )

            # Update last login
            await user_service.update_user_last_login(user.org_id, user.id)

            self.logger.info(
                "Authentication completed successfully",
                email=email,
                user_id=user.id,
                org_id=user.org_id,
                role=user.role,
            )

            return (
                access_token,
                refresh_token,
                {
                    "user_id": user.id,
                    "email": user.email,
                    "full_name": user.full_name,
                    "username": user.username,
                    "role": user.role,
                    "org_id": user.org_id,
                    "org_name": org.name,
                    "access_token_expires_at": access_token_info.expires_at.isoformat(),
                    "refresh_token_expires_at": refresh_token_info.expires_at.isoformat(),
                    "access_token_expires_in": int(
                        (
                            access_token_info.expires_at - access_token_info.issued_at
                        ).total_seconds()
                    ),
                    "refresh_token_expires_in": int(
                        (
                            refresh_token_info.expires_at - refresh_token_info.issued_at
                        ).total_seconds()
                    ),
                },
            )

        except (InvalidCredentialsError, UserInactiveError, OrganizationInactiveError):
            # These are expected authentication failures - re-raise them
            self.logger.info("Authentication failed - expected error")
            raise
        except Exception as e:
            # Unexpected errors - log detailed info for debugging
            self.logger.error(
                "Authentication failed - unexpected error",
                email=email,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            raise InvalidCredentialsError("Authentication failed")

    async def register_user_with_organization(
        self,
        email: str,
        password: str,
        full_name: str,
        username: str,
        organization_name: str,
        domain: Optional[str] = None,
        plan_type: PlanType = PlanType.FREE,
    ) -> Tuple[str, str, Dict[str, Any]]:
        """
        Register a new user to an organization (create org if needed).
        This is the primary registration flow for MVP - allows joining existing orgs.

        Args:
            email: User email address
            password: User password
            full_name: User's full name
            username: Username
            organization_name: Name of the organization
            domain: Optional organization domain
            plan_type: Organization plan type (only used if creating new org)

        Returns:
            Tuple of (access_token, refresh_token, user_data)

        Raises:
            RegistrationError: If registration fails
        """
        try:
            self.logger.info(
                "Starting user registration", email=email, org_name=organization_name
            )

            # Check if organization already exists
            existing_org = await organization_service.get_organization_by_name(
                organization_name
            )

            if existing_org:
                # Organization exists - add user to existing organization
                organization = existing_org
                user_role = UserRole.USER  # New users join as regular users
                self.logger.info(
                    "Adding user to existing organization",
                    email=email,
                    org_id=organization.id,
                    org_name=organization_name,
                )
            else:
                # Organization doesn't exist - create it
                org_data = OrganizationCreate(
                    name=organization_name,
                    domain=domain,
                    plan_type=plan_type,
                    settings={},
                )
                organization = await organization_service.create_organization(org_data)
                user_role = UserRole.ADMIN  # First user becomes admin
                self.logger.info(
                    "Created new organization and adding user as admin",
                    email=email,
                    org_id=organization.id,
                    org_name=organization_name,
                )

            # Create the user
            user_data = UserCreate(
                email=email,
                username=username,
                password=password,
                full_name=full_name,
                role=user_role,
            )

            user = await user_service.create_user(organization.id, user_data)

            # Create enterprise tokens for immediate login
            token_data = create_user_token_data(
                user.id, user.org_id, user.email, user.role
            )
            access_token, access_token_info = create_access_token(token_data)
            refresh_token, refresh_token_info = create_refresh_token(
                user.id, user.org_id
            )

            self.logger.info(
                "User registration completed successfully",
                email=email,
                user_id=user.id,
                org_id=organization.id,
                role=user_role.value,
            )

            return (
                access_token,
                refresh_token,
                {
                    "user_id": user.id,
                    "email": user.email,
                    "full_name": user.full_name,
                    "role": user.role,
                    "org_id": user.org_id,
                    "org_name": organization.name,
                    "access_token_expires_at": access_token_info.expires_at.isoformat(),
                    "refresh_token_expires_at": refresh_token_info.expires_at.isoformat(),
                    "access_token_expires_in": int(
                        (
                            access_token_info.expires_at - access_token_info.issued_at
                        ).total_seconds()
                    ),
                    "refresh_token_expires_in": int(
                        (
                            refresh_token_info.expires_at - refresh_token_info.issued_at
                        ).total_seconds()
                    ),
                },
            )
        except UserAlreadyExistsError as e:
            self.logger.warning(
                "User already exists in organization",
                email=email,
                org_name=organization_name,
                error=str(e),
            )
            raise RegistrationError(
                f"User with this email or username already exists in '{organization_name}'. Please use different credentials or try logging in."
            )
        except Exception as e:
            self.logger.error("Registration error", email=email, error=str(e))
            raise RegistrationError("Registration failed due to system error")

    async def register_user_with_invitation(
        self, invitation_token: str, password: str, full_name: str, username: str
    ) -> Tuple[str, str, Dict[str, Any]]:
        """
        Register a new user using an invitation token.
        This allows team members to join existing organizations.

        Args:
            invitation_token: Valid invitation token
            password: User password
            full_name: User's full name
            username: Username

        Returns:
            Tuple of (access_token, refresh_token, user_data)

        Raises:
            InvitationError: If invitation is invalid or expired
            RegistrationError: If registration fails
        """
        try:
            # Verify invitation token
            invite_data = verify_invitation_token(invitation_token)
            if not invite_data:
                raise InvitationError("Invalid or expired invitation token")

            org_id = invite_data["org_id"]
            email = invite_data["email"]
            role = UserRole(invite_data["role"])

            self.logger.info(
                "Processing invitation-based registration",
                email=email,
                org_id=org_id,
                role=role.value,
            )

            # Verify organization still exists and is active
            organization = await organization_service.get_organization(org_id)
            if not organization.is_active:
                raise InvitationError("Organization is no longer active")

            # Create user
            user_data = UserCreate(
                email=email,
                username=username,
                password=password,
                full_name=full_name,
                role=role,
            )

            user = await user_service.create_user(org_id, user_data)

            # Create enterprise tokens
            token_data = create_user_token_data(
                user.id, user.org_id, user.email, user.role
            )
            access_token, access_token_info = create_access_token(token_data)
            refresh_token, refresh_token_info = create_refresh_token(
                user.id, user.org_id
            )

            self.logger.info(
                "Invitation-based registration completed",
                email=email,
                user_id=user.id,
                org_id=org_id,
            )

            return (
                access_token,
                refresh_token,
                {
                    "user_id": user.id,
                    "email": user.email,
                    "full_name": user.full_name,
                    "role": user.role,
                    "org_id": user.org_id,
                    "org_name": organization.name,
                    "access_token_expires_at": access_token_info.expires_at.isoformat(),
                    "refresh_token_expires_at": refresh_token_info.expires_at.isoformat(),
                    "access_token_expires_in": int(
                        (
                            access_token_info.expires_at - access_token_info.issued_at
                        ).total_seconds()
                    ),
                    "refresh_token_expires_in": int(
                        (
                            refresh_token_info.expires_at - refresh_token_info.issued_at
                        ).total_seconds()
                    ),
                },
            )

        except InvitationError:
            raise
        except UserAlreadyExistsError as e:
            raise RegistrationError(f"User registration failed: {str(e)}")
        except Exception as e:
            self.logger.error("Invitation registration error", error=str(e))
            raise RegistrationError("Registration failed due to system error")

    async def create_invitation_token(
        self, org_id: str, email: str, role: UserRole, expires_hours: int = 168
    ) -> str:
        """
        Create an invitation token for a new user.

        Args:
            org_id: Organization ID
            email: Email address to invite
            role: Role to assign to the invited user
            expires_hours: Token expiration in hours

        Returns:
            Invitation token string
        """
        try:
            # Verify organization exists and is active
            organization = await organization_service.get_organization(org_id)
            if not organization.is_active:
                raise InvitationError("Cannot invite users to inactive organization")

            # Check if user already exists
            existing_user = await user_service.get_user_by_email(org_id, email)
            if existing_user:
                raise InvitationError("User already exists in organization")

            token = generate_invitation_token(org_id, email, role.value, expires_hours)

            self.logger.info(
                "Invitation token created", org_id=org_id, email=email, role=role.value
            )

            return token

        except InvitationError:
            raise
        except Exception as e:
            self.logger.error(
                "Error creating invitation", org_id=org_id, email=email, error=str(e)
            )
            raise InvitationError("Failed to create invitation")

    async def refresh_access_token(
        self, refresh_token: str
    ) -> Tuple[str, Optional[str], Dict[str, Any]]:
        """
        Create a new access token using a refresh token with enterprise rotation.

        Args:
            refresh_token: Valid refresh token

        Returns:
            Tuple of (new_access_token, new_refresh_token_if_rotated, token_info)

        Raises:
            AuthenticationError: If refresh token is invalid
        """
        try:
            from app.core.security import verify_token, blacklist_token

            # Verify refresh token
            payload = verify_token(refresh_token)
            if not payload or payload.get("type") != "refresh":
                raise AuthenticationError("Invalid refresh token")

            user_id = payload["sub"]
            org_id = payload["org_id"]
            old_token_id = payload.get("jti")
            family_id = payload.get("family_id")

            # Verify user still exists and is active
            user = await user_service.get_user(org_id, user_id)
            if not user.is_active:
                raise AuthenticationError("User account is inactive")

            # Verify organization is still active
            org = await organization_service.get_organization(org_id)
            # Handle both dict (from cache) and Pydantic model responses
            org_is_active = org.get('is_active', False) if isinstance(org, dict) else org.is_active
            if not org_is_active:
                raise AuthenticationError("Organization is inactive")

            # Create new access token
            token_data = create_user_token_data(
                user.id, user.org_id, user.email, user.role
            )
            access_token, access_token_info = create_access_token(token_data)

            new_refresh_token = None
            refresh_token_info = None

            # Implement refresh token rotation if enabled
            if settings.ENABLE_TOKEN_ROTATION and family_id:
                self.logger.info(
                    "Rotating refresh token",
                    user_id=user_id,
                    old_token_id=old_token_id[:8] + "..." if old_token_id else "legacy",
                    family_id=family_id[:8] + "...",
                )

                # Blacklist old refresh token
                if old_token_id:
                    blacklist_token(refresh_token, reason="token_rotation")

                # Create new refresh token with same family ID
                new_refresh_token, refresh_token_info = create_refresh_token(
                    user_id, org_id, family_id=family_id
                )

            token_info = {
                "access_token_expires_at": access_token_info.expires_at.isoformat(),
                "access_token_expires_in": int(
                    (
                        access_token_info.expires_at - access_token_info.issued_at
                    ).total_seconds()
                ),
                "rotation_enabled": settings.ENABLE_TOKEN_ROTATION,
                "refresh_token_rotated": new_refresh_token is not None,
            }

            if refresh_token_info:
                token_info.update(
                    {
                        "refresh_token_expires_at": refresh_token_info.expires_at.isoformat(),
                        "refresh_token_expires_in": int(
                            (
                                refresh_token_info.expires_at
                                - refresh_token_info.issued_at
                            ).total_seconds()
                        ),
                    }
                )

            self.logger.info(
                "Token refresh completed",
                user_id=user_id,
                org_id=org_id,
                new_access_token_id=access_token_info.token_id[:8] + "...",
                new_refresh_token_id=(
                    refresh_token_info.token_id[:8] + "..."
                    if refresh_token_info
                    else "not_rotated"
                ),
            )

            return access_token, new_refresh_token, token_info

        except Exception as e:
            self.logger.error("Token refresh error", error=str(e))
            raise AuthenticationError("Failed to refresh token")

    async def authenticate_user_simple(
        self, email: str, password: str
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Simple MVP authentication using session tokens.

        Args:
            email: User email address
            password: User password

        Returns:
            Tuple of (session_token, user_data)

        Raises:
            InvalidCredentialsError: If credentials are invalid
            UserInactiveError: If user is inactive
            OrganizationInactiveError: If organization is inactive
        """
        try:
            self.logger.info("Simple MVP authentication attempt", email=email)

            # Find user by email - use simple global search
            user = await user_service._get_user_by_email_simple(email)

            if not user:
                self.logger.warning(
                    "Authentication failed - user not found", email=email
                )
                raise InvalidCredentialsError("Invalid email or password")

            # Verify password
            self.logger.info("Verifying password", user_id=user.id)
            password_valid = await user_service.verify_password(
                password, user.password_hash
            )

            if not password_valid:
                self.logger.warning(
                    "Authentication failed - invalid password",
                    email=email,
                    user_id=user.id,
                )
                raise InvalidCredentialsError("Invalid email or password")

            # Check if user is active
            if not user.is_active:
                self.logger.warning(
                    "Authentication failed - user inactive",
                    email=email,
                    user_id=user.id,
                )
                raise UserInactiveError("User account is inactive")

            # Check if organization is active
            org = await organization_service.get_organization(user.org_id)
            # Handle both dict (from cache) and Pydantic model responses
            org_is_active = org.get('is_active', False) if isinstance(org, dict) else org.is_active
            if not org_is_active:
                self.logger.warning(
                    "Authentication failed - organization inactive",
                    email=email,
                    org_id=user.org_id,
                )
                raise OrganizationInactiveError("Organization is inactive")

            # Create simple session
            self.logger.info("Creating session for authentication", user_id=user.id)
            session = create_user_session(
                user_id=user.id,
                org_id=user.org_id,
                email=user.email,
                full_name=user.full_name,
                username=user.username,
                role=user.role.value if hasattr(user.role, "value") else str(user.role),
            )

            # Update last login
            await user_service.update_user_last_login(user.org_id, user.id)

            self.logger.info(
                "Simple authentication completed successfully",
                email=email,
                user_id=user.id,
                org_id=user.org_id,
                role=user.role,
                session_id=session.session_id[:8] + "...",
            )

            # Return session data in compatible format
            user_data = {
                "user_id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "username": user.username,
                "role": (
                    user.role.value if hasattr(user.role, "value") else str(user.role)
                ),
                "org_id": user.org_id,
                "org_name": org.name,
                "session_id": session.session_id,
                "created_at": session.created_at.isoformat(),
                "last_used": session.last_used.isoformat(),
                "expires_at": session.expires_at.isoformat(),
            }

            return session.session_id, user_data

        except (InvalidCredentialsError, UserInactiveError, OrganizationInactiveError):
            # These are expected authentication failures - re-raise them
            raise
        except Exception as e:
            # Unexpected errors - log detailed info for debugging
            self.logger.error(
                "Simple authentication failed - unexpected error",
                email=email,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            raise InvalidCredentialsError("Authentication failed")

    async def register_user_simple(
        self,
        email: str,
        password: str,
        full_name: str,
        username: str,
        organization_id: str,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Simple MVP registration by joining an existing organization.

        Args:
            email: User email address
            password: User password
            full_name: User's full name
            username: Username
            organization_id: ID of the organization to join

        Returns:
            Tuple of (session_token, user_data)

        Raises:
            RegistrationError: If registration fails
        """
        try:
            self.logger.info(
                "Starting simple MVP registration", email=email, org_id=organization_id
            )

            # Verify organization exists
            try:
                organization = await organization_service.get_organization(
                    organization_id
                )
                if not organization.is_active:
                    raise RegistrationError("Organization is not active")
            except Exception as e:
                self.logger.error(
                    "Organization verification failed",
                    org_id=organization_id,
                    error=str(e),
                )
                raise RegistrationError("Invalid organization selected")

            # Create the user - they join as regular user (not admin)
            from app.models.schemas import UserCreate
            from app.models.user import UserRole

            user_data = UserCreate(
                email=email,
                username=username,
                password=password,
                full_name=full_name,
                role=UserRole.USER,  # All new users join as regular users in MVP
            )

            user = await user_service.create_user(organization_id, user_data)

            # Create session for immediate login
            session = create_user_session(
                user_id=user.id,
                org_id=user.org_id,
                email=user.email,
                full_name=user.full_name,
                username=user.username,
                role=user.role.value if hasattr(user.role, "value") else str(user.role),
            )

            self.logger.info(
                "Simple MVP registration completed successfully",
                email=email,
                user_id=user.id,
                org_id=organization_id,
                role=user.role,
            )

            # Return session data in compatible format
            response_data = {
                "user_id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "username": user.username,
                "role": (
                    user.role.value if hasattr(user.role, "value") else str(user.role)
                ),
                "org_id": user.org_id,
                "org_name": organization.name,
                "session_id": session.session_id,
                "created_at": session.created_at.isoformat(),
                "last_used": session.last_used.isoformat(),
                "expires_at": session.expires_at.isoformat(),
            }

            return session.session_id, response_data

        except UserAlreadyExistsError as e:
            self.logger.warning(
                "User already exists", email=email, org_id=organization_id, error=str(e)
            )
            raise RegistrationError(
                "User with this email or username already exists in this organization. Please use different credentials or try logging in."
            )
        except RegistrationError:
            raise
        except Exception as e:
            self.logger.error("Simple registration error", email=email, error=str(e))
            raise RegistrationError("Registration failed due to system error")


# Global service instance
auth_service = AuthService()
