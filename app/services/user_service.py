import math
import asyncio
from typing import Optional
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from app.models.user import User
from app.models.schemas import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserList,
    PaginationParams,
    UserFilters,
)
from biz2bricks_core import (
    db,
    UserModel,
    OrganizationModel,
    AuditAction,
    AuditEntityType,
)
from app.core.security import hash_password, verify_password
from app.core.logging import get_service_logger
from app.core.cache import cached_users, invalidate_users
from app.services.audit_service import audit_service

logger = get_service_logger("user")


class UserNotFoundError(Exception):
    """User not found error."""

    pass


class UserAlreadyExistsError(Exception):
    """User already exists error."""

    pass


class OrganizationNotFoundError(Exception):
    """Organization not found error."""

    pass


class UserService:
    """Service for managing users with multi-tenant isolation."""

    def __init__(self):
        self.logger = logger

    def _model_to_pydantic(self, model: UserModel) -> User:
        """Convert SQLAlchemy model to Pydantic model."""
        return User(
            id=model.id,
            org_id=model.organization_id,
            email=model.email,
            username=model.username,
            password_hash=model.password_hash,
            full_name=model.full_name,
            role=model.role,
            is_active=model.is_active,
            last_login=model.last_login,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _ensure_response_model(self, data: UserResponse | dict) -> UserResponse:
        """Ensure cached data is converted back to Pydantic model.

        fastapi-cache2 serializes responses to JSON dicts when caching.
        This method ensures we always return a proper Pydantic model.
        """
        if isinstance(data, dict):
            return UserResponse.model_validate(data)
        return data

    async def _verify_organization_exists(self, org_id: str) -> bool:
        """Verify that an organization exists and is active."""
        try:
            async with db.session() as session:
                stmt = select(OrganizationModel).where(
                    OrganizationModel.id == org_id, OrganizationModel.is_active == True
                )
                result = await session.execute(stmt)
                org = result.scalar_one_or_none()
                return org is not None
        except Exception as e:
            self.logger.error(
                "Error verifying organization",
                org_id=org_id,
                error=str(e),
            )
            return False

    async def create_user(
        self,
        org_id: str,
        user_data: UserCreate,
        created_by_user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        session_id: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> UserResponse:
        """
        Create a new user in the specified organization.

        Args:
            org_id: Organization ID
            user_data: User creation data
            created_by_user_id: ID of user who created this user (for audit)
            ip_address: Client IP address (for audit)
            session_id: Session ID (for audit)
            user_agent: Client user agent (for audit)

        Returns:
            Created user response

        Raises:
            OrganizationNotFoundError: If organization doesn't exist
            UserAlreadyExistsError: If email or username already exists
        """
        try:
            async with db.session() as session:
                # Verify organization exists
                org_stmt = select(OrganizationModel).where(
                    OrganizationModel.id == org_id, OrganizationModel.is_active == True
                )
                org_result = await session.execute(org_stmt)
                if not org_result.scalar_one_or_none():
                    raise OrganizationNotFoundError(
                        f"Organization with ID {org_id} not found"
                    )

                # Check email uniqueness
                email_stmt = select(UserModel).where(
                    UserModel.email == user_data.email.lower(),
                    UserModel.is_active == True,
                )
                email_result = await session.execute(email_stmt)
                if email_result.scalar_one_or_none():
                    raise UserAlreadyExistsError(
                        f"User with email '{user_data.email}' already exists"
                    )

                # Check username uniqueness within organization
                username_stmt = select(UserModel).where(
                    UserModel.organization_id == org_id,
                    UserModel.username == user_data.username.lower(),
                    UserModel.is_active == True,
                )
                username_result = await session.execute(username_stmt)
                if username_result.scalar_one_or_none():
                    raise UserAlreadyExistsError(
                        f"User with username '{user_data.username}' already exists in organization"
                    )

                # Hash password
                password_hash = hash_password(user_data.password)

                # Create new user
                user_id = str(uuid4())
                now = datetime.now(timezone.utc)
                role_value = (
                    user_data.role.value
                    if hasattr(user_data.role, "value")
                    else user_data.role
                )

                user_model = UserModel(
                    id=user_id,
                    organization_id=org_id,
                    email=user_data.email.lower(),
                    username=user_data.username.lower(),
                    password_hash=password_hash,
                    full_name=user_data.full_name,
                    role=role_value,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )

                session.add(user_model)
                await session.flush()

                user = self._model_to_pydantic(user_model)
                self.logger.info(
                    "User created", org_id=org_id, user_id=user_id, email=user.email
                )

                # Invalidate user cache
                asyncio.create_task(invalidate_users(org_id))

                # Audit logging (non-blocking)
                asyncio.create_task(
                    audit_service.log_event(
                        org_id=org_id,
                        action=AuditAction.CREATE,
                        entity_type=AuditEntityType.USER,
                        entity_id=user_id,
                        user_id=created_by_user_id,
                        details={
                            "new_values": {
                                "email": user.email,
                                "username": user.username,
                                "full_name": user.full_name,
                                "role": user.role,
                            },
                            "operation": "create",
                        },
                        ip_address=ip_address,
                        session_id=session_id,
                        user_agent=user_agent,
                    )
                )

                return UserResponse.model_validate(user)

        except (OrganizationNotFoundError, UserAlreadyExistsError):
            raise
        except IntegrityError as e:
            self.logger.error("Database integrity error", error=str(e))
            raise UserAlreadyExistsError("User with this email already exists")
        except Exception as e:
            self.logger.error("Error creating user", org_id=org_id, error=str(e))
            raise

    async def get_user(self, org_id: str, user_id: str) -> UserResponse:
        """
        Get user by ID within organization.

        Args:
            org_id: Organization ID
            user_id: User ID

        Returns:
            User response (cached for 5 minutes)

        Raises:
            OrganizationNotFoundError: If organization doesn't exist
            UserNotFoundError: If user not found
        """
        result = await self._get_user_cached(org_id, user_id)
        return self._ensure_response_model(result)

    @cached_users()
    async def _get_user_cached(self, org_id: str, user_id: str) -> UserResponse:
        """Internal cached method for fetching user."""
        try:
            async with db.session() as session:
                # Verify organization exists
                if not await self._verify_organization_exists(org_id):
                    raise OrganizationNotFoundError(
                        f"Organization with ID {org_id} not found"
                    )

                stmt = select(UserModel).where(
                    UserModel.id == user_id,
                    UserModel.organization_id == org_id,
                    UserModel.is_active == True,
                )
                result = await session.execute(stmt)
                user_model = result.scalar_one_or_none()

                if not user_model:
                    raise UserNotFoundError(
                        f"User with ID {user_id} not found in organization {org_id}"
                    )

                user = self._model_to_pydantic(user_model)
                self.logger.debug("User retrieved", org_id=org_id, user_id=user_id)

                return UserResponse.model_validate(user)

        except (OrganizationNotFoundError, UserNotFoundError):
            raise
        except Exception as e:
            self.logger.error(
                "Error retrieving user", org_id=org_id, user_id=user_id, error=str(e)
            )
            raise

    async def update_user(
        self,
        org_id: str,
        user_id: str,
        update_data: UserUpdate,
        updated_by_user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        session_id: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> UserResponse:
        """
        Update user within organization.

        Args:
            org_id: Organization ID
            user_id: User ID
            update_data: Update data
            updated_by_user_id: ID of user who updated this user (for audit)
            ip_address: Client IP address (for audit)
            session_id: Session ID (for audit)
            user_agent: Client user agent (for audit)

        Returns:
            Updated user response

        Raises:
            OrganizationNotFoundError: If organization doesn't exist
            UserNotFoundError: If user not found
            UserAlreadyExistsError: If email/username conflict occurs
        """
        try:
            async with db.session() as session:
                # Verify organization exists
                if not await self._verify_organization_exists(org_id):
                    raise OrganizationNotFoundError(
                        f"Organization with ID {org_id} not found"
                    )

                # Get existing user
                stmt = select(UserModel).where(
                    UserModel.id == user_id,
                    UserModel.organization_id == org_id,
                    UserModel.is_active == True,
                )
                result = await session.execute(stmt)
                user_model = result.scalar_one_or_none()

                if not user_model:
                    raise UserNotFoundError(
                        f"User with ID {user_id} not found in organization {org_id}"
                    )

                # Capture old values for audit (before changes)
                old_values = {
                    "email": user_model.email,
                    "username": user_model.username,
                    "full_name": user_model.full_name,
                    "role": user_model.role,
                }

                # Check email uniqueness if email is being updated
                if update_data.email and update_data.email.lower() != user_model.email:
                    email_check = select(UserModel).where(
                        UserModel.email == update_data.email.lower(),
                        UserModel.id != user_id,
                        UserModel.is_active == True,
                    )
                    email_result = await session.execute(email_check)
                    if email_result.scalar_one_or_none():
                        raise UserAlreadyExistsError(
                            f"User with email '{update_data.email}' already exists"
                        )

                # Check username uniqueness if username is being updated
                if (
                    update_data.username
                    and update_data.username.lower() != user_model.username
                ):
                    username_check = select(UserModel).where(
                        UserModel.organization_id == org_id,
                        UserModel.username == update_data.username.lower(),
                        UserModel.id != user_id,
                        UserModel.is_active == True,
                    )
                    username_result = await session.execute(username_check)
                    if username_result.scalar_one_or_none():
                        raise UserAlreadyExistsError(
                            f"User with username '{update_data.username}' already exists in organization"
                        )

                # Update fields
                update_fields = update_data.model_dump(exclude_unset=True)
                for field, value in update_fields.items():
                    if field == "password" and value:
                        user_model.password_hash = hash_password(value)
                    elif field == "email" and value:
                        user_model.email = value.lower()
                    elif field == "username" and value:
                        user_model.username = value.lower()
                    elif field == "role" and hasattr(value, "value"):
                        user_model.role = value.value
                    elif hasattr(user_model, field):
                        setattr(user_model, field, value)

                user_model.updated_at = datetime.now(timezone.utc)
                await session.flush()

                user = self._model_to_pydantic(user_model)
                self.logger.info(
                    "User updated",
                    org_id=org_id,
                    user_id=user_id,
                    updates=list(update_fields.keys()),
                )

                # Capture new values for audit
                new_values = {
                    "email": user.email,
                    "username": user.username,
                    "full_name": user.full_name,
                    "role": user.role,
                }

                # Calculate changes
                changes = {}
                for key in new_values:
                    if old_values.get(key) != new_values.get(key):
                        changes[key] = {
                            "old": old_values.get(key),
                            "new": new_values.get(key),
                        }

                # Invalidate user cache
                asyncio.create_task(invalidate_users(org_id))

                # Audit logging (non-blocking)
                asyncio.create_task(
                    audit_service.log_event(
                        org_id=org_id,
                        action=AuditAction.UPDATE,
                        entity_type=AuditEntityType.USER,
                        entity_id=user_id,
                        user_id=updated_by_user_id,
                        details={
                            "old_values": old_values,
                            "new_values": new_values,
                            "changes": changes,
                            "operation": "update",
                        },
                        ip_address=ip_address,
                        session_id=session_id,
                        user_agent=user_agent,
                    )
                )

                return UserResponse.model_validate(user)

        except (OrganizationNotFoundError, UserNotFoundError, UserAlreadyExistsError):
            raise
        except Exception as e:
            self.logger.error(
                "Error updating user", org_id=org_id, user_id=user_id, error=str(e)
            )
            raise

    async def list_users(
        self,
        org_id: str,
        pagination: PaginationParams,
        filters: Optional[UserFilters] = None,
    ) -> UserList:
        """
        List users within organization with pagination and filtering.

        Args:
            org_id: Organization ID
            pagination: Pagination parameters
            filters: Optional filters

        Returns:
            Paginated user list

        Raises:
            OrganizationNotFoundError: If organization doesn't exist
        """
        try:
            async with db.session() as session:
                # Verify organization exists
                if not await self._verify_organization_exists(org_id):
                    raise OrganizationNotFoundError(
                        f"Organization with ID {org_id} not found"
                    )

                # Build base query
                stmt = select(UserModel).where(
                    UserModel.organization_id == org_id, UserModel.is_active == True
                )

                # Apply filters
                if filters:
                    if filters.role:
                        role_value = (
                            filters.role.value
                            if hasattr(filters.role, "value")
                            else filters.role
                        )
                        stmt = stmt.where(UserModel.role == role_value)

                    if filters.is_active is not None:
                        stmt = stmt.where(UserModel.is_active == filters.is_active)

                    if filters.email:
                        stmt = stmt.where(UserModel.email.ilike(f"%{filters.email}%"))

                    if filters.username:
                        stmt = stmt.where(
                            UserModel.username.ilike(f"%{filters.username}%")
                        )

                    if filters.full_name:
                        stmt = stmt.where(
                            UserModel.full_name.ilike(f"%{filters.full_name}%")
                        )

                # Get total count
                count_stmt = select(func.count()).select_from(stmt.subquery())
                count_result = await session.execute(count_stmt)
                total = count_result.scalar() or 0

                # Apply ordering and pagination
                stmt = stmt.order_by(UserModel.created_at.desc())
                stmt = stmt.offset(pagination.offset).limit(pagination.per_page)

                result = await session.execute(stmt)
                user_models = result.scalars().all()

                # Convert to response models
                user_responses = [
                    UserResponse.model_validate(self._model_to_pydantic(m))
                    for m in user_models
                ]

                # Calculate pagination info
                total_pages = math.ceil(total / pagination.per_page) if total > 0 else 0

                self.logger.debug(
                    "Users listed",
                    org_id=org_id,
                    count=len(user_responses),
                    total=total,
                    page=pagination.page,
                )

                return UserList(
                    users=user_responses,
                    total=total,
                    page=pagination.page,
                    per_page=pagination.per_page,
                    total_pages=total_pages,
                )

        except OrganizationNotFoundError:
            raise
        except Exception as e:
            self.logger.error("Error listing users", org_id=org_id, error=str(e))
            raise

    async def delete_user(
        self,
        org_id: str,
        user_id: str,
        deleted_by_user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        session_id: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> bool:
        """
        Soft delete user (set is_active=False) within organization.

        Args:
            org_id: Organization ID
            user_id: User ID
            deleted_by_user_id: ID of user who deleted this user (for audit)
            ip_address: Client IP address (for audit)
            session_id: Session ID (for audit)
            user_agent: Client user agent (for audit)

        Returns:
            True if deleted successfully

        Raises:
            OrganizationNotFoundError: If organization doesn't exist
            UserNotFoundError: If user not found
        """
        try:
            async with db.session() as session:
                # Verify organization exists
                if not await self._verify_organization_exists(org_id):
                    raise OrganizationNotFoundError(
                        f"Organization with ID {org_id} not found"
                    )

                stmt = select(UserModel).where(
                    UserModel.id == user_id,
                    UserModel.organization_id == org_id,
                    UserModel.is_active == True,
                )
                result = await session.execute(stmt)
                user_model = result.scalar_one_or_none()

                if not user_model:
                    raise UserNotFoundError(
                        f"User with ID {user_id} not found in organization {org_id}"
                    )

                # Capture user info for audit before delete
                deleted_user_info = {
                    "email": user_model.email,
                    "username": user_model.username,
                    "full_name": user_model.full_name,
                    "role": user_model.role,
                }

                # Soft delete
                user_model.is_active = False
                user_model.updated_at = datetime.now(timezone.utc)
                await session.flush()

                self.logger.info(
                    "User deleted",
                    org_id=org_id,
                    user_id=user_id,
                    email=user_model.email,
                )

                # Invalidate user cache
                asyncio.create_task(invalidate_users(org_id))

                # Audit logging (non-blocking)
                asyncio.create_task(
                    audit_service.log_event(
                        org_id=org_id,
                        action=AuditAction.DELETE,
                        entity_type=AuditEntityType.USER,
                        entity_id=user_id,
                        user_id=deleted_by_user_id,
                        details={
                            "deleted_values": deleted_user_info,
                            "operation": "delete",
                        },
                        ip_address=ip_address,
                        session_id=session_id,
                        user_agent=user_agent,
                    )
                )

                return True

        except (OrganizationNotFoundError, UserNotFoundError):
            raise
        except Exception as e:
            self.logger.error(
                "Error deleting user", org_id=org_id, user_id=user_id, error=str(e)
            )
            raise

    async def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        try:
            return verify_password(plain_password, hashed_password)
        except Exception as e:
            self.logger.error("Password verification error", error=str(e))
            return False

    async def get_user_by_email(
        self, org_id: str, email: str
    ) -> Optional[UserResponse]:
        """
        Get user by email within organization.

        Args:
            org_id: Organization ID
            email: User email

        Returns:
            User response or None if not found

        Raises:
            OrganizationNotFoundError: If organization doesn't exist
        """
        try:
            async with db.session() as session:
                # Verify organization exists
                if not await self._verify_organization_exists(org_id):
                    raise OrganizationNotFoundError(
                        f"Organization with ID {org_id} not found"
                    )

                stmt = select(UserModel).where(
                    UserModel.organization_id == org_id,
                    UserModel.email == email.lower(),
                    UserModel.is_active == True,
                )
                result = await session.execute(stmt)
                user_model = result.scalar_one_or_none()

                if not user_model:
                    return None

                user = self._model_to_pydantic(user_model)
                return UserResponse.model_validate(user)

        except OrganizationNotFoundError:
            raise
        except Exception as e:
            self.logger.error(
                "Error getting user by email", org_id=org_id, email=email, error=str(e)
            )
            raise

    async def get_user_by_username(
        self, org_id: str, username: str
    ) -> Optional[UserResponse]:
        """
        Get user by username within organization.

        Args:
            org_id: Organization ID
            username: Username

        Returns:
            User response or None if not found

        Raises:
            OrganizationNotFoundError: If organization doesn't exist
        """
        try:
            async with db.session() as session:
                # Verify organization exists
                if not await self._verify_organization_exists(org_id):
                    raise OrganizationNotFoundError(
                        f"Organization with ID {org_id} not found"
                    )

                stmt = select(UserModel).where(
                    UserModel.organization_id == org_id,
                    UserModel.username == username.lower(),
                    UserModel.is_active == True,
                )
                result = await session.execute(stmt)
                user_model = result.scalar_one_or_none()

                if not user_model:
                    return None

                user = self._model_to_pydantic(user_model)
                return UserResponse.model_validate(user)

        except OrganizationNotFoundError:
            raise
        except Exception as e:
            self.logger.error(
                "Error getting user by username",
                org_id=org_id,
                username=username,
                error=str(e),
            )
            raise

    async def _get_user_by_email_for_auth(
        self, org_id: str, email: str
    ) -> Optional[User]:
        """
        Internal method to get user by email for authentication (includes password_hash).
        """
        try:
            async with db.session() as session:
                stmt = select(UserModel).where(
                    UserModel.organization_id == org_id,
                    UserModel.email == email.lower(),
                    UserModel.is_active == True,
                )
                result = await session.execute(stmt)
                user_model = result.scalar_one_or_none()

                if not user_model:
                    return None

                return self._model_to_pydantic(user_model)

        except Exception as e:
            self.logger.error(
                "Error getting user by email for auth",
                org_id=org_id,
                email=email,
                error=str(e),
            )
            return None

    async def _get_user_by_email_simple(self, email: str) -> Optional[User]:
        """
        Simple user lookup by email across all organizations.
        """
        try:
            async with db.session() as session:
                stmt = select(UserModel).where(
                    UserModel.email == email.lower(), UserModel.is_active == True
                )
                result = await session.execute(stmt)
                user_model = result.scalar_one_or_none()

                if not user_model:
                    return None

                return self._model_to_pydantic(user_model)

        except Exception as e:
            self.logger.error("Simple user lookup failed", email=email, error=str(e))
            return None

    async def _get_user_by_email_global_for_auth(self, email: str) -> Optional[User]:
        """
        Internal method for global user search for authentication (includes password_hash).
        """
        try:
            async with db.session() as session:
                stmt = select(UserModel).where(
                    UserModel.email == email.lower(), UserModel.is_active == True
                )
                result = await session.execute(stmt)
                user_model = result.scalar_one_or_none()

                if not user_model:
                    self.logger.info(
                        "Global auth user search completed - no user found",
                        email=email,
                    )
                    return None

                self.logger.info(
                    "Global auth user search found user",
                    email=email,
                    user_id=user_model.id,
                    org_id=user_model.organization_id,
                )
                return self._model_to_pydantic(user_model)

        except Exception as e:
            self.logger.error(
                "Error in global auth user search",
                email=email,
                error=str(e),
            )
            return None

    async def get_user_by_email_global(self, email: str) -> Optional[UserResponse]:
        """
        Get user by email across all organizations (global search).
        """
        try:
            async with db.session() as session:
                stmt = select(UserModel).where(
                    UserModel.email == email.lower(), UserModel.is_active == True
                )
                result = await session.execute(stmt)
                user_model = result.scalar_one_or_none()

                if not user_model:
                    return None

                user = self._model_to_pydantic(user_model)
                return UserResponse.model_validate(user)

        except Exception as e:
            self.logger.error("Error in global user search", email=email, error=str(e))
            return None

    async def update_user_last_login(self, org_id: str, user_id: str) -> bool:
        """
        Update user's last login timestamp.
        """
        try:
            async with db.session() as session:
                stmt = select(UserModel).where(
                    UserModel.id == user_id,
                    UserModel.organization_id == org_id,
                    UserModel.is_active == True,
                )
                result = await session.execute(stmt)
                user_model = result.scalar_one_or_none()

                if not user_model:
                    raise UserNotFoundError(
                        f"User with ID {user_id} not found in organization {org_id}"
                    )

                user_model.last_login = datetime.now(timezone.utc)
                user_model.updated_at = datetime.now(timezone.utc)
                await session.flush()

                self.logger.debug(
                    "User last login updated", org_id=org_id, user_id=user_id
                )

                return True

        except UserNotFoundError:
            raise
        except Exception as e:
            self.logger.error(
                "Error updating user last login",
                org_id=org_id,
                user_id=user_id,
                error=str(e),
            )
            raise


# Global service instance
user_service = UserService()
