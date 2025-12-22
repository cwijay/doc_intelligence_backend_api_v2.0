"""Folder schemas for API requests and responses."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.schemas.validators import validate_filter_strings


class FolderBase(BaseModel):
    """Base folder schema with common fields."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Folder name",
        example="invoices",
    )
    parent_folder_id: Optional[str] = Field(
        None,
        description="Parent folder ID (null for root folders)",
        example="folder_parent123",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate folder name."""
        if not v or not v.strip():
            raise ValueError("Folder name cannot be empty")

        v = v.strip()

        # Check for invalid characters
        invalid_chars = ["/", "\\", ":", "*", "?", '"', "<", ">", "|", "\n", "\r", "\t"]
        for char in invalid_chars:
            if char in v:
                raise ValueError(f"Folder name cannot contain '{char}'")

        # Cannot be just dots
        if v in [".", ".."]:
            raise ValueError("Folder name cannot be '.' or '..'")

        return v


class FolderCreate(FolderBase):
    """Schema for creating a new folder."""

    pass


class FolderUpdate(BaseModel):
    """Schema for updating a folder (all fields optional)."""

    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="Folder name",
        example="invoices-2025",
    )

    # Apply same validators as base class
    _validate_name = field_validator("name")(FolderBase.validate_name.__func__)


class FolderMove(BaseModel):
    """Schema for moving a folder."""

    new_parent_folder_id: Optional[str] = Field(
        None,
        description="New parent folder ID (null to move to root)",
        example="folder_newparent456",
    )


class FolderResponse(FolderBase):
    """Schema for folder response."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(
        ...,
        description="Folder unique identifier",
        example="folder_abc123xyz",
    )
    org_id: str = Field(
        ...,
        description="Organization ID",
        example="org_xyz789abc",
    )
    path: str = Field(
        ...,
        description="Full folder path",
        example="/invoices/2025/q1",
    )
    created_by: str = Field(
        ...,
        description="User ID who created the folder",
        example="user_abc123",
    )
    is_active: bool = Field(
        ...,
        description="Whether folder is active",
        example=True,
    )
    created_at: datetime = Field(
        ...,
        description="When folder was created",
        example="2025-01-15T10:30:00Z",
    )
    updated_at: datetime = Field(
        ...,
        description="When folder was last updated",
        example="2025-01-15T14:45:00Z",
    )

    @property
    def depth(self) -> int:
        """Get folder depth."""
        return len([part for part in self.path.split("/") if part])

    @property
    def is_root(self) -> bool:
        """Check if this is a root folder."""
        return self.parent_folder_id is None


class FolderWithChildren(FolderResponse):
    """Schema for folder response with children."""

    children: List["FolderWithChildren"] = Field(
        default_factory=list,
        description="Child folders (nested)",
    )


class FolderList(BaseModel):
    """Schema for folder list response with pagination."""

    folders: List[FolderResponse] = Field(
        ...,
        description="List of folders",
    )
    total: int = Field(
        ...,
        description="Total number of folders",
        example=35,
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


class FolderTree(BaseModel):
    """Schema for folder tree structure."""

    folders: List[FolderWithChildren] = Field(
        ...,
        description="Root folders with nested children",
    )
    total_folders: int = Field(
        ...,
        description="Total number of folders",
        example=35,
    )


# Request/Response Models for API endpoints
class FolderCreateRequest(FolderCreate):
    """Request model for creating folder."""

    pass


class FolderUpdateRequest(FolderUpdate):
    """Request model for updating folder."""

    pass


class FolderMoveRequest(FolderMove):
    """Request model for moving folder."""

    pass


class FolderDeleteResponse(BaseModel):
    """Response model for folder deletion."""

    success: bool = Field(
        ...,
        description="Whether deletion was successful",
        example=True,
    )
    message: str = Field(
        ...,
        description="Deletion status message",
        example="Folder 'invoices' and its contents deleted successfully",
    )
    deleted_folders: int = Field(
        default=0,
        description="Number of folders deleted",
        example=3,
    )
    deleted_documents: int = Field(
        default=0,
        description="Number of documents deleted",
        example=15,
    )


class FolderFilters(BaseModel):
    """Filters for folder listing."""

    name: Optional[str] = Field(
        None,
        description="Filter by folder name (partial match)",
        example="invoices",
    )
    parent_folder_id: Optional[str] = Field(
        None,
        description="Filter by parent folder ID",
        example="folder_parent123",
    )
    created_by: Optional[str] = Field(
        None,
        description="Filter by creator user ID",
        example="user_abc123",
    )
    is_active: Optional[bool] = Field(
        None,
        description="Filter by active status",
        example=True,
    )

    @field_validator("name")
    @classmethod
    def validate_filter_strings_field(cls, v: Optional[str]) -> Optional[str]:
        """Validate and clean filter strings."""
        return validate_filter_strings(v)
