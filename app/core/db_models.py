"""
SQLAlchemy 2.0 async models for PostgreSQL.

Defines the database schema for:
- Organizations: Multi-tenant organization management
- Users: User management with organization scoping
- Folders: Hierarchical folder structure
- Documents: Document metadata (files stored in GCS)
- AuditLogs: Audit trail for all system events
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import uuid4
from enum import Enum as PyEnum

from sqlalchemy import (
    String,
    Text,
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class AuditAction(str, PyEnum):
    """Audit action types for tracking system events."""
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    UPLOAD = "UPLOAD"
    DOWNLOAD = "DOWNLOAD"
    MOVE = "MOVE"


class AuditEntityType(str, PyEnum):
    """Entity types that can be audited."""
    ORGANIZATION = "ORGANIZATION"
    USER = "USER"
    FOLDER = "FOLDER"
    DOCUMENT = "DOCUMENT"


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class OrganizationModel(Base):
    """
    Organization table for multi-tenancy.

    Stores organization data including plan type and settings.
    """
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    domain: Mapped[Optional[str]] = mapped_column(String(255))
    plan_type: Mapped[str] = mapped_column(String(50), default="free", nullable=False)
    settings: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Relationships
    users: Mapped[List["UserModel"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan"
    )
    folders: Mapped[List["FolderModel"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan"
    )
    documents: Mapped[List["DocumentModel"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_organizations_is_active", "is_active"),
        Index("idx_organizations_created_at", "created_at"),
        Index("idx_organizations_active_created", "is_active", "created_at"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "domain": self.domain,
            "plan_type": self.plan_type,
            "settings": self.settings,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class UserModel(Base):
    """
    User table for authentication and authorization.

    Scoped to organization for multi-tenancy.
    """
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="user", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Relationships
    organization: Mapped["OrganizationModel"] = relationship(back_populates="users")

    __table_args__ = (
        Index("idx_users_organization_id", "organization_id"),
        Index("idx_users_email", "email"),
        Index("idx_users_org_email", "organization_id", "email"),
        Index("idx_users_org_username", "organization_id", "username"),
        Index("idx_users_is_active", "is_active"),
        Index("idx_users_org_is_active", "organization_id", "is_active"),  # Common filter combo
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (excludes password_hash)."""
        return {
            "id": self.id,
            "org_id": self.organization_id,
            "email": self.email,
            "username": self.username,
            "full_name": self.full_name,
            "role": self.role,
            "is_active": self.is_active,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class FolderModel(Base):
    """
    Folder table for hierarchical document organization.

    Supports nested folder structure with path tracking.
    """
    __tablename__ = "folders"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_folder_id: Mapped[Optional[str]] = mapped_column(String(36))
    path: Mapped[str] = mapped_column(Text, default="/", nullable=False)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Relationships
    organization: Mapped["OrganizationModel"] = relationship(back_populates="folders")

    __table_args__ = (
        Index("idx_folders_organization_id", "organization_id"),
        Index("idx_folders_parent_id", "parent_folder_id"),
        Index("idx_folders_org_parent", "organization_id", "parent_folder_id"),
        Index("idx_folders_org_name", "organization_id", "name"),
        Index("idx_folders_path", "path"),
        Index("idx_folders_org_is_active", "organization_id", "is_active"),  # Most folder queries use both
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "org_id": self.organization_id,
            "name": self.name,
            "parent_folder_id": self.parent_folder_id,
            "path": self.path,
            "created_by": self.created_by,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class DocumentModel(Base):
    """
    Document table for document metadata.

    Actual files are stored in GCS; this table stores metadata only.
    """
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False
    )
    folder_id: Mapped[Optional[str]] = mapped_column(String(36))
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="uploaded", nullable=False)
    uploaded_by: Mapped[str] = mapped_column(String(36), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    doc_metadata: Mapped[Dict[str, Any]] = mapped_column(
        "metadata",  # Column name in database
        JSONB,
        default=dict,
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Relationships
    organization: Mapped["OrganizationModel"] = relationship(back_populates="documents")

    __table_args__ = (
        Index("idx_documents_organization_id", "organization_id"),
        Index("idx_documents_folder_id", "folder_id"),
        Index("idx_documents_org_active", "organization_id", "is_active"),
        Index("idx_documents_org_folder", "organization_id", "folder_id"),
        Index("idx_documents_status", "status"),
        Index("idx_documents_created_at", "created_at"),
        Index("idx_documents_storage_path", "storage_path"),
        Index("idx_documents_metadata", "metadata", postgresql_using="gin"),
        Index("idx_documents_filename", "filename"),  # Used in document search
        Index("idx_documents_org_filename", "organization_id", "filename"),  # Common filter combination
        Index("idx_documents_uploaded_by", "uploaded_by"),  # Filter by uploader
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "org_id": self.organization_id,
            "folder_id": self.folder_id,
            "filename": self.filename,
            "original_filename": self.original_filename,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "storage_path": self.storage_path,
            "status": self.status,
            "uploaded_by": self.uploaded_by,
            "is_active": self.is_active,
            "metadata": self.doc_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AuditLogModel(Base):
    """
    Audit log table for tracking all system events.

    Stores comprehensive audit trail for compliance and debugging.
    Design considerations:
    - Write-heavy, read-occasionally pattern
    - JSONB for flexible details storage
    - Indexed for common query patterns (org_id, entity_type, created_at)
    """
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True  # System actions may not have a user
    )
    action: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )
    entity_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )
    entity_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False
    )
    details: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False
    )
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))  # IPv6 max length
    session_id: Mapped[Optional[str]] = mapped_column(String(36))
    user_agent: Mapped[Optional[str]] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )

    # Relationships
    organization: Mapped["OrganizationModel"] = relationship()

    __table_args__ = (
        Index("idx_audit_logs_org_id", "organization_id"),
        Index("idx_audit_logs_entity", "entity_type", "entity_id"),
        Index("idx_audit_logs_user_id", "user_id"),
        Index("idx_audit_logs_action", "action"),
        Index("idx_audit_logs_created_at", "created_at"),
        # Composite indexes for common query patterns
        Index("idx_audit_logs_org_type_created", "organization_id", "entity_type", "created_at"),
        Index("idx_audit_logs_org_user_created", "organization_id", "user_id", "created_at"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "user_id": self.user_id,
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "details": self.details,
            "ip_address": self.ip_address,
            "session_id": self.session_id,
            "user_agent": self.user_agent,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
