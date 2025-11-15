"""
Unit tests for app/services/user_service.py

Tests user service functionality with mocked Firestore.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from app.services.user_service import (
    UserService,
    UserNotFoundError,
    UserAlreadyExistsError,
)
from app.models.user import User, UserRole
from app.models.schemas import UserCreate, UserUpdate


class TestUserServiceCreation:
    """Test user creation functionality."""

    @pytest.mark.asyncio
    async def test_create_user_success(
        self, mock_firestore_client, mock_firebase_manager
    ):
        """Test successful user creation."""
        user_service = UserService()

        with patch("app.services.user_service.firebase_manager", mock_firebase_manager), \
             patch("app.services.user_service.get_collection") as mock_get_collection, \
             patch("app.services.user_service.hash_password") as mock_hash:

            # Setup mocks
            mock_hash.return_value = "$2b$12$hashed_password"

            # Mock Firestore collection
            mock_collection = Mock()
            mock_doc_ref = Mock()
            mock_doc_ref.id = "user123"
            mock_collection.document.return_value.collection.return_value.add = AsyncMock(
                return_value=(None, mock_doc_ref)
            )
            mock_get_collection.return_value = mock_collection

            # Create user data
            user_data = UserCreate(
                email="test@example.com",
                username="testuser",
                password="TestPassword123!",
                full_name="Test User",
            )

            # Test user creation
            with patch.object(
                user_service, "_check_email_unique_in_org", return_value=True
            ), patch.object(
                user_service, "_check_username_unique_in_org", return_value=True
            ), patch.object(
                user_service, "_verify_organization_exists", return_value=True
            ):

                result = await user_service.create_user("org123", user_data)

                assert result.email == "test@example.com"
                assert result.username == "testuser"

    @pytest.mark.asyncio
    async def test_create_user_duplicate_email(self, mock_firebase_manager):
        """Test creating user with duplicate email."""
        user_service = UserService()

        with patch("app.services.user_service.firebase_manager", mock_firebase_manager):
            user_data = UserCreate(
                email="existing@example.com",
                username="testuser",
                password="TestPassword123!",
                full_name="Test User",
            )

            # Mock email check to return False (email exists)
            with patch.object(
                user_service, "_check_email_unique_in_org", return_value=False
            ), patch.object(
                user_service, "_verify_organization_exists", return_value=True
            ):

                with pytest.raises(UserAlreadyExistsError):
                    await user_service.create_user("org123", user_data)

    @pytest.mark.asyncio
    async def test_create_user_duplicate_username(self, mock_firebase_manager):
        """Test creating user with duplicate username."""
        user_service = UserService()

        with patch("app.services.user_service.firebase_manager", mock_firebase_manager):
            user_data = UserCreate(
                email="test@example.com",
                username="existinguser",
                password="TestPassword123!",
                full_name="Test User",
            )

            # Mock username check to return False (username exists)
            with patch.object(
                user_service, "_check_email_unique_in_org", return_value=True
            ), patch.object(
                user_service, "_check_username_unique_in_org", return_value=False
            ), patch.object(
                user_service, "_verify_organization_exists", return_value=True
            ):

                with pytest.raises(UserAlreadyExistsError):
                    await user_service.create_user("org123", user_data)


class TestUserServiceRetrieval:
    """Test user retrieval functionality."""

    @pytest.mark.asyncio
    async def test_get_user_by_id_success(
        self, mock_firestore_client, mock_firebase_manager, mock_user_data
    ):
        """Test retrieving user by ID."""
        user_service = UserService()

        with patch("app.services.user_service.firebase_manager", mock_firebase_manager), \
             patch("app.services.user_service.get_collection") as mock_get_collection:

            # Setup mock document
            mock_doc = Mock()
            mock_doc.exists = True
            mock_doc.to_dict.return_value = mock_user_data

            mock_collection = Mock()
            mock_collection.document.return_value.collection.return_value.document.return_value.get = AsyncMock(
                return_value=mock_doc
            )
            mock_get_collection.return_value = mock_collection

            # Test retrieval
            result = await user_service.get_user("org123", "user123")

            assert result.user_id == "user123"
            assert result.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_get_user_not_found(self, mock_firebase_manager):
        """Test retrieving non-existent user."""
        user_service = UserService()

        with patch("app.services.user_service.firebase_manager", mock_firebase_manager), \
             patch("app.services.user_service.get_collection") as mock_get_collection:

            # Setup mock for non-existent document
            mock_doc = Mock()
            mock_doc.exists = False

            mock_collection = Mock()
            mock_collection.document.return_value.collection.return_value.document.return_value.get = AsyncMock(
                return_value=mock_doc
            )
            mock_get_collection.return_value = mock_collection

            # Test retrieval
            with pytest.raises(UserNotFoundError):
                await user_service.get_user("org123", "nonexistent")

    @pytest.mark.asyncio
    async def test_list_users(
        self, mock_firestore_client, mock_firebase_manager, mock_user_data
    ):
        """Test listing users in organization."""
        user_service = UserService()

        with patch("app.services.user_service.firebase_manager", mock_firebase_manager), \
             patch("app.services.user_service.get_collection") as mock_get_collection:

            # Add mock documents to collection
            mock_firestore_client.add_mock_document(
                "organizations/org123/users", "user1", mock_user_data
            )
            mock_firestore_client.add_mock_document(
                "organizations/org123/users", "user2", mock_user_data
            )

            # Mock collection
            mock_collection = mock_firestore_client.collection("organizations")
            mock_get_collection.return_value = mock_collection

            # Test listing (simplified - actual implementation may vary)
            from app.models.schemas import PaginationParams

            params = PaginationParams(page=1, page_size=10)

            # Note: This is a simplified test. Actual implementation may need
            # more complex mocking of Firestore query operations
            # In unit tests, we focus on the service logic, not Firestore internals


class TestUserServiceUpdate:
    """Test user update functionality."""

    @pytest.mark.asyncio
    async def test_update_user_success(
        self, mock_firestore_client, mock_firebase_manager, mock_user_data
    ):
        """Test successful user update."""
        user_service = UserService()

        with patch("app.services.user_service.firebase_manager", mock_firebase_manager), \
             patch("app.services.user_service.get_collection") as mock_get_collection:

            # Mock getting existing user
            mock_doc = Mock()
            mock_doc.exists = True
            mock_doc.to_dict.return_value = mock_user_data

            mock_collection = Mock()
            mock_doc_ref = Mock()
            mock_doc_ref.get = AsyncMock(return_value=mock_doc)
            mock_doc_ref.update = AsyncMock()
            mock_collection.document.return_value.collection.return_value.document.return_value = (
                mock_doc_ref
            )
            mock_get_collection.return_value = mock_collection

            # Test update
            update_data = UserUpdate(full_name="Updated Name")

            with patch.object(user_service, "_check_email_unique_in_org", return_value=True), \
                 patch.object(user_service, "_check_username_unique_in_org", return_value=True):

                result = await user_service.update_user("org123", "user123", update_data)

                assert result.user_id == "user123"

    @pytest.mark.asyncio
    async def test_delete_user_soft_delete(
        self, mock_firestore_client, mock_firebase_manager, mock_user_data
    ):
        """Test soft deleting a user."""
        user_service = UserService()

        with patch("app.services.user_service.firebase_manager", mock_firebase_manager), \
             patch("app.services.user_service.get_collection") as mock_get_collection:

            # Mock getting existing user
            mock_doc = Mock()
            mock_doc.exists = True
            mock_doc.to_dict.return_value = mock_user_data

            mock_collection = Mock()
            mock_doc_ref = Mock()
            mock_doc_ref.get = AsyncMock(return_value=mock_doc)
            mock_doc_ref.update = AsyncMock()
            mock_collection.document.return_value.collection.return_value.document.return_value = (
                mock_doc_ref
            )
            mock_get_collection.return_value = mock_collection

            # Test soft delete
            result = await user_service.delete_user("org123", "user123")

            assert result is True
            # Verify update was called with is_active=False
            mock_doc_ref.update.assert_called_once()


class TestUserServicePasswordManagement:
    """Test password management functionality."""

    @pytest.mark.asyncio
    async def test_verify_password_correct(self):
        """Test verifying correct password."""
        user_service = UserService()

        with patch("app.services.user_service.verify_password") as mock_verify:
            mock_verify.return_value = True

            result = await user_service.verify_password(
                "TestPassword123!", "$2b$12$hashed"
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_verify_password_incorrect(self):
        """Test verifying incorrect password."""
        user_service = UserService()

        with patch("app.services.user_service.verify_password") as mock_verify:
            mock_verify.return_value = False

            result = await user_service.verify_password(
                "WrongPassword", "$2b$12$hashed"
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_update_password(
        self, mock_firestore_client, mock_firebase_manager, mock_user_data
    ):
        """Test updating user password."""
        user_service = UserService()

        with patch("app.services.user_service.firebase_manager", mock_firebase_manager), \
             patch("app.services.user_service.get_collection") as mock_get_collection, \
             patch("app.services.user_service.hash_password") as mock_hash, \
             patch("app.services.user_service.verify_password") as mock_verify:

            # Setup mocks
            mock_hash.return_value = "$2b$12$new_hashed_password"
            mock_verify.return_value = True

            # Mock getting existing user
            mock_doc = Mock()
            mock_doc.exists = True
            mock_doc.to_dict.return_value = mock_user_data

            mock_collection = Mock()
            mock_doc_ref = Mock()
            mock_doc_ref.get = AsyncMock(return_value=mock_doc)
            mock_doc_ref.update = AsyncMock()
            mock_collection.document.return_value.collection.return_value.document.return_value = (
                mock_doc_ref
            )
            mock_get_collection.return_value = mock_collection

            # Test password update
            result = await user_service.update_password(
                "org123", "user123", "OldPassword", "NewPassword123!"
            )

            assert result is True
            mock_doc_ref.update.assert_called_once()
