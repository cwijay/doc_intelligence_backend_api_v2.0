"""
Unit tests for app/models/organization.py

Tests Organization model functionality.
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from app.models.organization import Organization, PlanType


class TestOrganizationModel:
    """Test Organization model creation and validation."""

    def test_organization_creation_with_required_fields(self, mock_organization_data):
        """Test creating organization with all required fields."""
        org = Organization(**mock_organization_data)

        assert org.id == "org123"
        assert org.name == "Test Organization"
        assert org.domain == "test.com"
        assert org.plan_type == PlanType.FREE
        assert org.is_active is True

    def test_organization_creation_defaults(self):
        """Test organization creation with default values."""
        org = Organization(name="Test Org")

        assert org.plan_type == PlanType.FREE
        assert org.is_active is True
        assert isinstance(org.settings, dict)
        assert len(org.settings) == 0
        assert isinstance(org.created_at, datetime)
        assert isinstance(org.updated_at, datetime)

    def test_plan_type_enum(self):
        """Test PlanType enum values."""
        assert PlanType.FREE == "free"
        assert PlanType.STARTER == "starter"
        assert PlanType.PRO == "pro"

    def test_organization_to_dict(self, mock_organization_data):
        """Test converting organization to dictionary."""
        org = Organization(**mock_organization_data)
        org_dict = org.to_dict()

        assert "id" not in org_dict  # ID excluded
        assert org_dict["name"] == "Test Organization"
        assert org_dict["domain"] == "test.com"
        assert org_dict["plan_type"] == "free"
        assert isinstance(org_dict["created_at"], str)  # ISO format
        assert isinstance(org_dict["updated_at"], str)  # ISO format

    def test_organization_from_dict(self, mock_organization_data):
        """Test creating organization from dictionary."""
        org = Organization.from_dict(mock_organization_data, doc_id="org123")

        assert org.id == "org123"
        assert org.name == "Test Organization"
        assert org.domain == "test.com"

    def test_organization_from_dict_with_datetime_strings(self):
        """Test creating organization from dict with datetime strings."""
        data = {
            "name": "Test Org",
            "domain": "test.com",
            "settings": {},
            "plan_type": "free",
            "is_active": True,
            "created_at": "2024-01-01T12:00:00",
            "updated_at": "2024-01-01T12:00:00",
        }

        org = Organization.from_dict(data, doc_id="org123")

        assert isinstance(org.created_at, datetime)
        assert isinstance(org.updated_at, datetime)


class TestOrganizationProperties:
    """Test Organization model properties and methods."""

    def test_is_premium_property_free(self):
        """Test is_premium property for free plan."""
        org = Organization(name="Test Org", plan_type=PlanType.FREE)

        assert org.is_premium is False

    def test_is_premium_property_starter(self):
        """Test is_premium property for starter plan."""
        org = Organization(name="Test Org", plan_type=PlanType.STARTER)

        assert org.is_premium is True

    def test_is_premium_property_pro(self):
        """Test is_premium property for pro plan."""
        org = Organization(name="Test Org", plan_type=PlanType.PRO)

        assert org.is_premium is True
        assert org.is_pro is True

    def test_is_pro_property(self):
        """Test is_pro property."""
        free_org = Organization(name="Free Org", plan_type=PlanType.FREE)
        starter_org = Organization(name="Starter Org", plan_type=PlanType.STARTER)
        pro_org = Organization(name="Pro Org", plan_type=PlanType.PRO)

        assert free_org.is_pro is False
        assert starter_org.is_pro is False
        assert pro_org.is_pro is True

    def test_update_timestamp(self, mock_organization_data):
        """Test updating timestamp."""
        org = Organization(**mock_organization_data)
        original_updated_at = org.updated_at

        # Wait a moment and update
        import time
        time.sleep(0.01)
        org.update_timestamp()

        assert org.updated_at > original_updated_at

    def test_organization_with_settings(self):
        """Test organization with custom settings."""
        org = Organization(
            name="Test Org",
            settings={
                "feature_flags": {"ai_enabled": True},
                "limits": {"max_documents": 100},
            },
        )

        assert org.settings["feature_flags"]["ai_enabled"] is True
        assert org.settings["limits"]["max_documents"] == 100

    def test_organization_repr(self):
        """Test organization string representation."""
        org = Organization(id="org123", name="Test Org", plan_type=PlanType.PRO)

        repr_str = repr(org)

        assert "org123" in repr_str
        assert "Test Org" in repr_str
        assert "pro" in repr_str
