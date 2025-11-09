import uuid
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional

from pydantic import BaseModel, Field


class PlanType(str, Enum):
    """Organization plan types."""
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"


class Organization(BaseModel):
    """Organization Firestore model for multi-tenancy."""
    
    # Primary key - Firestore document ID (managed by Firestore)
    id: Optional[str] = Field(None, description="Unique organization identifier (Firestore document ID)")
    
    # Core fields
    name: str = Field(..., description="Organization name (must be unique)")
    domain: Optional[str] = Field(None, description="Organization domain (optional)")
    
    # Settings as dict for flexibility
    settings: Dict[str, Any] = Field(default_factory=dict, description="Organization settings and preferences")
    
    # Plan type
    plan_type: PlanType = Field(default=PlanType.FREE, description="Organization plan type")
    
    # Status
    is_active: bool = Field(default=True, description="Whether organization is active (for soft delete)")
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, description="When organization was created")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="When organization was last updated")
    
    class Config:
        """Pydantic configuration."""
        use_enum_values = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat(),
        }
    
    def __repr__(self) -> str:
        return f"<Organization(id={self.id}, name='{self.name}', plan='{self.plan_type}')>"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert organization to dictionary for Firestore."""
        data = self.model_dump(exclude={'id'})
        # Convert datetime objects to ISO format for Firestore
        if 'created_at' in data:
            data['created_at'] = self.created_at.isoformat()
        if 'updated_at' in data:
            data['updated_at'] = self.updated_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], doc_id: Optional[str] = None) -> "Organization":
        """Create Organization from Firestore document data."""
        # Handle datetime parsing
        if 'created_at' in data and isinstance(data['created_at'], str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if 'updated_at' in data and isinstance(data['updated_at'], str):
            data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        
        # Add document ID if provided
        if doc_id:
            data['id'] = doc_id
            
        return cls(**data)
    
    @property
    def is_premium(self) -> bool:
        """Check if organization has premium plan."""
        return self.plan_type in [PlanType.STARTER, PlanType.PRO]
    
    @property
    def is_pro(self) -> bool:
        """Check if organization has pro plan."""
        return self.plan_type == PlanType.PRO
    
    def update_timestamp(self):
        """Update the updated_at timestamp."""
        self.updated_at = datetime.utcnow()