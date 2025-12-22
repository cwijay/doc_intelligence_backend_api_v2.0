from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class PlanType(str, Enum):
    """Organization plan types."""

    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    BUSINESS = "business"


class Organization(BaseModel):
    """Organization model for multi-tenancy."""

    # Primary key
    id: Optional[str] = Field(None, description="Unique organization identifier")

    # Core fields
    name: str = Field(..., description="Organization name (must be unique)")
    domain: Optional[str] = Field(None, description="Organization domain (optional)")

    # Settings as dict for flexibility
    settings: Dict[str, Any] = Field(
        default_factory=dict, description="Organization settings and preferences"
    )

    # Plan type
    plan_type: PlanType = Field(
        default=PlanType.FREE, description="Organization plan type"
    )

    # Subscription reference (for usage tracking)
    plan_id: Optional[str] = Field(
        None, description="Subscription plan ID (FK to subscription_plans)"
    )

    # Subscription status
    subscription_status: str = Field(
        default="active",
        description="Subscription status (active, past_due, canceled, trialing)",
    )

    # Status
    is_active: bool = Field(
        default=True, description="Whether organization is active (for soft delete)"
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When organization was created",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When organization was last updated",
    )

    model_config = ConfigDict(use_enum_values=True)

    @field_serializer("created_at", "updated_at")
    def serialize_datetime(self, value: datetime) -> str:
        """Serialize datetime fields to ISO format."""
        return value.isoformat() if value else None

    def __repr__(self) -> str:
        return (
            f"<Organization(id={self.id}, name='{self.name}', plan='{self.plan_type}')>"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert organization to dictionary for database storage."""
        data = self.model_dump(exclude={"id"})
        # Convert datetime objects to ISO format
        if "created_at" in data:
            data["created_at"] = self.created_at.isoformat()
        if "updated_at" in data:
            data["updated_at"] = self.updated_at.isoformat()
        return data

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], doc_id: Optional[str] = None
    ) -> "Organization":
        """Create Organization from database record."""
        # Handle datetime parsing
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data and isinstance(data["updated_at"], str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])

        # Add document ID if provided
        if doc_id:
            data["id"] = doc_id

        return cls(**data)

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

    def update_timestamp(self):
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now(timezone.utc)
