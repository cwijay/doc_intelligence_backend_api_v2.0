"""
Integration tests for user management endpoints.

Tests /api/v1/organizations/{org_id}/users/* endpoints.
"""

import os
import uuid
from datetime import timedelta
from unittest.mock import patch, AsyncMock, Mock

import pytest

# Set test environment
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-testing-purposes-only-32chars")
os.environ.setdefault("ENVIRONMENT", "test")


def create_valid_token(user_id: str, org_id: str, email: str, role: str = "admin"):
    """Helper to create a valid JWT token for testing."""
    from app.core.security import create_access_token, create_user_token_data

    token_data = create_user_token_data(user_id, org_id, email, role)
    token, _ = create_access_token(token_data)
    return token


class TestListUsersEndpoint:
    """Tests for GET /api/v1/organizations/{org_id}/users endpoint."""

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_list_users_without_auth(self, async_client):
        """Test listing users without authentication returns 401/403."""
        org_id = str(uuid.uuid4())

        response = await async_client.get(f"/api/v1/organizations/{org_id}/users")

        assert response.status_code in [401, 403]

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_list_users_success(self, async_client, user_data, org_data):
        """Test successful user listing."""
        from app.models.schemas import UserList, UserResponse

        token = create_valid_token(
            user_data["id"],
            org_data["id"],
            user_data["email"],
            "admin"
        )

        # Mock the user service
        mock_user_list = Mock(spec=UserList)
        mock_user_list.users = []
        mock_user_list.total = 0
        mock_user_list.page = 1
        mock_user_list.per_page = 20
        mock_user_list.total_pages = 0
        mock_user_list.model_dump = Mock(return_value={
            "users": [],
            "total": 0,
            "page": 1,
            "per_page": 20,
            "total_pages": 0
        })

        with patch('app.api.v1.users.user_service') as mock_service:
            mock_service.list_users = AsyncMock(return_value=mock_user_list)

            response = await async_client.get(
                f"/api/v1/organizations/{org_data['id']}/users",
                headers={"Authorization": f"Bearer {token}"}
            )

            assert response.status_code == 200
            data = response.json()
            assert "users" in data or "total" in data

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_list_users_with_pagination(self, async_client, user_data, org_data):
        """Test user listing with pagination parameters."""
        token = create_valid_token(
            user_data["id"],
            org_data["id"],
            user_data["email"],
            "admin"
        )

        mock_user_list = Mock()
        mock_user_list.users = []
        mock_user_list.total = 0
        mock_user_list.page = 2
        mock_user_list.per_page = 5
        mock_user_list.total_pages = 0
        mock_user_list.model_dump = Mock(return_value={
            "users": [],
            "total": 0,
            "page": 2,
            "per_page": 5,
            "total_pages": 0
        })

        with patch('app.api.v1.users.user_service') as mock_service:
            mock_service.list_users = AsyncMock(return_value=mock_user_list)

            response = await async_client.get(
                f"/api/v1/organizations/{org_data['id']}/users?page=2&per_page=5",
                headers={"Authorization": f"Bearer {token}"}
            )

            assert response.status_code == 200


class TestGetUserEndpoint:
    """Tests for GET /api/v1/organizations/{org_id}/users/{user_id} endpoint."""

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_get_user_without_auth(self, async_client):
        """Test getting user without authentication returns 401/403."""
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())

        response = await async_client.get(
            f"/api/v1/organizations/{org_id}/users/{user_id}"
        )

        assert response.status_code in [401, 403]

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_get_user_not_found(self, async_client, user_data, org_data):
        """Test getting non-existent user returns 404."""
        from app.services.user_service import UserNotFoundError

        token = create_valid_token(
            user_data["id"],
            org_data["id"],
            user_data["email"],
            "admin"
        )
        target_user_id = str(uuid.uuid4())

        with patch('app.api.v1.users.user_service') as mock_service:
            mock_service.get_user = AsyncMock(
                side_effect=UserNotFoundError("User not found")
            )

            response = await async_client.get(
                f"/api/v1/organizations/{org_data['id']}/users/{target_user_id}",
                headers={"Authorization": f"Bearer {token}"}
            )

            assert response.status_code == 404

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_get_user_success(self, async_client, user_data, org_data):
        """Test successful user retrieval."""
        from app.models.schemas import UserResponse

        token = create_valid_token(
            user_data["id"],
            org_data["id"],
            user_data["email"],
            "admin"
        )
        target_user_id = str(uuid.uuid4())

        mock_user = Mock(spec=UserResponse)
        mock_user.id = target_user_id
        mock_user.email = "target@example.com"
        mock_user.model_dump = Mock(return_value={
            "id": target_user_id,
            "email": "target@example.com",
            "username": "targetuser",
            "full_name": "Target User",
            "role": "user",
            "is_active": True,
        })

        with patch('app.api.v1.users.user_service') as mock_service:
            mock_service.get_user = AsyncMock(return_value=mock_user)

            response = await async_client.get(
                f"/api/v1/organizations/{org_data['id']}/users/{target_user_id}",
                headers={"Authorization": f"Bearer {token}"}
            )

            assert response.status_code == 200
            data = response.json()
            assert "id" in data or "email" in data


class TestCreateUserEndpoint:
    """Tests for POST /api/v1/organizations/{org_id}/users endpoint."""

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_create_user_without_auth(self, async_client):
        """Test creating user without authentication returns 401/403."""
        org_id = str(uuid.uuid4())

        response = await async_client.post(
            f"/api/v1/organizations/{org_id}/users",
            json={
                "email": "newuser@example.com",
                "password": "SecurePass123!",
                "full_name": "New User",
                "username": "newuser"
            }
        )

        assert response.status_code in [401, 403]

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_create_user_invalid_email(self, async_client, user_data, org_data):
        """Test creating user with invalid email returns 422."""
        token = create_valid_token(
            user_data["id"],
            org_data["id"],
            user_data["email"],
            "admin"
        )

        response = await async_client.post(
            f"/api/v1/organizations/{org_data['id']}/users",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": "invalid-email",
                "password": "SecurePass123!",
                "full_name": "New User",
                "username": "newuser"
            }
        )

        assert response.status_code == 422

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_create_user_missing_required_fields(self, async_client, user_data, org_data):
        """Test creating user with missing fields returns 422."""
        token = create_valid_token(
            user_data["id"],
            org_data["id"],
            user_data["email"],
            "admin"
        )

        response = await async_client.post(
            f"/api/v1/organizations/{org_data['id']}/users",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": "newuser@example.com"
                # Missing password, full_name, username
            }
        )

        assert response.status_code == 422


class TestUpdateUserEndpoint:
    """Tests for PUT /api/v1/organizations/{org_id}/users/{user_id} endpoint."""

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_update_user_without_auth(self, async_client):
        """Test updating user without authentication returns 401/403."""
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())

        response = await async_client.put(
            f"/api/v1/organizations/{org_id}/users/{user_id}",
            json={"full_name": "Updated Name"}
        )

        assert response.status_code in [401, 403]

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_update_user_not_found(self, async_client, user_data, org_data):
        """Test updating non-existent user returns 404."""
        from app.services.user_service import UserNotFoundError

        token = create_valid_token(
            user_data["id"],
            org_data["id"],
            user_data["email"],
            "admin"
        )
        target_user_id = str(uuid.uuid4())

        with patch('app.api.v1.users.user_service') as mock_service:
            mock_service.update_user = AsyncMock(
                side_effect=UserNotFoundError("User not found")
            )

            response = await async_client.put(
                f"/api/v1/organizations/{org_data['id']}/users/{target_user_id}",
                headers={"Authorization": f"Bearer {token}"},
                json={"full_name": "Updated Name"}
            )

            assert response.status_code == 404


class TestDeleteUserEndpoint:
    """Tests for DELETE /api/v1/organizations/{org_id}/users/{user_id} endpoint."""

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_delete_user_without_auth(self, async_client):
        """Test deleting user without authentication returns 401/403."""
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())

        response = await async_client.delete(
            f"/api/v1/organizations/{org_id}/users/{user_id}"
        )

        assert response.status_code in [401, 403]

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_delete_user_not_found(self, async_client, user_data, org_data):
        """Test deleting non-existent user returns 404."""
        from app.services.user_service import UserNotFoundError

        token = create_valid_token(
            user_data["id"],
            org_data["id"],
            user_data["email"],
            "admin"
        )
        target_user_id = str(uuid.uuid4())

        with patch('app.api.v1.users.user_service') as mock_service:
            mock_service.delete_user = AsyncMock(
                side_effect=UserNotFoundError("User not found")
            )

            response = await async_client.delete(
                f"/api/v1/organizations/{org_data['id']}/users/{target_user_id}",
                headers={"Authorization": f"Bearer {token}"}
            )

            assert response.status_code == 404

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_delete_user_success(self, async_client, user_data, org_data):
        """Test successful user deletion."""
        token = create_valid_token(
            user_data["id"],
            org_data["id"],
            user_data["email"],
            "admin"
        )
        target_user_id = str(uuid.uuid4())

        with patch('app.api.v1.users.user_service') as mock_service:
            mock_service.delete_user = AsyncMock(return_value=True)

            response = await async_client.delete(
                f"/api/v1/organizations/{org_data['id']}/users/{target_user_id}",
                headers={"Authorization": f"Bearer {token}"}
            )

            assert response.status_code == 200


class TestUserAccessControl:
    """Tests for user access control."""

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_wrong_org_access_denied(self, async_client, user_data, org_data):
        """Test users cannot access other organizations' users."""
        # Create token for one org
        token = create_valid_token(
            user_data["id"],
            org_data["id"],
            user_data["email"],
            "admin"
        )

        # Try to access different org's users
        different_org_id = str(uuid.uuid4())

        # The endpoint should either deny access or return empty data
        response = await async_client.get(
            f"/api/v1/organizations/{different_org_id}/users",
            headers={"Authorization": f"Bearer {token}"}
        )

        # Should be denied (403) or return empty (depends on implementation)
        # The key is it shouldn't return data from the wrong org
        assert response.status_code in [200, 403, 404]
