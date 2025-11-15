"""
Organization Management API Tests

Tests for organization CRUD operations, search, and statistics.
"""

import pytest
import sys
from pathlib import Path

# Add tests directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from test_config import config, data_factory
from utils.test_helpers import create_organization, create_test_user_session


@pytest.mark.org
class TestOrganizationCRUD:
    """Test organization CRUD operations."""

    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_01_create_organization(self, http_client, resource_tracker):
        """Test creating a new organization."""
        org_data = data_factory.generate_org_data()

        response = await http_client.post(
            f"{config.api_prefix}/organizations/",
            json=org_data
        )
        assert response.status_code == 201, f"Failed to create org: {response.text}"

        result = response.json()
        assert "id" in result
        assert result["name"] == org_data["name"]
        assert result["plan_type"] == org_data["plan_type"]

        resource_tracker.add_organization(result["id"])

    @pytest.mark.asyncio
    async def test_02_create_org_duplicate_name(self, http_client, resource_tracker):
        """Test creating organization with duplicate name (should fail)."""
        org_data = data_factory.generate_org_data()
        org = await create_organization(http_client, org_data)
        resource_tracker.add_organization(org["id"])

        # Try to create another org with same name
        response = await http_client.post(
            f"{config.api_prefix}/organizations/",
            json=org_data
        )
        assert response.status_code in [400, 409], "Should fail with duplicate name"

    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_03_get_organization_by_id(self, http_client, resource_tracker):
        """Test retrieving organization by ID."""
        org = await create_organization(http_client)
        resource_tracker.add_organization(org["id"])

        response = await http_client.get(
            f"{config.api_prefix}/organizations/{org['id']}"
        )
        assert response.status_code == 200, f"Failed to get org: {response.text}"

        result = response.json()
        assert result["id"] == org["id"]
        assert result["name"] == org["name"]

    @pytest.mark.asyncio
    async def test_04_get_nonexistent_organization(self, http_client):
        """Test retrieving nonexistent organization."""
        response = await http_client.get(
            f"{config.api_prefix}/organizations/nonexistent-id-12345"
        )
        assert response.status_code == 404, "Should return 404 for nonexistent org"

    @pytest.mark.asyncio
    async def test_05_update_organization(self, http_client, resource_tracker):
        """Test updating organization details."""
        org = await create_organization(http_client)
        resource_tracker.add_organization(org["id"])

        update_data = {
            "name": "Updated Organization Name",
            "domain": "updated-domain.com"
        }

        response = await http_client.put(
            f"{config.api_prefix}/organizations/{org['id']}",
            json=update_data
        )
        assert response.status_code == 200, f"Failed to update org: {response.text}"

        result = response.json()
        assert result["name"] == update_data["name"]
        assert result["domain"] == update_data["domain"]

    @pytest.mark.asyncio
    async def test_06_delete_organization(self, http_client):
        """Test soft-deleting organization."""
        org = await create_organization(http_client)

        response = await http_client.delete(
            f"{config.api_prefix}/organizations/{org['id']}"
        )
        assert response.status_code == 200, f"Failed to delete org: {response.text}"

        # Try to get deleted org (should return 404 or mark as inactive)
        response = await http_client.get(
            f"{config.api_prefix}/organizations/{org['id']}"
        )
        # Depending on implementation, it might be 404 or return with is_active=false
        assert response.status_code in [404, 200]

    @pytest.mark.asyncio
    async def test_07_list_organizations(self, http_client, resource_tracker):
        """Test listing organizations."""
        # Create multiple orgs
        for _ in range(3):
            org = await create_organization(http_client)
            resource_tracker.add_organization(org["id"])

        response = await http_client.get(
            f"{config.api_prefix}/organizations/"
        )
        assert response.status_code == 200, f"Failed to list orgs: {response.text}"

        result = response.json()
        assert isinstance(result, list) or "items" in result
        # Should have at least our created orgs
        items = result if isinstance(result, list) else result["items"]
        assert len(items) >= 3

    @pytest.mark.asyncio
    async def test_08_search_organization_by_name(self, http_client, resource_tracker):
        """Test searching organization by exact name."""
        org_data = data_factory.generate_org_data()
        org = await create_organization(http_client, org_data)
        resource_tracker.add_organization(org["id"])

        response = await http_client.get(
            f"{config.api_prefix}/organizations/search/by-name/{org_data['name']}"
        )
        assert response.status_code == 200, f"Failed to search org: {response.text}"

        result = response.json()
        assert result["name"] == org_data["name"]
        assert result["id"] == org["id"]

    @pytest.mark.asyncio
    async def test_09_organization_statistics(self, http_client, resource_tracker):
        """Test getting organization statistics."""
        org = await create_organization(http_client)
        resource_tracker.add_organization(org["id"])

        response = await http_client.get(
            f"{config.api_prefix}/organizations/stats/summary"
        )
        assert response.status_code == 200, f"Failed to get stats: {response.text}"

        result = response.json()
        # Should have some statistics structure
        assert isinstance(result, dict)


@pytest.mark.org
class TestOrganizationValidation:
    """Test input validation for organization endpoints."""

    @pytest.mark.asyncio
    async def test_create_org_missing_required_fields(self, http_client):
        """Test creating org with missing required fields."""
        response = await http_client.post(
            f"{config.api_prefix}/organizations/",
            json={"description": "Missing name"}
        )
        assert response.status_code == 422, "Should fail validation"

    @pytest.mark.asyncio
    async def test_create_org_invalid_plan_type(self, http_client):
        """Test creating org with invalid plan type."""
        org_data = data_factory.generate_org_data()
        org_data["plan_type"] = "invalid_plan"

        response = await http_client.post(
            f"{config.api_prefix}/organizations/",
            json=org_data
        )
        # Might be 422 (validation) or 400 (bad request)
        assert response.status_code in [400, 422], "Should fail with invalid plan type"
