import uuid
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional

from pydantic import BaseModel, Field, field_validator


class UserRole(str, Enum):
    """User role types."""
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"


class User(BaseModel):
    """User Firestore model for multi-tenant user management."""
    
    # Primary key - Firestore document ID (managed by Firestore)
    id: Optional[str] = Field(None, description="Unique user identifier (Firestore document ID)")
    
    # Multi-tenancy
    org_id: str = Field(..., description="Organization ID (foreign key)")
    
    # Authentication
    email: str = Field(..., description="User email (unique within organization)")
    username: str = Field(..., description="Username (unique within organization)")
    password_hash: str = Field(..., description="Hashed password")
    
    # Profile
    full_name: str = Field(..., description="User's full name")
    
    # Authorization
    role: UserRole = Field(default=UserRole.USER, description="User role")
    
    # Status
    is_active: bool = Field(default=True, description="Whether user is active (for soft delete)")
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, description="When user was created")
    last_login: Optional[datetime] = Field(None, description="When user last logged in")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="When user was last updated")
    
    class Config:
        """Pydantic configuration."""
        use_enum_values = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat() if dt else None,
        }
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', org_id='{self.org_id}', role='{self.role}')>"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert user to dictionary for Firestore."""
        data = self.model_dump(exclude={'id'})
        # Convert datetime objects to ISO format for Firestore
        if 'created_at' in data and data['created_at']:
            data['created_at'] = self.created_at.isoformat()
        if 'updated_at' in data and data['updated_at']:
            data['updated_at'] = self.updated_at.isoformat()
        if 'last_login' in data and data['last_login']:
            data['last_login'] = self.last_login.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], doc_id: Optional[str] = None) -> "User":
        """Create User from Firestore document data."""
        # Handle datetime parsing
        if 'created_at' in data and isinstance(data['created_at'], str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if 'updated_at' in data and isinstance(data['updated_at'], str):
            data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        if 'last_login' in data and isinstance(data['last_login'], str):
            data['last_login'] = datetime.fromisoformat(data['last_login'])
        
        # Add document ID if provided
        if doc_id:
            data['id'] = doc_id
            
        return cls(**data)
    
    @property
    def is_admin(self) -> bool:
        """Check if user is admin."""
        return self.role == UserRole.ADMIN
    
    @property
    def is_user(self) -> bool:
        """Check if user is regular user."""
        return self.role == UserRole.USER
    
    @property
    def is_viewer(self) -> bool:
        """Check if user is viewer."""
        return self.role == UserRole.VIEWER
    
    @property
    def can_modify(self) -> bool:
        """Check if user can modify data (admin or user)."""
        return self.role in [UserRole.ADMIN, UserRole.USER]
    
    @property
    def can_admin(self) -> bool:
        """Check if user has admin privileges."""
        return self.role == UserRole.ADMIN
    
    def update_timestamp(self):
        """Update the updated_at timestamp."""
        self.updated_at = datetime.utcnow()
    
    def update_last_login(self):
        """Update the last_login timestamp."""
        self.last_login = datetime.utcnow()
        self.update_timestamp()