"""
Authentication API Tests

Tests for all authentication endpoints including registration, login,
token management, and session validation.
"""

import pytest
from typing import Dict
import sys
from pathlib import Path

# Add tests directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from test_config import config, data_factory
from utils.test_helpers import (
    create_organization,
    register_user,
    login_user,
    logout_user
)


@pytest.mark.auth
class TestAuthenticationFlow:
    """Test complete authentication flow."""

    @pytest.mark.asyncio
    async def test_01_list_organizations_for_registration(self, http_client, resource_tracker):
        """Test listing organizations available for registration."""
        # Create a test org first
        org_data = data_factory.generate_org_data()
        org = await create_organization(http_client, org_data)
        resource_tracker.add_organization(org["id"])

        # List organizations
        response = await http_client.get(f"{config.api_prefix}/auth/organizations")
        assert response.status_code == 200, f"Failed to list orgs: {response.text}"

        orgs = response.json()
        assert isinstance(orgs, list), "Response should be a list"
        assert len(orgs) > 0, "Should have at least one organization"

        # Verify org structure
        first_org = orgs[0]
        assert "id" in first_org
        assert "name" in first_org

    @pytest.mark.asyncio
    async def test_02_organization_lookup_by_name(self, http_client, resource_tracker):
        """Test organization lookup by name."""
        # Create org with known name
        org_data = data_factory.generate_org_data()
        org = await create_organization(http_client, org_data)
        resource_tracker.add_organization(org["id"])

        # Lookup by exact name
        response = await http_client.get(
            f"{config.api_prefix}/auth/organizations/lookup",
            params={"query": org_data["name"]}
        )
        assert response.status_code == 200, f"Failed to lookup org: {response.text}"

        results = response.json()
        assert isinstance(results, list)
        assert len(results) > 0
        assert any(o["name"] == org_data["name"] for o in results)

    @pytest.mark.asyncio
    async def test_03_check_org_name_availability(self, http_client, resource_tracker):
        """Test organization name availability check."""
        # Check non-existent org name (should be available)
        unique_name = data_factory.generate_org_name("UniqueOrg")
        response = await http_client.get(
            f"{config.api_prefix}/auth/organizations/check-availability/{unique_name}"
        )
        assert response.status_code == 200
        result = response.json()
        assert result.get("available") is True

        # Create org and check again (should not be available)
        org_data = data_factory.generate_org_data(name=unique_name)
        org = await create_organization(http_client, org_data)
        resource_tracker.add_organization(org["id"])

        response = await http_client.get(
            f"{config.api_prefix}/auth/organizations/check-availability/{unique_name}"
        )
        assert response.status_code == 200
        result = response.json()
        assert result.get("available") is False

    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_04_register_new_user(self, http_client, resource_tracker):
        """Test user registration with existing organization."""
        # Create organization
        org = await create_organization(http_client)
        resource_tracker.add_organization(org["id"])

        # Register user
        user_data = data_factory.generate_user_data()
        response = await http_client.post(
            f"{config.api_prefix}/auth/register",
            json={
                **user_data,
                "organization_id": org["id"]
            }
        )
        assert response.status_code in [200, 201], f"Registration failed: {response.text}"

        result = response.json()
        assert "message" in result or "user" in result

    @pytest.mark.asyncio
    async def test_05_register_user_duplicate_email(self, http_client, resource_tracker):
        """Test registration with duplicate email (should fail)."""
        # Create org and register first user
        org = await create_organization(http_client)
        resource_tracker.add_organization(org["id"])

        user_data = data_factory.generate_user_data()
        await register_user(http_client, org["id"], user_data)

        # Try to register again with same email
        response = await http_client.post(
            f"{config.api_prefix}/auth/register",
            json={
                **user_data,
                "org_id": org["id"]
            }
        )
        assert response.status_code in [400, 409], "Should fail with duplicate email"

    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_06_login_with_valid_credentials(self, http_client, resource_tracker):
        """Test login with valid email and password."""
        # Create org and register user
        org = await create_organization(http_client)
        resource_tracker.add_organization(org["id"])

        user_data = data_factory.generate_user_data()
        await register_user(http_client, org["id"], user_data)

        # Login
        credentials = await login_user(http_client, user_data["email"], user_data["password"])

        assert credentials.is_authenticated
        assert credentials.access_token is not None
        assert credentials.refresh_token is not None
        assert credentials.user_id is not None
        assert credentials.org_id == org["id"]
        assert credentials.email == user_data["email"]

    @pytest.mark.asyncio
    async def test_07_login_with_invalid_credentials(self, http_client, resource_tracker):
        """Test login with invalid password."""
        # Create org and register user
        org = await create_organization(http_client)
        resource_tracker.add_organization(org["id"])

        user_data = data_factory.generate_user_data()
        await register_user(http_client, org["id"], user_data)

        # Try login with wrong password
        response = await http_client.post(
            f"{config.api_prefix}/auth/login",
            json={
                "email": user_data["email"],
                "password": "WrongPassword123!"
            }
        )
        assert response.status_code in [401, 400], "Should fail with invalid credentials"

    @pytest.mark.asyncio
    async def test_08_login_nonexistent_user(self, http_client):
        """Test login with nonexistent email."""
        response = await http_client.post(
            f"{config.api_prefix}/auth/login",
            json={
                "email": "nonexistent@test.com",
                "password": "Password123!"
            }
        )
        assert response.status_code in [401, 404], "Should fail with nonexistent user"

    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_09_validate_session(self, http_client, resource_tracker):
        """Test session validation endpoint."""
        # Create org, register, and login
        org = await create_organization(http_client)
        resource_tracker.add_organization(org["id"])

        user_data = data_factory.generate_user_data()
        await register_user(http_client, org["id"], user_data)
        credentials = await login_user(http_client, user_data["email"], user_data["password"])

        # Validate session
        response = await http_client.get(
            f"{config.api_prefix}/auth/validate",
            headers=credentials.auth_headers
        )
        assert response.status_code == 200, f"Validation failed: {response.text}"

        result = response.json()
        assert result.get("valid") is True
        assert result.get("user_id") == credentials.user_id
        assert result.get("org_id") == org["id"]

    @pytest.mark.asyncio
    async def test_10_validate_invalid_token(self, http_client):
        """Test session validation with invalid token."""
        response = await http_client.get(
            f"{config.api_prefix}/auth/validate",
            headers={"Authorization": "Bearer invalid-token-12345"}
        )
        assert response.status_code in [401, 403], "Should fail with invalid token"

    @pytest.mark.asyncio
    async def test_11_refresh_session(self, http_client, resource_tracker):
        """Test session refresh with refresh token."""
        # Create org, register, and login
        org = await create_organization(http_client)
        resource_tracker.add_organization(org["id"])

        user_data = data_factory.generate_user_data()
        await register_user(http_client, org["id"], user_data)
        credentials = await login_user(http_client, user_data["email"], user_data["password"])

        # Refresh session
        response = await http_client.post(
            f"{config.api_prefix}/auth/refresh-session",
            json={"refresh_token": credentials.refresh_token}
        )
        assert response.status_code == 200, f"Refresh failed: {response.text}"

        result = response.json()
        assert "access_token" in result
        assert "refresh_token" in result
        # New tokens should be different
        assert result["access_token"] != credentials.access_token

    @pytest.mark.asyncio
    async def test_12_refresh_with_invalid_token(self, http_client):
        """Test session refresh with invalid refresh token."""
        response = await http_client.post(
            f"{config.api_prefix}/auth/refresh-session",
            json={"refresh_token": "invalid-refresh-token"}
        )
        assert response.status_code in [401, 400], "Should fail with invalid refresh token"

    @pytest.mark.asyncio
    async def test_13_logout_user(self, http_client, resource_tracker):
        """Test user logout."""
        # Create org, register, and login
        org = await create_organization(http_client)
        resource_tracker.add_organization(org["id"])

        user_data = data_factory.generate_user_data()
        await register_user(http_client, org["id"], user_data)
        credentials = await login_user(http_client, user_data["email"], user_data["password"])

        # Logout
        await logout_user(http_client, credentials.access_token)

        # Try to use token after logout (should fail)
        response = await http_client.get(
            f"{config.api_prefix}/auth/validate",
            headers=credentials.auth_headers
        )
        assert response.status_code in [401, 403], "Token should be invalid after logout"

    @pytest.mark.asyncio
    async def test_14_logout_all_devices(self, http_client, resource_tracker):
        """Test logout from all devices."""
        # Create org, register user
        org = await create_organization(http_client)
        resource_tracker.add_organization(org["id"])

        user_data = data_factory.generate_user_data()
        await register_user(http_client, org["id"], user_data)

        # Login multiple times (simulate multiple devices)
        creds1 = await login_user(http_client, user_data["email"], user_data["password"])
        creds2 = await login_user(http_client, user_data["email"], user_data["password"])

        # Logout from all devices using first token
        response = await http_client.post(
            f"{config.api_prefix}/auth/logout-all",
            headers=creds1.auth_headers
        )
        assert response.status_code == 200, f"Logout all failed: {response.text}"

        # Both tokens should be invalid now
        response1 = await http_client.get(
            f"{config.api_prefix}/auth/validate",
            headers=creds1.auth_headers
        )
        response2 = await http_client.get(
            f"{config.api_prefix}/auth/validate",
            headers=creds2.auth_headers
        )
        assert response1.status_code in [401, 403]
        assert response2.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_15_debug_session_info(self, http_client, resource_tracker):
        """Test debug session info endpoint."""
        # Create org, register, and login
        org = await create_organization(http_client)
        resource_tracker.add_organization(org["id"])

        user_data = data_factory.generate_user_data()
        await register_user(http_client, org["id"], user_data)
        credentials = await login_user(http_client, user_data["email"], user_data["password"])

        # Get session info
        response = await http_client.get(
            f"{config.api_prefix}/auth/debug/session-info",
            headers=credentials.auth_headers
        )
        assert response.status_code == 200, f"Debug info failed: {response.text}"

        result = response.json()
        assert "session_id" in result
        assert "user_id" in result
        assert "org_id" in result
        assert result["user_id"] == credentials.user_id
        assert result["org_id"] == org["id"]


@pytest.mark.auth
class TestAuthenticationValidation:
    """Test input validation for authentication endpoints."""

    @pytest.mark.asyncio
    async def test_register_missing_required_fields(self, http_client, resource_tracker):
        """Test registration with missing required fields."""
        org = await create_organization(http_client)
        resource_tracker.add_organization(org["id"])

        # Missing password
        response = await http_client.post(
            f"{config.api_prefix}/auth/register",
            json={
                "email": "test@example.com",
                "full_name": "Test User",
                "org_id": org["id"]
                # Missing password
            }
        )
        assert response.status_code == 422, "Should fail validation"

    @pytest.mark.asyncio
    async def test_register_invalid_email_format(self, http_client, resource_tracker):
        """Test registration with invalid email format."""
        org = await create_organization(http_client)
        resource_tracker.add_organization(org["id"])

        response = await http_client.post(
            f"{config.api_prefix}/auth/register",
            json={
                "email": "not-an-email",
                "password": "Password123!",
                "full_name": "Test User",
                "username": "testuser",
                "org_id": org["id"]
            }
        )
        assert response.status_code == 422, "Should fail with invalid email"

    @pytest.mark.asyncio
    async def test_login_missing_credentials(self, http_client):
        """Test login with missing credentials."""
        # Missing password
        response = await http_client.post(
            f"{config.api_prefix}/auth/login",
            json={"email": "test@example.com"}
        )
        assert response.status_code == 422, "Should fail validation"

        # Missing email
        response = await http_client.post(
            f"{config.api_prefix}/auth/login",
            json={"password": "Password123!"}
        )
        assert response.status_code == 422, "Should fail validation"


@pytest.mark.auth
class TestAuthenticationEdgeCases:
    """Test edge cases and error scenarios."""

    @pytest.mark.asyncio
    async def test_concurrent_logins_same_user(self, http_client, resource_tracker):
        """Test multiple concurrent logins for same user."""
        # Create org and register user
        org = await create_organization(http_client)
        resource_tracker.add_organization(org["id"])

        user_data = data_factory.generate_user_data()
        await register_user(http_client, org["id"], user_data)

        # Login multiple times
        creds1 = await login_user(http_client, user_data["email"], user_data["password"])
        creds2 = await login_user(http_client, user_data["email"], user_data["password"])
        creds3 = await login_user(http_client, user_data["email"], user_data["password"])

        # All sessions should be valid
        for creds in [creds1, creds2, creds3]:
            response = await http_client.get(
                f"{config.api_prefix}/auth/validate",
                headers=creds.auth_headers
            )
            assert response.status_code == 200, "All sessions should be valid"

    @pytest.mark.asyncio
    async def test_logout_already_logged_out(self, http_client, resource_tracker):
        """Test logout when already logged out."""
        # Create org, register, and login
        org = await create_organization(http_client)
        resource_tracker.add_organization(org["id"])

        user_data = data_factory.generate_user_data()
        await register_user(http_client, org["id"], user_data)
        credentials = await login_user(http_client, user_data["email"], user_data["password"])

        # First logout should succeed
        await logout_user(http_client, credentials.access_token)

        # Second logout with same token (should fail or handle gracefully)
        response = await http_client.post(
            f"{config.api_prefix}/auth/logout",
            headers=credentials.auth_headers
        )
        assert response.status_code in [401, 403, 200], "Should handle already logged out"
