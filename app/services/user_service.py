import math
from typing import Optional
from datetime import datetime

from google.cloud.firestore_v1 import FieldFilter

from app.models.user import User
from app.models.schemas import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserList,
    PaginationParams,
    UserFilters,
)
from app.core.firebase_client import (
    get_collection,
    firebase_manager,
)
from app.core.security import hash_password, verify_password
from app.core.logging import get_service_logger

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

    def _get_users_collection(self, org_id: str):
        """Get the users subcollection for an organization."""
        return get_collection("organizations").document(org_id).collection("users")

    async def _verify_organization_exists(self, org_id: str) -> bool:
        """Verify that an organization exists and is active."""
        try:
            # Check if firebase is initialized
            if not firebase_manager.is_initialized:
                self.logger.warning(
                    "Firebase not initialized when verifying organization",
                    org_id=org_id,
                )
                return False

            org_doc = await get_collection("organizations").document(org_id).get()
            if not org_doc.exists:
                self.logger.debug("Organization document does not exist", org_id=org_id)
                return False

            org_data = org_doc.to_dict()
            is_active = org_data.get("is_active", False)
            self.logger.debug(
                "Organization verification result", org_id=org_id, is_active=is_active
            )
            return is_active
        except Exception as e:
            self.logger.error(
                "Error verifying organization",
                org_id=org_id,
                error=str(e),
                exc_info=True,
            )
            return False

    async def _check_email_unique_in_org(
        self, org_id: str, email: str, exclude_user_id: Optional[str] = None
    ) -> bool:
        """Check if email is unique within the organization."""
        try:
            collection = self._get_users_collection(org_id)
            query = collection.where(filter=FieldFilter("email", "==", email.lower()))

            docs = query.stream()
            async for doc in docs:
                # If we're updating a user, exclude their current ID
                if exclude_user_id and doc.id == exclude_user_id:
                    continue

                user_data = doc.to_dict()
                # Only check active users
                if user_data.get("is_active", True):
                    return False

            return True
        except Exception as e:
            self.logger.error(
                "Error checking email uniqueness",
                org_id=org_id,
                email=email,
                error=str(e),
            )
            return False

    async def _check_username_unique_in_org(
        self, org_id: str, username: str, exclude_user_id: Optional[str] = None
    ) -> bool:
        """Check if username is unique within the organization."""
        try:
            collection = self._get_users_collection(org_id)
            query = collection.where(
                filter=FieldFilter("username", "==", username.lower())
            )

            docs = query.stream()
            async for doc in docs:
                # If we're updating a user, exclude their current ID
                if exclude_user_id and doc.id == exclude_user_id:
                    continue

                user_data = doc.to_dict()
                # Only check active users
                if user_data.get("is_active", True):
                    return False

            return True
        except Exception as e:
            self.logger.error(
                "Error checking username uniqueness",
                org_id=org_id,
                username=username,
                error=str(e),
            )
            return False

    async def create_user(self, org_id: str, user_data: UserCreate) -> UserResponse:
        """
        Create a new user in the specified organization.

        Args:
            org_id: Organization ID
            user_data: User creation data

        Returns:
            Created user response

        Raises:
            OrganizationNotFoundError: If organization doesn't exist
            UserAlreadyExistsError: If email or username already exists in org
        """
        try:
            # Verify organization exists
            if not await self._verify_organization_exists(org_id):
                raise OrganizationNotFoundError(
                    f"Organization with ID {org_id} not found"
                )

            # Check email uniqueness within organization
            if not await self._check_email_unique_in_org(org_id, user_data.email):
                raise UserAlreadyExistsError(
                    f"User with email '{user_data.email}' already exists in organization"
                )

            # Check username uniqueness within organization
            if not await self._check_username_unique_in_org(org_id, user_data.username):
                raise UserAlreadyExistsError(
                    f"User with username '{user_data.username}' already exists in organization"
                )

            # Hash password
            password_hash = hash_password(user_data.password)

            # Create new user
            user = User(
                org_id=org_id,
                email=user_data.email.lower(),
                username=user_data.username.lower(),
                password_hash=password_hash,
                full_name=user_data.full_name,
                role=user_data.role,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )

            # Add to Firestore subcollection
            collection = self._get_users_collection(org_id)
            timestamp, doc_ref = await collection.add(user.to_dict())
            user_id = doc_ref.id
            user.id = user_id

            self.logger.info(
                "User created", org_id=org_id, user_id=user_id, email=user.email
            )

            return UserResponse.model_validate(user)

        except (OrganizationNotFoundError, UserAlreadyExistsError):
            raise
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
            User response

        Raises:
            OrganizationNotFoundError: If organization doesn't exist
            UserNotFoundError: If user not found
        """
        try:
            # Verify organization exists
            if not await self._verify_organization_exists(org_id):
                raise OrganizationNotFoundError(
                    f"Organization with ID {org_id} not found"
                )

            doc_ref = self._get_users_collection(org_id).document(user_id)
            doc = await doc_ref.get()

            if not doc.exists:
                raise UserNotFoundError(
                    f"User with ID {user_id} not found in organization {org_id}"
                )

            user_data = doc.to_dict()
            user = User.from_dict(user_data, doc.id)

            if not user.is_active:
                raise UserNotFoundError(
                    f"User with ID {user_id} not found in organization {org_id}"
                )

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
        self, org_id: str, user_id: str, update_data: UserUpdate
    ) -> UserResponse:
        """
        Update user within organization.

        Args:
            org_id: Organization ID
            user_id: User ID
            update_data: Update data

        Returns:
            Updated user response

        Raises:
            OrganizationNotFoundError: If organization doesn't exist
            UserNotFoundError: If user not found
            UserAlreadyExistsError: If email/username conflict occurs
        """
        try:
            # Verify organization exists
            if not await self._verify_organization_exists(org_id):
                raise OrganizationNotFoundError(
                    f"Organization with ID {org_id} not found"
                )

            # Get existing user
            doc_ref = self._get_users_collection(org_id).document(user_id)
            doc = await doc_ref.get()

            if not doc.exists:
                raise UserNotFoundError(
                    f"User with ID {user_id} not found in organization {org_id}"
                )

            user_data = doc.to_dict()
            user = User.from_dict(user_data, doc.id)

            if not user.is_active:
                raise UserNotFoundError(
                    f"User with ID {user_id} not found in organization {org_id}"
                )

            # Check email uniqueness if email is being updated
            if update_data.email and update_data.email.lower() != user.email:
                if not await self._check_email_unique_in_org(
                    org_id, update_data.email, user_id
                ):
                    raise UserAlreadyExistsError(
                        f"User with email '{update_data.email}' already exists in organization"
                    )

            # Check username uniqueness if username is being updated
            if update_data.username and update_data.username.lower() != user.username:
                if not await self._check_username_unique_in_org(
                    org_id, update_data.username, user_id
                ):
                    raise UserAlreadyExistsError(
                        f"User with username '{update_data.username}' already exists in organization"
                    )

            # Update fields
            update_fields = update_data.model_dump(exclude_unset=True)
            for field, value in update_fields.items():
                if field == "password" and value:
                    # Hash new password
                    user.password_hash = hash_password(value)
                elif field == "email" and value:
                    user.email = value.lower()
                elif field == "username" and value:
                    user.username = value.lower()
                elif hasattr(user, field):
                    setattr(user, field, value)

            # Update timestamp
            user.update_timestamp()

            # Save to Firestore
            await doc_ref.update(user.to_dict())

            self.logger.info(
                "User updated",
                org_id=org_id,
                user_id=user_id,
                updates=list(update_fields.keys()),
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
            # In development, allow graceful fallback when Firestore isn't initialized
            from app.core.config import settings

            if not firebase_manager.is_initialized:
                if settings.is_development:
                    self.logger.warning(
                        "Firestore not initialized; returning empty user list (development mode)",
                        org_id=org_id,
                        page=pagination.page,
                        per_page=pagination.per_page,
                    )
                    return UserList(
                        users=[],
                        total=0,
                        page=pagination.page,
                        per_page=pagination.per_page,
                        total_pages=0,
                    )
                # In non-development environments, fail fast with a clear error
                raise RuntimeError("Firebase not initialized")

            # Verify organization exists
            if not await self._verify_organization_exists(org_id):
                raise OrganizationNotFoundError(
                    f"Organization with ID {org_id} not found"
                )

            collection = self._get_users_collection(org_id)

            # Build query with filters
            query = collection
            firestore_filters = []

            # Always filter for active users
            firestore_filters.append(FieldFilter("is_active", "==", True))

            if filters:
                if filters.role:
                    firestore_filters.append(
                        FieldFilter("role", "==", filters.role.value)
                    )

                if filters.is_active is not None:
                    # Update the active filter
                    firestore_filters[-1] = FieldFilter(
                        "is_active", "==", filters.is_active
                    )

            # Apply filters
            for filter_obj in firestore_filters:
                query = query.where(filter=filter_obj)

            # Order by created_at descending
            from google.cloud.firestore import Query

            query = query.order_by("created_at", direction=Query.DESCENDING)

            # Get all documents for filtering and counting
            docs = query.stream()
            all_users = []

            async for doc in docs:
                user_data = doc.to_dict()
                user = User.from_dict(user_data, doc.id)

                # Apply client-side filters for text search (Firestore doesn't support ILIKE)
                if filters:
                    if (
                        filters.email
                        and filters.email.lower() not in user.email.lower()
                    ):
                        continue
                    if (
                        filters.username
                        and filters.username.lower() not in user.username.lower()
                    ):
                        continue
                    if (
                        filters.full_name
                        and filters.full_name.lower() not in user.full_name.lower()
                    ):
                        continue

                all_users.append(user)

            # Get total count
            total = len(all_users)

            # Apply pagination
            start_idx = pagination.offset
            end_idx = start_idx + pagination.per_page
            paginated_users = all_users[start_idx:end_idx]

            # Convert to response models
            user_responses = [
                UserResponse.model_validate(user) for user in paginated_users
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

    async def delete_user(self, org_id: str, user_id: str) -> bool:
        """
        Soft delete user (set is_active=False) within organization.

        Args:
            org_id: Organization ID
            user_id: User ID

        Returns:
            True if deleted successfully

        Raises:
            OrganizationNotFoundError: If organization doesn't exist
            UserNotFoundError: If user not found
        """
        try:
            # Verify organization exists
            if not await self._verify_organization_exists(org_id):
                raise OrganizationNotFoundError(
                    f"Organization with ID {org_id} not found"
                )

            # Get user
            doc_ref = self._get_users_collection(org_id).document(user_id)
            doc = await doc_ref.get()

            if not doc.exists:
                raise UserNotFoundError(
                    f"User with ID {user_id} not found in organization {org_id}"
                )

            user_data = doc.to_dict()
            user = User.from_dict(user_data, doc.id)

            if not user.is_active:
                raise UserNotFoundError(
                    f"User with ID {user_id} not found in organization {org_id}"
                )

            # Soft delete - update is_active to False
            await doc_ref.update(
                {"is_active": False, "updated_at": datetime.utcnow().isoformat()}
            )

            self.logger.info(
                "User deleted", org_id=org_id, user_id=user_id, email=user.email
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
        """
        Verify a password against its hash.

        Args:
            plain_password: Plain text password
            hashed_password: Hashed password

        Returns:
            True if password matches
        """
        try:
            self.logger.info(
                "Verifying password",
                has_password=bool(plain_password),
                has_hash=bool(hashed_password),
                hash_starts_with=hashed_password[:10] if hashed_password else None,
            )

            result = verify_password(plain_password, hashed_password)

            self.logger.info(
                "Password verification result",
                verified=result,
                hash_length=len(hashed_password) if hashed_password else 0,
            )

            return result
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
            # Verify organization exists
            if not await self._verify_organization_exists(org_id):
                raise OrganizationNotFoundError(
                    f"Organization with ID {org_id} not found"
                )

            collection = self._get_users_collection(org_id)
            query = collection.where(filter=FieldFilter("email", "==", email.lower()))

            docs = query.stream()
            async for doc in docs:
                user_data = doc.to_dict()
                user = User.from_dict(user_data, doc.id)

                if user.is_active:
                    return UserResponse.model_validate(user)

            return None

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
            # Verify organization exists
            if not await self._verify_organization_exists(org_id):
                raise OrganizationNotFoundError(
                    f"Organization with ID {org_id} not found"
                )

            collection = self._get_users_collection(org_id)
            query = collection.where(
                filter=FieldFilter("username", "==", username.lower())
            )

            docs = query.stream()
            async for doc in docs:
                user_data = doc.to_dict()
                user = User.from_dict(user_data, doc.id)

                if user.is_active:
                    return UserResponse.model_validate(user)

            return None

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

        This method returns the raw User model object including password_hash
        for authentication purposes. Should only be used internally by auth service.

        Args:
            org_id: Organization ID
            email: User email

        Returns:
            User model object or None if not found
        """
        try:
            # Verify organization exists
            if not await self._verify_organization_exists(org_id):
                raise OrganizationNotFoundError(
                    f"Organization with ID {org_id} not found"
                )

            collection = self._get_users_collection(org_id)
            query = collection.where(filter=FieldFilter("email", "==", email.lower()))

            docs = query.stream()
            async for doc in docs:
                user_data = doc.to_dict()
                user = User.from_dict(user_data, doc.id)

                if user.is_active:
                    return user

            return None

        except OrganizationNotFoundError:
            raise
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

        Args:
            email: User email

        Returns:
            User model object or None if not found
        """
        try:
            self.logger.info("Starting simple user lookup", email=email)

            # Check if firebase is initialized
            if not firebase_manager.is_initialized:
                self.logger.error(
                    "Firebase not initialized for simple user lookup", email=email
                )
                return None

            self.logger.info(
                "Firebase is initialized, proceeding with user lookup", email=email
            )

            # Get all organizations
            orgs_collection = get_collection("organizations")
            orgs_query = orgs_collection.where(
                filter=FieldFilter("is_active", "==", True)
            )

            self.logger.info(
                "Created organizations query, fetching active organizations",
                email=email,
            )
            orgs_docs = orgs_query.stream()

            # Search each organization for the user
            organizations_searched = 0
            async for org_doc in orgs_docs:
                org_id = org_doc.id
                org_data = org_doc.to_dict()
                organizations_searched += 1

                self.logger.info(
                    "Searching organization for user",
                    org_id=org_id,
                    org_name=org_data.get("name", "unknown"),
                    email=email,
                    org_active=org_data.get("is_active", False),
                )

                try:
                    collection = self._get_users_collection(org_id)
                    query = collection.where(
                        filter=FieldFilter("email", "==", email.lower())
                    )
                    docs = query.stream()

                    users_found_in_org = 0
                    async for doc in docs:
                        users_found_in_org += 1
                        user_data = doc.to_dict()
                        user = User.from_dict(user_data, doc.id)

                        self.logger.info(
                            "Found user in organization",
                            email=email,
                            user_id=user.id,
                            org_id=org_id,
                            user_active=user.is_active,
                            has_password=bool(user.password_hash),
                        )

                        if user.is_active:
                            self.logger.info(
                                "Returning active user",
                                email=email,
                                user_id=user.id,
                                org_id=org_id,
                            )
                            return user
                        else:
                            self.logger.warning(
                                "User found but inactive",
                                email=email,
                                user_id=user.id,
                                org_id=org_id,
                            )

                    if users_found_in_org == 0:
                        self.logger.debug(
                            "No users found in organization", org_id=org_id, email=email
                        )

                except Exception as org_error:
                    self.logger.error(
                        "Error searching organization",
                        org_id=org_id,
                        email=email,
                        error=str(org_error),
                    )
                    continue

            self.logger.warning(
                "User not found in any organization",
                email=email,
                organizations_searched=organizations_searched,
            )
            return None

        except Exception as e:
            self.logger.error("Simple user lookup failed", email=email, error=str(e))
            return None

    async def _get_user_by_email_global_for_auth(self, email: str) -> Optional[User]:
        """
        Internal method for global user search for authentication (includes password_hash).

        This method searches across all organizations to find a user by email
        and returns the raw User model object including password_hash
        for authentication purposes. Should only be used internally by auth service.

        Args:
            email: User email

        Returns:
            User model object or None if not found
        """
        import asyncio

        max_retries = 3
        retry_delay = 0.1  # 100ms delay between retries

        for attempt in range(max_retries):
            try:
                # Check if firebase is initialized
                if not firebase_manager.is_initialized:
                    self.logger.warning(
                        "Firebase not initialized for global auth user search",
                        email=email,
                        attempt=attempt + 1,
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        continue
                    return None

                self.logger.debug(
                    "Starting global user search for auth",
                    email=email,
                    attempt=attempt + 1,
                    max_retries=max_retries,
                )

                # Get all organizations first with timeout
                orgs_collection = get_collection("organizations")
                orgs_query = orgs_collection.where(
                    filter=FieldFilter("is_active", "==", True)
                )

                # Get all org documents with better error handling
                try:
                    org_docs = orgs_query.stream()
                    organizations_searched = 0

                    async for org_doc in org_docs:
                        org_id = org_doc.id
                        organizations_searched += 1
                        self.logger.debug(
                            "Searching in organization for auth",
                            org_id=org_id,
                            email=email,
                            org_count=organizations_searched,
                        )

                        try:
                            # Search for user in this organization using internal auth method
                            user = await self._get_user_by_email_for_auth(org_id, email)
                            if user:
                                self.logger.info(
                                    "Global auth user search found user",
                                    email=email,
                                    user_id=user.id,
                                    org_id=org_id,
                                    organizations_searched=organizations_searched,
                                    attempt=attempt + 1,
                                )
                                return user
                        except Exception as org_search_error:
                            # Log but continue searching in other orgs
                            self.logger.debug(
                                "Error searching in specific org for auth",
                                org_id=org_id,
                                email=email,
                                error=str(org_search_error),
                                error_type=type(org_search_error).__name__,
                            )
                            continue

                    self.logger.info(
                        "Global auth user search completed - no user found",
                        email=email,
                        organizations_searched=organizations_searched,
                        attempt=attempt + 1,
                    )
                    return None

                except Exception as query_error:
                    self.logger.warning(
                        "Error executing organizations query",
                        email=email,
                        error=str(query_error),
                        error_type=type(query_error).__name__,
                        attempt=attempt + 1,
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(
                            retry_delay * (2**attempt)
                        )  # Exponential backoff
                        continue
                    raise query_error

            except Exception as e:
                self.logger.error(
                    "Error in global auth user search",
                    email=email,
                    error=str(e),
                    error_type=type(e).__name__,
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    exc_info=True,
                )

                if attempt < max_retries - 1:
                    # Wait before retrying with exponential backoff
                    wait_time = retry_delay * (2**attempt)
                    self.logger.info(
                        "Retrying global user search",
                        email=email,
                        attempt=attempt + 1,
                        wait_time=wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    # Final attempt failed
                    self.logger.error(
                        "Global auth user search failed after all retries",
                        email=email,
                        attempts=max_retries,
                    )
                    return None

        return None

    async def get_user_by_email_global(self, email: str) -> Optional[UserResponse]:
        """
        Get user by email across all organizations (global search).

        This method searches across all organizations to find a user by email.
        If multiple users exist with the same email in different orgs,
        returns the first active user found.

        Args:
            email: User email

        Returns:
            User response or None if not found
        """
        try:
            # Check if firebase is initialized
            if not firebase_manager.is_initialized:
                self.logger.warning(
                    "Firebase not initialized for global user search", email=email
                )
                return None

            self.logger.debug("Starting global user search", email=email)

            # Get all organizations first
            orgs_collection = get_collection("organizations")
            orgs_query = orgs_collection.where(
                filter=FieldFilter("is_active", "==", True)
            )

            # Get all org documents
            org_docs = orgs_query.stream()
            async for org_doc in org_docs:
                org_id = org_doc.id
                self.logger.debug(
                    "Searching in organization", org_id=org_id, email=email
                )

                try:
                    # Search for user in this organization using existing method
                    user = await self.get_user_by_email(org_id, email)
                    if user:
                        self.logger.debug(
                            "Global user search found user",
                            email=email,
                            user_id=user.id,
                            org_id=org_id,
                        )
                        return user
                except Exception as e:
                    # Log but continue searching in other orgs
                    self.logger.debug(
                        "Error searching in org",
                        org_id=org_id,
                        email=email,
                        error=str(e),
                    )
                    continue

            self.logger.debug("Global user search - no user found", email=email)
            return None

        except Exception as e:
            self.logger.error("Error in global user search", email=email, error=str(e))
            return None

    async def update_user_last_login(self, org_id: str, user_id: str) -> bool:
        """
        Update user's last login timestamp.

        Args:
            org_id: Organization ID
            user_id: User ID

        Returns:
            True if updated successfully

        Raises:
            OrganizationNotFoundError: If organization doesn't exist
            UserNotFoundError: If user not found
        """
        try:
            # Verify organization exists
            if not await self._verify_organization_exists(org_id):
                raise OrganizationNotFoundError(
                    f"Organization with ID {org_id} not found"
                )

            # Get user
            doc_ref = self._get_users_collection(org_id).document(user_id)
            doc = await doc_ref.get()

            if not doc.exists:
                raise UserNotFoundError(
                    f"User with ID {user_id} not found in organization {org_id}"
                )

            user_data = doc.to_dict()
            user = User.from_dict(user_data, doc.id)

            if not user.is_active:
                raise UserNotFoundError(
                    f"User with ID {user_id} not found in organization {org_id}"
                )

            # Update last login
            await doc_ref.update(
                {
                    "last_login": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                }
            )

            self.logger.debug("User last login updated", org_id=org_id, user_id=user_id)

            return True

        except (OrganizationNotFoundError, UserNotFoundError):
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
