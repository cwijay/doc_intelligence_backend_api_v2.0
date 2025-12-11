"""
Integration tests for authentication workflows.

Tests complete authentication flows end-to-end.
"""

import os
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock, Mock

import pytest

# Set test environment
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-testing-purposes-only-32chars")
os.environ.setdefault("ENVIRONMENT", "test")


class TestLoginLogoutWorkflow:
    """Tests for complete login/logout workflow."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_login_logout_flow(self, async_client):
        """Test complete login followed by logout."""
        # Step 1: Login
        mock_login_response = {
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
            mock_auth.authenticate_user_simple = AsyncMock(return_value=mock_login_response)

            login_response = await async_client.post(
                "/api/v1/auth/login",
                json={
                    "email": "test@example.com",
                    "password": "SecurePass123!"
                }
            )

            assert login_response.status_code == 200
            login_data = login_response.json()
            access_token = login_data.get("access_token")

            # Step 2: Verify token works by accessing /me
            # Need to create a real token for this
            from app.core.security import create_access_token, create_user_token_data

            token_data = create_user_token_data(
                user_id=mock_login_response["user"]["id"],
                org_id=mock_login_response["user"]["org_id"],
                email=mock_login_response["user"]["email"],
                role=mock_login_response["user"]["role"]
            )
            real_token, _ = create_access_token(token_data)

            me_response = await async_client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {real_token}"}
            )
            assert me_response.status_code == 200

            # Step 3: Logout
            with patch('app.core.security.blacklist_token', return_value=True):
                logout_response = await async_client.post(
                    "/api/v1/auth/logout",
                    headers={"Authorization": f"Bearer {real_token}"}
                )

                assert logout_response.status_code == 200


class TestTokenRefreshWorkflow:
    """Tests for token refresh workflow."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_token_refresh_flow(self, async_client):
        """Test token refresh workflow."""
        user_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())

        # Create initial tokens
        from app.core.security import (
            create_access_token,
            create_refresh_token,
            create_user_token_data,
            verify_token,
        )

        # Step 1: Create initial access token
        token_data = create_user_token_data(
            user_id=user_id,
            org_id=org_id,
            email="test@example.com",
            role="user"
        )
        access_token, _ = create_access_token(token_data)
        refresh_token, _ = create_refresh_token(user_id, org_id)

        # Step 2: Verify initial token works
        payload = verify_token(access_token)
        assert payload is not None
        assert payload["sub"] == user_id

        # Step 3: Mock refresh flow
        mock_refresh_response = {
            "access_token": str(uuid.uuid4()),
            "refresh_token": str(uuid.uuid4()),
            "token_type": "bearer",
        }

        with patch('app.api.v1.auth.auth_service') as mock_auth:
            mock_auth.refresh_access_token = AsyncMock(return_value=mock_refresh_response)

            refresh_response = await async_client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": refresh_token}
            )

            assert refresh_response.status_code == 200


class TestSessionManagement:
    """Tests for session management workflow."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_multiple_sessions(self):
        """Test creating multiple sessions for the same user."""
        from app.core.security import (
            create_access_token,
            create_user_token_data,
            get_user_active_session_count,
        )

        user_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())

        token_data = create_user_token_data(
            user_id=user_id,
            org_id=org_id,
            email="test@example.com",
            role="user"
        )

        # Create multiple tokens (sessions)
        tokens = []
        for _ in range(3):
            token, _ = create_access_token(token_data)
            tokens.append(token)

        # Verify session count
        session_count = get_user_active_session_count(user_id, org_id)
        assert session_count >= 3  # May have more from other tests

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_session_invalidation(self):
        """Test invalidating all user sessions except current."""
        from app.core.security import (
            create_access_token,
            create_user_token_data,
            invalidate_user_sessions,
            is_token_blacklisted,
        )

        user_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())

        token_data = create_user_token_data(
            user_id=user_id,
            org_id=org_id,
            email="test@example.com",
            role="user"
        )

        # Create multiple tokens
        tokens = []
        token_ids = []
        for _ in range(3):
            token, token_info = create_access_token(token_data)
            tokens.append(token)
            token_ids.append(token_info.token_id)

        # Invalidate all except the last one
        count = invalidate_user_sessions(user_id, org_id, exclude_token_id=token_ids[-1])

        # Previous tokens should be invalidated
        assert count >= 2


class TestTokenBlacklisting:
    """Tests for token blacklisting workflow."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_blacklisted_token_rejected(self, async_client):
        """Test that blacklisted tokens are rejected."""
        from app.core.security import (
            create_access_token,
            create_user_token_data,
            blacklist_token,
            is_token_blacklisted,
        )

        user_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())

        token_data = create_user_token_data(
            user_id=user_id,
            org_id=org_id,
            email="test@example.com",
            role="user"
        )
        token, _ = create_access_token(token_data)

        # Verify token works initially
        me_response = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert me_response.status_code == 200

        # Blacklist the token
        blacklist_token(token, reason="test_blacklist")
        assert is_token_blacklisted(token) is True

        # Verify token is now rejected
        me_response = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert me_response.status_code == 401


class TestExpiredTokenHandling:
    """Tests for expired token handling."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_expired_access_token_requires_refresh(self, async_client):
        """Test that expired access token requires refresh."""
        from app.core.security import (
            create_access_token,
            create_user_token_data,
        )

        user_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())

        token_data = create_user_token_data(
            user_id=user_id,
            org_id=org_id,
            email="test@example.com",
            role="user"
        )

        # Create expired token
        expired_delta = timedelta(seconds=-60)
        expired_token, _ = create_access_token(token_data, expires_delta=expired_delta)

        # Verify expired token is rejected
        me_response = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"}
        )
        assert me_response.status_code == 401


class TestInvitationWorkflow:
    """Tests for invitation-based registration workflow."""

    @pytest.mark.integration
    def test_invitation_token_generation_and_verification(self):
        """Test invitation token generation and verification."""
        from app.core.security import (
            generate_invitation_token,
            verify_invitation_token,
        )

        org_id = str(uuid.uuid4())
        email = "invitee@example.com"
        role = "user"

        # Generate invitation token
        invitation_token = generate_invitation_token(org_id, email, role)
        assert invitation_token is not None

        # Verify invitation token
        payload = verify_invitation_token(invitation_token)
        assert payload is not None
        assert payload["org_id"] == org_id
        assert payload["email"] == email
        assert payload["role"] == role
        assert payload["type"] == "invitation"

    @pytest.mark.integration
    def test_expired_invitation_token_rejected(self):
        """Test that expired invitation tokens are rejected."""
        from app.core.security import (
            generate_invitation_token,
            verify_invitation_token,
        )

        org_id = str(uuid.uuid4())
        email = "invitee@example.com"
        role = "user"

        # Generate expired invitation token
        invitation_token = generate_invitation_token(
            org_id, email, role, expires_hours=-1
        )

        # Verify expired token is rejected
        payload = verify_invitation_token(invitation_token)
        assert payload is None
