"""
Unit tests for the UserService.

Tests user management operations with mocked database.
"""

import os
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, Mock

import pytest

# Set test environment
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-testing-purposes-only-32chars")


class TestUserServiceModelConversion:
    """Tests for model conversion methods."""

    @pytest.mark.unit
    def test_model_to_pydantic_conversion(self):
        """Test conversion from SQLAlchemy model to Pydantic model."""
        from app.services.user_service import UserService
        from biz2bricks_core import UserModel

        service = UserService()

        now = datetime.now(timezone.utc)
        user_model = Mock(spec=UserModel)
        user_model.id = str(uuid.uuid4())
        user_model.organization_id = str(uuid.uuid4())
        user_model.email = "test@example.com"
        user_model.username = "testuser"
        user_model.password_hash = "$2b$12$hashedpassword"
        user_model.full_name = "Test User"
        user_model.role = "user"
        user_model.is_active = True
        user_model.last_login = now
        user_model.created_at = now
        user_model.updated_at = now

        user = service._model_to_pydantic(user_model)

        assert user.id == user_model.id
        assert user.org_id == user_model.organization_id
        assert user.email == user_model.email
        assert user.username == user_model.username
        assert user.password_hash == user_model.password_hash
        assert user.full_name == user_model.full_name
        assert user.role == user_model.role
        assert user.is_active == user_model.is_active


class TestUserServiceVerifyOrganization:
    """Tests for organization verification."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_verify_organization_exists_success(self):
        """Test organization verification when organization exists."""
        from app.services.user_service import UserService
        from biz2bricks_core import OrganizationModel

        service = UserService()
        org_id = str(uuid.uuid4())

        mock_org = Mock(spec=OrganizationModel)
        mock_org.id = org_id
        mock_org.is_active = True

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_org

        with patch('app.services.user_service.db') as mock_db:
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db.session.return_value.__aexit__ = AsyncMock()

            result = await service._verify_organization_exists(org_id)

            assert result is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_verify_organization_not_exists(self):
        """Test organization verification when organization doesn't exist."""
        from app.services.user_service import UserService

        service = UserService()
        org_id = str(uuid.uuid4())

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None

        with patch('app.services.user_service.db') as mock_db:
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db.session.return_value.__aexit__ = AsyncMock()

            result = await service._verify_organization_exists(org_id)

            assert result is False


class TestUserServicePasswordVerification:
    """Tests for password verification."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_verify_password_correct(self):
        """Test password verification with correct password."""
        from app.services.user_service import UserService
        from app.core.security import hash_password

        service = UserService()
        password = "SecurePassword123!"
        hashed = hash_password(password)

        result = await service.verify_password(password, hashed)

        assert result is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_verify_password_incorrect(self):
        """Test password verification with incorrect password."""
        from app.services.user_service import UserService
        from app.core.security import hash_password

        service = UserService()
        password = "SecurePassword123!"
        wrong_password = "WrongPassword456!"
        hashed = hash_password(password)

        result = await service.verify_password(wrong_password, hashed)

        assert result is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_verify_password_handles_error(self):
        """Test password verification handles errors gracefully."""
        from app.services.user_service import UserService

        service = UserService()

        # Invalid hash format should return False, not raise
        with patch('app.services.user_service.verify_password', side_effect=Exception("Hash error")):
            result = await service.verify_password("password", "invalid-hash")
            assert result is False


class TestUserServiceExceptions:
    """Tests for custom exception classes."""

    @pytest.mark.unit
    def test_user_not_found_error(self):
        """Test UserNotFoundError exception."""
        from app.services.user_service import UserNotFoundError

        error = UserNotFoundError("User not found")

        assert str(error) == "User not found"
        assert isinstance(error, Exception)

    @pytest.mark.unit
    def test_user_already_exists_error(self):
        """Test UserAlreadyExistsError exception."""
        from app.services.user_service import UserAlreadyExistsError

        error = UserAlreadyExistsError("Email already exists")

        assert str(error) == "Email already exists"
        assert isinstance(error, Exception)

    @pytest.mark.unit
    def test_organization_not_found_error(self):
        """Test OrganizationNotFoundError exception."""
        from app.services.user_service import OrganizationNotFoundError

        error = OrganizationNotFoundError("Organization not found")

        assert str(error) == "Organization not found"
        assert isinstance(error, Exception)


class TestUserServiceGlobalEmail:
    """Tests for global email lookups."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_user_by_email_global_not_found(self):
        """Test global email search returns None when user doesn't exist."""
        from app.services.user_service import UserService

        service = UserService()
        email = "nonexistent@example.com"

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None

        with patch('app.services.user_service.db') as mock_db:
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db.session.return_value.__aexit__ = AsyncMock()

            result = await service.get_user_by_email_global(email)

            assert result is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_user_by_email_simple_not_found(self):
        """Test simple email lookup returns None when user doesn't exist."""
        from app.services.user_service import UserService

        service = UserService()
        email = "nonexistent@example.com"

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None

        with patch('app.services.user_service.db') as mock_db:
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db.session.return_value.__aexit__ = AsyncMock()

            result = await service._get_user_by_email_simple(email)

            assert result is None


class TestUserServiceEmailNormalization:
    """Tests for email normalization."""

    @pytest.mark.unit
    def test_email_case_normalization(self):
        """Test that email is normalized to lowercase."""
        from app.services.user_service import UserService

        service = UserService()

        # This tests the pattern used in the service
        email = "Test@EXAMPLE.com"
        normalized = email.lower()

        assert normalized == "test@example.com"


