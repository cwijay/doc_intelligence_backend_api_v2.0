"""
Integration tests for authentication endpoints.

Tests /api/v1/auth/* endpoints.
"""

import os
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock, Mock

import pytest

# Set test environment
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-testing-purposes-only-32chars")
os.environ.setdefault("ENVIRONMENT", "test")


class TestLoginEndpoint:
    """Tests for POST /api/v1/auth/login endpoint."""

    @pytest.mark.api
    @pytest.mark.auth
    @pytest.mark.asyncio
    async def test_login_missing_credentials(self, async_client):
        """Test login with missing credentials returns 422."""
        response = await async_client.post(
            "/api/v1/auth/login",
            json={}
        )

        assert response.status_code == 422

    @pytest.mark.api
    @pytest.mark.auth
    @pytest.mark.asyncio
    async def test_login_invalid_email_format(self, async_client):
        """Test login with invalid email format returns 422."""
        response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": "invalid-email",
                "password": "password123"
            }
        )

        assert response.status_code == 422

    @pytest.mark.api
    @pytest.mark.auth
    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self, async_client):
        """Test login with invalid credentials returns 401."""
        # Mock the auth service to return None (invalid credentials)
        with patch('app.api.v1.auth.auth_service') as mock_auth:
            mock_auth.authenticate_user_simple = AsyncMock(return_value=None)

            response = await async_client.post(
                "/api/v1/auth/login",
                json={
                    "email": "test@example.com",
                    "password": "wrongpassword"
                }
            )

            assert response.status_code == 401
            data = response.json()
            assert "detail" in data

    @pytest.mark.api
    @pytest.mark.auth
    @pytest.mark.asyncio
    async def test_login_success(self, async_client):
        """Test successful login returns tokens."""
        # Mock successful authentication
        mock_token_data = {
            "access_token": str(uuid.uuid4()),
            "refresh_token": str(uuid.uuid4()),
            "token_type": "bearer",
            "user": {
                "id": str(uuid.uuid4()),
                "email": "test@example.com",
                "org_id": str(uuid.uuid4()),
                "role": "user"
            }
        }

        with patch('app.api.v1.auth.auth_service') as mock_auth:
            mock_auth.authenticate_user_simple = AsyncMock(return_value=mock_token_data)

            response = await async_client.post(
                "/api/v1/auth/login",
                json={
                    "email": "test@example.com",
                    "password": "SecurePass123!"
                }
            )

            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert "token_type" in data


class TestLogoutEndpoint:
    """Tests for POST /api/v1/auth/logout endpoint."""

    @pytest.mark.api
    @pytest.mark.auth
    @pytest.mark.asyncio
    async def test_logout_without_token(self, async_client):
        """Test logout without token returns 401/403."""
        response = await async_client.post("/api/v1/auth/logout")

        # Should require authentication
        assert response.status_code in [401, 403]

    @pytest.mark.api
    @pytest.mark.auth
    @pytest.mark.asyncio
    async def test_logout_with_invalid_token(self, async_client):
        """Test logout with invalid token returns 401."""
        response = await async_client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": "Bearer invalid-token"}
        )

        assert response.status_code == 401


class TestRefreshEndpoint:
    """Tests for POST /api/v1/auth/refresh endpoint."""

    @pytest.mark.api
    @pytest.mark.auth
    @pytest.mark.asyncio
    async def test_refresh_missing_token(self, async_client):
        """Test refresh with missing token returns 422."""
        response = await async_client.post(
            "/api/v1/auth/refresh",
            json={}
        )

        assert response.status_code == 422

    @pytest.mark.api
    @pytest.mark.auth
    @pytest.mark.asyncio
    async def test_refresh_invalid_token(self, async_client):
        """Test refresh with invalid token returns 401."""
        with patch('app.api.v1.auth.auth_service') as mock_auth:
            mock_auth.refresh_access_token = AsyncMock(return_value=None)

            response = await async_client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": "invalid-refresh-token"}
            )

            assert response.status_code == 401


class TestRegisterEndpoint:
    """Tests for POST /api/v1/auth/register endpoint."""

    @pytest.mark.api
    @pytest.mark.auth
    @pytest.mark.asyncio
    async def test_register_missing_fields(self, async_client):
        """Test registration with missing fields returns 422."""
        response = await async_client.post(
            "/api/v1/auth/register",
            json={
                "email": "test@example.com"
                # Missing password, full_name, etc.
            }
        )

        assert response.status_code == 422

    @pytest.mark.api
    @pytest.mark.auth
    @pytest.mark.asyncio
    async def test_register_invalid_email(self, async_client):
        """Test registration with invalid email returns 422."""
        response = await async_client.post(
            "/api/v1/auth/register",
            json={
                "email": "invalid-email",
                "password": "SecurePass123!",
                "full_name": "Test User",
                "username": "testuser",
                "org_id": str(uuid.uuid4())
            }
        )

        assert response.status_code == 422

    @pytest.mark.api
    @pytest.mark.auth
    @pytest.mark.asyncio
    async def test_register_weak_password(self, async_client):
        """Test registration with weak password validation."""
        # Note: Password strength is validated at service level
        response = await async_client.post(
            "/api/v1/auth/register",
            json={
                "email": "test@example.com",
                "password": "weak",  # Too short
                "full_name": "Test User",
                "username": "testuser",
                "org_id": str(uuid.uuid4())
            }
        )

        # May return 422 (validation) or 400 (business logic)
        assert response.status_code in [400, 422]


class TestMeEndpoint:
    """Tests for GET /api/v1/auth/me endpoint."""

    @pytest.mark.api
    @pytest.mark.auth
    @pytest.mark.asyncio
    async def test_me_without_token(self, async_client):
        """Test /me without token returns 401/403."""
        response = await async_client.get("/api/v1/auth/me")

        assert response.status_code in [401, 403]

    @pytest.mark.api
    @pytest.mark.auth
    @pytest.mark.asyncio
    async def test_me_with_invalid_token(self, async_client):
        """Test /me with invalid token returns 401."""
        response = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid-token"}
        )

        assert response.status_code == 401

    @pytest.mark.api
    @pytest.mark.auth
    @pytest.mark.asyncio
    async def test_me_with_valid_token(self, async_client, mock_current_user):
        """Test /me with valid token returns user data."""
        from app.core.security import create_access_token, create_user_token_data

        # Create a valid token
        token_data = create_user_token_data(
            user_id=mock_current_user["user_id"],
            org_id=mock_current_user["org_id"],
            email=mock_current_user["email"],
            role=mock_current_user["role"]
        )
        token, _ = create_access_token(token_data)

        response = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "user_id" in data
        assert "org_id" in data
        assert "email" in data


class TestAuthorizationHeader:
    """Tests for Authorization header handling."""

    @pytest.mark.api
    @pytest.mark.auth
    @pytest.mark.asyncio
    async def test_missing_bearer_prefix(self, async_client):
        """Test authorization without 'Bearer' prefix."""
        response = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "some-token-without-bearer"}
        )

        # Should fail with 401 or 403
        assert response.status_code in [401, 403]

    @pytest.mark.api
    @pytest.mark.auth
    @pytest.mark.asyncio
    async def test_empty_bearer_token(self, async_client):
        """Test authorization with empty Bearer token."""
        response = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer "}
        )

        assert response.status_code in [401, 403, 422]


class TestTokenExpiration:
    """Tests for token expiration handling."""

    @pytest.mark.api
    @pytest.mark.auth
    @pytest.mark.asyncio
    async def test_expired_token_rejected(self, async_client, mock_current_user):
        """Test expired tokens are rejected."""
        from app.core.security import create_access_token, create_user_token_data

        # Create an expired token
        token_data = create_user_token_data(
            user_id=mock_current_user["user_id"],
            org_id=mock_current_user["org_id"],
            email=mock_current_user["email"],
            role=mock_current_user["role"]
        )
        # Create token that's already expired
        expired_delta = timedelta(seconds=-60)
        token, _ = create_access_token(token_data, expires_delta=expired_delta)

        response = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 401
