"""User schemas for API requests and responses."""

import re
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.user import UserRole
from app.models.schemas.validators import validate_filter_strings


class UserBase(BaseModel):
    """Base user schema with common fields."""

    email: str = Field(
        ...,
        min_length=5,
        max_length=255,
        description="User email address",
        example="john.doe@example.com",
    )
    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Username",
        example="johndoe",
    )
    full_name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="User's full name",
        example="John Doe",
    )
    role: UserRole = Field(
        default=UserRole.USER,
        description="User role",
        example="user",
    )

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Validate email format."""
        if not v or not v.strip():
            raise ValueError("Email cannot be empty")

        v = v.strip().lower()

        # Basic email validation regex
        # Allow underscores in domain for test environments (e.g., test-YYYYMMDD_HHMMSS.com)
        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9._-]+\.[a-zA-Z]{2,}$"
        if not re.match(email_pattern, v):
            raise ValueError("Invalid email format")

        return v

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username format."""
        if not v or not v.strip():
            raise ValueError("Username cannot be empty")

        v = v.strip().lower()

        # Username can contain letters, numbers, underscores, hyphens
        if not re.match(r"^[a-z0-9_-]+$", v):
            raise ValueError(
                "Username can only contain letters, numbers, underscores, and hyphens"
            )

        # Must start with letter or number
        if not re.match(r"^[a-z0-9]", v):
            raise ValueError("Username must start with a letter or number")

        # Check for reserved usernames
        reserved = ["admin", "api", "www", "mail", "support", "help", "info", "root"]
        if v in reserved:
            raise ValueError(f"Username '{v}' is reserved")

        return v

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        """Validate full name."""
        if not v or not v.strip():
            raise ValueError("Full name cannot be empty")

        v = v.strip()

        # Allow letters, spaces, apostrophes, hyphens
        if not re.match(r"^[a-zA-Z\s'-]+$", v):
            raise ValueError(
                "Full name can only contain letters, spaces, apostrophes, and hyphens"
            )

        return v


class UserCreate(UserBase):
    """Schema for creating a new user."""

    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="User password",
        example="SecureP@ss123!",
    )

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password strength."""
        from app.core.security import validate_password_strength

        is_valid, error_msg = validate_password_strength(v)
        if not is_valid:
            raise ValueError(error_msg)

        return v


class UserUpdate(BaseModel):
    """Schema for updating a user (all fields optional)."""

    email: Optional[str] = Field(
        None,
        min_length=5,
        max_length=255,
        description="User email address",
        example="john.doe.updated@example.com",
    )
    username: Optional[str] = Field(
        None,
        min_length=3,
        max_length=50,
        description="Username",
        example="johndoe_updated",
    )
    full_name: Optional[str] = Field(
        None,
        min_length=2,
        max_length=100,
        description="User's full name",
        example="John D. Doe",
    )
    role: Optional[UserRole] = Field(
        None,
        description="User role",
        example="admin",
    )
    password: Optional[str] = Field(
        None,
        min_length=8,
        max_length=128,
        description="New password",
        example="NewSecureP@ss456!",
    )

    # Apply same validators as base class
    _validate_email = field_validator("email")(UserBase.validate_email.__func__)
    _validate_username = field_validator("username")(
        UserBase.validate_username.__func__
    )
    _validate_full_name = field_validator("full_name")(
        UserBase.validate_full_name.__func__
    )

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: Optional[str]) -> Optional[str]:
        """Validate password strength if provided."""
        if v is None:
            return v

        from app.core.security import validate_password_strength

        is_valid, error_msg = validate_password_strength(v)
        if not is_valid:
            raise ValueError(error_msg)

        return v


class UserResponse(UserBase):
    """Schema for user response."""

    model_config = ConfigDict(from_attributes=True, exclude={"password_hash"})

    id: str = Field(
        ...,
        description="User unique identifier",
        example="user_abc123xyz",
    )
    org_id: str = Field(
        ...,
        description="Organization ID",
        example="org_xyz789abc",
    )
    is_active: bool = Field(
        ...,
        description="Whether user is active",
        example=True,
    )
    created_at: datetime = Field(
        ...,
        description="When user was created",
        example="2025-01-15T10:30:00Z",
    )
    last_login: Optional[datetime] = Field(
        None,
        description="When user last logged in",
        example="2025-01-16T08:45:00Z",
    )
    updated_at: datetime = Field(
        ...,
        description="When user was last updated",
        example="2025-01-15T14:30:00Z",
    )

    @property
    def is_admin(self) -> bool:
        """Check if user is admin."""
        return self.role == UserRole.ADMIN

    @property
    def can_modify(self) -> bool:
        """Check if user can modify data."""
        return self.role in [UserRole.ADMIN, UserRole.USER]


class UserList(BaseModel):
    """Schema for user list response with pagination."""

    users: List[UserResponse] = Field(
        ...,
        description="List of users",
    )
    total: int = Field(
        ...,
        description="Total number of users",
        example=50,
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
        example=3,
    )

    @property
    def has_next(self) -> bool:
        """Check if there are more pages."""
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        """Check if there are previous pages."""
        return self.page > 1


# Request/Response Models for API endpoints
class UserCreateRequest(UserCreate):
    """Request model for creating user."""

    pass


class UserUpdateRequest(UserUpdate):
    """Request model for updating user."""

    pass


class UserDeleteResponse(BaseModel):
    """Response model for user deletion."""

    success: bool = Field(
        ...,
        description="Whether deletion was successful",
        example=True,
    )
    message: str = Field(
        ...,
        description="Deletion status message",
        example="User 'johndoe' deleted successfully",
    )


class UserFilters(BaseModel):
    """Filters for user listing within organization."""

    email: Optional[str] = Field(
        None,
        description="Filter by email (partial match)",
        example="john",
    )
    username: Optional[str] = Field(
        None,
        description="Filter by username (partial match)",
        example="john",
    )
    full_name: Optional[str] = Field(
        None,
        description="Filter by full name (partial match)",
        example="John",
    )
    role: Optional[UserRole] = Field(
        None,
        description="Filter by role",
        example="user",
    )
    is_active: Optional[bool] = Field(
        None,
        description="Filter by active status",
        example=True,
    )

    @field_validator("email", "username", "full_name")
    @classmethod
    def validate_filter_strings_field(cls, v: Optional[str]) -> Optional[str]:
        """Validate and clean filter strings."""
        return validate_filter_strings(v, extra_chars="@'")
