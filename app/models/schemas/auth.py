"""Authentication request/response schemas.

Provides:
- Login and registration request models
- Token response models
- Logout response models
"""

from typing import Dict, Any, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.organization import PlanType


class LoginRequest(BaseModel):
    """Request model for user login."""

    email: str = Field(..., description="User email address")
    password: str = Field(..., description="User password")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Validate email format."""
        v = v.strip().lower()
        if not v:
            raise ValueError("Email cannot be empty")
        return v


class RegisterRequest(BaseModel):
    """Request model for MVP user registration with organization selection."""

    email: str = Field(..., description="User email address")
    password: str = Field(..., description="User password (min 8 chars)")
    full_name: str = Field(..., description="User's full name")
    username: str = Field(..., description="Username")
    organization_id: str = Field(..., description="ID of the organization to join")

    # Legacy fields - kept for backwards compatibility but deprecated
    organization_name: Optional[str] = Field(
        None, description="Deprecated: use organization_id instead"
    )
    domain: Optional[str] = Field(None, description="Deprecated: not used in MVP")
    plan_type: Optional[PlanType] = Field(
        None, description="Organization plan type to set during registration"
    )

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Validate email format."""
        v = v.strip().lower()
        if not v:
            raise ValueError("Email cannot be empty")
        return v

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username."""
        v = v.strip().lower()
        if not v:
            raise ValueError("Username cannot be empty")
        return v

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        """Validate full name."""
        v = v.strip()
        if not v:
            raise ValueError("Full name cannot be empty")
        return v

    @field_validator("organization_id")
    @classmethod
    def validate_organization_id(cls, v: str) -> str:
        """Validate organization ID."""
        v = v.strip()
        if not v:
            raise ValueError("Organization ID cannot be empty")
        return v


class InviteRegisterRequest(BaseModel):
    """Request model for user registration with invitation token."""

    invitation_token: str = Field(..., description="Valid invitation token")
    password: str = Field(..., description="User password (min 8 chars)")
    full_name: str = Field(..., description="User's full name")
    username: str = Field(..., description="Username")

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username."""
        v = v.strip().lower()
        if not v:
            raise ValueError("Username cannot be empty")
        return v

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        """Validate full name."""
        v = v.strip()
        if not v:
            raise ValueError("Full name cannot be empty")
        return v


class RefreshTokenRequest(BaseModel):
    """Request model for token refresh."""

    refresh_token: str = Field(..., description="Valid refresh token")


class AuthResponse(BaseModel):
    """Response model for authentication operations."""

    access_token: str = Field(..., description="Session access token")
    refresh_token: str = Field(..., description="Session refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Access token expiration in seconds")
    refresh_expires_in: int = Field(
        ..., description="Refresh token expiration in seconds"
    )
    access_token_expires_at: str = Field(
        ..., description="Access token expiration timestamp (ISO format)"
    )
    refresh_token_expires_at: str = Field(
        ..., description="Refresh token expiration timestamp (ISO format)"
    )
    user: Dict[str, Any] = Field(..., description="User information")


class AccessTokenResponse(BaseModel):
    """Response model for access token refresh."""

    access_token: str = Field(..., description="New session access token")
    refresh_token: Optional[str] = Field(
        None, description="New refresh token if rotation is enabled"
    )
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Access token expiration in seconds")
    access_token_expires_at: str = Field(
        ..., description="Access token expiration timestamp (ISO format)"
    )
    refresh_token_expires_at: Optional[str] = Field(
        None, description="Refresh token expiration timestamp if rotated"
    )
    refresh_token_expires_in: Optional[int] = Field(
        None, description="Refresh token expiration in seconds if rotated"
    )
    rotation_enabled: bool = Field(..., description="Whether token rotation is enabled")
    refresh_token_rotated: bool = Field(
        ..., description="Whether refresh token was rotated"
    )


class InvitationTokenResponse(BaseModel):
    """Response model for invitation token creation."""

    invitation_token: str = Field(..., description="Invitation token")
    expires_in_hours: int = Field(..., description="Token expiration in hours")


class LogoutResponse(BaseModel):
    """Response model for logout operation."""

    message: str = Field(..., description="Logout confirmation message")
    logged_out_at: str = Field(..., description="Logout timestamp")


class LogoutAllResponse(BaseModel):
    """Response model for logout-all operation."""

    message: str = Field(..., description="Logout confirmation message")
    sessions_invalidated: int = Field(..., description="Number of sessions invalidated")
    logged_out_at: str = Field(..., description="Logout timestamp")
