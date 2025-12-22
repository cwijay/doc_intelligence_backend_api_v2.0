"""Organization schemas for API requests and responses."""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.organization import PlanType
from app.models.schemas.validators import validate_filter_strings, validate_settings


class OrganizationBase(BaseModel):
    """Base organization schema with common fields."""

    name: str = Field(
        ...,
        min_length=2,
        max_length=255,
        description="Organization name",
        example="Acme Corporation",
    )
    domain: Optional[str] = Field(
        None,
        max_length=255,
        description="Organization domain (optional)",
        example="acme.com",
    )
    settings: Dict[str, Any] = Field(
        default_factory=dict,
        description="Organization settings and preferences",
        example={"timezone": "America/New_York", "default_language": "en"},
    )
    plan_type: PlanType = Field(
        default=PlanType.FREE,
        description="Organization plan type",
        example="free",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate organization name."""
        if not v or not v.strip():
            raise ValueError("Organization name cannot be empty")

        # Remove extra whitespace
        v = v.strip()

        # Check for minimum length after stripping
        if len(v) < 2:
            raise ValueError("Organization name must be at least 2 characters long")

        # Check for special characters (allow letters, numbers, spaces, hyphens, underscores)
        if not re.match(r"^[a-zA-Z0-9\s\-_]+$", v):
            raise ValueError(
                "Organization name can only contain letters, numbers, spaces, hyphens, and underscores"
            )

        return v

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: Optional[str]) -> Optional[str]:
        """Validate organization domain."""
        if v is None:
            return v

        v = v.strip().lower()

        if not v:
            return None

        # Basic domain validation regex
        domain_pattern = r"^[a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9]*\.([a-zA-Z]{2,})$"
        if not re.match(domain_pattern, v):
            raise ValueError("Invalid domain format")

        return v

    @field_validator("settings")
    @classmethod
    def validate_settings_field(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Validate organization settings."""
        return validate_settings(v)


class OrganizationCreate(OrganizationBase):
    """Schema for creating a new organization."""

    pass


class OrganizationUpdate(BaseModel):
    """Schema for updating an organization (all fields optional)."""

    name: Optional[str] = Field(
        None,
        min_length=2,
        max_length=255,
        description="Organization name",
        example="Acme Corporation Updated",
    )
    domain: Optional[str] = Field(
        None,
        max_length=255,
        description="Organization domain",
        example="acme-corp.com",
    )
    settings: Optional[Dict[str, Any]] = Field(
        None,
        description="Organization settings and preferences",
        example={"timezone": "Europe/London", "default_language": "en-GB"},
    )
    plan_type: Optional[PlanType] = Field(
        None,
        description="Organization plan type",
        example="starter",
    )

    # Apply same validators as base class
    _validate_name = field_validator("name")(OrganizationBase.validate_name.__func__)
    _validate_domain = field_validator("domain")(
        OrganizationBase.validate_domain.__func__
    )
    _validate_settings = field_validator("settings")(
        OrganizationBase.validate_settings_field.__func__
    )


class OrganizationResponse(OrganizationBase):
    """Schema for organization response."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(
        ...,
        description="Organization unique identifier",
        example="org_abc123xyz",
    )
    plan_id: Optional[str] = Field(
        None,
        description="Subscription plan ID",
        example="plan_starter_monthly",
    )
    subscription_status: str = Field(
        default="active",
        description="Subscription status (active, past_due, canceled, trialing)",
        example="active",
    )
    is_active: bool = Field(
        ...,
        description="Whether organization is active",
        example=True,
    )
    created_at: datetime = Field(
        ...,
        description="When organization was created",
        example="2025-01-15T10:30:00Z",
    )
    updated_at: datetime = Field(
        ...,
        description="When organization was last updated",
        example="2025-01-15T14:45:00Z",
    )

    @property
    def is_premium(self) -> bool:
        """Check if organization has premium plan."""
        return self.plan_type in [PlanType.STARTER, PlanType.PRO, PlanType.BUSINESS]

    @property
    def is_pro(self) -> bool:
        """Check if organization has pro plan."""
        return self.plan_type == PlanType.PRO

    @property
    def is_business(self) -> bool:
        """Check if organization has business plan."""
        return self.plan_type == PlanType.BUSINESS


class OrganizationList(BaseModel):
    """Schema for organization list response with pagination."""

    items: List[OrganizationResponse] = Field(
        ...,
        description="List of organizations",
    )
    total: int = Field(
        ...,
        description="Total number of organizations",
        example=25,
    )
    page: int = Field(
        ...,
        description="Current page number",
        example=1,
    )
    per_page: int = Field(
        ...,
        description="Number of items per page",
        example=20,
    )
    total_pages: int = Field(
        ...,
        description="Total number of pages",
        example=2,
    )

    @property
    def has_next(self) -> bool:
        """Check if there are more pages."""
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        """Check if there are previous pages."""
        return self.page > 1

    @property
    def organizations(self) -> List[OrganizationResponse]:
        """Temporary compatibility alias for legacy callers."""
        return self.items


# Request/Response Models for API endpoints
class OrganizationCreateRequest(OrganizationCreate):
    """Request model for creating organization."""

    pass


class OrganizationUpdateRequest(OrganizationUpdate):
    """Request model for updating organization."""

    pass


class OrganizationDeleteResponse(BaseModel):
    """Response model for organization deletion."""

    success: bool = Field(
        ...,
        description="Whether deletion was successful",
        example=True,
    )
    message: str = Field(
        ...,
        description="Deletion status message",
        example="Organization 'Acme Corporation' deleted successfully",
    )


class OrganizationFilters(BaseModel):
    """Filters for organization listing."""

    name: Optional[str] = Field(
        None,
        description="Filter by organization name (partial match)",
        example="Acme",
    )
    domain: Optional[str] = Field(
        None,
        description="Filter by domain (partial match)",
        example="acme.com",
    )
    plan_type: Optional[PlanType] = Field(
        None,
        description="Filter by plan type",
        example="starter",
    )
    is_active: Optional[bool] = Field(
        None,
        description="Filter by active status",
        example=True,
    )

    @field_validator("name", "domain")
    @classmethod
    def validate_filter_strings_field(cls, v: Optional[str]) -> Optional[str]:
        """Validate and clean filter strings."""
        return validate_filter_strings(v, extra_chars="@")
