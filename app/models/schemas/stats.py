"""Stats and audit log response schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class UserStatsResponse(BaseModel):
    """Response model for user statistics."""

    total_users: int = Field(..., description="Total number of users", example=25)
    active_users: int = Field(..., description="Number of active users", example=20)
    inactive_users: int = Field(..., description="Number of inactive users", example=5)
    users_with_recent_activity: int = Field(
        ..., description="Users active in last 30 days", example=15
    )
    role_distribution: Dict[str, int] = Field(
        ...,
        description="User count by role",
        example={"admin": 2, "user": 18, "viewer": 5},
    )
    privileged_users: int = Field(
        ..., description="Users with admin or user role", example=20
    )


class OrganizationStatsResponse(BaseModel):
    """Response model for organization statistics."""

    total_organizations: int = Field(
        ..., description="Total number of organizations", example=10
    )
    active_organizations: int = Field(
        ..., description="Number of active organizations", example=8
    )
    inactive_organizations: int = Field(
        ..., description="Number of inactive organizations", example=2
    )
    organizations_with_domain: int = Field(
        ..., description="Organizations with domain configured", example=6
    )
    plan_distribution: Dict[str, int] = Field(
        ...,
        description="Organization count by plan type",
        example={"free": 5, "starter": 3, "pro": 2, "business": 1},
    )
    premium_organizations: int = Field(
        ..., description="Organizations with paid plans", example=5
    )


class FolderStatsResponse(BaseModel):
    """Response model for folder statistics."""

    total_folders: int = Field(..., description="Total number of folders", example=50)
    active_folders: int = Field(..., description="Number of active folders", example=45)
    inactive_folders: int = Field(
        ..., description="Number of inactive folders", example=5
    )
    root_folders: int = Field(
        ..., description="Number of root-level folders", example=5
    )
    depth_distribution: Dict[str, int] = Field(
        ...,
        description="Folder count by depth level",
        example={"1": 5, "2": 20, "3": 15, "4": 10},
    )
    max_depth: int = Field(..., description="Maximum folder nesting depth", example=4)


class DocumentStatsResponse(BaseModel):
    """Response model for document statistics."""

    total_documents: int = Field(
        ..., description="Total number of documents", example=150
    )
    active_documents: int = Field(
        ..., description="Number of active documents", example=140
    )
    deleted_documents: int = Field(
        ..., description="Number of soft-deleted documents", example=10
    )
    total_size_bytes: int = Field(
        ..., description="Total storage used in bytes", example=1073741824
    )
    file_type_distribution: Dict[str, int] = Field(
        ...,
        description="Document count by file type",
        example={"pdf": 80, "xlsx": 40, "docx": 30},
    )
    status_distribution: Dict[str, int] = Field(
        ...,
        description="Document count by processing status",
        example={"uploaded": 145, "uploading": 3, "failed": 2},
    )


class AuditLogEntry(BaseModel):
    """Single audit log entry."""

    id: str = Field(..., description="Audit log entry ID", example="audit_abc123")
    action: str = Field(..., description="Action performed", example="CREATE")
    entity_type: str = Field(
        ..., description="Entity type affected", example="DOCUMENT"
    )
    entity_id: str = Field(..., description="Entity ID affected", example="doc_xyz789")
    user_id: Optional[str] = Field(
        None, description="User who performed action", example="user_abc123"
    )
    timestamp: datetime = Field(
        ..., description="When action occurred", example="2025-01-15T10:30:00Z"
    )
    details: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional context",
        example={"filename": "invoice.pdf", "folder": "/invoices"},
    )
    ip_address: Optional[str] = Field(
        None, description="Client IP address", example="192.168.1.100"
    )
    session_id: Optional[str] = Field(
        None, description="Session ID", example="session_abc123"
    )
    user_agent: Optional[str] = Field(
        None,
        description="Client user agent",
        example="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    )

    # AI Processing audit fields
    event_type: Optional[str] = Field(
        None,
        description="AI event type (e.g., document_parsed, summary_generated)",
        example="document_parsed",
    )
    document_hash: Optional[str] = Field(
        None,
        description="SHA-256 hash of document being processed",
        example="a1b2c3d4e5f6...",
    )
    file_name: Optional[str] = Field(
        None, description="Filename for display", example="invoice-2025-001.pdf"
    )
    job_id: Optional[str] = Field(
        None, description="Reference to processing job", example="job_xyz789"
    )


class AuditLogListResponse(BaseModel):
    """Response model for audit log list."""

    logs: List[AuditLogEntry] = Field(..., description="List of audit log entries")
    total: int = Field(..., description="Total number of matching logs", example=150)
    page: int = Field(..., description="Current page number", example=1)
    per_page: int = Field(..., description="Items per page", example=50)
    total_pages: int = Field(..., description="Total number of pages", example=3)


class TokenValidationResponse(BaseModel):
    """Response model for token validation."""

    valid: bool = Field(..., description="Whether token is valid", example=True)
    expires_at: str = Field(
        ..., description="Token expiration timestamp", example="2025-01-15T14:00:00Z"
    )
    time_remaining: int = Field(
        ..., description="Seconds until expiration", example=3600
    )
    in_grace_period: bool = Field(
        ..., description="Whether token is in grace period", example=False
    )
    can_refresh: bool = Field(
        ..., description="Whether token can be refreshed", example=True
    )
    user: Dict[str, Any] = Field(
        ...,
        description="User information",
        example={
            "user_id": "user_abc123",
            "email": "john@example.com",
            "full_name": "John Doe",
            "role": "user",
            "org_id": "org_xyz789",
        },
    )
