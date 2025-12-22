"""Base schemas and pagination models.

This module contains base classes and common models used across
all schema modules.
"""

from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    """Pagination parameters."""

    page: int = Field(
        default=1,
        ge=1,
        description="Page number (starts from 1)",
        example=1,
    )
    per_page: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Items per page (max 100)",
        example=20,
    )

    @property
    def offset(self) -> int:
        """Calculate database offset."""
        return (self.page - 1) * self.per_page
