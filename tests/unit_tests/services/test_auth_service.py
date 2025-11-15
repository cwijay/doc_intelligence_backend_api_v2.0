"""
Unit tests for app/services/auth_service.py

Tests authentication service functionality with mocked dependencies.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from app.services.auth_service import (
    AuthService,
    InvalidCredentialsError,
    UserInactiveError,
    OrganizationInactiveError,
    RegistrationError,
)
from app.models.user import User, UserRole
from app.models.organization import Organization, PlanType


class TestAuthServiceAuthentication:
    """Test authentication functionality."""

    @pytest.mark.asyncio
    async def test_authenticate_user_success(
        self, mock_firebase_manager, mock_user_data, mock_organization_data
    ):
        """Test successful user authentication."""
        auth_service = AuthService()

        # Mock user service
        with patch("app.services.auth_service.user_service") as mock_user_service, \
             patch("app.services.auth_service.organization_service") as mock_org_service, \
             patch("app.services.auth_service.create_user_token_data") as mock_token_data, \
             patch("app.services.auth_service.create_access_token") as mock_create_access:

            # Setup mocks
            user = User(**mock_user_data)
            org = Organization(**mock_organization_data)

            mock_user_service._get_user_by_email_simple = AsyncMock(return_value=user)
            mock_user_service.verify_password = AsyncMock(return_value=True)
            mock_org_service.get_organization = AsyncMock(return_value=org)

            mock_token_data.return_value = {"sub": "user123", "org_id": "org123"}

            # Mock TokenInfo-like object
            mock_token_info = Mock()
            mock_token_info.token_id = "token123"
            mock_create_access.return_value = ("mock_access_token", mock_token_info)

            # Test authentication
            result = await auth_service.authenticate_user(
                email="test@example.com", password="TestPassword123!"
            )

            access_token, refresh_token, user_data = result

            assert access_token == "mock_access_token"
            assert user_data["user_id"] == "user123"
            assert user_data["org_id"] == "org123"

    @pytest.mark.asyncio
    async def test_authenticate_user_not_found(self):
        """Test authentication with non-existent user."""
        auth_service = AuthService()

        with patch("app.services.auth_service.user_service") as mock_user_service:
            mock_user_service._get_user_by_email_simple = AsyncMock(return_value=None)

            with pytest.raises(InvalidCredentialsError) as exc_info:
                await auth_service.authenticate_user(
                    email="nonexistent@example.com", password="password"
                )

            assert "Invalid email or password" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_authenticate_user_wrong_password(self, mock_user_data):
        """Test authentication with wrong password."""
        auth_service = AuthService()

        with patch("app.services.auth_service.user_service") as mock_user_service:
            user = User(**mock_user_data)

            mock_user_service._get_user_by_email_simple = AsyncMock(return_value=user)
            mock_user_service.verify_password = AsyncMock(return_value=False)

            with pytest.raises(InvalidCredentialsError) as exc_info:
                await auth_service.authenticate_user(
                    email="test@example.com", password="WrongPassword"
                )

            assert "Invalid email or password" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_authenticate_inactive_user(self, mock_user_data):
        """Test authentication with inactive user."""
        auth_service = AuthService()

        with patch("app.services.auth_service.user_service") as mock_user_service:
            user_data = mock_user_data.copy()
            user_data["is_active"] = False
            user = User(**user_data)

            mock_user_service._get_user_by_email_simple = AsyncMock(return_value=user)
            mock_user_service.verify_password = AsyncMock(return_value=True)

            with pytest.raises(UserInactiveError) as exc_info:
                await auth_service.authenticate_user(
                    email="test@example.com", password="TestPassword123!"
                )

            assert "User account is inactive" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_authenticate_inactive_organization(
        self, mock_user_data, mock_organization_data
    ):
        """Test authentication with inactive organization."""
        auth_service = AuthService()

        with patch("app.services.auth_service.user_service") as mock_user_service, \
             patch("app.services.auth_service.organization_service") as mock_org_service:

            user = User(**mock_user_data)
            org_data = mock_organization_data.copy()
            org_data["is_active"] = False
            org = Organization(**org_data)

            mock_user_service._get_user_by_email_simple = AsyncMock(return_value=user)
            mock_user_service.verify_password = AsyncMock(return_value=True)
            mock_org_service.get_organization = AsyncMock(return_value=org)

            with pytest.raises(OrganizationInactiveError) as exc_info:
                await auth_service.authenticate_user(
                    email="test@example.com", password="TestPassword123!"
                )

            assert "Organization is inactive" in str(exc_info.value)


class TestAuthServiceRegistration:
    """Test user registration functionality."""

    @pytest.mark.asyncio
    async def test_register_user_success(self):
        """Test successful user registration."""
        auth_service = AuthService()

        with patch("app.services.auth_service.user_service") as mock_user_service, \
             patch("app.services.auth_service.organization_service") as mock_org_service:

            # Mock organization verification
            mock_org_service.get_organization = AsyncMock(
                return_value=Organization(
                    id="org123",
                    name="Test Org",
                    is_active=True,
                )
            )

            # Mock user creation
            mock_user_response = Mock()
            mock_user_response.user_id = "user123"
            mock_user_response.email = "test@example.com"
            mock_user_service.create_user = AsyncMock(return_value=mock_user_response)

            # Test registration
            from app.models.schemas import UserCreate

            user_data = UserCreate(
                email="test@example.com",
                username="testuser",
                password="TestPassword123!",
                full_name="Test User",
            )

            result = await auth_service.register_user("org123", user_data)

            assert result.user_id == "user123"
            assert result.email == "test@example.com"


class TestAuthServiceInvitations:
    """Test invitation functionality."""

    def test_generate_invitation_token(self):
        """Test generating invitation token."""
        auth_service = AuthService()

        with patch("app.services.auth_service.generate_invitation_token") as mock_gen:
            mock_gen.return_value = "invitation_token_12345"

            token = auth_service.generate_organization_invitation(
                org_id="org123", inviter_id="user123"
            )

            assert token == "invitation_token_12345"
            mock_gen.assert_called_once()

    def test_verify_invitation_token_valid(self):
        """Test verifying valid invitation token."""
        auth_service = AuthService()

        with patch("app.services.auth_service.verify_invitation_token") as mock_verify:
            mock_verify.return_value = {"org_id": "org123", "inviter_id": "user123"}

            result = auth_service.verify_invitation_token("valid_token")

            assert result["org_id"] == "org123"
            assert result["inviter_id"] == "user123"

    def test_verify_invitation_token_invalid(self):
        """Test verifying invalid invitation token."""
        auth_service = AuthService()

        with patch("app.services.auth_service.verify_invitation_token") as mock_verify:
            mock_verify.return_value = None

            result = auth_service.verify_invitation_token("invalid_token")

            assert result is None
